#!/usr/bin/env python3
"""state.py - project folders and stage tracking for /yt-produce.

Deterministic bookkeeping only. No network, no LLM calls, no API keys, no uploads.

    python3 state.py new "The fall of Constantinople" [--minutes 12] [--slug fall-of-constantinople]
    python3 state.py list
    python3 state.py status  [project]
    python3 state.py next    [project] [--post]
    python3 state.py check-tools [project]
    python3 state.py capability <project> <name> <available|unavailable> --note "how it was verified"
    python3 state.py set <project> <stage> <status> [--note ...] [--output path ...]
                         [--cmd "command" --exit N] [--user-statement "verbatim approval"]
    python3 state.py coverage [project]           # which of the 11 original skills this video used
    python3 state.py where                        # paths of this skill, sibling tools, projects root

[project] is the folder name, its slug, or omitted for the most recently updated project.
Projects live in $YT_PRODUCTIONS_DIR, default ~/youtube-productions.
The voice profile is $YT_VOICE_FILE, default ~/.claude/youtube/voice.md. Its CONTENTS are never
read into project files or printed by this script - only whether it is usable.
"""
import datetime as dt, glob, importlib.util, json, os, re, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = Path(os.environ.get("YT_SKILLS_DIR", HERE.parent)).expanduser()
ROOT = Path(os.environ.get("YT_PRODUCTIONS_DIR", "~/youtube-productions")).expanduser()
VOICE = Path(os.environ.get("YT_VOICE_FILE", "~/.claude/youtube/voice.md")).expanduser()
TTS_PY = Path(os.environ.get("YT_TTS_PYTHON", "~/.local/share/yt-tts/venv/bin/python")).expanduser()
QWEN_PY = Path(os.environ.get("YT_QWEN_PYTHON", "~/.local/share/qwen-tts/venv/bin/python")).expanduser()

SIBLING_TOOLS = {
    "hookscore": SKILLS / "yt-script" / "hookscore.py",
    "title": SKILLS / "yt-package" / "title.py",
    "chapters": SKILLS / "yt-chapters" / "chapters.py",
    "deadair": SKILLS / "yt-edit" / "deadair.py",
    "images": SKILLS / "yt-images" / "images.py",
}
IMAGE_KEY = Path(os.environ.get("OPENLUX_KEY_FILE", "~/.config/yt-claude/yt-images/openlux.key")).expanduser()

# id, title, phase, default outputs (globs allowed), depends on, pauses for the user
STAGES = [
    ("intake",    "Intake + voice profile",   "pre",  ["brief.md"],                                   [],                 False),
    ("tools",     "Capability check",          "pre",  [],                                             ["intake"],         False),
    ("niche",     "Niche check (/yt-viral)",   "pre",  ["research/niche.md"],                          ["tools"],          False),
    ("research",  "Research",                  "pre",  ["research/notes.md"],                          ["tools"],          True),
    ("sources",   "Source verification",       "pre",  ["research/sources.json", "research/sources.md"], ["research"],     False),
    ("outline",   "Outline + claim inventory", "pre",  ["outline.md"],                                 ["sources"],        False),
    ("hooks",     "Hooks (/yt-script)",        "pre",  ["hooks/hooks.txt", "hooks/hookscore.json", "hooks/chosen.txt"], ["outline"], True),
    ("script",    "Script (/yt-script)",       "pre",  ["script/script.md"],                           ["hooks"],          False),
    ("factcheck", "Fact-check (independent)",  "pre",  ["factcheck/claims.json", "factcheck/claims.md"], ["script", "sources"], True),
    ("package",   "Title + thumbnail (/yt-package)", "pre", ["package/titles.txt", "package/title-lint.json",
                   "package/chosen-title.txt", "package/chosen-thumb.txt", "package/thumbnail-brief.md"], ["factcheck"], True),
    ("visuals",   "Visual plan",               "pre",  ["visuals/shotlist.md", "visuals/assets.md"],   ["factcheck"],      False),
    ("narration", "Narration prep",            "pre",  ["narration/narration.md", "narration/pronunciation.md"], ["factcheck"], False),
    ("images",    "Scene images (/yt-images)", "pre",  ["visuals/prompts.json", "visuals/manifest.json", "visuals/review.json",
                   "visuals/plan.json"], ["narration", "visuals"], True),
    ("render",    "Video assembly (render.py)", "pre",  ["render/render.json", "render/captions.srt"], ["narration", "visuals"], True),
    ("seo",       "Description + tags (/yt-seo)", "pre", ["seo/description.md", "seo/tags.txt", "seo/chapters-provisional.txt"], ["package"], False),
    ("qa",        "Quality checks",            "pre",  ["qa/report.md"],                               ["factcheck", "package", "seo"], False),
    ("handoff",   "Upload pack (awaits approval)", "pre", ["publish/upload-pack.md"],                  ["qa"],             True),
    ("post_transcript", "Transcript (recording or voiceover)", "post", ["post/transcript.*"],          ["factcheck"],      False),
    ("post_edit",     "Edit decision list (/yt-edit)",  "post", ["post/edl.txt"],                      ["post_transcript"], False),
    ("post_chapters", "Chapters (/yt-chapters)",        "post", ["post/chapters.txt"],                 ["post_transcript"], False),
    ("post_shorts",   "Shorts picked (/yt-shorts)",     "post", ["post/shorts.md"],                    ["post_transcript"], False),
    ("post_short_render", "Shorts rendered (render.py --clip)", "post", ["render/shorts/*/render.json"], ["post_shorts"], True),
    ("schedule",      "Week plan (/yt-plan)",           "post", ["publish/plan.md"],                   ["handoff"],        True),
    ("retention",     "Retention read (/yt-retention)", "after", ["post/retention.md"],                ["handoff"],        False),
    ("comments",      "Comment replies (/yt-comment)",  "after", ["post/comments.md"],                 ["handoff"],        True),
    ("audit",         "Channel audit (/yt-audit)",      "after", ["post/channel-audit.md"],            ["handoff"],        False),
]
# which of the original skills each stage runs - drives `state.py coverage`
SKILL_STAGES = {"yt-viral": ["niche"], "yt-script": ["hooks", "script"], "yt-package": ["package"],
                "yt-seo": ["seo"], "yt-edit": ["post_edit"], "yt-chapters": ["post_chapters"],
                "yt-shorts": ["post_shorts", "post_short_render"], "yt-plan": ["schedule"],
                "yt-retention": ["retention"], "yt-comment": ["comments"], "yt-audit": ["audit"]}
SKILL_NEEDS = {"yt-viral": "yt-dlp or a list of channel videos you collect", "yt-edit": "a transcript (recording or voiceover)",
               "yt-chapters": "a transcript (recording or voiceover)", "yt-shorts": "a transcript (recording or voiceover)",
               "yt-plan": "your hours this week and your best upload day", "yt-retention": "the published video's retention CSV from YouTube Studio",
               "yt-comment": "comments pasted from the published video", "yt-audit": "your channel URL and recent video data"}
STAGE = {s[0]: dict(zip(("id", "title", "phase", "outputs", "deps", "checkpoint"), s)) for s in STAGES}
ORDER = [s[0] for s in STAGES]

STATUSES = ["pending", "in_progress", "done", "needs_input", "unavailable", "skipped",
            "awaiting_approval", "approved"]
ICON = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "needs_input": "[!] NEEDS INPUT",
        "unavailable": "[-] UNAVAILABLE", "skipped": "[>] skipped",
        "awaiting_approval": "[?] AWAITING YOUR APPROVAL", "approved": "[x] approved by you"}
OPTIONAL = {"niche", "images", "render", "post_short_render", "schedule", "retention", "comments", "audit"}   # never block the chain
SETTLED = {"done", "skipped", "approved"}            # satisfies a dependency
PASSED_OVER = SETTLED | {"unavailable"}              # `next` moves past these
TEMPLATE_MARKERS = ("Paste the transcript of your best-performing video here",
                    "Copy this to `~/.claude/youtube/voice.md` and fill it in")
DIRS = ["research", "hooks", "script", "factcheck", "package", "visuals", "narration", "seo",
        "qa", "publish", "post"]


def now(): return dt.datetime.now().astimezone().isoformat(timespec="seconds")
def die(msg, code=2): print(f"error: {msg}", file=sys.stderr); sys.exit(code)


def slugify(t):
    s = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return (s[:50].rstrip("-")) or "untitled"


def resolve(name=None):
    if not ROOT.exists(): die(f"no projects yet - {ROOT} does not exist. Start one with: state.py new \"topic\"")
    projects = [p for p in ROOT.iterdir() if (p / "project.json").exists()]
    if not projects: die(f"no projects in {ROOT}")
    if not name:
        return max(projects, key=lambda p: load(p)["updated"])
    exact = [p for p in projects if p.name == name]
    if exact: return exact[0]
    hits = [p for p in projects if p.name.endswith("-" + name) or name in p.name]
    if len(hits) == 1: return hits[0]
    if not hits: die(f"no project matches '{name}'. Try: state.py list")
    die(f"'{name}' matches several projects: " + ", ".join(sorted(h.name for h in hits)))


def load(pdir):
    data = json.loads((Path(pdir) / "project.json").read_text())
    for sid in ORDER:          # projects made before a stage existed get it as pending
        data["stages"].setdefault(sid, {"status": "pending", "updated": data.get("updated"),
                                        "outputs": [], "commands": [], "notes": []})
    return data


def save(pdir, data):
    data["updated"] = now()
    tmp = Path(pdir) / "project.json.tmp"
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(Path(pdir) / "project.json")
    (Path(pdir) / "STATUS.md").write_text(render(pdir, data))


def outputs_present(pdir, patterns):
    missing = []
    for pat in patterns:
        found = [f for f in glob.glob(str(Path(pdir) / pat)) if os.path.isfile(f) and os.path.getsize(f) > 0]
        if not found: missing.append(pat)
    return missing


def next_stage(data, include_post=False):
    """Return (stage_id or None, reason)."""
    st = data["stages"]
    for sid in ORDER:
        if STAGE[sid]["phase"] != "pre" and not include_post: continue
        s = st[sid]["status"]
        if s in PASSED_OVER or (sid in OPTIONAL and s in ("pending", "needs_input")): continue
        if s == "awaiting_approval":
            return sid, "waiting for your explicit approval - nothing is uploaded or scheduled"
        if s == "needs_input":
            return sid, "blocked - needs input: " + (st[sid]["notes"][-1] if st[sid]["notes"] else "see notes")
        bad = [d for d in STAGE[sid]["deps"] if st[d]["status"] not in SETTLED]
        if bad:
            return sid, "blocked - depends on " + ", ".join(f"{d} ({st[d]['status']})" for d in bad)
        return sid, "ready"
    return None, "all stages settled" + ("" if include_post else " (post-production: use --post)")


def render(pdir, data):
    L = [f"# {data['topic']}", "",
         f"Project: `{Path(pdir).name}`  ", f"Target length: {data['target_minutes']} min  ",
         f"Updated: {data['updated']}", ""]
    nid, why = next_stage(data)
    L += [f"**Next:** {STAGE[nid]['title'] + ' - ' + why if nid else why}", "", "## Stages", ""]
    for phase, head in (("pre", None), ("post", "## After the voiceover or recording"), ("after", "## After publishing")):
        if head: L += ["", head, ""]
        for sid in ORDER:
            if STAGE[sid]["phase"] != phase: continue
            s = data["stages"][sid]
            line = f"- {ICON[s['status']]} **{STAGE[sid]['title']}** (`{sid}`)"
            if STAGE[sid]["checkpoint"]: line += " - pauses for you"
            if sid in OPTIONAL: line += " (optional)"
            L.append(line)
            if s["notes"] and s["status"] not in ("done", "pending"):
                L.append(f"  - {s['notes'][-1]}")
    L += ["", "## Skills used", "", "| skill | stages | status |", "| --- | --- | --- |"]
    L += [f"| `/{k}` | {', '.join(v['stages'])} | {v['status']} |" for k, v in coverage(data).items()]
    caps = data.get("capabilities", {})
    if caps:
        L += ["", "## Capabilities", ""]
        for k, v in sorted(caps.items()):
            L.append(f"- {k}: **{v['status']}** - {v.get('detail', '')}")
    L += ["", "## Publishing", "",
          "Nothing in this project is uploaded, scheduled or published by /yt-produce. "
          "You do that yourself, after approving the upload pack."]
    if data.get("approval"):
        L.append(f"Approved {data['approval']['approved_at']}: \"{data['approval']['user_statement']}\"")
    return "\n".join(L) + "\n"


def coverage(data):
    """Per original skill: which stages run it and where it stands. Honest: 'used' only when a stage is done."""
    out = {}
    for skill, sids in SKILL_STAGES.items():
        sts = [data["stages"][x]["status"] for x in sids]
        notes = [data["stages"][x]["notes"][-1] for x in sids if data["stages"][x]["notes"]]
        if all(x in ("done", "approved") for x in sts): status = "used"
        elif any(x in ("done", "approved") for x in sts): status = "partly used"
        elif "in_progress" in sts: status = "in progress"
        elif "needs_input" in sts: status = "waiting for you: " + (notes[-1] if notes else SKILL_NEEDS.get(skill, ""))
        elif "unavailable" in sts: status = "unavailable: " + (notes[-1] if notes else "")
        elif "skipped" in sts: status = "skipped: " + (notes[-1] if notes else "")
        else: status = "not run yet" + (f" (needs {SKILL_NEEDS[skill]})" if skill in SKILL_NEEDS else "")
        out[skill] = {"stages": sids, "status": status}
    return out


# ---------------------------------------------------------------- commands

def cmd_new(args):
    if not args: die('usage: state.py new "topic" [--minutes N] [--slug s]')
    topic, minutes, slug = args[0], 10, None
    if "--minutes" in args: minutes = float(args[args.index("--minutes") + 1])
    if "--slug" in args: slug = slugify(args[args.index("--slug") + 1])
    slug = slug or slugify(topic)
    pdir = ROOT / f"{dt.date.today().isoformat()}-{slug}"
    if pdir.exists(): die(f"{pdir} already exists - resume it instead: state.py status {pdir.name}")
    pdir.mkdir(parents=True)
    for d in DIRS: (pdir / d).mkdir()
    t = now()
    data = {"schema": 1, "slug": slug, "topic": topic, "target_minutes": minutes,
            "created": t, "updated": t, "capabilities": {}, "approval": None, "history": [],
            "stages": {sid: {"status": "pending", "updated": t, "outputs": [], "commands": [], "notes": []}
                       for sid in ORDER}}
    save(pdir, data)
    print(pdir)


def cmd_list(args):
    if not ROOT.exists(): print(f"no projects yet ({ROOT})"); return
    rows = []
    for p in sorted(ROOT.iterdir()):
        if (p / "project.json").exists():
            d = load(p); nid, why = next_stage(d)
            rows.append(f"{p.name:<50} next: {nid or '-'} ({why})")
    print("\n".join(rows) if rows else f"no projects in {ROOT}")


def cmd_status(args):
    pdir = resolve(args[0] if args else None)
    data = load(pdir)
    print(render(pdir, data), end="")
    print(f"\n(folder: {pdir})")


def cmd_next(args):
    post = "--post" in args; args = [a for a in args if a != "--post"]
    pdir = resolve(args[0] if args else None)
    nid, why = next_stage(load(pdir), post)
    print(json.dumps({"project": pdir.name, "folder": str(pdir), "stage": nid,
                      "title": STAGE[nid]["title"] if nid else None, "reason": why,
                      "checkpoint": STAGE[nid]["checkpoint"] if nid else False}, indent=1))


def voice_status():
    """Usability of the voice profile. Never returns its contents."""
    if not VOICE.exists():
        return "missing", f"{VOICE} does not exist"
    try:
        text = VOICE.read_text(errors="replace")
    except OSError as e:
        return "unreadable", f"{VOICE} cannot be read ({e.__class__.__name__})"
    if len(text.strip()) < 200 or any(m in text for m in TEMPLATE_MARKERS):
        return "template", f"{VOICE} exists but still looks like the unfilled template"
    return "available", f"{VOICE} is readable ({len(text)} chars)"


def probe_tools():
    caps = {}
    def put(k, ok, detail): caps[k] = {"status": "available" if ok else "unavailable", "detail": detail, "checked_at": now()}

    put("python3", True, sys.version.split()[0])
    for name, path in SIBLING_TOOLS.items():
        if not path.exists():
            put(f"tool:{name}", False, f"not found at {path}"); continue
        probe = {"hookscore": ["--hook", "Why did the walls finally fall in 1453?"],
                 "title": ["--title", "Why the walls of Constantinople fell in 1453"]}.get(name)
        if probe:
            r = subprocess.run([sys.executable, str(path), *probe, "--json"], capture_output=True, text=True, timeout=30)
            put(f"tool:{name}", r.returncode == 0, f"{path} (probe exit {r.returncode})")
        else:
            put(f"tool:{name}", True, f"{path} (present)")
    for exe in ("yt-dlp", "ffmpeg", "whisper", "piper", "espeak-ng", "espeak"):
        w = shutil.which(exe); put(f"bin:{exe}", bool(w), w or "not on PATH")
    for mod in ("whisper", "faster_whisper"):
        ok = importlib.util.find_spec(mod) is not None
        put(f"py:{mod}", ok, "importable" if ok else "not installed")

    for key, py, mod in (("tts:kokoro", TTS_PY, "kokoro"), ("tts:qwen", QWEN_PY, "qwen_tts")):
        if not py.exists():
            put(key, False, f"no venv at {py} (see stages/narration.md to install)"); continue
        try:
            r = subprocess.run([str(py), "-c", f"import {mod}"], capture_output=True, text=True, timeout=180)
            put(key, r.returncode == 0, f"{py}" + ("" if r.returncode == 0 else
                f" exists but 'import {mod}' failed: {(r.stderr.strip().splitlines() or ['?'])[-1][:120]}"))
        except (OSError, subprocess.TimeoutExpired) as e:
            put(key, False, f"{py} could not run ({e.__class__.__name__})")

    def any_ok(*keys): return [k for k in keys if caps[k]["status"] == "available"]
    tts = any_ok("tts:qwen", "tts:kokoro", "bin:piper", "bin:espeak-ng", "bin:espeak")
    put("narration_audio", bool(tts), ("local TTS via " + ", ".join(tts)) if tts else
        "no local TTS (Qwen3-TTS/Kokoro/piper/espeak-ng) - narration text is still prepared; record it yourself")
    stt = any_ok("bin:whisper", "py:whisper", "py:faster_whisper")
    put("transcription", bool(stt) and caps["bin:ffmpeg"]["status"] == "available",
        ("local whisper + ffmpeg" if stt and caps["bin:ffmpeg"]["status"] == "available" else
         "no local whisper+ffmpeg - supply a transcript (.srt/.vtt) yourself, e.g. YouTube's auto-captions on an unlisted upload"))
    put("niche_research", caps["bin:yt-dlp"]["status"] == "available",
        "yt-dlp present (public listings only)" if caps["bin:yt-dlp"]["status"] == "available"
        else "no yt-dlp - /yt-viral needs a list you collect by hand, or skip it")
    # paid image generation (/yt-images): only whether the key FILE is there and private - its contents are never read here
    if not SIBLING_TOOLS["images"].exists():
        put("image_generation", False, f"yt-images not found at {SIBLING_TOOLS['images']}")
    elif not IMAGE_KEY.is_file():
        put("image_generation", False, f"no OpenLux key file at {IMAGE_KEY} - see ../yt-images/SKILL.md (or make images yourself and import them)")
    elif IMAGE_KEY.stat().st_mode & 0o077:
        put("image_generation", False, f"{IMAGE_KEY} is readable by other users - run: chmod 600 {IMAGE_KEY}")
    else:
        put("image_generation", caps["bin:ffmpeg"]["status"] == "available",
            "key file present and private (not read); paid per image - ask the creator for a spending limit"
            if caps["bin:ffmpeg"]["status"] == "available" else "key file present but ffmpeg is missing")
    vs, vd = voice_status()
    caps["voice_profile"] = {"status": "available" if vs == "available" else "unavailable", "detail": vd, "checked_at": now()}
    return caps, vs, vd


def cmd_check_tools(args):
    caps, vs, vd = probe_tools()
    if args or ROOT.exists():
        try: pdir = resolve(args[0] if args else None)
        except SystemExit:
            pdir = None
        if pdir:
            data = load(pdir)
            web = data.get("capabilities", {}).get("web_research")
            data["capabilities"] = {**caps, "web_research": web or {
                "status": "unverified", "detail": "Claude must run a test WebSearch/WebFetch and record it with `state.py capability`",
                "checked_at": now()}}
            if vs != "available":
                _transition(data, "intake", "needs_input",
                            f"voice profile {vs}: {vd}. Fill it in (templates/voice.md shows the shape) and resume.")
            save(pdir, data)
            print(f"recorded in {pdir / 'project.json'}")
    for k, v in sorted(caps.items()):
        print(f"{k:<20} {v['status']:<12} {v['detail']}")
    print(f"{'web_research':<20} {'unverified':<12} not checkable from Python - Claude verifies it with a real search")


def cmd_capability(args):
    if len(args) < 3 or "--note" not in args:
        die("usage: state.py capability <project> <name> <available|unavailable> --note \"evidence\"")
    pdir = resolve(args[0]); name, status = args[1], args[2]
    if status not in ("available", "unavailable"): die("status must be available or unavailable")
    note = args[args.index("--note") + 1]
    data = load(pdir)
    data.setdefault("capabilities", {})[name] = {"status": status, "detail": note, "checked_at": now()}
    save(pdir, data)
    print(f"{name}: {status}")


def _transition(data, sid, status, note=None):
    s = data["stages"][sid]
    data["history"].append({"at": now(), "stage": sid, "from": s["status"], "to": status, "note": note})
    s["status"], s["updated"] = status, now()
    if note: s["notes"].append(note)


def cmd_set(args):
    if len(args) < 3: die("usage: state.py set <project> <stage> <status> [--note ...] [--output p ...] [--cmd c --exit n]")
    pdir = resolve(args[0]); sid, status = args[1], args[2]
    if sid not in STAGE: die(f"unknown stage '{sid}'. Stages: {', '.join(ORDER)}")
    if status not in STATUSES: die(f"unknown status '{status}'. Statuses: {', '.join(STATUSES)}")
    rest = args[3:]
    def opt(flag):
        return rest[rest.index(flag) + 1] if flag in rest and rest.index(flag) + 1 < len(rest) else None
    note, cmd, ex, stmt = opt("--note"), opt("--cmd"), opt("--exit"), opt("--user-statement")
    outs = [rest[i + 1] for i, a in enumerate(rest) if a == "--output" and i + 1 < len(rest)]

    data = load(pdir); s = data["stages"][sid]
    if cmd is not None:
        if ex is None: die("--cmd needs --exit with the real exit code")
        s["commands"].append({"cmd": cmd, "exit": int(ex), "at": now()})
    for o in outs:
        if o not in s["outputs"]: s["outputs"].append(o)

    if status in ("needs_input", "unavailable", "skipped") and not note:
        die(f"'{status}' needs --note explaining why (what is missing, or that you asked to skip it)")
    if status in ("awaiting_approval", "approved") and sid != "handoff":
        die("only the handoff stage can await or receive approval")
    if status == "awaiting_approval" and data["stages"]["qa"]["status"] != "done":
        die("handoff cannot await approval until qa is done")
    if status == "awaiting_approval" and s["status"] == "approved":
        if not note: die("re-opening an approved pack needs --note saying what changed")
        data["approval"] = None          # the old approval covered the old pack; the creator must approve again
    if status == "approved":
        if s["status"] != "awaiting_approval": die("approval requires the upload pack to be awaiting approval first")
        if not stmt or len(stmt.strip()) < 3:
            die("approval needs --user-statement with the user's own words. Never infer approval.")
        data["approval"] = {"approved_at": now(), "user_statement": stmt.strip()}
    if status in ("done", "awaiting_approval"):
        missing = outputs_present(pdir, STAGE[sid]["outputs"] + outs)
        if missing: die(f"cannot mark {sid} {status}: missing or empty output(s): {', '.join(missing)}")
        failed = [c for c in s["commands"] if c["exit"] != 0 and c["at"] >= s.get("reset_at", "")]
        if failed: die(f"cannot mark {sid} {status}: a recorded command failed: {failed[-1]['cmd']} (exit {failed[-1]['exit']})")
        if sid == "tools" and not data.get("capabilities"):
            die("run `state.py check-tools <project>` before marking tools done")
        if sid == "tools" and data["capabilities"].get("web_research", {}).get("status") == "unverified":
            die("web_research is unverified - run a real WebSearch/WebFetch and record it with `state.py capability`")
        import qa  # same folder; validation lives in one place
        problems = qa.stage_gate(pdir, sid)
        if problems: die(f"cannot mark {sid} {status}:\n  - " + "\n  - ".join(problems))
    if status == "in_progress":
        s["reset_at"] = now()
    _transition(data, sid, status, note)
    save(pdir, data)
    nid, why = next_stage(data)
    print(f"{sid}: {status}.  next: {nid or '-'} ({why})")


def cmd_coverage(args):
    pdir = resolve(args[0] if args else None)
    cov = coverage(load(pdir))
    for k, v in cov.items(): print(f"/{k:<14} {', '.join(v['stages']):<32} {v['status']}")
    used = sum(v["status"] == "used" for v in cov.values())
    print(f"\n{used} of {len(cov)} original skills used on this video")


def cmd_where(args):
    print(json.dumps({"skill_dir": str(HERE), "skills_dir": str(SKILLS), "projects_root": str(ROOT),
                      "voice_file": str(VOICE), "tts_python": str(TTS_PY), "qwen_python": str(QWEN_PY), "tts": str(HERE / "tts.py"), "render": str(HERE / "render.py"), "images": str(SIBLING_TOOLS["images"]), "tools": {k: str(v) for k, v in SIBLING_TOOLS.items()},
                      "qa": str(HERE / "qa.py")}, indent=1))


COMMANDS = {"new": cmd_new, "list": cmd_list, "status": cmd_status, "next": cmd_next,
            "check-tools": cmd_check_tools, "coverage": cmd_coverage, "capability": cmd_capability, "set": cmd_set, "where": cmd_where}

if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__); sys.exit(0 if len(sys.argv) < 2 else 2)
    COMMANDS[sys.argv[1]](sys.argv[2:])
