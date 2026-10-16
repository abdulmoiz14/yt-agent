#!/usr/bin/env python3
"""render.py - assemble the video locally with ffmpeg: voiceover + licensed images + captions.

No API keys, no cloud, no generative video. Every picture is either a file the creator cleared
(licence recorded) or a plain title card saying what belongs there.

    python3 render.py <project folder> [--size 1920x1080 | --vertical] [--pitch 1.08]
                      [--variant short] [--no-captions] [--dry-run]

--variant NAME renders a second cut (e.g. a one-minute vertical Short) from
narration/NAME-voiceover.wav/.json and visuals/NAME-plan.json into render/NAME/.

Inputs (inside the project):
  narration/voiceover.wav + voiceover.json   from tts.py (line start/end times)
  visuals/plan.json                          which picture covers which narration lines:
    [{"start_line": 0, "image": "visuals/images/walls.jpg", "licence": "Public domain",
      "source_url": "https://commons.wikimedia.org/wiki/File:...", "attribution": "", "card": "The land walls"},
     {"start_line": 3, "image": null, "card": "Map: the Golden Horn"}]
    A segment runs from its start_line to the next entry's start_line. start_line 0 must exist.
    An image is used ONLY if the file exists and `licence` is set and not "unknown";
    otherwise the segment becomes a title card showing `card` - never a guessed picture.

Outputs (project/render/):
  draft.mp4 (any placeholder cards) or video.mp4 (every segment a cleared image)
  captions.srt   - upload it to YouTube as subtitles too
  credits.txt    - attribution lines for the description
  render.json    - what was used where, placeholders, licences, the exact ffmpeg commands

--pitch raises (>1) or lowers (<1) the voice without changing its speed (ffmpeg rubberband,
or asetrate+atempo if rubberband is missing). 1.05-1.12 is a natural range.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

FPS = 30
FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                   "/usr/share/fonts/opentype/inter/Inter-Regular.otf"]


def die(msg, code=2): print(f"error: {msg}", file=sys.stderr); sys.exit(code)


def font():
    for f in FONT_CANDIDATES:
        if os.path.exists(f): return f
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True).stdout.strip()
        if out and os.path.exists(out): return out
    except OSError: pass
    die("no font found for title cards (install fonts-dejavu-core)")


def usable(entry, pdir):
    img, lic = entry.get("image"), str(entry.get("licence") or "").strip().lower()
    return bool(img) and (pdir / img).is_file() and lic not in ("", "unknown", "licence unknown", "none", "to check")


def build_segments(pdir, plan, lines, total):
    if not plan or plan[0].get("start_line") != 0: die("visuals/plan.json must start with an entry at start_line 0")
    starts = [e["start_line"] for e in plan]
    if starts != sorted(set(starts)): die("plan.json start_line values must be unique and increasing")
    if starts[-1] >= len(lines): die(f"plan.json start_line {starts[-1]} is past the last narration line ({len(lines) - 1})")
    segs = []
    for i, e in enumerate(plan):
        t0 = 0.0 if i == 0 else lines[e["start_line"]]["start"]
        t1 = total if i == len(plan) - 1 else lines[plan[i + 1]["start_line"]]["start"]
        ok = usable(e, pdir)
        segs.append({"index": i, "start": round(t0, 2), "end": round(t1, 2), "duration": round(max(t1 - t0, 0.5), 2),
                     "kind": "image" if ok else "card", "image": e.get("image") if ok else None,
                     "card": e.get("card") or (Path(e["image"]).stem.replace("_", " ") if e.get("image") else "Visual to find"),
                     "licence": e.get("licence") if ok else None, "source_url": e.get("source_url") if ok else None,
                     "attribution": e.get("attribution") or "",
                     "why_card": None if ok else ("no image" if not e.get("image") else
                                                  "file missing" if not (pdir / e["image"]).is_file() else "licence not cleared")})
    return segs


def srt_time(t):
    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def wrap(text, width=42):
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out


def captions(lines):
    rows, n = [], 0
    for ln in lines:
        text = re.sub(r"\s*/\s*", " ", re.sub(r"\[PAUSE\]", "", ln["line"], flags=re.I)).strip()
        if not text or ln["end"] - ln["start"] < 0.3: continue
        chunks = [" ".join(wrap(text)[i:i + 2]) for i in range(0, len(wrap(text)), 2)]   # two caption lines max
        chunks = [ "\n".join(wrap(c)) for c in chunks]
        span = (ln["end"] - ln["start"]) / len(chunks)
        for k, c in enumerate(chunks):
            n += 1; a = ln["start"] + k * span
            rows.append(f"{n}\n{srt_time(a)} --> {srt_time(a + span - 0.02)}\n{c}\n")
    return "\n".join(rows)


def seg_cmd(seg, pdir, work, W, H, fontfile):
    out = work / f"seg{seg['index']:03d}.mp4"
    frames = max(int(seg["duration"] * FPS), 1)
    common = ["-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)]
    if seg["kind"] == "image":
        zoom_in = seg["index"] % 2 == 0
        z = f"min(1+0.10*on/{frames},1.10)" if zoom_in else f"max(1.10-0.10*on/{frames},1.0)"
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
        return out, ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", str(seg["duration"]),
                     "-i", str(pdir / seg["image"]), "-vf", vf, "-frames:v", str(frames)] + common
    tf = work / f"card{seg['index']:03d}.txt"
    tf.write_text("\n".join(wrap(seg["card"], 28)))
    size = max(int(H / 14), 28)
    vf = (f"drawtext=fontfile='{fontfile}':textfile='{tf}':fontcolor=white:fontsize={size}:line_spacing={size // 3}:"
          f"x=(w-text_w)/2:y=(h-text_h)/2,"
          f"drawtext=fontfile='{fontfile}':text='VISUAL TO ADD':fontcolor=0xAAAAAA:fontsize={size // 2}:x=(w-text_w)/2:y=h*0.08")
    return out, ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x15171c:s={W}x{H}:d={seg['duration']}:r={FPS}",
                 "-vf", vf, "-frames:v", str(frames)] + common


def audio_filter(pitch):
    if not pitch or abs(pitch - 1) < 1e-3: return None
    have_rb = "rubberband" in subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return f"rubberband=pitch={pitch}" if have_rb else f"asetrate=24000*{pitch},aresample=24000,atempo={1 / pitch:.5f}"


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"): print(__doc__); sys.exit(2)
    pdir = Path(a[0]).expanduser().resolve()
    def opt(f, d=None): return a[a.index(f) + 1] if f in a and a.index(f) + 1 < len(a) else d
    W, H = (1080, 1920) if "--vertical" in a else map(int, opt("--size", "1920x1080").lower().split("x"))
    pitch = float(opt("--pitch", "1.0"))

    var = opt("--variant")
    if var and not re.fullmatch(r"[a-z0-9-]{1,20}", var): die("--variant must be short lowercase letters, digits or -")
    pre = f"{var}-" if var else ""
    vo, meta_p, plan_p = pdir / f"narration/{pre}voiceover.wav", pdir / f"narration/{pre}voiceover.json", pdir / f"visuals/{pre}plan.json"
    for p in (vo, meta_p, plan_p):
        if not p.exists(): die(f"{p.relative_to(pdir)} not found" + (" - make it with tts.py" if "voiceover" in p.name else " - write the visual plan first (stages/render.md)"))
    meta, plan = json.loads(meta_p.read_text()), json.loads(plan_p.read_text())
    lines, total = meta["lines"], float(meta["duration_sec"])
    segs = build_segments(pdir, plan, lines, total)
    cards = [s for s in segs if s["kind"] == "card"]

    if "--dry-run" in a:
        for s in segs:
            what = s["image"] + f"  [{s['licence']}]" if s["kind"] == "image" else f"CARD \"{s['card']}\" ({s['why_card']})"
            print(f"{s['start']:7.2f}-{s['end']:7.2f}s  {what}")
        print(f"\n{len(segs)} segments, {len(cards)} placeholder card(s), {total:.1f} s, {W}x{H}")
        return

    if not shutil.which("ffmpeg"): die("ffmpeg is not installed", 3)
    out_dir = pdir / "render" / var if var else pdir / "render"
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    fontfile = font() if cards else None
    cmds = []
    seg_files = []
    for s in segs:
        out, cmd = seg_cmd(s, pdir, work, W, H, fontfile)
        r = subprocess.run(cmd, capture_output=True, text=True)
        cmds.append({"cmd": " ".join(cmd), "exit": r.returncode})
        if r.returncode: die(f"segment {s['index']} failed: {r.stderr.strip()[:400]}", 1)
        seg_files.append(out)
    (work / "list.txt").write_text("".join(f"file '{f.name}'\n" for f in seg_files))
    (out_dir / "captions.srt").write_text(captions(lines))

    name = "video.mp4" if not cards else "draft.mp4"
    vf = [] if "--no-captions" in a else [
        "-vf", f"subtitles=../captions.srt:force_style='FontName=DejaVu Sans,FontSize={18 if H > W else 20},"
               f"Outline=2,Shadow=0,MarginV={int(H * 0.06) if H > W else 40}'"]
    af = audio_filter(pitch)
    cmd = (["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-i", str(vo)] + vf
           + (["-af", af] if af else []) + ["-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
           str(out_dir / name)])
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=work)
    cmds.append({"cmd": " ".join(cmd), "exit": r.returncode})
    if r.returncode: die(f"final mux failed: {r.stderr.strip()[:400]}", 1)
    other = out_dir / ("draft.mp4" if name == "video.mp4" else "video.mp4")
    if other.exists(): other.unlink()                     # never leave a stale "final" next to a new draft

    credits = sorted({f"{s['card']}: {s['attribution'] or s['licence']} - {s['source_url']}" for s in segs
                      if s["kind"] == "image" and (s["attribution"] or s["source_url"])})
    (out_dir / "credits.txt").write_text("\n".join(credits) + ("\n" if credits else ""))
    report = {"output": str((out_dir / name).relative_to(pdir)), "variant": var, "draft": bool(cards), "size": f"{W}x{H}", "pitch": pitch,
              "duration_sec": total, "placeholders": len(cards), "segments": segs, "commands": cmds}
    (out_dir / "render.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {out_dir / name} ({total:.0f} s, {W}x{H})" +
          (f" - DRAFT: {len(cards)} placeholder card(s) still need a cleared image" if cards else ""))


if __name__ == "__main__":
    main()
