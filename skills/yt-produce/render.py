#!/usr/bin/env python3
"""render.py - assemble the video locally with ffmpeg: voiceover + licensed images + captions.

No API keys, no cloud, no generative video. Every picture is either a file the creator cleared
(licence recorded), a designed title card (dates, chapters), or a plain placeholder card saying what
belongs there.

    python3 render.py <project folder> [--size 1920x1080 | --vertical] [--pitch 1.08]
                      [--variant short] [--no-captions] [--dry-run]
                      [--transition fade|cut] [--fade 0.6] [--sfx none|whoosh|click]
                      [--music track.mp3 --music-licence "where it is from, its licence" [--music-volume 0.12]]
                      [--label-text "AI illustration"]

Motion: every image gets a slow camera move - zoom in, zoom out, or a pan - varied from one image to the
next (or set per entry with "motion": zoom_in|zoom_out|pan_left|pan_right|pan_up|pan_down). Images
crossfade into each other (--transition cut for hard cuts). --sfx adds a quiet whoosh or click on each
change of picture; --music lays a track under the voice and ducks it while the narrator speaks.

AI images: any image whose licence starts with "AI illustration" (images.py writes that) makes render.py
burn a small "AI illustration" label into the corner for the whole video. Reword it with --label-text. It is
off only when the creator has written `ai_label: off` (with the date and reason) in the project's brief.md or the
channel notes - see settings.py - or passes --ai-label off; the setting is recorded in render.json and qa.py reports
it. --ai-label on forces the label whatever the notes say. The description must still disclose the AI images.

--clip A B [--intro-audio narration/short-1-intro.wav] [--hook-text "WORDS"] [--name short-1]
cuts narration lines A..B (0-based; `render.py <p> --list-lines` prints them with times) out of the long video as a vertical Short
into render/shorts/NAME/: same pictures and voice, a new spoken first line in front (made with
tts.py), on-screen hook words for the first two seconds - what /yt-shorts asks for.

--variant NAME renders a second cut (e.g. a one-minute vertical Short) from
narration/NAME-voiceover.wav/.json and visuals/NAME-plan.json into render/NAME/.

Inputs (inside the project):
  narration/voiceover.wav + voiceover.json   from tts.py (line start/end times)
  visuals/plan.json                          which picture covers which narration lines:
    [{"start_line": 0, "image": "visuals/images/walls.jpg", "licence": "Public domain",
      "source_url": "https://commons.wikimedia.org/wiki/File:...", "attribution": "", "card": "The land walls"},
     {"start_line": 3, "image": null, "card": "Map: the Golden Horn"},
     {"start_line": 5, "kind": "title", "card": "1453", "subtitle": "The last siege"}]
    A segment runs from its start_line to the next entry's start_line. start_line 0 must exist.
    "kind": "title" is a designed card (big text, optional subtitle, over a darkened cleared image if
    one is given) - a finished part of the video, not a placeholder.
    An image is used ONLY if the file exists and `licence` is set and not "unknown";
    otherwise the segment becomes a title card showing `card` - never a guessed picture.

Outputs (project/render/):
  draft.mp4 (any placeholder cards) or video.mp4 (every segment a cleared image or a title card)
  captions.srt   - upload it to YouTube as subtitles too
  credits.txt    - attribution lines for the description
  render.json    - what was used where, placeholders, licences, the exact ffmpeg commands

--pitch raises (>1) or lowers (<1) the voice without changing its speed (ffmpeg rubberband,
or asetrate+atempo if rubberband is missing). 1.05-1.12 is a natural range.

Optional enhanced look (all off by default; the plain render above is unchanged - see effects.py):
    --enhanced | --opening | --animate-cards | --name-tags FILE | --timeline | --mixed-transitions | --texture
    --emblem PNG --emblem-licence "where it is from, its licence"   (the opening's title sting)
    [--hook-file hooks/chosen.txt] [--chapters seo/chapters-provisional.txt] [--claims factcheck/claims.json]
    [--smooth-motion]   camera moves drawn at sub-pixel precision (no zoom stutter; needs Pillow); on with --enhanced
    [--output render/NAME/NAME.mp4]       write the video there instead of render/[variant/]video.mp4
Enhanced renders burn in no narration captions, keep the AI label (when it is on) on top of every effect, and write effects-log.md.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

EFFECT_FLAGS = ("--enhanced", "--opening", "--animate-cards", "--name-tags", "--timeline", "--mixed-transitions", "--texture")
FPS = 30
MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")
MOTION_CYCLE = ("zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "pan_up", "zoom_out", "pan_down")
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
        # an entry may carry "parts": it is then cut into consecutive shots (a picture with its own crop, or a map), each given
        # a share of the entry's time by its "weight" (default 1); a part's own fields override the entry's
        parts = e.get("parts") or [{}]
        wsum = sum(float(p.get("weight", 1)) for p in parts); cur = t0
        for j, part in enumerate(parts):
            ee = {**e, **part}
            end = t1 if j == len(parts) - 1 else cur + (t1 - t0) * float(part.get("weight", 1)) / wsum
            ok = usable(ee, pdir)
            title = ee.get("kind") == "title"
            is_map = ee.get("kind") == "map"
            if title and not str(ee.get("card") or "").strip(): die(f"plan.json entry {i}: a title card needs 'card' text")
            if is_map and not isinstance(ee.get("map"), dict): die(f"plan.json entry {i}: a map shot needs a 'map' object (effects.py draws it)")
            if ee.get("motion") and ee["motion"] not in MOTIONS: die(f"plan.json entry {i}: motion must be one of {', '.join(MOTIONS)}")
            if ee.get("shot") is not None and not (isinstance(ee["shot"], dict) and set(ee["shot"]) == {"z0", "z1", "cx0", "cy0", "cx1", "cy1"}):
                die(f"plan.json entry {i}: 'shot' needs exactly z0, z1, cx0, cy0, cx1, cy1")
            n = len(segs)
            segs.append({"index": n, "start": round(cur, 2), "end": round(end, 2), "duration": round(max(end - cur, 0.5), 2),
                         "kind": "title" if title else "map" if is_map else "image" if ok else "card",
                         "image": ee.get("image") if ok else None,
                         "subtitle": ee.get("subtitle") or "", "motion": ee.get("motion") or MOTION_CYCLE[n % len(MOTION_CYCLE)],
                         "card": ee.get("card") or (Path(ee["image"]).stem.replace("_", " ") if ee.get("image") else "Visual to find"),
                         "licence": ee.get("licence") if ok else None, "source_url": ee.get("source_url") if ok else None,
                         "attribution": ee.get("attribution") or "",
                         "why_card": None if (ok or title or is_map) else ("no image" if not ee.get("image") else
                                                      "file missing" if not (pdir / ee["image"]).is_file() else "licence not cleared"),
                         **({"shot": ee["shot"], "part": j} if ee.get("shot") is not None and ok else {}),
                         **({"map": ee["map"]} if is_map else {})})
            cur = end
    return segs


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)   # whole ms: never ",1000"
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap(text, width=42):
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out


def captions(lines, width=42):
    rows, n = [], 0
    for ln in lines:
        text = re.sub(r"\s*/\s*", " ", re.sub(r"\[PAUSE\]", "", ln["line"], flags=re.I)).strip()
        if not text or ln["end"] - ln["start"] < 0.3: continue
        parts = wrap(text, width)
        chunks = ["\n".join(parts[i:i + 2]) for i in range(0, len(parts), 2)]   # two caption lines max
        span = (ln["end"] - ln["start"]) / len(chunks)
        for k, c in enumerate(chunks):
            n += 1; a = ln["start"] + k * span
            rows.append(f"{n}\n{srt_time(a)} --> {srt_time(a + span - 0.02)}\n{c}\n")
    return "\n".join(rows)


def motion_filter(motion, frames, W, H):
    """A slow camera move over a still: gentle enough to read as documentary, varied so 100 images do not blur together."""
    t = f"on/{frames}"
    if motion == "zoom_in":   z, x, y = f"min(1+0.12*{t},1.12)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out": z, x, y = f"max(1.12-0.12*{t},1.0)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "pan_right": z, x, y = "1.15", f"(iw-iw/zoom)*{t}", "ih/2-(ih/zoom/2)"
    elif motion == "pan_left":  z, x, y = "1.15", f"(iw-iw/zoom)*(1-{t})", "ih/2-(ih/zoom/2)"
    elif motion == "pan_down":  z, x, y = "1.15", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*{t}"
    else:                       z, x, y = "1.15", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-{t})"      # pan_up
    return (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
            f"zoompan=z='{z}':d={frames}:x='{x}':y='{y}':s={W}x{H}:fps={FPS}")


def seg_cmd(seg, pdir, work, W, H, fontfile, length=None):
    """ffmpeg command for one segment. `length` may exceed the segment's duration by the crossfade overlap."""
    out = work / f"seg{seg['index']:03d}.mp4"
    length = length or seg["duration"]
    frames = max(int(round(length * FPS)), 1)
    common = ["-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)]
    if seg["kind"] == "image":
        return out, ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{length:.3f}",
                     "-i", str(pdir / seg["image"]), "-vf", motion_filter(seg["motion"], frames, W, H), "-frames:v", str(frames)] + common
    tf = work / f"card{seg['index']:03d}.txt"
    if seg["kind"] == "title":
        tf.write_text("\n".join(wrap(seg["card"], 22)))
        big, small = max(int(H / 9), 30), max(int(H / 24), 18)
        fade = "alpha='min(1,t/0.6)'"
        text = (f"drawtext=fontfile='{fontfile}':textfile='{tf}':fontcolor=0xF4EBD8:fontsize={big}:line_spacing={big // 4}:"
                f"borderw=3:bordercolor=0x000000@0.6:x=(w-text_w)/2:y=(h-text_h)/2-{small}:{fade},"
                f"drawbox=x=iw*0.38:y=ih/2+{big // 2}:w=iw*0.24:h=3:color=0xC9A25E@0.9:t=fill")
        if seg.get("subtitle"):
            sf = work / f"sub{seg['index']:03d}.txt"; sf.write_text("\n".join(wrap(seg["subtitle"], 40)))
            text += (f",drawtext=fontfile='{fontfile}':textfile='{sf}':fontcolor=0xE2CFA0:fontsize={small}:"
                     f"x=(w-text_w)/2:y=h/2+{big // 2}+{small}:{fade}")
        if seg.get("image"):                          # a cleared picture behind the title, blurred and darkened
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=18:2,eq=brightness=-0.28:saturation=0.7,"
                  + text)
            return out, ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{length:.3f}", "-i", str(pdir / seg["image"]),
                         "-vf", vf, "-frames:v", str(frames)] + common
        return out, ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                     f"color=c=0x241d16:s={W}x{H}:d={length:.3f}:r={FPS}", "-vf", "vignette=PI/3.5," + text,
                     "-frames:v", str(frames)] + common
    tf.write_text("\n".join(wrap(seg["card"], 28)))
    size = max(int(H / 14), 28)
    vf = (f"drawtext=fontfile='{fontfile}':textfile='{tf}':fontcolor=white:fontsize={size}:line_spacing={size // 3}:"
          f"x=(w-text_w)/2:y=(h-text_h)/2,"
          f"drawtext=fontfile='{fontfile}':text='VISUAL TO ADD':fontcolor=0xAAAAAA:fontsize={size // 2}:x=(w-text_w)/2:y=h*0.08")
    return out, ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x15171c:s={W}x{H}:d={length:.3f}:r={FPS}",
                 "-vf", vf, "-frames:v", str(frames)] + common


def crossfade(files, lengths, d, work, run, chunk=8):
    """Join clips with `d`-second crossfades. Clips already carry the overlap, so the result keeps the voiceover's
    timing. Joined in chunks so a 100-image video never opens 100 decoders at once."""
    level = 0
    while len(files) > 1:
        nf, nl = [], []
        for g in range(0, len(files), chunk):
            grp, gl = files[g:g + chunk], lengths[g:g + chunk]
            if len(grp) == 1: nf.append(grp[0]); nl.append(gl[0]); continue
            fc = [f"[{i}:v]settb=AVTB,fps={FPS},format=yuv420p[v{i}]" for i in range(len(grp))]
            cur, cur_len = "v0", gl[0]
            for i in range(1, len(grp)):
                fc.append(f"[{cur}][v{i}]xfade=transition=fade:duration={d:.3f}:offset={cur_len - d:.3f}[x{i}]")
                cur, cur_len = f"x{i}", cur_len + gl[i] - d
            out = work / f"xf{level}-{g:04d}.mp4"
            run(["ffmpeg", "-y", "-loglevel", "error"] + sum((["-i", str(f)] for f in grp), []) +
                ["-filter_complex", ";".join(fc), "-map", f"[{cur}]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)], "crossfade")
            nf.append(out); nl.append(cur_len)
        files, lengths, level = nf, nl, level + 1
    return files[0]


def sfx_file(kind, work, run):
    """A quiet transition sound synthesised here (no downloaded audio, nothing to license)."""
    out = work / f"sfx-{kind}.wav"
    src = ("anoisesrc=color=pink:duration=0.55:amplitude=0.5:sample_rate=48000,highpass=f=350,lowpass=f=2600,"
           "afade=t=in:d=0.25,afade=t=out:st=0.25:d=0.3,volume=0.22" if kind == "whoosh" else
           "sine=frequency=1900:duration=0.035:sample_rate=48000,afade=t=out:d=0.035,volume=0.25")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-ac", "1", str(out)], f"{kind} sound")
    return out


def audio_filter(pitch, sr=24000):
    if not pitch or abs(pitch - 1) < 1e-3: return None
    have_rb = "rubberband" in subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return f"rubberband=pitch={pitch}" if have_rb else f"asetrate={sr}*{pitch},aresample={sr},atempo={1 / pitch:.5f}"


def clip_window(segs, lines, a, b, intro_dur, intro_lines):
    """Cut lines a..b out of the long timeline; shift so the Short starts at 0 with its new intro."""
    t0, t1 = lines[a]["start"], lines[b]["end"]
    out = []
    for sg in segs:
        lo, hi = max(sg["start"], t0), min(sg["end"], t1)
        if hi - lo < 0.05: continue
        n = dict(sg, start=round(lo - t0 + intro_dur, 2), end=round(hi - t0 + intro_dur, 2))
        out.append(n)
    if out: out[0]["start"] = 0.0                      # the intro plays over the first picture
    for k, sg in enumerate(out):
        sg["index"] = k; sg["duration"] = round(max(sg["end"] - sg["start"], 0.5), 2)
    cap = list(intro_lines) + [dict(ln, start=round(ln["start"] - t0 + intro_dur, 2), end=round(ln["end"] - t0 + intro_dur, 2))
                               for ln in lines[a:b + 1]]
    return out, cap, t0, t1


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"): print(__doc__); sys.exit(2)
    pdir = Path(a[0]).expanduser().resolve()
    def opt(f, d=None): return a[a.index(f) + 1] if f in a and a.index(f) + 1 < len(a) else d
    clip = [int(x) for x in a[a.index("--clip") + 1:a.index("--clip") + 3]] if "--clip" in a else None
    W, H = (1080, 1920) if ("--vertical" in a or (clip and "--size" not in a)) else map(int, opt("--size", "1920x1080").lower().split("x"))
    pitch = float(opt("--pitch", "1.0"))

    var = opt("--variant")
    if var and not re.fullmatch(r"[a-z0-9-]{1,20}", var): die("--variant must be short lowercase letters, digits or -")
    name_opt = opt("--name")
    if clip and name_opt and not re.fullmatch(r"[a-z0-9-]{1,30}", name_opt): die("--name must be lowercase letters, digits or -")
    pre = f"{var}-" if var else ""
    vo, meta_p, plan_p = pdir / f"narration/{pre}voiceover.wav", pdir / f"narration/{pre}voiceover.json", pdir / f"visuals/{pre}plan.json"
    for p in (vo, meta_p, plan_p):
        if not p.exists(): die(f"{p.relative_to(pdir)} not found" + (" - make it with tts.py" if "voiceover" in p.name else " - write the visual plan first (stages/render.md)"))
    meta, plan = json.loads(meta_p.read_text()), json.loads(plan_p.read_text())
    lines, total = meta["lines"], float(meta["duration_sec"])
    if "--list-lines" in a:                            # the numbers --clip and plan.json use (pause lines count too)
        for k, ln in enumerate(lines): print(f"{k:4d}  {ln['start']:7.2f}-{ln['end']:7.2f}s  {ln['line'][:90]}")
        return
    segs = build_segments(pdir, plan, lines, total)
    if any(s["kind"] == "map" for s in segs) and not any(f in a for f in EFFECT_FLAGS):
        die("map shots are drawn by effects.py: pass an enhanced flag (for example --animate-cards or --enhanced)")
    cap_lines, clip_info, intro = lines, None, None
    if clip:
        ca, cb = clip
        if not (0 <= ca <= cb < len(lines)): die(f"--clip lines must be within 0..{len(lines) - 1}, first <= last")
        intro_dur, intro_lines = 0.0, []
        if opt("--intro-audio"):
            intro = (pdir / opt("--intro-audio")) if not Path(opt("--intro-audio")).is_absolute() else Path(opt("--intro-audio"))
            ij = intro.with_suffix(".json")
            if not intro.exists() or not ij.exists(): die("--intro-audio needs the .wav and its .json from tts.py")
            imeta = json.loads(ij.read_text()); intro_dur, intro_lines = float(imeta["duration_sec"]), imeta["lines"]
        segs, cap_lines, t0, t1 = clip_window(segs, lines, ca, cb, intro_dur, intro_lines)
        total = round(intro_dur + (t1 - t0), 2)
        clip_info = {"lines": [ca, cb], "from_sec": t0, "to_sec": t1, "intro_audio": str(intro.relative_to(pdir)) if intro else None,
                     "intro_sec": intro_dur, "hook_text": opt("--hook-text")}
        if total > 60: print(f"warning: this Short runs {total:.0f} s; YouTube Shorts are capped at 3 minutes but under 60 s is the safe target", file=sys.stderr)
    cards = [s for s in segs if s["kind"] == "card"]
    titles = [s for s in segs if s["kind"] == "title"]
    ai = any(str(s.get("licence") or "").lower().startswith("ai illustration") for s in segs if s["kind"] == "image")
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import settings
    ai_set, ai_src, ai_note = settings.ai_label(pdir)
    if opt("--ai-label"):
        if opt("--ai-label") not in ("on", "off"): die("--ai-label must be on or off")
        ai_set, ai_src, ai_note = opt("--ai-label"), "--ai-label flag", ""
    label_off = bool(ai) and ai_set == "off"
    label = (opt("--label-text") or "AI illustration") if ai and not label_off else None
    transition = opt("--transition", "fade")
    if transition not in ("fade", "cut"): die("--transition must be fade or cut")
    durs = [s["duration"] for s in segs]
    fade = min(float(opt("--fade", "0.6")), min(durs) / 3) if transition == "fade" and len(segs) > 1 else 0.0
    if fade < 0.1: fade = 0.0
    sfx = opt("--sfx", "none")
    if sfx not in ("none", "whoosh", "click"): die("--sfx must be none, whoosh or click")
    music = opt("--music")
    music_licence = opt("--music-licence")
    music_vol = float(opt("--music-volume", "0.12"))
    if music:
        music = (pdir / music) if not Path(music).is_absolute() else Path(music)
        if not music.is_file(): die(f"--music file not found: {music}")
        if not music_licence or len(music_licence.strip()) < 4:
            die("--music needs --music-licence saying where the track is from and its licence (it goes in credits.txt)")

    fxo, fxlog, fxinfo, bounds, chapters, tags, fxnotes = None, [], {}, None, [], [], []
    smooth = "--smooth-motion" in a or "--enhanced" in a
    if smooth:
        if clip: die("--smooth-motion is for the long video; --clip Shorts keep the plain render")
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import effects
        try: effects.need_pillow()
        except effects.FxError as e: die(str(e))
    if any(f in a for f in EFFECT_FLAGS):
        if clip: die("the enhanced effects are for the long video; --clip Shorts keep the plain render")
        if not fade: die("the enhanced effects need crossfades (do not use --transition cut)")
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import effects
        try:
            fxo = effects.parse_flags(a, pdir, opt); effects.need_pillow()
            hook = fxo["hook_file"].read_text().strip() if fxo["opening"] and fxo["hook_file"].exists() else None
            chapters = effects.parse_chapters(fxo["chapters_file"].read_text()) if fxo["chapters_file"].exists() and (fxo["timeline"] or fxo["mixed"]) else []
            chapters = [c for c in chapters if c["t"] < total - 1]
            segs, bounds, fxlog, fxinfo = effects.plan(fxo, segs, lines, total, fade, hook, chapters)
            if fxo["tags"]:
                tg, problems = effects.load_name_tags((pdir / fxo["tags"]) if not Path(fxo["tags"]).is_absolute() else Path(fxo["tags"]),
                                                      fxo["claims_file"], lines)
                for pr in problems: print(f"warning: name tag skipped: {pr}", file=sys.stderr); fxnotes.append(f"name tag skipped: {pr}")
                tags = effects.schedule_tags(tg, segs)
            effects.describe(fxo, segs, bounds, chapters, tags, total, fxlog)
        except effects.FxError as e: die(str(e))
        cards = [s for s in segs if s["kind"] == "card"]; titles = [s for s in segs if s["kind"] == "title"]

    if "--dry-run" in a:
        for s in segs:
            if s["kind"] == "sting": what = "TITLE STING \"PAST IN MINUTES\""
            elif s["kind"] == "image": what = s["image"] + f"  [{s['licence']}]  " + ("punch-in crop" if s.get("shot") else s["motion"])
            elif s["kind"] == "map": what = "MAP SHOT " + str(s["map"].get("caption") or "")
            elif s["kind"] == "title": what = f"TITLE \"{s['card']}\"" + (f" / {s['subtitle']}" if s['subtitle'] else "")
            else: what = f"CARD \"{s['card']}\" ({s['why_card']})"
            print(f"{s['start']:7.2f}-{s['end']:7.2f}s  {what}")
        print(f"\n{len(segs)} segments, {len(cards)} placeholder card(s), {len(titles)} title card(s), {total:.1f} s, {W}x{H}"
              + (f", clip of lines {clip[0]}-{clip[1]}" if clip else "")
              + (f", {fade:.2f}s crossfades" if fade else ", hard cuts") + (f", label '{label}'" if label else (f", label OFF ({ai_src}: {ai_note or 'ai_label: off'})" if label_off else ""))
              + (f", {sfx} on changes" if sfx != "none" else "") + (f", music {music.name}" if music else ""))
        if fxo:
            print("\nenhanced effects:")
            for r in sorted(fxlog, key=lambda r: (r[0], r[2])): print(f"{effects.clock(r[0])}-{effects.clock(r[1])}  {r[2]}: {r[3]}")
        return

    if not shutil.which("ffmpeg"): die("ffmpeg is not installed", 3)
    if clip: out_dir = pdir / "render" / "shorts" / (name_opt or f"lines-{clip[0]}-{clip[1]}")
    else: out_dir = pdir / "render" / var if var else pdir / "render"
    out_name = None
    if opt("--output"):
        o = Path(opt("--output")); o = o if o.is_absolute() else pdir / o
        if o.suffix != ".mp4": die("--output must be an .mp4 path")
        out_dir, out_name = o.parent, o.name
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    hook_text = opt("--hook-text")
    fontfile = font() if (cards or titles or hook_text or label) else None
    cmds = []
    def run(cmd, what, cwd=None):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        cmds.append({"cmd": " ".join(cmd), "exit": r.returncode})
        if r.returncode: die(f"{what} failed: {r.stderr.strip()[:400]}", 1)
    seg_files, lengths = [], []
    for k, s in enumerate(segs):
        if fxo:                                               # enhanced: clip lengths come from each boundary's own transition
            try: out = effects.seg_clip(s, pdir, work, W, H, run, smooth)
            except effects.FxError as e: die(str(e), 1)
            if out is None:
                out, cmd = seg_cmd(s, pdir, work, W, H, fontfile, s["length"]); run(cmd, f"segment {s['index']}")
            seg_files.append(out); lengths.append(s["length"]); continue
        # each picture change is centred on its narration line: the fade runs from half a fade before to half after
        length = s["duration"] + (0.0 if not fade else fade / 2 if k in (0, len(segs) - 1) else fade)
        out, cmd = seg_cmd(s, pdir, work, W, H, fontfile, length)
        if smooth and s["kind"] == "image":
            try: effects.smooth_clip(s, pdir, out, W, H, max(int(round(length * FPS)), 1), run)
            except effects.FxError as e: die(str(e), 1)
        else: run(cmd, f"segment {s['index']}")
        seg_files.append(out); lengths.append(length)
    if fxo:
        joined = effects.join(seg_files, segs, bounds, work, run)
        video_in = ["-i", str(joined)]
    elif fade:
        joined = crossfade(seg_files, lengths, fade, work, run)
        video_in = ["-i", str(joined)]
    else:
        (work / "list.txt").write_text("".join(f"file '{f.name}'\n" for f in seg_files))
        video_in = ["-f", "concat", "-safe", "0", "-i", "list.txt"]
    (out_dir / "captions.srt").write_text(captions(cap_lines, 24 if H > W else 42))

    audio = vo
    if clip:                                          # cut the voiceover window; put the new first line in front
        audio = work / "audio.wav"
        trim = f"atrim=start={clip_info['from_sec']}:end={clip_info['to_sec']},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=mono"
        if intro:
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(intro), "-i", str(vo), "-filter_complex",
                 f"[0:a]aresample=48000,aformat=channel_layouts=mono[i];[1:a]{trim}[b];[i][b]concat=n=2:v=0:a=1[a]",
                 "-map", "[a]", str(audio)], "audio cut")
        else:
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vo), "-af", trim, str(audio)], "audio cut")

    name = out_name or ("video.mp4" if not cards else "draft.mp4")
    burn = "--no-captions" not in a and not fxo
    filters = [] if not burn else [
        # libass sizes against a 288-line grid: vertical needs a smaller number, and captions sit
        # above the bottom fifth, which the Shorts player covers with its buttons and title
        f"subtitles=../captions.srt:force_style='FontName=DejaVu Sans,FontSize={11 if H > W else 20},"
        f"Outline=2,Shadow=0,MarginV={62 if H > W else 40}'"]
    label_geo = None
    if hook_text:                                     # /yt-shorts: on-screen words for the first two seconds
        tf = work / "hook.txt"; tf.write_text("\n".join(wrap(hook_text, 18)))
        size = int(W / 11)
        filters.append(f"drawtext=fontfile='{fontfile}':textfile='{tf}':fontcolor=white:fontsize={size}:borderw=6:"
                       f"bordercolor=black:line_spacing={size // 4}:x=(w-text_w)/2:y=h*0.2:enable='between(t,0,2)'")
    if label:                                         # AI images: a permanent, honest corner label
        lf = work / "label.txt"; lf.write_text(label)
        lsize = max(int(H / (54 if H > W else 40)), 14)
        label_geo = {"text": label, "fontfile": fontfile, "fontsize": lsize, "boxborderw": lsize // 3, "x": "w*0.025",
                     "y": "h*0.12" if H > W else "h*0.04", "size": f"{W}x{H}"}
        filters.append(f"drawtext=fontfile='{fontfile}':textfile='{lf}':fontcolor=white@0.85:fontsize={lsize}:"
                       f"box=1:boxcolor=black@0.35:boxborderw={lsize // 3}:x=w*0.025:y={'h*0.12' if H > W else 'h*0.04'}")

    # audio: voice (+pitch) [+ music ducked under the voice] [+ quiet sounds on picture changes]
    sr = 48000 if clip else int(meta.get("sample_rate") or 24000)
    af = audio_filter(pitch, sr)
    inputs = video_in + ["-i", str(audio)]
    graph = [f"[1:a]{af + ',' if af else ''}aresample=48000,aformat=channel_layouts=mono[vo]"]
    mix, n_in = ["[vo1]"], 2
    changes = [(round(s["start"] - fade / 2, 3), sfx) for s in segs[1:]] if sfx != "none" else []
    if fxo and opt("--sfx") in (None, "whoosh"):          # enhanced: whooshes on flashes and date/chapter cards, a click on about every third change
        changes = [(t, kind) for t, kind, _ in effects.sfx_events(segs, bounds)]; sfx = "whoosh+click"
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        graph[0] = graph[0].replace("[vo]", "[vo0]") + ";[vo0]asplit=2[vo1][vosc]"
        graph.append(f"[{n_in}:a]aresample=48000,aformat=channel_layouts=mono,atrim=0:{total:.3f},volume={music_vol},"
                     f"afade=t=in:d=2,afade=t=out:st={max(total - 3, 0):.3f}:d=3[mu]")
        graph.append("[mu][vosc]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500[mud]")
        mix.append("[mud]"); n_in += 1
    else:
        graph[0] = graph[0].replace("[vo]", "[vo1]")
    if sfx != "none" and changes:
        kinds = sorted({k for _, k in changes}); src = {}
        for kd in kinds:
            idx = [i for i, (_, k) in enumerate(changes) if k == kd]
            inputs += ["-i", str(sfx_file(kd, work, run))]; n = n_in; n_in += 1
            graph.append(f"[{n}:a]asplit={len(idx)}" + "".join(f"[{kd[0]}{i}]" for i in idx) if len(idx) > 1 else f"[{n}:a]anull[{kd[0]}{idx[0]}]")
        for i, (t, kd) in enumerate(changes):
            ms = max(int((t - (0.25 if kd == "whoosh" else 0)) * 1000), 0)
            graph.append(f"[{kd[0]}{i}]adelay={ms}|{ms}[d{i}]")
        graph.append("".join(f"[d{i}]" for i in range(len(changes))) + f"amix=inputs={len(changes)}:normalize=0[sfx]")
        mix.append("[sfx]"); n_in += 0
    graph.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0[a]" if len(mix) > 1 else f"{mix[0]}anull[a]")
    if fxo:                                           # the whoosh must not push the narration past its true-peak ceiling
        graph[-1] = graph[-1].replace("[a]", "[a0]"); graph.append("[a0]alimiter=limit=0.80:level=false[a]")
    vmap, vin = "0:v", "[0:v]"
    if fxo:
        pieces, vin, n_in = effects.final_graph(fxo, W, H, total, bounds, segs, chapters, tags, work, inputs, n_in)
        graph += pieces
        if vin != "[0:v]": vmap = vin
    if filters:                                       # the AI label, when on, is always the last filter: nothing drawn above can cover it
        graph.append(vin + ",".join(filters) + "[v]"); vmap = "[v]"
    run(["ffmpeg", "-y", "-loglevel", "error"] + inputs + ["-filter_complex", ";".join(graph), "-map", vmap, "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         "-t", f"{total:.3f}", "-movflags", "+faststart", str(out_dir / name)], "final mux", cwd=work)
    other = out_dir / ("draft.mp4" if name == "video.mp4" else "video.mp4")
    if other.exists() and not out_name: other.unlink()                     # never leave a stale "final" next to a new draft

    credits = sorted({f"{s['card']}: {s['attribution'] or s['licence']} - {s['source_url']}" for s in segs
                      if s["kind"] == "image" and (s["attribution"] or s["source_url"])})
    if ai: credits.append(f"Illustrations: {label or 'AI illustration'} - AI-generated for this video, not historical images.")
    if music: credits.append(f"Music: {music.name} - {music_licence.strip()}")
    (out_dir / "credits.txt").write_text("\n".join(credits) + ("\n" if credits else ""))
    report = {"output": str((out_dir / name).relative_to(pdir)), "variant": var, "clip": clip_info, "draft": bool(cards),
              "size": f"{W}x{H}", "pitch": pitch, "duration_sec": total, "placeholders": len(cards), "titles": len(titles),
              "transition": "fade" if fade else "cut", "fade_sec": fade, "label": label, "sfx": sfx,
              "music": {"file": music.name, "licence": music_licence.strip(), "volume": music_vol} if music else None,
              "burned_captions": burn, "smooth_motion": smooth,
              "ai_label": {"setting": ai_set, "source": ai_src, "note": ai_note, "ai_images": bool(ai), "shown": bool(label)}, "label_geometry": label_geo if label else None,
              "segments": segs, "commands": cmds}
    if fxo:
        assets = [f"AI scene images and title cards: as listed in segments (licence recorded per image)", "fonts: DejaVu Sans / Serif (system fonts, free licence)"]
        mp = [s for s in segs if s["kind"] == "map"]
        if mp: assets.append(f"base map: Natural Earth 1:50m land ({mp[0]['map']['land']}); public domain per https://www.naturalearthdata.com/about/terms-of-use/ ; routes drawn by effects.py and simplified")
        if fxo["opening"]: assets.append(f"channel emblem {fxo['emblem']} (sha256 {effects.sha(fxo['emblem'])}): {fxo['emblem_licence'].strip()}")
        report["enhanced"] = {"flags": {k: bool(v) for k, v in fxo.items() if k in ("opening", "cards", "tags", "timeline", "mixed", "texture")},
                              "strong_transitions": fxinfo.get("strong", []), "sting": fxinfo.get("sting"), "flash": fxinfo.get("flash"),
                              "emblem": {"file": str(fxo["emblem"]), "licence": fxo["emblem_licence"].strip()} if fxo["opening"] else None,
                              "name_tags": [{k: t[k] for k in ("name", "fact", "claims", "at", "end")} for t in tags],
                              "label_on_top": bool(label), "effects": effects.write_log(out_dir / "effects-log.md", fxlog, fxinfo, assets, fxnotes)}
    (out_dir / "render.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {out_dir / name} ({total:.0f} s, {W}x{H})" +
          (f" - DRAFT: {len(cards)} placeholder card(s) still need a cleared image" if cards else ""))


if __name__ == "__main__":
    main()
