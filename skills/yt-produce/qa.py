#!/usr/bin/env python3
"""qa.py - deterministic checks for a /yt-produce project. No network, no LLM, no uploads.

    python3 qa.py [project]            # full check, writes qa/report.md, exit 1 on any FAIL
    python3 qa.py [project] --gate STAGE   # just the rules for marking one stage done

It checks structure and consistency. It cannot tell whether a source says what it is claimed to
say - that is the fact-checker's job, and this script never reports a source as verified.
Results: PASS, FAIL (blocks handoff), WARN (you should look), SKIP (could not check, and says why).
"""
import json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import state  # noqa: E402
import quotecheck  # noqa: E402
import settings  # noqa: E402

WPM = 150
TIERS = {"primary", "scholarly", "secondary", "weak"}
ACCESS = {"web_fetch", "user_provided", "local_file"}
QUOTE_CHECK = {"raw_text_match", "summary_only", "user_provided_unchecked"}
CLAIM_STATUS = {"supported", "partly_supported", "contested", "unsupported", "removed"}
CHECKERS = {"yt-fact-checker", "general-purpose:yt-fact-checker-instructions"}
PLACEHOLDER = re.compile(r"\bTODO\b|\bTBD\b|\bFIXME\b|\bXXX\b|\[citation needed\]|\[source\?\]|"
                         r"lorem ipsum|\{\{|\}\}|<insert", re.I)
TEXT_FILES = ["hooks/chosen.txt", "script/script.md", "narration/narration.md", "seo/description.md",
              "package/chosen-title.txt", "package/chosen-thumb.txt", "publish/upload-pack.md"]
META = re.compile(r"^\s*(spoken )?(word count|words|runtime|duration|scratch audio|voiceover)\b[^:=]{0,40}[:=]", re.I)
TS = re.compile(r"^\s*((?:\d+:)?\d{1,2}:\d{2})\s+\S")


def read_json(p):
    try:
        return json.loads(Path(p).read_text()), None
    except FileNotFoundError:
        return None, f"{Path(p).name} is missing"
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"{Path(p).name} is not valid JSON ({e})"


def secs(ts):
    parts = [int(x) for x in ts.split(":")]
    return sum(v * 60 ** i for i, v in enumerate(reversed(parts)))


# ---------------------------------------------------------------- per-stage gates

def gate_sources(pdir):
    data, err = read_json(Path(pdir) / "research/sources.json")
    if err: return [err]
    if not isinstance(data, list) or not data: return ["sources.json must be a non-empty list"]
    probs, ids = [], set()
    for i, s in enumerate(data):
        tag = s.get("id") or f"#{i + 1}"
        for f in ("id", "title", "retrieved", "accessed_via", "quote", "tier"):
            if not str(s.get(f, "")).strip(): probs.append(f"source {tag}: missing '{f}'")
        if s.get("id") in ids: probs.append(f"source {tag}: duplicate id")
        ids.add(s.get("id"))
        if s.get("tier") and s["tier"] not in TIERS: probs.append(f"source {tag}: tier must be one of {sorted(TIERS)}")
        via = s.get("accessed_via")
        if via and via not in ACCESS: probs.append(f"source {tag}: accessed_via must be one of {sorted(ACCESS)}")
        if via == "web_fetch" and not re.match(r"^https?://\S+$", str(s.get("url", ""))):
            probs.append(f"source {tag}: accessed_via web_fetch needs the exact http(s) url that was fetched")
        if via in ("user_provided", "local_file") and not (s.get("url") or s.get("path") or s.get("citation")):
            probs.append(f"source {tag}: give the url, path or full citation the user provided")
        if s.get("retrieved") and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(s["retrieved"])):
            probs.append(f"source {tag}: retrieved must be YYYY-MM-DD")
        qc = s.get("quote_check")
        if qc not in QUOTE_CHECK:
            probs.append(f"source {tag}: quote_check must be one of {sorted(QUOTE_CHECK)} "
                         "(a quote that failed its check does not belong in the list)")
        elif qc == "raw_text_match":
            page = Path(pdir) / str(s.get("page", ""))
            if not s.get("page") or not page.is_file():
                probs.append(f"source {tag}: raw_text_match needs 'page' - the saved download, e.g. research/pages/{tag}.html")
            elif s.get("quote") and not quotecheck.check(page, s["quote"])[0]:
                probs.append(f"source {tag}: quote is NOT on the saved page {s['page']} - it is not a raw_text_match")
    return probs


def gate_factcheck(pdir):
    pdir = Path(pdir)
    data, err = read_json(pdir / "factcheck/claims.json")
    if err: return [err]
    srcs, serr = read_json(pdir / "research/sources.json")
    known = {s.get("id") for s in srcs} if isinstance(srcs, list) else set()
    probs = []
    if data.get("checked_by") not in CHECKERS:
        probs.append(f"claims.json checked_by must be one of {sorted(CHECKERS)} - the script's author does not check its own facts")
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims: return probs + ["claims.json has no claims"]
    for c in claims:
        cid, st = c.get("id", "?"), c.get("status")
        if st not in CLAIM_STATUS: probs.append(f"claim {cid}: status must be one of {sorted(CLAIM_STATUS)}"); continue
        if not str(c.get("text", "")).strip(): probs.append(f"claim {cid}: missing text")
        if st == "unsupported":
            probs.append(f"claim {cid}: UNSUPPORTED - remove it from the script (mark 'removed') or find a real source")
        if st in ("supported", "partly_supported", "contested"):
            cited = c.get("sources") or []
            if not cited: probs.append(f"claim {cid}: {st} but cites no source")
            for sid in cited:
                if sid not in known: probs.append(f"claim {cid}: cites unknown source '{sid}'")
        if st in ("partly_supported", "contested") and not str(c.get("note", "")).strip():
            probs.append(f"claim {cid}: {st} needs a note saying how the script hedges it")
    prev, _ = read_json(pdir / "factcheck/claims.prev.json")
    if isinstance(prev, dict):
        norm = lambda t: re.sub(r"\s+", " ", str(t)).strip().lower()
        old = {c.get("id"): c for c in prev.get("claims", []) if isinstance(c, dict)}
        for c in claims:
            o = old.get(c.get("id"))
            if not o or o.get("status") == c.get("status"): continue
            same_text = norm(o.get("text")) == norm(c.get("text"))
            same_srcs = sorted(o.get("sources") or []) == sorted(c.get("sources") or [])
            if same_text and same_srcs and not str(c.get("change_reason", "")).strip():
                probs.append(f"claim {c.get('id')}: ruling changed {o.get('status')} -> {c.get('status')} with the same "
                             "wording and sources - keep the earlier ruling or give change_reason")
    script = pdir / "script/script.md"
    if script.exists() and script.stat().st_mtime > (pdir / "factcheck/claims.json").stat().st_mtime + 1:
        probs.append("script/script.md changed after the fact-check - re-run the fact-check")
    return probs


def gate_hooks(pdir):
    pdir = Path(pdir)
    hooks = [l.strip() for l in (pdir / "hooks/hooks.txt").read_text().splitlines() if l.strip()] \
        if (pdir / "hooks/hooks.txt").exists() else []
    probs = [] if len(hooks) >= 5 else [f"hooks.txt has {len(hooks)} hooks - /yt-script writes five"]
    scored, err = read_json(pdir / "hooks/hookscore.json")
    if err: probs.append(err + " - save the output of hookscore.py --json")
    elif not (isinstance(scored, list) and scored and all("verdict" in r for r in scored)):
        probs.append("hookscore.json is not hookscore.py --json output")
    chosen = (pdir / "hooks/chosen.txt").read_text().strip() if (pdir / "hooks/chosen.txt").exists() else ""
    if chosen and chosen not in hooks: probs.append("hooks/chosen.txt is not one of the scored hooks")
    return probs


def gate_package(pdir):
    pdir = Path(pdir)
    probs = []
    lint, err = read_json(pdir / "package/title-lint.json")
    if err: probs.append(err + " - save the output of title.py --json")
    titles = [l.strip() for l in (pdir / "package/titles.txt").read_text().splitlines() if l.strip()] \
        if (pdir / "package/titles.txt").exists() else []
    chosen = (pdir / "package/chosen-title.txt").read_text().strip() if (pdir / "package/chosen-title.txt").exists() else ""
    if chosen and chosen not in titles: probs.append("chosen-title.txt is not one of the linted titles")
    return probs


def chapter_problems(text):
    rows = [TS.match(l).group(1) for l in text.splitlines() if TS.match(l)]
    if len(rows) < 3: return [f"{len(rows)} chapters - YouTube needs at least three"]
    probs = [] if secs(rows[0]) == 0 else ["first chapter must be 00:00"]
    for a, b in zip(rows, rows[1:]):
        if secs(b) - secs(a) < 10: probs.append(f"chapter at {a} is under 10 seconds")
    return probs


def gate_seo(pdir):
    p = Path(pdir) / "seo/chapters-provisional.txt"
    return [f"chapters-provisional.txt: {x}" for x in chapter_problems(p.read_text())] if p.exists() else []


def gate_images(pdir):
    """Every generated picture the plan uses was reviewed by yt-image-reviewer and approved in the creator's words."""
    pdir = Path(pdir); probs = []
    man, err = read_json(pdir / "visuals/manifest.json")
    if err: return [err + " - made by images.py generate"]
    plan, err = read_json(pdir / "visuals/plan.json")
    if err: return [err + " - write it with images.py plan"]
    rev, err = read_json(pdir / "visuals/review.json")
    if err: return [err + " - run the yt-image-reviewer agent on the images"]
    if not isinstance(rev, dict) or rev.get("checked_by") != "yt-image-reviewer":
        probs.append("review.json checked_by must be yt-image-reviewer - the prompt writer does not grade its own images")
    reviewed = {(r.get("scene"), r.get("file")) for r in (rev or {}).get("scenes", []) if isinstance(r, dict)} if isinstance(rev, dict) else set()
    by_file = {e.get("file"): e for e in (man or {}).get("scenes", {}).values()}
    for e in plan if isinstance(plan, list) else []:
        img = e.get("image") or ""
        if not img.startswith("visuals/images/"): continue
        rec = by_file.get(Path(img).name)
        if rec is None:
            if str(e.get("licence", "")).lower().startswith("ai illustration"):
                probs.append(f"plan uses {img} but the manifest has no record of it")
            continue
        if rec.get("status") != "approved" or not str(rec.get("approval_statement", "")).strip():
            probs.append(f"{img} is in the plan but not approved by the creator (images.py approve --statement ...)")
        if (rec.get("scene"), rec.get("file")) not in reviewed:
            probs.append(f"{img} was not reviewed by yt-image-reviewer")
        if not str(e.get("licence", "")).lower().startswith("ai illustration"):
            probs.append(f"{img} is AI-generated but its licence does not say 'AI illustration'")
    return probs


def gate_qa(pdir):
    data = state.load(pdir)
    r = (data.get("qa") or {}).get("result")
    return [] if r == "PASS" else [f"last qa run was {r or 'never run'} - run qa.py until it passes"]


GATES = {"sources": gate_sources, "factcheck": gate_factcheck, "hooks": gate_hooks,
         "package": gate_package, "seo": gate_seo, "images": gate_images, "qa": gate_qa}


def stage_gate(pdir, sid):
    fn = GATES.get(sid)
    return fn(pdir) if fn else []


# ---------------------------------------------------------------- full run

def banned_words():
    """Phrases from the voice profile's 'Words I never use' section. Returns (list, skip_reason)."""
    vs, vd = state.voice_status()
    if vs != "available": return None, vd
    text = state.VOICE.read_text(errors="replace")
    m = re.search(r"^##\s*words i never use\s*$(.*?)(?=^##\s|\Z)", text, re.I | re.M | re.S)
    if not m: return None, "voice profile has no 'Words I never use' section"
    body = m.group(1)
    quoted = re.findall(r"[\"“']([^\"”']{2,40})[\"”']", body)
    items = quoted or [x.strip(" -*•\t") for x in re.split(r"[,\n;]", body)]
    return sorted({i.lower() for i in items if 1 < len(i) <= 40}), None


def spoken_words(text):
    text = re.sub(r"\[[^\]]*\]", " ", text)                       # [ON SCREEN: ...], [PAUSE]
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(("#", "|", ">")) and not META.match(l))
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", text))


def run_tool(path, args):
    if not path.exists(): return None, f"{path.name} not found at {path}"
    r = subprocess.run([sys.executable, str(path), *args, "--json"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0: return None, f"{path.name} exited {r.returncode}: {r.stderr.strip()[:200]}"
    try: return json.loads(r.stdout), None
    except json.JSONDecodeError: return None, f"{path.name} did not return JSON"


def render_reports(pdir):
    """Every render.json that belongs to a current render. Anything under a folder named _old was archived by the creator and is not checked."""
    return sorted(p for p in pdir.glob("render/**/render.json") if "_old" not in p.relative_to(pdir).parts)


def stream_seconds(path, kind):
    """Length of the first video ('v') or audio ('a') stream, or None when ffprobe is missing or cannot say."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", kind, "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True)
        return float(r.stdout.split()[0])
    except (OSError, ValueError, IndexError): return None


def full_run(pdir):
    pdir = Path(pdir); data = state.load(pdir); R = []
    add = lambda lvl, check, msg: R.append((lvl, check, msg))

    for sid in state.ORDER:
        s = data["stages"][sid]; title = state.STAGE[sid]["title"]
        if state.STAGE[sid]["phase"] != "pre" or sid in ("qa", "handoff"): continue
        if sid in state.OPTIONAL and s["status"] == "pending": continue
        if s["status"] == "done":
            miss = state.outputs_present(pdir, state.STAGE[sid]["outputs"] + s["outputs"])
            probs = [f"missing {m}" for m in miss] + stage_gate(pdir, sid)
            add("FAIL" if probs else "PASS", f"stage {sid}", "; ".join(probs) or "outputs present, rules met")
        elif s["status"] in ("unavailable", "skipped") or (sid in state.OPTIONAL and s["status"] == "needs_input"):
            add("WARN", f"stage {sid}", f"{s['status']}: {s['notes'][-1] if s['notes'] else ''}")
        else:
            lvl = "FAIL" if sid in ("intake", "sources", "script", "factcheck", "package", "seo") else "WARN"
            add(lvl, f"stage {sid}", f"not done ({s['status']})")
    for k, v in sorted(data.get("capabilities", {}).items()):
        if v["status"] != "available" and not k.startswith(("bin:", "py:")):
            add("WARN", f"capability {k}", f"{v['status']}: {v.get('detail', '')}")

    chosen = pdir / "hooks/chosen.txt"
    if chosen.exists() and chosen.read_text().strip():
        scored, _ = read_json(pdir / "hooks/hookscore.json")
        hset = scored[0].get("set") if isinstance(scored, list) and scored and isinstance(scored[0], dict) else None
        out, err = run_tool(state.SIBLING_TOOLS["hookscore"], ["--hook", chosen.read_text().strip()] + (["--set", hset] if hset else []))
        if err: add("SKIP", "hook score", err)
        else:
            r = out[0]; msg = f"{r['verdict']} {r['band']} ({r['formula']}) - heuristic, not a predictor"
            ov = pdir / "hooks/override.txt"
            if r["band"] != "WEAK": add("PASS", "hook score", msg)
            elif ov.exists() and ov.read_text().strip():
                txt = ov.read_text()
                m = re.search(r"^HOOK:\s*(.+)$", txt, re.M)
                reason = re.search(r"^REASON:\s*(.+)$", txt, re.M)
                reason = (reason.group(1) if reason else txt).strip()[:160]
                if not m:
                    add("WARN", "hook score", msg + f"; kept by the creator (override does not say which wording it covers): {reason}")
                elif m.group(1).strip() != chosen.read_text().strip():
                    add("FAIL", "hook score", msg + "; the override was given for different wording - ask the creator whether it still applies")
                else:
                    add("WARN", "hook score", msg + f"; kept by the creator: {reason}")
            else:
                add("FAIL", "hook score", msg + "; rewrite it, or record the creator's reason for keeping it in hooks/override.txt")
    else:
        add("SKIP", "hook score", "no hooks/chosen.txt yet")

    t, th = pdir / "package/chosen-title.txt", pdir / "package/chosen-thumb.txt"
    if t.exists() and t.read_text().strip():
        args = ["--title", t.read_text().strip()] + (["--thumb", th.read_text().strip()] if th.exists() and th.read_text().strip() else [])
        out, err = run_tool(state.SIBLING_TOOLS["title"], args)
        if err: add("SKIP", "title lint", err)
        else:
            r = out[0]; issues = "; ".join(m for _, m in r["issues"]) or "no issues"
            add("FAIL" if r["score"] < 50 else "WARN" if r["score"] < 70 else "PASS", "title lint", f"{r['score']}/100 - {issues}")
    else:
        add("SKIP", "title lint", "no package/chosen-title.txt yet")

    for rel in TEXT_FILES:
        p = pdir / rel
        if p.exists():
            hits = sorted({m.group(0) for m in PLACEHOLDER.finditer(p.read_text(errors="replace"))})
            if hits: add("FAIL", "placeholders", f"{rel}: {', '.join(hits)}")
    if not any(r[1] == "placeholders" for r in R): add("PASS", "placeholders", "none found")

    words, why = banned_words()
    if words is None: add("SKIP", "banned words", why)
    else:
        found = []
        for rel in TEXT_FILES:
            p = pdir / rel
            if p.exists():
                low = p.read_text(errors="replace").lower()
                found += [f"{rel}: '{w}'" for w in words if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low)]
        add("FAIL" if found else "PASS", "banned words", "; ".join(found) or f"none of {len(words)} found")

    src = pdir / "narration/narration.md"
    src = src if src.exists() else pdir / "script/script.md"
    if src.exists():
        n = spoken_words(src.read_text(errors="replace")); mins = n / WPM; tgt = float(data["target_minutes"])
        off = abs(mins - tgt) / tgt if tgt else 0
        add("WARN" if off > 0.2 else "PASS", "runtime", f"{n} spoken words = {mins:.1f} min at {WPM} wpm (target {tgt:g}) from {src.relative_to(pdir)}")
    else:
        add("SKIP", "runtime", "no narration or script yet")

    vo, vmeta = pdir / "narration/voiceover.wav", pdir / "narration/voiceover.json"
    if vo.exists():
        meta, _ = read_json(vmeta)
        if (pdir / "narration/narration.md").exists() and (pdir / "narration/narration.md").stat().st_mtime > vo.stat().st_mtime + 1:
            add("WARN", "voiceover", "narration.md changed after voiceover.wav was made - regenerate it")
        elif isinstance(meta, dict) and meta.get("scratch"):
            add("WARN", "voiceover", "voiceover.wav is a SCRATCH track (made with unresolved CHECK pronunciations)")
        elif isinstance(meta, dict):
            add("PASS", "voiceover", f"{meta.get('duration_sec')} s, voice {meta.get('voice')}, {meta.get('engine')} - listen to every name before publishing")
        else:
            add("WARN", "voiceover", "voiceover.wav has no voiceover.json - was it made by tts.py?")
    for rj in render_reports(pdir):
        rep, _ = read_json(rj); label = f"render {rj.parent.relative_to(pdir)}"
        if not isinstance(rep, dict): add("WARN", label, "render.json unreadable"); continue
        bad = [s["index"] for s in rep.get("segments", []) if s.get("kind") == "image" and not s.get("licence")]
        src_vo = pdir / "narration" / (f"{rep['variant']}-voiceover.wav" if rep.get("variant") else "voiceover.wav")
        vid = pdir / rep["output"] if rep.get("output") else None
        vlen, alen = (stream_seconds(vid, "v"), stream_seconds(vid, "a")) if vid and vid.is_file() else (None, None)
        if bad: add("FAIL", label, f"segments {bad} use an image with no recorded licence")
        elif vlen is not None and alen is not None and alen - vlen > 1.0:
            add("FAIL", label, f"{rep['output']}: the picture ends at {vlen:.1f} s but the sound runs to {alen:.1f} s - the video is cut short, re-render")
        elif src_vo.exists() and src_vo.stat().st_mtime > rj.stat().st_mtime + 1:
            add("WARN", label, "the voiceover changed after this render - re-render")
        elif rep.get("draft"):
            add("WARN", label, f"{rep['output']} is a DRAFT: {rep['placeholders']} placeholder card(s) still need a cleared image")
        else:
            add("PASS", label, f"{rep['output']}, every image has a recorded licence - watch it through before upload")
    ai_renders = []
    ai_set, ai_src, ai_note = settings.ai_label(pdir)
    for rj in render_reports(pdir):
        rep, _ = read_json(rj)
        if isinstance(rep, dict) and any(str(s.get("licence") or "").lower().startswith("ai illustration")
                                         for s in rep.get("segments", []) if s.get("kind") == "image"):
            ai_renders.append(rj)
            if not rep.get("label"):
                if ai_set == "off":
                    add("PASS", "AI label", f"{rj.parent.relative_to(pdir)}: label off by creator decision ({ai_src}: {ai_note or 'ai_label: off'}) - "
                        "the disclosure is in the channel text and each description; answer YouTube's altered or synthetic content question truthfully")
                else:
                    add("FAIL", "AI disclosure", f"{rj.parent.relative_to(pdir)} uses AI images but has no on-screen label - re-render with this render.py "
                        "(or, if the creator decided against the label, write `ai_label: off` with the date and reason in brief.md)")
    rv, _ = read_json(pdir / "visuals/review.json")
    if isinstance(rv, dict):
        redo = [str(r.get("scene")) for r in rv.get("scenes", []) if isinstance(r, dict) and r.get("verdict") == "redo"]
        if redo: add("WARN", "image review", f"scenes marked redo by yt-image-reviewer: {', '.join(redo)} - regenerate or confirm with the creator")
    if ai_renders:
        docs = [pdir / "seo/description.md"] + [x for x in (pdir / "publish/upload-pack.md",) if x.exists()]
        probs = [f"{d.relative_to(pdir)}: {settings.disclosure_problem(d.read_text(errors='replace')) if d.exists() else 'not written yet'}"
                 for d in docs if not d.exists() or settings.disclosure_problem(d.read_text(errors="replace"))]
        if not probs:
            add("PASS", "AI disclosure", ("on-screen label and " if not ai_set == "off" else "") + "the description draft"
                + (" and upload pack" if len(docs) > 1 else "") + " carry the AI-disclosure line followed by the sources")
        else:
            add("FAIL", "AI disclosure", "the video uses AI illustrations - every description draft and upload pack must contain the line "
                f"'{settings.DISCLOSURE}' followed by the sources. " + "; ".join(probs))
    srcs, _ = read_json(pdir / "research/sources.json")
    if isinstance(srcs, list) and srcs:
        weakq = [f"{s.get('id')} ({s.get('quote_check')})" for s in srcs if s.get("quote_check") != "raw_text_match"]
        if weakq: add("WARN", "quote checks", "not matched against the raw page text: " + ", ".join(weakq))
        else: add("PASS", "quote checks", f"all {len(srcs)} quotes matched against saved page text")
        if not any(s.get("tier") in ("primary", "scholarly") for s in srcs):
            add("WARN", "source strength", "no primary or scholarly source - everything rests on secondary or weak sources")
    known = {s.get("url") for s in srcs} if isinstance(srcs, list) else set()
    for rel in ("seo/description.md", "publish/upload-pack.md"):
        p = pdir / rel
        if p.exists():
            urls = set(re.findall(r"https?://[^\s)\]>\"']+", p.read_text(errors="replace")))
            stray = sorted(u.rstrip(".,") for u in urls if u.rstrip(".,") not in known)
            if stray: add("WARN", "links", f"{rel} links not in sources.json (check each is real and intended): {', '.join(stray)}")

    if data.get("approval") and data["stages"]["handoff"]["status"] != "approved":
        add("FAIL", "approval", "approval recorded but handoff is not in the approved state")
    return R


def write_report(pdir, R):
    result = "FAIL" if any(r[0] == "FAIL" for r in R) else "PASS"
    data = state.load(pdir)
    L = [f"# QA report - {data['topic']}", "", f"**Result: {result}**  ({state.now()})", "",
         "PASS = met. FAIL = blocks handoff. WARN = look at it. SKIP = could not be checked (reason given).",
         "This report checks structure and consistency. It does not and cannot confirm that a source "
         "says what the claims ledger says it does - that is the fact-checker's job.", "",
         "| result | check | detail |", "| --- | --- | --- |"]
    L += [f"| {lvl} | {chk} | {msg.replace('|', '/')} |" for lvl, chk, msg in R]
    rp = Path(pdir) / "qa/report.md"
    rp.parent.mkdir(exist_ok=True)
    old = rp.read_text() if rp.exists() else ""
    notes = old[old.index("## Reviewer notes"):] if "## Reviewer notes" in old else ""
    rp.write_text("\n".join(L) + "\n" + ("\n" + notes if notes else ""))
    data["qa"] = {"result": result, "at": state.now(),
                  "fails": sum(r[0] == "FAIL" for r in R), "warns": sum(r[0] == "WARN" for r in R)}
    state.save(pdir, data)
    return result


def main():
    a = sys.argv[1:]
    gate = a[a.index("--gate") + 1] if "--gate" in a else None
    a = [x for i, x in enumerate(a) if x != "--gate" and (i == 0 or a[i - 1] != "--gate")]
    pdir = state.resolve(a[0] if a else None)
    if gate:
        probs = stage_gate(pdir, gate)
        print("\n".join(f"FAIL  {p}" for p in probs) or f"PASS  {gate} gate")
        sys.exit(1 if probs else 0)
    R = full_run(pdir)
    result = write_report(pdir, R)
    for lvl, chk, msg in R: print(f"{lvl:<5} {chk:<22} {msg}")
    print(f"\n{result} - report: {pdir / 'qa/report.md'}")
    sys.exit(1 if result == "FAIL" else 0)


if __name__ == "__main__":
    main()
