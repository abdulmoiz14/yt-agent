#!/usr/bin/env python3
"""tts.py - local, offline voiceover from narration/narration.md. No API keys, no cloud.

Two engines, each run with the Python of its own virtual environment (see stages/narration.md):

  Kokoro (default) - fast, runs fine on CPU:
    ~/.local/share/yt-tts/venv/bin/python tts.py narration/narration.md -o narration/voiceover.wav \
        [--voice am_michael] [--speed 1.0] [--lexicon narration/tts-lexicon.txt]

  Qwen3-TTS (--engine qwen) - more natural; wants Apple Silicon (MPS) or an NVIDIA GPU:
    # 1. design the narrator ONCE from a description -> a short reference clip + its transcript
    ~/.local/share/qwen-tts/venv/bin/python tts.py design-ref narration/voice-ref.wav \
        --instruct "Warm, slightly higher-pitched male documentary narrator, calm and clear"
    # 2. narrate every line in that same voice by cloning the clip (Base model) - consistent voice
    ~/.local/share/qwen-tts/venv/bin/python tts.py narration/narration.md --engine qwen --qwen-mode clone \
        --ref-audio narration/voice-ref.wav --lexicon narration/tts-lexicon.txt
    Other modes: --qwen-mode custom --speaker Ryan (preset voices; their commercial voice rights are
    an open question upstream), --qwen-mode design --instruct "..." (re-designs per line: may drift).
    --model <HF id> overrides the checkpoint; --device auto|mps|cuda|cpu; --language English.

  Common: [--allow-check] scratch track only; --dry-run needs no engine.

What it speaks: every line of narration.md except headings (#), tables (|), quotes (>), metadata
lines ("Runtime: ..."), [ON SCREEN ...] cues and claim tags like {C4}. "[PAUSE]" = 0.7 s silence,
"/" = 0.25 s breath (Kokoro; Qwen reads it as a comma), 0.35 s after each line.

Pronunciation: --lexicon `Word = respelling` lines, applied as text before synthesis (neither engine
has a phoneme API in this tool). If narration/pronunciation.md still has CHECK, it refuses unless
--allow-check. Qwen has been reported to add laughter or words not in the text: listen to it all.

Writes the WAV (mono, 16-bit, the engine's sample rate), a .json with each line's start/end time, and
a .srt transcript (one cue per line, exact timings) for chapters, the edit list and Shorts.
"""
import json, re, sys, wave
from pathlib import Path

SR = 24000
PAUSE, BREATH, LINE_GAP = 0.7, 0.25, 0.35
WPM = 150
META = re.compile(r"^\s*(spoken )?(word count|words|runtime|duration|scratch audio|voiceover)\b[^:=]{0,40}[:=]", re.I)   # "Spoken words: 451", "Runtime: 3:00" - notes, not narration


def spoken_lines(text):
    out = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith(("#", "|", ">", "---", "<!--")) or META.match(s): continue
        s = re.sub(r"\[ON SCREEN[^\]]*\]", " ", s, flags=re.I)
        s = re.sub(r"\{[CU]\d+\}", " ", s)
        s = s.replace("**", "").replace("__", "")
        s = re.sub(r"^\s*[-*]\s+", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        if re.fullmatch(r"(\[PAUSE\]\s*)+", s, re.I) or (s and re.search(r"[A-Za-z0-9]", s)):
            out.append(s)
    return out


def load_lexicon(path):
    lex = {}
    if not path: return lex
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            if k.strip() and v.strip(): lex[k.strip()] = v.strip()
    return lex


def apply_lexicon(s, lex):
    for k in sorted(lex, key=len, reverse=True):
        s = re.sub(r"(?<![\w'])" + re.escape(k) + r"(?![\w'])", lex[k], s)
    return s


def plan(lines, lex, breaths=True):
    """Each line -> list of ('say', text) / ('gap', seconds).
    breaths=False (Qwen) keeps a line in one call - "/" becomes a comma - because many tiny calls
    sound choppy and are slow; [PAUSE] still splits."""
    out = []
    for line in lines:
        parts = []
        for chunk in re.split(r"(\[PAUSE\])", line, flags=re.I):
            if chunk.upper() == "[PAUSE]": parts.append(("gap", PAUSE)); continue
            if not breaths: chunk = re.sub(r"\s*([,;:.!?]?)\s*/\s*", lambda m: (m.group(1) or ",") + " ", chunk)
            for i, piece in enumerate((chunk.split(" / ") if " / " in chunk else chunk.split("/")) if breaths else [chunk]):
                if i: parts.append(("gap", BREATH))
                piece = apply_lexicon(piece.strip(), lex)
                if re.search(r"[A-Za-z0-9]", piece): parts.append(("say", piece))
        parts.append(("gap", LINE_GAP))
        out.append((line, parts))
    return out


def unresolved_checks(narration_path):
    p = Path(narration_path).with_name("pronunciation.md")
    if not p.exists(): return []
    return [l.strip() for l in p.read_text().splitlines() if re.search(r"\bCHECK\b", l)]


def to_int16(samples):
    try:
        import numpy as np
        a = np.clip(np.asarray(samples, dtype="float32").reshape(-1), -1, 1)
        return (a * 32767).astype("<i2").tobytes()
    except ImportError:
        import struct
        return b"".join(struct.pack("<h", int(max(-1, min(1, float(x))) * 32767)) for x in samples)


def missing(engine, venv):
    print(f"error: {engine} is not installed in this Python. Run tts.py with {venv} (see stages/narration.md).",
          file=sys.stderr)
    sys.exit(3)


class Kokoro:
    name, breaths = "kokoro", True
    def __init__(self, voice, speed):
        try: from kokoro import KPipeline
        except ImportError: missing("Kokoro", "~/.local/share/yt-tts/venv/bin/python")
        self.pipe, self.voice, self.speed, self.sr = KPipeline(lang_code=voice[0] if voice[:1] in "ab" else "a"), voice, speed, SR
        self.label = voice
    def speak(self, text):
        for _, _, audio in self.pipe(text, voice=self.voice, speed=self.speed, split_pattern=None):
            if audio is not None: yield audio.numpy() if hasattr(audio, "numpy") else audio


QWEN_DEFAULTS = {"design": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "custom": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                 "clone": "Qwen/Qwen3-TTS-12Hz-0.6B-Base"}


def pick_device(want):
    try: import torch
    except ImportError: return "cpu", None
    if want == "auto":
        want = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else \
               "cuda" if torch.cuda.is_available() else "cpu"
    return want, (torch.float32 if want == "cpu" else torch.bfloat16)


class Qwen:
    name, breaths = "qwen3-tts", False
    def __init__(self, mode, model_id, device, language, instruct=None, speaker=None, ref_audio=None, ref_text=None):
        try: from qwen_tts import Qwen3TTSModel
        except ImportError: missing("qwen-tts", "~/.local/share/qwen-tts/venv/bin/python")
        if mode == "design" and not instruct: sys.exit("error: --qwen-mode design needs --instruct \"voice description\"")
        if mode == "custom" and not speaker: sys.exit("error: --qwen-mode custom needs --speaker NAME")
        if mode == "clone":
            if not ref_audio or not Path(ref_audio).exists(): sys.exit("error: --qwen-mode clone needs --ref-audio FILE")
            ref_text = ref_text or (Path(ref_audio).with_suffix(".txt").read_text().strip()
                                    if Path(ref_audio).with_suffix(".txt").exists() else None)
            if not ref_text: sys.exit("error: clone needs the reference transcript: --ref-text or a .txt beside the clip")
        self.mode, self.language, self.instruct, self.speaker = mode, language, instruct, speaker
        self.ref_audio, self.ref_text, self.model_id = ref_audio, ref_text, model_id or QWEN_DEFAULTS[mode]
        self.device, dtype = pick_device(device)
        if self.device == "cpu":
            print("warning: Qwen3-TTS on CPU can be very slow (reports of 20+ minutes for short text).", file=sys.stderr)
        self.model = None
        for kw in ({"device_map": self.device, "dtype": dtype}, {"device_map": self.device, "torch_dtype": dtype},
                   {"device_map": self.device}, {}):
            kw = {k: v for k, v in kw.items() if v is not None}
            try: self.model = Qwen3TTSModel.from_pretrained(self.model_id, **kw); break
            except TypeError: continue
        if self.model is None: sys.exit(f"error: could not load {self.model_id}")
        self.prompt = None
        if mode == "clone" and hasattr(self.model, "create_voice_clone_prompt"):
            try: self.prompt = self.model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text)
            except Exception: self.prompt = None          # fall back to passing the reference every call
        self.sr = None
        self.label = {"design": f"designed: {instruct}", "custom": f"preset: {speaker}",
                      "clone": f"cloned from {ref_audio}"}[mode]
    def speak(self, text):
        m, kw = self.model, {"text": text, "language": self.language}
        if self.mode == "design": wavs, sr = m.generate_voice_design(instruct=self.instruct, **kw)
        elif self.mode == "custom":
            wavs, sr = m.generate_custom_voice(speaker=self.speaker, **({"instruct": self.instruct} if self.instruct else {}), **kw)
        elif self.prompt is not None: wavs, sr = m.generate_voice_clone(voice_clone_prompt=self.prompt, **kw)
        else: wavs, sr = m.generate_voice_clone(ref_audio=self.ref_audio, ref_text=self.ref_text, **kw)
        if self.sr and sr != self.sr: sys.exit(f"error: sample rate changed mid-file ({self.sr} -> {sr})")
        self.sr = sr
        yield wavs[0]


def synthesize(planned, engine):
    """Silence is written as soon as the sample rate is known (Kokoro: at once; Qwen: after its first
    audio), so line timings stay exact either way."""
    pcm, timings, t = bytearray(), [], 0.0
    pending = 0.0
    def flush():
        nonlocal pending, t
        if pending and engine.sr:
            pcm.extend(b"\x00\x00" * int(engine.sr * pending)); t += pending; pending = 0.0
    for line, parts in planned:
        flush(); start = t + pending
        for kind, val in parts:
            if kind == "gap": pending += val; flush(); continue
            for data in engine.speak(val):
                flush(); pcm.extend(to_int16(data)); t += len(data) / engine.sr
        timings.append({"line": line, "start": round(start, 2), "end": round(max(t + pending, start), 2)})
    flush()
    return bytes(pcm), timings


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def transcript_srt(timings):
    """One cue per spoken line, the script's own spelling (not the lexicon's respelling), exact timings.
    Lets /yt-chapters, /yt-edit and /yt-shorts run on a synthetic voiceover without a recording."""
    rows, n = [], 0
    for ln in timings:
        text = re.sub(r"\s*/\s*", " ", re.sub(r"\[PAUSE\]", " ", ln["line"], flags=re.I))
        text = re.sub(r"\s+", " ", text).strip()
        if not text or ln["end"] <= ln["start"]: continue
        n += 1
        rows.append(f"{n}\n{srt_time(ln['start'])} --> {srt_time(ln['end'])}\n{text}\n")
    return "\n".join(rows)


def write_wav(path, pcm, sr):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)


REF_TEXT = ("History is full of turning points. Some arrive with a battle, some with a single decision, "
            "and some with an idea that nobody believed until it worked.")


def design_ref(a, opt):
    if len(a) < 2 or a[1].startswith("-"): sys.exit("usage: tts.py design-ref OUT.wav --instruct \"description\" [--text ...]")
    out, instruct = Path(a[1]), opt("--instruct")
    if not instruct: sys.exit("error: design-ref needs --instruct \"voice description\"")
    text = opt("--text", REF_TEXT)
    eng = Qwen("design", opt("--model"), opt("--device", "auto"), opt("--language", "English"), instruct=instruct)
    pcm, _ = synthesize([(text, [("say", text)])], eng)
    write_wav(out, pcm, eng.sr)
    out.with_suffix(".txt").write_text(text + "\n")
    out.with_suffix(".json").write_text(json.dumps({"engine": eng.name, "model": eng.model_id, "instruct": instruct,
        "text": text, "sample_rate": eng.sr, "duration_sec": round(len(pcm) / 2 / eng.sr, 2)}, indent=1) + "\n")
    print(f"wrote {out} and {out.with_suffix('.txt').name} - listen; if you like it, clone it with --qwen-mode clone --ref-audio {out}")


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"): print(__doc__); sys.exit(2)
    def opt(flag, default=None):
        return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else default
    if a[0] == "design-ref": return design_ref(a, opt)
    src = Path(a[0])
    if not src.exists(): print(f"error: {src} not found", file=sys.stderr); sys.exit(2)
    engine_name = opt("--engine", "kokoro")
    if engine_name not in ("kokoro", "qwen"): sys.exit("error: --engine must be kokoro or qwen")
    planned = plan(spoken_lines(src.read_text()), load_lexicon(opt("--lexicon")), breaths=(engine_name == "kokoro"))
    words = sum(len(re.findall(r"[A-Za-z0-9']+", p[1])) for _, ps in planned for p in ps if p[0] == "say")
    if not planned: print("error: nothing to speak in " + str(src), file=sys.stderr); sys.exit(2)

    if "--dry-run" in a:
        for line, parts in planned:
            print(" ".join(f"«{v}»" if k == "say" else f"[{v}s]" for k, v in parts))
        print(f"\n{len(planned)} lines, {words} words, ~{words / WPM:.1f} min at {WPM} wpm (the voice's real pace may differ)")
        return

    checks = unresolved_checks(src)
    if checks and "--allow-check" not in a:
        print("error: pronunciation.md still has CHECK entries - resolve them (and add respellings to the "
              "lexicon) before a final voiceover, or pass --allow-check for a scratch track:\n  "
              + "\n  ".join(checks[:10]), file=sys.stderr)
        sys.exit(4)
    # narration.md -> voiceover.wav; anything else (a Short's intro line) -> its own name, never the main voiceover
    out = Path(opt("-o", str(src.with_name("voiceover.wav") if src.name == "narration.md" else src.with_suffix(".wav"))))
    if engine_name == "kokoro":
        eng = Kokoro(opt("--voice", "am_michael"), float(opt("--speed", "1.0")))
    else:
        eng = Qwen(opt("--qwen-mode", "clone"), opt("--model"), opt("--device", "auto"), opt("--language", "English"),
                   instruct=opt("--instruct"), speaker=opt("--speaker"), ref_audio=opt("--ref-audio"), ref_text=opt("--ref-text"))
    pcm, timings = synthesize(planned, eng)
    write_wav(out, pcm, eng.sr)
    meta = {"voice": eng.label, "engine": f"{eng.name} (local)" + (f", {eng.model_id}" if engine_name == "qwen" else ""),
            "speed": float(opt("--speed", "1.0")) if engine_name == "kokoro" else None, "sample_rate": eng.sr,
            "duration_sec": round(len(pcm) / 2 / eng.sr, 2), "scratch": bool(checks), "lines": timings}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    out.with_suffix(".srt").write_text(transcript_srt(timings))
    print(f"wrote {out} ({meta['duration_sec']} s, {eng.label}){' - SCRATCH: unresolved CHECK pronunciations' if checks else ''}"
          + (" - listen for extra words or laughter (a known Qwen issue)" if engine_name == "qwen" else ""))


if __name__ == "__main__":
    main()
