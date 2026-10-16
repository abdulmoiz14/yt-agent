#!/usr/bin/env python3
"""tts.py - local, offline voiceover from narration/narration.md using Kokoro. No API keys.

Run it with the Python that has Kokoro installed (see stages/narration.md):

    ~/.local/share/yt-tts/venv/bin/python tts.py narration/narration.md -o narration/voiceover.wav
        [--voice am_michael] [--speed 1.0] [--lexicon narration/tts-lexicon.txt]
        [--allow-check]   # scratch track only: ignore unresolved CHECK pronunciations
    python3 tts.py narration/narration.md --dry-run     # no Kokoro needed: show what would be spoken

What it speaks: every line of narration.md except headings (#), tables (|), quotes (>),
[ON SCREEN ...] cues and claim tags like {C4}. **bold** markers are dropped (Kokoro has no stress
control). "[PAUSE]" becomes 0.7 s of silence, "/" a 0.25 s breath, and each line ends with 0.35 s.

Pronunciation: --lexicon is a text file of `Word = respelling` lines (e.g. `Sphrantzes = Sfrant-zess`),
applied as whole-word replacements before synthesis. If narration/pronunciation.md still contains
CHECK, it refuses unless --allow-check, because a final voiceover must not guess names.

Writes the WAV (24 kHz mono, 16-bit) and a .json beside it with each line's start and end time,
which later stages can use for timing visuals and chapters.
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


def plan(lines, lex):
    """Each line -> list of ('say', text) / ('gap', seconds)."""
    out = []
    for line in lines:
        parts = []
        for chunk in re.split(r"(\[PAUSE\])", line, flags=re.I):
            if chunk.upper() == "[PAUSE]": parts.append(("gap", PAUSE)); continue
            for i, piece in enumerate(chunk.split(" / ") if " / " in chunk else chunk.split("/")):
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
        a = np.clip(np.asarray(samples, dtype="float32"), -1, 1)
        return (a * 32767).astype("<i2").tobytes()
    except ImportError:
        import struct
        return b"".join(struct.pack("<h", int(max(-1, min(1, float(x))) * 32767)) for x in samples)


def synthesize(planned, voice, speed):
    try:
        from kokoro import KPipeline
    except ImportError:
        print("error: Kokoro is not installed in this Python. Run tts.py with the yt-tts venv: "
              "~/.local/share/yt-tts/venv/bin/python (see stages/narration.md).", file=sys.stderr)
        sys.exit(3)
    lang = voice[0] if voice[:1] in "ab" else "a"          # a = American, b = British voices
    pipe = KPipeline(lang_code=lang)
    pcm, timings, t = bytearray(), [], 0.0
    def silence(sec):
        nonlocal t; pcm.extend(b"\x00\x00" * int(SR * sec)); t += sec
    for line, parts in planned:
        start = t
        for kind, val in parts:
            if kind == "gap": silence(val); continue
            for _, _, audio in pipe(val, voice=voice, speed=speed, split_pattern=None):
                if audio is None: continue
                data = audio.numpy() if hasattr(audio, "numpy") else audio
                pcm.extend(to_int16(data)); t += len(data) / SR
        timings.append({"line": line, "start": round(start, 2), "end": round(t, 2)})
    return bytes(pcm), timings


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"): print(__doc__); sys.exit(2)
    def opt(flag, default=None):
        return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else default
    src = Path(a[0])
    if not src.exists(): print(f"error: {src} not found", file=sys.stderr); sys.exit(2)
    voice, speed = opt("--voice", "am_michael"), float(opt("--speed", "1.0"))
    planned = plan(spoken_lines(src.read_text()), load_lexicon(opt("--lexicon")))
    words = sum(len(re.findall(r"[A-Za-z0-9']+", p[1])) for _, ps in planned for p in ps if p[0] == "say")
    if not planned: print("error: nothing to speak in " + str(src), file=sys.stderr); sys.exit(2)

    if "--dry-run" in a:
        for line, parts in planned:
            print(" ".join(f"«{v}»" if k == "say" else f"[{v}s]" for k, v in parts))
        print(f"\n{len(planned)} lines, {words} words, ~{words / WPM:.1f} min at {WPM} wpm (Kokoro's real pace may differ)")
        return

    checks = unresolved_checks(src)
    if checks and "--allow-check" not in a:
        print("error: pronunciation.md still has CHECK entries - resolve them (and add respellings to the "
              "lexicon) before a final voiceover, or pass --allow-check for a scratch track:\n  "
              + "\n  ".join(checks[:10]), file=sys.stderr)
        sys.exit(4)
    out = Path(opt("-o", str(src.with_name("voiceover.wav"))))
    pcm, timings = synthesize(planned, voice, speed)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
    meta = {"voice": voice, "speed": speed, "engine": "kokoro (local)", "sample_rate": SR,
            "duration_sec": round(len(pcm) / 2 / SR, 2), "scratch": bool(checks), "lines": timings}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({meta['duration_sec']} s, voice {voice}){' - SCRATCH: unresolved CHECK pronunciations' if checks else ''}")


if __name__ == "__main__":
    main()
