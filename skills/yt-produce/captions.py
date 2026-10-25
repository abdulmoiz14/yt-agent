#!/usr/bin/env python3
"""captions.py - write captions.srt and captions.vtt from the narration timings, then validate both.

    python3 captions.py <project folder> [--variant v3] [--out-dir DIR] [--check-only]

Reads narration/[VARIANT-]voiceover.json (the exact line start/end times tts.py or the join step wrote) and writes
captions.srt and captions.vtt into DIR (default: render/[VARIANT/]). The cue text and splitting are render.py's own
captions(), so the files match what the captioned render burns in. --check-only validates the files already there.

Validation (exit 1 on any problem): SRT cue numbers run 1..n, timestamps are well formed, every cue has 1-2 text
lines of at most 42 characters, start < end, cues are in order and never overlap, nothing runs past the narration,
and the VTT starts with WEBVTT, uses '.' for milliseconds and holds exactly the cues the SRT does.
"""
import importlib.util, json, re, sys
from pathlib import Path

MAX_LINE, MAX_LINES = 42, 2
SRT_T = r"(\d{2}):([0-5]\d):([0-5]\d),(\d{3})"
VTT_T = r"(\d{2}):([0-5]\d):([0-5]\d)\.(\d{3})"


def _render():
    spec = importlib.util.spec_from_file_location("yt_render", Path(__file__).resolve().parent / "render.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def secs(m): return int(m[0]) * 3600 + int(m[1]) * 60 + int(m[2]) + int(m[3]) / 1000


def parse_srt(text):
    """[(number, start, end, [lines])] - raises ValueError on a block that is not a cue."""
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        rows = block.split("\n")
        m = re.fullmatch(rf"{SRT_T} --> {SRT_T}", rows[1]) if len(rows) >= 3 and rows[0].isdigit() else None
        if not m: raise ValueError(f"not a cue: {block[:60]!r}")
        g = m.groups(); cues.append((int(rows[0]), secs(g[:4]), secs(g[4:]), rows[2:]))
    return cues


def to_vtt(cues):
    def t(x): ms = int(round(x * 1000)); return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"
    return "WEBVTT\n\n" + "\n".join(f"{t(a)} --> {t(b)}\n" + "\n".join(rows) + "\n" for _, a, b, rows in cues)


def validate_srt(text, duration=None):
    try: cues = parse_srt(text)
    except ValueError as e: return [str(e)]
    if not cues: return ["no cues"]
    problems, prev_end = [], 0.0
    for k, (n, a, b, rows) in enumerate(cues, 1):
        if n != k: problems.append(f"cue {k}: numbered {n}")
        if b <= a: problems.append(f"cue {n}: ends ({b:.3f}) before it starts ({a:.3f})")
        if a < prev_end - 1e-6: problems.append(f"cue {n}: starts {a:.3f} before the previous cue ends {prev_end:.3f}")
        if len(rows) > MAX_LINES: problems.append(f"cue {n}: {len(rows)} text lines (max {MAX_LINES})")
        if any(len(r) > MAX_LINE for r in rows): problems.append(f"cue {n}: a line is over {MAX_LINE} characters")
        if not any(r.strip() for r in rows): problems.append(f"cue {n}: empty text")
        prev_end = max(prev_end, b)
    if duration is not None and prev_end > duration + 0.05: problems.append(f"last cue ends {prev_end:.2f}s, after the narration ({duration:.2f}s)")
    return problems


def validate_vtt(text, srt_cues):
    if not text.startswith("WEBVTT\n\n"): return ["VTT does not start with WEBVTT and a blank line"]
    if "," in "".join(re.findall(r"[\d:,.]+ --> [\d:,.]+", text)): return ["VTT timestamps use ',' for milliseconds"]
    blocks = [b for b in re.split(r"\n\s*\n", text[len("WEBVTT"):].strip()) if b.strip()]
    if len(blocks) != len(srt_cues): return [f"VTT has {len(blocks)} cues, the SRT {len(srt_cues)}"]
    problems = []
    for k, (b, (n, a, e, rows)) in enumerate(zip(blocks, srt_cues), 1):
        r = b.split("\n"); m = re.fullmatch(rf"{VTT_T} --> {VTT_T}", r[0])
        if not m: problems.append(f"VTT cue {k}: bad timing line {r[0]!r}"); continue
        g = m.groups()
        if abs(secs(g[:4]) - a) > 0.001 or abs(secs(g[4:]) - e) > 0.001 or r[1:] != rows: problems.append(f"VTT cue {k} differs from SRT cue {n}")
    return problems


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"): print(__doc__); sys.exit(2)
    opt = lambda f, d=None: a[a.index(f) + 1] if f in a and a.index(f) + 1 < len(a) else d
    pdir, var = Path(a[0]).expanduser().resolve(), opt("--variant")
    if var and not re.fullmatch(r"[a-z0-9-]{1,20}", var): sys.exit("error: --variant must be short lowercase letters, digits or -")
    meta = pdir / f"narration/{var + '-' if var else ''}voiceover.json"
    if not meta.is_file(): sys.exit(f"error: {meta} not found")
    vo = json.loads(meta.read_text())
    out = Path(opt("--out-dir") or (pdir / "render" / var if var else pdir / "render")).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    if "--check-only" not in a:
        srt = _render().captions(vo["lines"])
        (out / "captions.srt").write_text(srt); (out / "captions.vtt").write_text(to_vtt(parse_srt(srt)))
    srt_text = (out / "captions.srt").read_text()
    problems = validate_srt(srt_text, vo.get("duration_sec"))
    if not problems: problems = validate_vtt((out / "captions.vtt").read_text(), parse_srt(srt_text))
    n = len(parse_srt(srt_text)) if not problems else "?"
    for p in problems: print(f"FAIL  {p}")
    print(f"{'FAIL' if problems else 'PASS'}  {out / 'captions.srt'} + captions.vtt: {n} cues" + (f", {len(problems)} problem(s)" if problems else ", valid"))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
