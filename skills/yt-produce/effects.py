#!/usr/bin/env python3
"""effects.py - the optional "enhanced" look for render.py. Nothing here runs unless render.py is given
--enhanced or one of the single-effect flags, so the plain render is byte-for-byte what it always was.

Everything is generated locally: ffmpeg filters and Pillow drawings. No downloaded footage, sounds or fonts.
The one outside file is the channel emblem for the opening sting; render.py refuses it without a recorded licence.

Flags (all off by default; --enhanced turns on every one of them that has its inputs):
  --opening        first 20 s: 2-3 s shots with punch-in crops of the same image, a flash + whoosh,
                   then a 2 s channel title sting (needs --emblem and --emblem-licence; hook from --hook-file)
  --animate-cards  date and chapter cards: year counting or sliding in, a drawn line, a soft glow
  --name-tags F    name tags for named people from visuals/name-tags.json, each fact checked against factcheck/claims.json
  --timeline       a thin chapter progress line at the bottom, shown for a few seconds at each chapter change
  --mixed-transitions  crossfade by default; dip to black, push or a short flash at chapter breaks
  --texture        very light film grain and vignette
  --smooth-motion  (also on with --enhanced) draw every camera move at sub-pixel precision instead of ffmpeg's whole-pixel zoompan

Rules these effects keep: the "AI illustration" label (unless the creator set ai_label: off, see settings.py) is the last
filter in the chain, so no effect or card can cover it; no narration captions are burned in; narration timing is never changed
(effects only change what is drawn inside the time the narration already takes); at most one stronger transition
(dip, push, flash, sting) per 20 s.
"""
import hashlib, json, math, re, shutil, subprocess, sys
from pathlib import Path

FPS = 30
OPEN_SEC = 20.0            # the opening covers the first 20 s
STING_SEC = 2.0
FLASH_PEAK = 0.55          # a flash never goes fully white: the label stays readable
SFX_GAP = 1.0              # no two sounds closer than this
WHOOSH_LEAD = 0.25         # a whoosh starts this long before the change it belongs to
STRONG_GAP = 20.0          # at most one stronger transition per this many seconds
TAG_SEC, TAG_GAP = 3.2, 3.4
TIMELINE_SEC = 4.0
GRAIN, VIGNETTE = 4, "PI/5.5"   # noise strength (0-255 scale) and vignette angle: kept very light
STRONG_CYCLE = ("fadeblack", "push", "flash")
PUSH_DIRS = ("slideleft", "slideup", "slideright", "slidedown")
SHOTS = (  # punch-in crops of one picture: (zoom start, zoom end, centre x/y start, centre x/y end), fractions of the image
    (1.00, 1.20, (.50, .50), (.50, .46)),    # slow push in on the middle
    (1.55, 1.55, (.28, .38), (.38, .36)),    # tight on the upper left, drifting right
    (1.45, 1.55, (.74, .60), (.66, .56)),    # tight on the lower right
    (1.30, 1.00, (.55, .35), (.50, .50)),    # start high, pull back to the whole picture
    (1.60, 1.60, (.50, .66), (.50, .58)),    # tight on the lower middle, drifting up
)
GOLD, CREAM, SUBTLE, BG = (201, 162, 94), (244, 235, 216), (226, 207, 160), (36, 29, 22)
SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
OK_STATUS = ("supported", "partly_supported")


class FxError(Exception): pass


# ---------------------------------------------------------------- flags

def parse_flags(a, pdir, opt):
    """The effects asked for on the command line, or None when none were: render.py then takes its old path."""
    every = "--enhanced" in a
    on = lambda f: every or f in a
    fx = {"opening": on("--opening"), "cards": on("--animate-cards"), "timeline": on("--timeline"),
          "mixed": on("--mixed-transitions"), "texture": on("--texture")}
    tags = opt("--name-tags")
    if every and not tags and (pdir / "visuals/name-tags.json").exists(): tags = "visuals/name-tags.json"
    fx["tags"] = tags
    if not any(fx.values()): return None
    fx["every"] = every
    fx["emblem"] = opt("--emblem"); fx["emblem_licence"] = opt("--emblem-licence")
    if fx["opening"]:
        if not fx["emblem"] or len((fx["emblem_licence"] or "").strip()) < 4:
            raise FxError("--opening needs --emblem PNG and --emblem-licence saying where the emblem is from and its licence "
                          "(the sting never uses an asset without a recorded licence)")
        fx["emblem"] = (pdir / fx["emblem"]) if not Path(fx["emblem"]).is_absolute() else Path(fx["emblem"])
        if not fx["emblem"].is_file(): raise FxError(f"--emblem file not found: {fx['emblem']}")
    fx["hook_file"] = pdir / (opt("--hook-file") or "hooks/chosen.txt")
    fx["chapters_file"] = pdir / (opt("--chapters") or "seo/chapters-provisional.txt")
    fx["claims_file"] = pdir / (opt("--claims") or "factcheck/claims.json")
    if fx["timeline"] and not fx["chapters_file"].exists():
        if every: fx["timeline"] = False
        else: raise FxError(f"--timeline needs chapters: {fx['chapters_file']} not found (or pass --chapters FILE)")
    return fx


def need_pillow():
    try:
        import PIL, numpy  # noqa: F401
    except ImportError:
        raise FxError("the enhanced effects need Pillow and numpy (pip install pillow numpy); the plain render does not")


# ---------------------------------------------------------------- small helpers

def ease_out(x): x = min(max(x, 0.0), 1.0); return 1 - (1 - x) ** 3
def ease_io(x): x = min(max(x, 0.0), 1.0); return x * x * (3 - 2 * x)


def words(s): return re.findall(r"[a-z0-9']+", s.lower().replace("-", " "))


def clock(t): return f"{int(t // 60):02d}:{t % 60:05.2f}"


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def num_words(n):
    """Spoken forms of a number as the scripts write them: 44 -> 'forty-four', 476 -> 'four seventy-six' / 'four hundred seventy-six'."""
    if n < 20: return [ONES[n]]
    if n < 100: return [TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")]
    h, r = divmod(n, 100)
    tail = num_words(r)[0] if r else ""
    out = [f"{ONES[h]} hundred" + (f" {tail}" if tail else "")]
    if n >= 1000 or h >= 10: return out
    out.append(f"{ONES[h]} {tail}".strip() if r else f"{ONES[h]} hundred")      # years: "four seventy-six"
    return out


# ---------------------------------------------------------------- hook, chapters, name tags

def hook_end_time(hook_text, lines):
    """End time of the last narration line that belongs to the chosen hook, or None if the hook is not at the start."""
    hook_text = re.sub(r"\d+", lambda m: num_words(int(m.group(0)))[-1], hook_text)     # "753 BC" is narrated "seven fifty-three BC"
    target = words(hook_text); got, end = [], None
    for ln in lines:
        w = words(re.sub(r"\[PAUSE\]", "", ln["line"], flags=re.I))
        if not w: continue
        got += w
        if got == target[:len(got)]:
            end = ln["end"]
            if len(got) == len(target): return end
        else: break
    return end


def parse_chapters(text):
    out = []
    for ln in text.splitlines():
        m = re.match(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s+(\S.*)$", ln)
        if m: out.append({"t": int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)), "title": m.group(4).strip()})
    return out


def load_name_tags(path, claims_path, lines, min_start=OPEN_SEC):
    """Name tags whose every date and fact is taken from the fact-checked claims list. Returns (tags, problems).
    A tag is rejected, never repaired: a number, BC/AD or a word of 4+ letters that no cited claim contains is invented."""
    problems, tags = [], []
    try: raw = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e: return [], [f"{path}: unreadable ({e})"]
    try: claims = {c["id"]: c for c in json.loads(Path(claims_path).read_text())["claims"]}
    except (OSError, ValueError, KeyError) as e: return [], [f"{claims_path}: unreadable ({e})"]
    for i, t in enumerate(raw if isinstance(raw, list) else []):
        name, fact, cids = str(t.get("name") or "").strip(), str(t.get("fact") or "").strip(), t.get("claims") or []
        why = f"tag {i} ({name or '?'})"
        if not name or not cids: problems.append(f"{why}: needs a name and the claim ids it comes from"); continue
        missing = [c for c in cids if c not in claims]
        if missing: problems.append(f"{why}: unknown claim id(s) {', '.join(missing)}"); continue
        weak = [c for c in cids if claims[c].get("status") not in OK_STATUS]
        if weak: problems.append(f"{why}: claim(s) {', '.join(weak)} are not supported ({', '.join(str(claims[c].get('status')) for c in weak)})"); continue
        have = " ".join(claims[c]["text"] for c in cids).lower().replace("-", " ")
        have_words = set(words(have)); bad = []
        for tok in re.findall(r"\d+", f"{name} {fact}"):
            if not (tok in re.findall(r"\d+", have) or any(w.replace("-", " ") in have for w in num_words(int(tok)))): bad.append(tok)
        for tok in re.findall(r"\b(BC|AD)\b", fact):
            if tok.lower() not in have_words: bad.append(tok)
        for w in words(f"{name} {re.sub(r'[0-9]+', '', fact)}"):
            if len(w) >= 4 and w not in have_words and not any(h.startswith(w[:5]) for h in have_words if len(h) >= 4): bad.append(w)
        if bad: problems.append(f"{why}: not in claim(s) {', '.join(cids)}: {', '.join(sorted(set(bad)))}"); continue
        pat = re.compile(r"\b" + (t.get("match") or re.escape(name.split()[-1])) + r"\b")
        hit = next((k for k, ln in enumerate(lines) if ln["start"] >= min_start and pat.search(ln["line"])), None)
        first = next((k for k, ln in enumerate(lines) if pat.search(ln["line"])), None)
        if hit is None: problems.append(f"{why}: the name is never spoken after {min_start:g} s"); continue
        tags.append({"name": name, "fact": fact, "claims": list(cids), "line": hit, "first_spoken_line": first,
                     "t": lines[hit]["start"]})
    return tags, problems


def schedule_tags(tags, segs):
    """One appearance per person. People first spoken in the same line appear together, stacked (0.3 s apart); groups
    never overlap in time; never on a title card or the sting."""
    out, free = [], -99.0
    groups = {}
    for t in sorted(tags, key=lambda x: x["t"]): groups.setdefault(t["line"], []).append(t)
    for line in sorted(groups):
        base = max(groups[line][0]["t"], free)
        for _ in range(4):
            s = next((s for s in segs if s["start"] <= base < s["end"]), None)
            if s and s["kind"] in ("title", "sting", "card", "map"): base = s["end"] + 0.1
            else: break
        for slot, t in enumerate(groups[line]):
            at = base + 0.3 * slot
            out.append(dict(t, at=round(at, 2), end=round(at + TAG_SEC, 2), slot=slot, delayed=round(at - t["t"], 2)))
        free = out[-1]["end"] + 0.2
    return out


# ---------------------------------------------------------------- planning (pure; no ffmpeg)

def plan(fx, segs, lines, total, fade, hook_text=None, chapters=None):
    """Rewrite the segment list for the enhanced look. Returns (segs, bounds, log, info). Narration timing stays intact:
    segments are only split, or have a sting carved out of the front; their union is still [0, total]."""
    log, info = [], {"strong": [], "sting": None, "flash": None, "hook_end": None}
    segs = [dict(s) for s in segs]
    if fx["opening"]:
        end = hook_end_time(hook_text or "", lines) if hook_text else None
        if end is None:
            end = next((ln["end"] for ln in lines if ln["end"] >= 10), lines[min(2, len(lines) - 1)]["end"])
            log.append((0, 0, "note", "hook text not found at the start of the narration; the sting follows the first line that ends after 10 s"))
        info["hook_end"] = round(end, 2)
        segs = _opening(segs, end, info, fx["emblem"])
    for k, s in enumerate(segs):
        s["index"] = k
        s["duration"] = round(max(s["end"] - s["start"], 0.5), 2)
        if fx["cards"] and s["kind"] == "title": s["anim"] = True
    bounds = [None] + [{"kind": "fade", "xf": "fade", "d": fade} for _ in segs[1:]]
    if fx["opening"]: _opening_bounds(segs, bounds, info, fade)
    for k in range(1, len(segs)):            # a new crop of the same picture is a hard cut, not a dissolve
        a, b = segs[k - 1], segs[k]
        if bounds[k] and bounds[k]["kind"] == "fade" and b.get("shot") is not None and a.get("image") and a["image"] == b.get("image"):
            bounds[k] = {"kind": "cut", "xf": "fade", "d": 1 / FPS}
    if fx["mixed"] and chapters: _chapter_bounds(segs, bounds, chapters, info, fade, log)
    _finalise(segs, bounds, total)
    return segs, bounds, log, info


def _shot(i): z0, z1, c0, c1 = SHOTS[i % len(SHOTS)]; return {"z0": z0, "z1": z1, "cx0": c0[0], "cy0": c0[1], "cx1": c1[0], "cy1": c1[1]}


def _opening(segs, ts, info, emblem):
    """Carve the opening: the first date card holds for its count-up, then shots of the pictures in 2-3 s cuts; the
    sting starts at `ts` (the end of the hook) and takes STING_SEC out of the front of the segment that starts there."""
    out = []
    for pos, s in enumerate(segs):
        if pos == 0 and s["kind"] == "title":
            nxt = segs[1] if len(segs) > 1 and segs[1]["kind"] == "image" else None
            hold = min(2.9, s["duration"] * 0.5)
            if nxt and s["duration"] - hold >= 1.2:
                out.append(dict(s, end=round(s["start"] + hold, 2)))
                out += _shots(dict(nxt, start=round(s["start"] + hold, 2), end=s["end"], borrowed=True))
            else: out.append(s)
        elif s["start"] <= ts < s["end"] and min(ts + STING_SEC, s["end"]) - ts >= 1.5:
            end = round(min(ts + STING_SEC, s["end"]), 2)
            if ts - s["start"] > 0.3: out += _shots(dict(s, end=round(ts, 2)))
            out.append({"index": 0, "start": round(ts, 2), "end": end, "duration": round(end - ts, 2), "kind": "sting", "image": None,
                        "subtitle": "", "motion": "none", "card": "PAST IN MINUTES", "licence": None, "source_url": None,
                        "attribution": "", "why_card": None, "emblem": str(emblem)})
            info["sting"] = [round(ts, 2), end]
            if s["end"] - end > 0.3: out += _shots(dict(s, start=end))
        elif s["kind"] == "image" and s["start"] < OPEN_SEC: out += _shots(s)
        else: out.append(s)
    k = 0
    for s in out:                                        # number the shots so neighbouring crops always differ
        if s.get("shot") is not None: s["shot"] = _shot(k); k += 1
    return out


def _shots(s):
    """Split one picture into 2-3 s shots, each its own punch-in crop of the same image."""
    dur = s["end"] - s["start"]
    n = 1 if dur <= 3.5 else max(2, round(dur / 2.6))
    out = []
    for i in range(n):
        a = s["start"] + dur * i / n; b = s["start"] + dur * (i + 1) / n
        out.append(dict(s, start=round(a, 2), end=round(b if i < n - 1 else s["end"], 2), shot=_shot(0), part=i))
    return out


def _opening_bounds(segs, bounds, info, fade):
    for k in range(1, len(segs)):
        a, b = segs[k - 1], segs[k]
        if b["kind"] == "sting":
            bounds[k] = {"kind": "flash", "xf": "fade", "d": 1 / FPS, "flash": True}
            info["flash"] = round(b["start"], 2); info["strong"].append(round(b["start"], 2))
        elif a["kind"] == "sting": bounds[k] = {"kind": "fade", "xf": "fade", "d": min(fade, 0.5)}
        elif b["start"] < OPEN_SEC + 4:
            same = a.get("image") and a.get("image") == b.get("image")
            bounds[k] = {"kind": "cut" if same else "quick", "xf": "fade", "d": 1 / FPS if same else 0.2}


def _chapter_bounds(segs, bounds, chapters, info, fade, log):
    last = max(info["strong"]) if info["strong"] else -99.0
    if info["sting"]: last = max(last, info["sting"][1])
    n = 0
    for ch in sorted(chapters, key=lambda c: c["t"]):
        if ch["t"] < 1: continue
        k = min(range(1, len(segs)), key=lambda i: abs(segs[i]["start"] - ch["t"]))
        t = segs[k]["start"]
        if abs(t - ch["t"]) > 2.0 or bounds[k]["kind"] != "fade": continue
        if t - last < STRONG_GAP:
            log.append((t, t, "note", f"chapter '{ch['title']}': stronger transition skipped (one per {STRONG_GAP:g} s)")); continue
        kind = STRONG_CYCLE[n % len(STRONG_CYCLE)]; n += 1
        if kind == "fadeblack": bounds[k] = {"kind": "dip to black", "xf": "fadeblack", "d": 0.9}
        elif kind == "push": bounds[k] = {"kind": "push", "xf": PUSH_DIRS[(n // 3) % len(PUSH_DIRS)], "d": 0.6}
        else: bounds[k] = {"kind": "flash", "xf": "fade", "d": 1 / FPS, "flash": True}
        bounds[k]["chapter"] = ch["title"]; info["strong"].append(round(t, 2)); last = t


def _finalise(segs, bounds, total):
    """Each clip runs from half its incoming transition before its start to half the outgoing one after its end, so the
    joined video keeps the narration's timing (this is what render.py's own crossfade does with one fixed length)."""
    for k, s in enumerate(segs):
        d_in = bounds[k]["d"] if k > 0 else 0.0
        d_out = bounds[k + 1]["d"] if k + 1 < len(segs) else 0.0
        s["lead"] = round(d_in / 2, 3); s["length"] = round(s["duration"] + d_in / 2 + d_out / 2, 3)


# ---------------------------------------------------------------- segment clips

def shot_filter(sh, frames, W, H):
    t = f"on/{max(frames, 1)}"
    z = f"({sh['z0']}+({sh['z1']}-{sh['z0']})*{t})"
    cx, cy = f"({sh['cx0']}+({sh['cx1']}-{sh['cx0']})*{t})", f"({sh['cy0']}+({sh['cy1']}-{sh['cy0']})*{t})"
    x, y = f"max(0,min(iw-iw/zoom,{cx}*iw-iw/zoom/2))", f"max(0,min(ih-ih/zoom,{cy}*ih-ih/zoom/2))"
    return (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
            f"zoompan=z='{z}':d={frames}:x='{x}':y='{y}':s={W}x{H}:fps={FPS}")


def motion_box(motion, t, W, H, sw, sh):
    """Source-pixel window (x0, y0, x1, y1), as floats, for a camera move at time fraction t in [0, 1]. `motion` is one of
    render.py's names or an opening shot dict. Same moves as render.motion_filter and shot_filter, but never rounded to a pixel."""
    if isinstance(motion, dict):
        z = motion["z0"] + (motion["z1"] - motion["z0"]) * t
        cx, cy = motion["cx0"] + (motion["cx1"] - motion["cx0"]) * t, motion["cy0"] + (motion["cy1"] - motion["cy0"]) * t
        fx, fy = min(max(cx - 1 / (2 * z), 0), 1 - 1 / z), min(max(cy - 1 / (2 * z), 0), 1 - 1 / z)
    else:
        z = {"zoom_in": min(1 + 0.12 * t, 1.12), "zoom_out": max(1.12 - 0.12 * t, 1.0)}.get(motion, 1.15)
        m = (1 - 1 / z)
        fx = m * t if motion == "pan_right" else m * (1 - t) if motion == "pan_left" else m / 2
        fy = m * t if motion == "pan_down" else m * (1 - t) if motion == "pan_up" else m / 2
    bw, bh = (sh * W / H, sh) if sw / sh > W / H else (sw, sw * H / W)         # the part of the picture a 16:9 / 9:16 frame shows
    bx, by = (sw - bw) / 2, (sh - bh) / 2
    return (bx + fx * bw, by + fy * bh, bx + fx * bw + bw / z, by + fy * bh + bh / z)


def smooth_clip(seg, pdir, out, W, H, frames, run):
    """An image segment's camera move drawn frame by frame with Pillow at sub-pixel precision. ffmpeg's zoompan rounds its
    window to whole pixels, which makes slow moves step and shimmer (the picture 'jitters'); this does not."""
    from PIL import Image
    src = Image.open(pdir / seg["image"]).convert("RGB"); sw, sh = src.size
    mo = seg.get("shot") or seg["motion"]
    def frame(t):
        n = min(int(round(t * FPS)), frames - 1)
        return src.resize((W, H), Image.LANCZOS, box=motion_box(mo, n / frames, W, H, sw, sh))
    _pipe(out, W, H, frames, frame, 0.0, 0.0, 0.0, run)
    return out


def seg_clip(seg, pdir, work, W, H, run, smooth=False):
    """Render one enhanced segment. Returns the clip path, or None when this segment is not one of ours."""
    out = work / f"seg{seg['index']:03d}.mp4"; frames = max(int(round(seg["length"] * FPS)), 1)
    common = ["-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)]
    if smooth and seg["kind"] == "image":
        return smooth_clip(seg, pdir, out, W, H, frames, run)
    if seg.get("shot") and seg["kind"] == "image":
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{seg['length']:.3f}", "-i", str(pdir / seg["image"]),
             "-vf", shot_filter(seg["shot"], frames, W, H), "-frames:v", str(frames)] + common, f"shot {seg['index']}")
        return out
    if seg["kind"] == "map":
        _pipe(out, W, H, frames, lambda t: _map_frame(t, W, H, seg), seg["lead"], 0.0, 0.0, run)
        return out
    if seg["kind"] == "sting":
        _pipe(out, W, H, frames, lambda t: _sting_frame(t, W, H, seg["emblem"]), seg["lead"], STING_SEC, 0.0, run)
        return out
    if seg["kind"] == "title" and seg.get("anim"):
        _pipe(out, W, H, frames, lambda t: _card_frame(t, W, H, seg), seg["lead"], 2.4, 2.4, run)
        return out
    return None


def _pipe(out, W, H, frames, draw, lead, anim_sec, settle, run):
    """Draw frames with Pillow and feed them to ffmpeg. After `settle` seconds a card no longer changes, so its last frame repeats."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    last, last_t = None, None
    try:
        for n in range(frames):
            t = n / FPS - lead
            if settle and t >= settle and last is not None: p.stdin.write(last); continue
            last = draw(max(t, 0.0)).convert("RGB").tobytes(); p.stdin.write(last)
        p.stdin.close(); err = p.stderr.read().decode()[:300]; code = p.wait()
    except BrokenPipeError:
        err = p.stderr.read().decode()[:300]; code = p.wait()
    if code: raise FxError(f"drawing {out.name} failed: {err}")


# ---------------------------------------------------------------- map shots (Pillow; Natural Earth land, public domain)

MAP_SEA, MAP_LAND, MAP_COAST, MAP_GRID = (44, 56, 52), (216, 199, 162), (92, 72, 46), (64, 78, 72)
ROUTE_RGB = {"red": (176, 58, 44), "gold": GOLD, "cream": CREAM}


def _land_polys(path):
    k = ("land", str(path))
    if k not in _cache:
        import numpy as np
        gj = json.loads(Path(path).read_text()); out = []
        for f in gj["features"]:
            g = f["geometry"]
            for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
                out.append(np.array(poly[0], dtype="float64"))          # outer ring only
        _cache[k] = out
    return _cache[k]


def _map_view(bbox, W, H):
    """lon/lat -> pixels for a view box: longitude shortened by cos(latitude), widened to the frame's shape. Works on arrays too."""
    lon0, lat0, lon1, lat1 = bbox; cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    k = math.cos(math.radians(cy)); w, h = (lon1 - lon0) * k, lat1 - lat0
    if w / h < W / H: w = h * W / H
    else: h = w * H / W
    s = W / w
    return (lambda lon, lat: ((lon - cx) * k * s + W / 2, (cy - lat) * s + H / 2)), s


def _map_label(od, xy, text, size, rgb, a, anchor="lm"):
    od.text(xy, text, font=_font(SANS_BOLD, size), fill=rgb + (int(255 * a),), anchor=anchor,
            stroke_width=max(size // 9, 2), stroke_fill=(20, 15, 11, int(255 * a)))


def _map_frame(t, W, H, seg):
    """A parchment-coloured map: the sea, the land, a faint grid, then routes that draw themselves with a moving arrowhead,
    pins that pulse and labels that fade in. seg['map'] = {land, bbox | bbox0+bbox1, routes[], pins[], caption}."""
    import numpy as np
    from PIL import Image, ImageDraw
    m = seg["map"]; dur = max(seg.get("duration", 1.0), 0.5)
    a0 = m.get("bbox0") or m["bbox"]; a1 = m.get("bbox1") or a0; e = ease_io(t / dur)
    bbox = [a0[i] + (a1[i] - a0[i]) * e for i in range(4)]
    P, s = _map_view(bbox, W, H)
    img = Image.new("RGB", (W, H), MAP_SEA); d = ImageDraw.Draw(img)
    for lon in range(-40, 70, 5):
        x0, y0 = P(lon, 70); x1, y1 = P(lon, 10); d.line([(x0, y0), (x1, y1)], fill=MAP_GRID, width=1)
    for lat in range(10, 75, 5):
        x0, y0 = P(-40, lat); x1, y1 = P(70, lat); d.line([(x0, y0), (x1, y1)], fill=MAP_GRID, width=1)
    for poly in _land_polys(m["land"]):
        x, y = P(poly[:, 0], poly[:, 1])
        if x.max() < -50 or x.min() > W + 50 or y.max() < -50 or y.min() > H + 50: continue
        pts = list(zip(x.tolist(), y.tolist()))
        if len(pts) < 3: continue
        d.polygon(pts, fill=MAP_LAND); d.line(pts + [pts[0]], fill=MAP_COAST, width=max(int(H / 540), 2), joint="curve")
    k = ("mapvig", W, H)
    if k not in _cache:
        yy, xx = np.mgrid[0:H, 0:W]; r = np.sqrt(((xx - W / 2) / (W * .62)) ** 2 + ((yy - H / 2) / (H * .72)) ** 2)
        _cache[k] = np.clip(1.12 - 0.55 * r ** 2, 0.45, 1.05)[..., None].astype("float32")
    img = Image.fromarray(np.clip(np.asarray(img, dtype="float32") * _cache[k], 0, 255).astype("uint8"), "RGB")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov); lab = max(int(H / 30), 18)
    for r in m.get("routes", []):
        state = r.get("state", "anim")
        if state == "hidden": continue
        pts = [P(*q) for q in r["points"]]; L = [0.0]
        for i in range(1, len(pts)): L.append(L[-1] + math.dist(pts[i - 1], pts[i]))
        p = 1.0 if state == "done" else ease_io((t - r.get("start", 0.2)) / max(r.get("dur", 2.0), 0.1))
        head = L[-1] * p; drawn = [pts[0]]
        for i in range(1, len(pts)):
            if L[i] <= head: drawn.append(pts[i])
            else:
                f = (head - L[i - 1]) / max(L[i] - L[i - 1], 1e-6)
                drawn.append((pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f)); break
        col = ROUTE_RGB[r.get("colour", "red")]; wd = max(int(H / 150), 4)
        if len(drawn) > 1:
            od.line(drawn, fill=(20, 15, 11, 150), width=wd + 6, joint="curve")
            od.line(drawn, fill=col + (255,), width=wd, joint="curve")
            if r.get("arrow", True) and p > 0.02:
                (x0, y0), (x1, y1) = drawn[-2], drawn[-1]; n = math.hypot(x1 - x0, y1 - y0) or 1.0; ux, uy = (x1 - x0) / n, (y1 - y0) / n; sz = H / 34
                od.polygon([(x1 + ux * sz * .6, y1 + uy * sz * .6), (x1 - ux * sz - uy * sz * .55, y1 - uy * sz + ux * sz * .55),
                            (x1 - ux * sz + uy * sz * .55, y1 - uy * sz - ux * sz * .55)], fill=col + (255,), outline=(20, 15, 11, 200))
        if r.get("label") and (state == "done" or p > 0.25):
            la = 1.0 if state == "done" else ease_out((p - 0.25) / 0.3)
            lx, ly = P(*r["label_at"]); _map_label(od, (lx + r.get("dx", 0) * H, ly + r.get("dy", 0) * H), r["label"], lab, col if r.get("colour") != "red" else (232, 120, 100), la)
    for pin in m.get("pins", []):
        pa = ease_out((t - pin.get("start", 0.2)) / 0.5)
        if pa <= 0: continue
        x, y = P(*pin["at"]); rad = max(int(H / 85), 7); col = ROUTE_RGB[pin.get("colour", "gold")]
        if pin.get("ring", True):
            ph = (t * 0.9) % 1.0; rr = rad * (1.6 + ph * 3.2)
            od.ellipse([x - rr, y - rr, x + rr, y + rr], outline=col + (int(200 * (1 - ph) * pa),), width=3)
        od.ellipse([x - rad, y - rad, x + rad, y + rad], fill=col + (int(255 * pa),), outline=(20, 15, 11, int(255 * pa)), width=3)
        if pin.get("label"):
            left = pin.get("side") == "left"
            _map_label(od, (x + (-1 if left else 1) * rad * 2.2 + pin.get("dx", 0) * H, y + pin.get("dy", 0) * H), pin["label"], int(lab * 1.15), CREAM, pa,
                       "rm" if left else "lm")
    cap = m.get("caption")
    if cap:
        ca = ease_out((t - 0.2) / 0.6); f = _font(SANS_BOLD, max(int(H / 26), 18)); tw = od.textlength(cap, font=f); pad = int(H / 60)
        od.rounded_rectangle([W * 0.04, H * 0.05, W * 0.04 + tw + pad * 2, H * 0.05 + f.size + pad * 1.6], radius=pad // 2, fill=(20, 15, 11, int(200 * ca)))
        od.rectangle([W * 0.04 + pad * 0.5, H * 0.05 + pad * 0.7, W * 0.04 + pad * 0.5 + 4, H * 0.05 + f.size + pad * 0.9], fill=GOLD + (int(255 * ca),))
        od.text((W * 0.04 + pad * 1.4, H * 0.05 + pad * 0.8), cap, font=f, fill=CREAM + (int(255 * ca),))
    if m.get("routes") or m.get("pins"):
        _map_label(od, (W * 0.985, H * 0.975), "Map: Natural Earth (public domain). Routes simplified.", max(int(H / 62), 12), CREAM, 0.55, "rd")
    img.paste(ov, (0, 0), ov)
    return img


# ---------------------------------------------------------------- drawings (Pillow)

_cache = {}


def _font(path, size):
    from PIL import ImageFont
    k = (path, size)
    if k not in _cache: _cache[k] = ImageFont.truetype(path, size)
    return _cache[k]


def _bg(W, H):
    k = ("bg", W, H)
    if k not in _cache:
        import numpy as np
        from PIL import Image
        yy, xx = np.mgrid[0:H, 0:W]; r = np.sqrt(((xx - W / 2) / (W * .62)) ** 2 + ((yy - H / 2) / (H * .72)) ** 2)
        v = np.clip(1.12 - 0.5 * r ** 2, 0.45, 1.12)[..., None]
        _cache[k] = Image.fromarray(np.clip(np.array(BG)[None, None, :] * v, 0, 255).astype("uint8"), "RGB")
    return _cache[k].copy()


def _glow(img, layer_mask, colour, strength, radius):
    from PIL import Image, ImageFilter
    g = layer_mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(v * strength))
    img.paste(Image.new("RGB", img.size, colour), (0, 0), g)


def _count(text, k):
    return re.sub(r"\d+", lambda m: str(int(round(int(m.group(0)) * k))), text)


def _card_frame(t, W, H, seg):
    """A date or chapter card: the year counts up (or the text slides in), a line is drawn, a soft glow breathes. Readable at rest."""
    from PIL import Image, ImageDraw
    big, small = max(int(H / 9), 30), max(int(H / 24), 18)
    img = _bg(W, H); text = seg["card"]; has_num = bool(re.search(r"\d", text))
    k = ease_out(t / 1.4)
    shown = _count(text, k) if has_num else text
    slide = 0 if has_num else int((1 - ease_out(t / 0.9)) * W * 0.04)
    a = min(1.0, t / 0.5) if not has_num else 1.0
    cy = H / 2 - small
    mask = Image.new("L", (W, H), 0); d = ImageDraw.Draw(mask)
    d.text((W / 2 - slide, cy), shown, font=_font(SANS_BOLD, big), fill=int(255 * a), anchor="mm")
    _glow(img, mask, GOLD, 0.40 + 0.08 * math.sin(t * 2.4), H / 55)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.text((W / 2 - slide + 3, cy + 3), shown, font=_font(SANS_BOLD, big), fill=(0, 0, 0, int(150 * a)), anchor="mm")
    d.text((W / 2 - slide, cy), shown, font=_font(SANS_BOLD, big), fill=CREAM + (int(255 * a),), anchor="mm")
    half = W * 0.12 * ease_out((t - 0.35) / 1.0); ly = int(H / 2 + big / 2)
    if half > 1: d.rectangle([W / 2 - half, ly, W / 2 + half, ly + 2], fill=GOLD + (230,))
    sub = seg.get("subtitle") or ""
    if sub:
        sa = ease_out((t - 0.7) / 0.7); dy = int((1 - sa) * H * 0.018)
        d.text((W / 2, ly + small + dy), sub, font=_font(SANS_BOLD, small), fill=SUBTLE + (int(255 * sa),), anchor="mm")
    img.paste(layer, (0, 0), layer)
    return img


def _sting_frame(t, W, H, emblem):
    """PAST IN MINUTES: the hourglass emblem eases in, a line is drawn, the name settles in."""
    from PIL import Image, ImageDraw, ImageFilter
    img = _bg(W, H); key = ("emblem", emblem, H)
    if key not in _cache:
        em = Image.open(emblem).convert("RGB"); s = em.width; c = s / 2; r = s * 0.43
        m = Image.new("L", em.size, 0); ImageDraw.Draw(m).ellipse([c - r, c - r, c + r, c + r], fill=255)
        m = m.filter(ImageFilter.GaussianBlur(s * 0.03)); side = int(H * 0.42)
        _cache[key] = (em.resize((side, side), Image.LANCZOS), m.resize((side, side), Image.LANCZOS))
    em, m = _cache[key]
    e = ease_out(t / 0.8); sc = 0.93 + 0.07 * e; side = max(int(em.width * sc), 8)
    emr, mr = em.resize((side, side), Image.LANCZOS), m.resize((side, side), Image.LANCZOS).point(lambda v: int(v * e))
    pos = (int(W / 2 - side / 2), int(H * 0.40 - side / 2))
    glow = Image.new("L", (W, H), 0); glow.paste(mr, pos)
    _glow(img, glow, GOLD, 0.22 + 0.06 * math.sin(t * 3), H / 30)
    img.paste(emr, pos, mr)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    ly = int(H * 0.70); half = W * 0.10 * ease_out((t - 0.45) / 0.7)
    if half > 1: d.rectangle([W / 2 - half, ly, W / 2 + half, ly + 2], fill=GOLD + (230,))
    ta = ease_out((t - 0.55) / 0.6); track = (1 - ta) * H * 0.012 + H * 0.008
    f = _font(SERIF_BOLD, int(H / 15)); label = "PAST IN MINUTES"
    widths = [d.textlength(ch, font=f) for ch in label]; total = sum(widths) + track * (len(label) - 1); x = W / 2 - total / 2
    for ch, w in zip(label, widths):
        d.text((x, ly + H * 0.07), ch, font=f, fill=GOLD + (int(255 * ta),), anchor="lm"); x += w + track
    img.paste(layer, (0, 0), layer)
    return img


def tag_png(tag, path, H):
    from PIL import Image, ImageDraw
    n, f = _font(SANS_BOLD, max(int(H / 32), 18)), _font(SANS_BOLD, max(int(H / 44), 14))
    pad = int(H / 60); probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w = int(max(probe.textlength(tag["name"], font=n), probe.textlength(tag["fact"], font=f) if tag["fact"] else 0)) + pad * 3
    h = int(n.size * 1.2 + (f.size * 1.4 if tag["fact"] else 0)) + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=pad // 2, fill=(20, 15, 11, 190))
    d.rectangle([pad // 2, pad, pad // 2 + 3, h - pad], fill=GOLD + (255,))
    d.text((pad * 1.4, pad), tag["name"], font=n, fill=CREAM + (255,))
    if tag["fact"]: d.text((pad * 1.4, pad + n.size * 1.2), tag["fact"], font=f, fill=SUBTLE + (240,))
    im.save(path); return im.size


def timeline_png(chapters, total, current, path, W, H):
    from PIL import Image, ImageDraw
    h = int(H * 0.06); im = Image.new("RGBA", (W, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x0, x1, y = W * 0.06, W * 0.94, int(h * 0.72)
    d.rectangle([x0, y, x1, y + 2], fill=(255, 255, 255, 70))
    cx = x0 + (x1 - x0) * current["t"] / max(total, 1)
    d.rectangle([x0, y, cx, y + 2], fill=GOLD + (225,))
    for c in chapters:
        x = x0 + (x1 - x0) * c["t"] / max(total, 1); d.rectangle([x - 1, y - 6, x + 1, y + 8], fill=CREAM + (150,))
    d.ellipse([cx - 6, y - 5, cx + 6, y + 7], fill=GOLD + (255,))
    f = _font(SANS_BOLD, max(int(H / 56), 13)); tw = d.textlength(current["title"], font=f)
    d.text((min(max(cx - tw / 2, x0), x1 - tw), y - 14), current["title"], font=f, fill=CREAM + (215,), anchor="ls")
    im.save(path); return im.size


# ---------------------------------------------------------------- final pass: overlays, texture, flash

def final_graph(fx, W, H, total, bounds, segs, chapters, tags, work, inputs, n_in):
    """Extra ffmpeg inputs and filter-graph pieces for the final pass. Returns (graph pieces, last video label, next input index).
    The caller appends the AI label AFTER this, so it is always the top layer."""
    g, cur = [], "[0:v]"
    def nxt(): nonlocal cur; cur = f"[o{len(g)}]"; return cur
    if fx["texture"]:
        g.append(f"{cur}noise=alls={GRAIN}:allf=t,vignette={VIGNETTE}{nxt()}")
    for k, b in enumerate(bounds):
        if not b or not b.get("flash"): continue
        t = segs[k]["start"]; t0 = max(t - 0.1, 0)
        inputs += ["-f", "lavfi", "-t", "0.45", "-i", f"color=c=white:s={W}x{H}:r={FPS}"]
        g.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0:d=0.1:alpha=1,fade=t=out:st=0.1:d=0.3:alpha=1,"
                 f"colorchannelmixer=aa={FLASH_PEAK},setpts=PTS+{t0:.3f}/TB[fl{k}]")
        g.append(f"{cur}[fl{k}]overlay=0:0:eof_action=pass:enable='between(t,{t0:.3f},{t0 + 0.45:.3f})'{nxt()}")
        n_in += 1
    if fx["timeline"] and chapters:
        for c in sorted(chapters, key=lambda c: c["t"]):
            if c["t"] < 1: continue
            png = work / f"timeline{int(c['t'])}.png"; w, h = timeline_png(chapters, total, c, png, W, H)
            inputs += ["-loop", "1", "-t", f"{TIMELINE_SEC + 0.1:.2f}", "-i", str(png)]
            t0 = float(c["t"])
            g.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0:d=0.5:alpha=1,fade=t=out:st={TIMELINE_SEC - 0.7:.2f}:d=0.7:alpha=1,setpts=PTS+{t0:.3f}/TB[tl{n_in}]")
            g.append(f"{cur}[tl{n_in}]overlay=0:{H - h - int(H * 0.012)}:eof_action=pass:enable='between(t,{t0:.3f},{t0 + TIMELINE_SEC:.3f})'{nxt()}")
            n_in += 1
    for t in tags:
        png = work / f"tag-{re.sub(r'[^a-z]', '', t['name'].lower())}.png"; w, h = tag_png(t, png, H)
        inputs += ["-loop", "1", "-t", f"{TAG_SEC + 0.1:.2f}", "-i", str(png)]
        g.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0:d=0.6:alpha=1,fade=t=out:st={TAG_SEC - 0.5:.2f}:d=0.5:alpha=1,setpts=PTS+{t['at']:.3f}/TB[tg{n_in}]")
        g.append(f"{cur}[tg{n_in}]overlay={int(W * 0.05)}:{int(H * 0.80 - h - t['slot'] * (h + H * 0.012))}:eof_action=pass:enable='between(t,{t['at']:.3f},{t['end']:.3f})'{nxt()}")
        n_in += 1
    return g, cur, n_in


# ---------------------------------------------------------------- joining

def nframes(path):
    """The real frame count of a clip. Clips are drawn with a rounded frame count, so their true length differs from the plan by
    up to half a frame; an xfade whose offset lands past the end of its first clip silently drops the clip after it."""
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v", "-show_entries", "stream=nb_read_packets",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try: return int(r.stdout.strip().split(",")[0])
    except ValueError: raise FxError(f"cannot read the frame count of {path}")


def join(files, segs, bounds, work, run, chunk=8):
    """render.py's crossfade, but each boundary has its own transition and length. Same chunked joins, same timing.
    Offsets are worked out in whole frames from each clip's real frame count (see nframes), never from the planned seconds."""
    level = 0; specs = list(bounds); files = list(files); frames = [nframes(f) for f in files]
    while len(files) > 1:
        nf, nn, ns = [], [], []
        for g in range(0, len(files), chunk):
            grp, gn, gs = files[g:g + chunk], frames[g:g + chunk], specs[g:g + chunk]
            if len(grp) == 1: nf.append(grp[0]); nn.append(gn[0]); ns.append(gs[0]); continue
            fc = [f"[{i}:v]settb=AVTB,fps={FPS},format=yuv420p[v{i}]" for i in range(len(grp))]
            cur, cur_n = "v0", gn[0]
            for i in range(1, len(grp)):
                dn = max(1, min(int(round(gs[i]["d"] * FPS)), cur_n - 1, gn[i] - 1))
                fc.append(f"[{cur}][v{i}]xfade=transition={gs[i]['xf']}:duration={dn / FPS:.6f}:offset={(cur_n - dn) / FPS - 1e-4:.6f}[x{i}]")
                cur, cur_n = f"x{i}", cur_n + gn[i] - dn
            out = work / f"xf{level}-{g:04d}.mp4"
            run(["ffmpeg", "-y", "-loglevel", "error"] + sum((["-i", str(f)] for f in grp), []) +
                ["-filter_complex", ";".join(fc), "-map", f"[{cur}]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)], "crossfade")
            got = nframes(out)
            if abs(got - cur_n) > 2: raise FxError(f"joining clips {g}..{g + len(grp) - 1} gave {got} frames, expected {cur_n}")
            nf.append(out); nn.append(got); ns.append(gs[0])
        files, frames, specs, level = nf, nn, ns, level + 1
    return files[0]


# ---------------------------------------------------------------- the log

def card_log(segs, log):
    for s in segs:
        if s["kind"] == "title" and s.get("anim"):
            what = "year counts up" if re.search(r"\d", s["card"]) else "text slides in"
            log.append((s["start"], s["start"] + 2.4, "animated card", f"'{s['card']}': {what}, line drawn, soft glow"
                        + (f", subtitle '{s['subtitle']}' slides up" if s.get("subtitle") else "")))
        elif s["kind"] == "map":
            log.append((s["start"], s["end"], "animated map", f"{s['map'].get('caption') or 'map'}: Natural Earth base map (public domain), "
                        "routes, pins and labels drawn by effects.py"))
        elif s["kind"] == "sting":
            log.append((s["start"], s["end"], "title sting", "PAST IN MINUTES with the channel emblem easing in, line drawn"))
        elif s.get("shot") and s["start"] < OPEN_SEC + 6:
            log.append((s["start"], s["end"], "punch-in shot", f"{Path(s['image']).name}, zoom {s['shot']['z0']:.2f}->{s['shot']['z1']:.2f}, "
                        f"centre ({s['shot']['cx0']:.2f},{s['shot']['cy0']:.2f})->({s['shot']['cx1']:.2f},{s['shot']['cy1']:.2f})"
                        + (", image reused from the next scene" if s.get("borrowed") else "")))


def transition_log(segs, bounds, log):
    for k, b in enumerate(bounds):
        if not b or b["kind"] in ("fade",): continue
        if b["kind"] in ("cut", "quick"): log.append((segs[k]["start"], segs[k]["start"] + b["d"], "cut", ("hard cut, same picture with a new crop" if b["kind"] == "cut" else "quick 0.2 s cut to the next picture") + " (opening)")); continue
        if b["kind"] == "flash": continue            # logged with its overlay
        log.append((segs[k]["start"] - b["d"] / 2, segs[k]["start"] + b["d"] / 2, b["kind"],
                    ("slide (" + b["xf"] + ")" if b["kind"] == "push" else "fade through black") + (f" at chapter '{b['chapter']}'" if b.get("chapter") else "")))


def sfx_events(segs, bounds):
    """The quiet sounds, as (time of the picture change, 'whoosh' | 'click', why). A whoosh goes on every flash, date or
    chapter card and chapter transition; a click on about every third plain picture-to-picture change after the opening.
    No two sounds fall within SFX_GAP of each other, and nothing is added to the narration's timing."""
    whoosh = []
    for k, s in enumerate(segs):
        b = bounds[k]
        if b and b.get("flash"): whoosh.append((s["start"], "timed to the flash"))
        elif b and b.get("chapter"): whoosh.append((s["start"], f"at chapter '{b['chapter']}'"))
        elif s["kind"] == "title": whoosh.append((s["start"], f"on the date/chapter card '{s['card']}'"))
        elif s["kind"] == "map" and (k == 0 or segs[k - 1]["kind"] != "map"): whoosh.append((s["start"], "on the map shot"))
    ev, last = [], -99.0
    for t, why in sorted(whoosh):
        if t - last >= SFX_GAP: ev.append((round(t, 3), "whoosh", why)); last = t
    n = 0
    for k in range(1, len(segs)):
        a, b, s = segs[k - 1], bounds[k], segs[k]
        if s["start"] < OPEN_SEC + 4 or a["kind"] != "image" or s["kind"] != "image" or b["kind"] != "fade": continue
        n += 1
        if n % 3 == 0 and all(abs(s["start"] - e[0]) >= SFX_GAP for e in ev): ev.append((round(s["start"], 3), "click", "on every third picture change"))
    return sorted(ev)


def describe(fx, segs, bounds, chapters, tags, total, log):
    """Add every effect, with its timestamps, to `log` (rows of from, to, effect, detail). Pure: no ffmpeg."""
    card_log(segs, log); transition_log(segs, bounds, log)
    if fx["texture"]: log.append((0, total, "texture", f"very light film grain (noise {GRAIN}/255) and a soft vignette over the whole video, made by ffmpeg"))
    for k, b in enumerate(bounds):
        if b and b.get("flash"):
            t = segs[k]["start"]
            log.append((max(t - 0.1, 0), max(t - 0.1, 0) + 0.4, "flash", f"short white flash, peak {int(FLASH_PEAK * 100)}% so the label stays readable"
                        + (f" (chapter '{b['chapter']}')" if b.get("chapter") else " into the title sting")))
    for t, kind, why in sfx_events(segs, bounds):
        if kind == "whoosh": log.append((max(t - WHOOSH_LEAD, 0), max(t - WHOOSH_LEAD, 0) + 0.55, "whoosh", f"quiet whoosh synthesised by ffmpeg, {why}"))
        else: log.append((t, t + 0.04, "click", f"soft click synthesised by ffmpeg, {why}"))
    if fx["timeline"]:
        for c in sorted(chapters, key=lambda c: c["t"]):
            if c["t"] >= 1: log.append((c["t"], c["t"] + TIMELINE_SEC, "timeline", f"chapter line at the bottom: '{c['title']}'"))
    for t in tags:
        log.append((t["at"], t["end"], "name tag", f"{t['name']}" + (f" - {t['fact']}" if t["fact"] else "") + f" (claims {', '.join(t['claims'])}; "
                    f"first spoken in line {t['first_spoken_line']}" + (f", shown {t['delayed']:g} s later" + (" (stacked with the others named in that line)" if t["slot"] else "") if t["delayed"] else "") + ")"))


def write_log(path, log, info, assets, notes):
    rows = sorted(log, key=lambda r: (r[0], r[2]))
    md = ["# Effects log", "", "Every effect with its timestamp (mm:ss.ss). Generated by render.py --enhanced; nothing here changes the narration timing.", "",
          "| from | to | effect | detail |", "| --- | --- | --- | --- |"]
    md += [f"| {clock(a)} | {clock(b)} | {n} | {str(d).replace('|', '/')} |" for a, b, n, d in rows]
    md += ["", "## Stronger transitions (at most one per %g s)" % STRONG_GAP, ""]
    md += [f"- {clock(t)}" for t in sorted(info["strong"])] or ["- none"]
    md += ["", "## Assets", ""] + [f"- {a}" for a in assets] + ["", "## Not used", "",
           "- Burned-in narration captions: none in this video.", "- Downloaded assets, footage or sounds: none (the whoosh is synthesised by ffmpeg)."]
    if notes: md += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    Path(path).write_text("\n".join(md) + "\n")
    return [{"from": round(a, 2), "to": round(b, 2), "effect": n, "detail": d} for a, b, n, d in rows]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
