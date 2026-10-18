#!/usr/bin/env python3
"""images.py - scene images and thumbnails for a /yt-produce project, made with an image model you pay for.

Standard library + ffmpeg/ffprobe. The only network calls are to the image provider you choose, with the
key YOU saved in a file outside every repo. Nothing is uploaded or published.

    python3 images.py init <project> --style natural|comic|roundhead|stickman   # visuals/prompts.json from a preset
    python3 images.py check <project>                     # validate prompts, print what would be sent
    python3 images.py generate <project> --limit 3 --max-spend 0.05            # small test batch first
    python3 images.py generate <project> --max-images 120 --max-spend 1.20     # the rest
    python3 images.py retry <project> --max-spend 0.10    # failed scenes only, never automatic
    python3 images.py sheet <project>                     # visuals/contact-sheet.html (images, prompts, review)
    python3 images.py approve <project> --scenes all --statement "the creator's own words"
    python3 images.py plan <project>                      # visuals/plan.json for render.py (approved scenes only)
    python3 images.py thumb <project> --text "ROME FELL" [--from-scene 4 | --prompt "..."] --max-spend 0.02
    python3 images.py import <project> files...           # images you made elsewhere (matched by scene_NNN or order)
    python3 images.py status <project>

Providers: --provider openlux (default model gpt-image-2-c) | local (your own command) | fake (offline tests).
Rules kept in code: a paid run prints its estimate and refuses without --max-spend or above it; the first run on
a project needs --limit; 401/402/403/429 stop the batch with no retry; nothing is overwritten (a changed prompt
makes scene_003.v2.png); every generated image is recorded as "AI illustration", never as a photo or archive.
"""
import base64, hashlib, html, json, math, os, re, shutil, subprocess, sys, tempfile, time
import urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STYLES = HERE / "styles"
LABEL = "AI illustration"
LICENCE = f"{LABEL} - creator-generated"
KEY_FILE = "~/.config/yt-claude/yt-images/openlux.key"
OPENLUX = "https://api.openlux.ai"
# Per-image prices used for the spending cap: the amounts actually BILLED on 2026-10-19 where known (a listed price
# was once 21x off). Check your console after a run; add or correct prices in <project>/yt-images.json "prices".
PRICES = {"gpt-image-2-c": 0.00882, "gemini-nano-banana-2.1": 0.0133, "gemini-3.1-flash-image": 0.0122,
          "gemini-2.5-flash-image": 0.011, "doubao-seedream-4-5-251128": 0.0188, "qwen-image-3.0": 0.0212,
          "gpt-image-2.5-flare-c": 0.0118}
DEFAULTS = {"provider": "openlux", "model": "gpt-image-2-c", "max_images_per_run": 5,
            "models": {"gpt-image-2-c": {"size": "1536x1024"}, "doubao-seedream-4-5-251128": {"size": "2K"}},
            "prices": {}, "local_command": []}
STATUS_DONE = ("done", "approved")


class Fail(Exception):
    """A provider or file problem. fatal=True stops the whole batch (auth, credit, rate limit, unreachable)."""
    def __init__(self, msg, fatal=False):
        super().__init__(msg); self.fatal = fatal


def die(msg, code=2): print(f"error: {msg}", file=sys.stderr); sys.exit(code)
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path, text):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".tmp-{path.name}"); tmp.write_text(text, encoding="utf-8"); os.replace(tmp, path)


def paths(p):
    v = Path(p) / "visuals"
    return {"visuals": v, "prompts": v / "prompts.json", "manifest": v / "manifest.json", "images": v / "images",
            "pending": v / "pending", "sheet": v / "contact-sheet.html", "review": v / "review.json", "plan": v / "plan.json"}


def load_cfg(p):
    cfg = json.loads(json.dumps(DEFAULTS))
    f = Path(p) / "yt-images.json"
    if f.is_file():
        user = json.loads(f.read_text(encoding="utf-8"))
        cfg["models"].update(user.pop("models", {})); cfg["prices"].update(user.pop("prices", {})); cfg.update(user)
    return cfg


# ---------------------------------------------------------------- prompts and manifest

def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list) or not data["scenes"]:
        return ["'scenes' must be a non-empty list - write one scene every 6-10 seconds of narration"]
    out, seen = [], set()
    size = data.get("size", [1920, 1080])
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(x, int) and 64 <= x <= 4096 for x in size)):
        out.append("'size' must be [width, height] (the video size, e.g. [1920, 1080])")
    for i, s in enumerate(data["scenes"]):
        if not isinstance(s, dict) or not isinstance(s.get("scene"), int) or s["scene"] < 1:
            out.append(f"scenes[{i}]: 'scene' must be an integer >= 1"); continue
        n = s["scene"]
        if n in seen: out.append(f"scene {n} appears twice")
        seen.add(n)
        if s.get("kind") == "title":
            if not str(s.get("card", "")).strip(): out.append(f"scene {n}: a title card needs 'card' text")
        elif not str(s.get("prompt", "")).strip():
            out.append(f"scene {n}: empty prompt")
        if "start_line" in s and not (isinstance(s["start_line"], int) and s["start_line"] >= 0):
            out.append(f"scene {n}: start_line must be a narration line number (render.py --list-lines)")
        for c in s.get("characters", []):
            if c not in (data.get("characters") or {}): out.append(f"scene {n}: character {c!r} is not defined in 'characters'")
    return out


def load_prompts(p):
    f = paths(p)["prompts"]
    if not f.is_file(): die(f"no {f} - run: images.py init <project> --style natural")
    try: data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e: die(f"prompts.json is not valid JSON: {e}")
    probs = validate(data)
    if probs: die("prompts.json problems:\n  " + "\n  ".join(probs))
    return data


def full_prompt(data, sc):
    """Style first, then each named character's fixed description, then the scene. Consistency comes from here."""
    parts = [str(data.get("style", "")).strip()]
    for name in sc.get("characters", []):
        parts.append(f"{name}: {data['characters'][name]}")
    parts.append(str(sc["prompt"]).strip())
    return ". ".join(x.rstrip(". ") for x in parts if x)


def load_manifest(p):
    f = paths(p)["manifest"]
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"version": 1, "label": LABEL, "scenes": {}}


def save_manifest(p, m): atomic_write(paths(p)["manifest"], json.dumps(m, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
def image_name(n, v): return f"scene_{n:03d}.png" if v == 1 else f"scene_{n:03d}.v{v}.png"


def job_key(provider, prompt, negative, w, h, seed):
    return hashlib.sha256(json.dumps([provider, prompt, negative, w, h, seed]).encode()).hexdigest()


def jobs(p, data, provider_name):
    w, h = data.get("size", [1920, 1080]); neg = data.get("negative", "")
    for sc in sorted(data["scenes"], key=lambda s: s["scene"]):
        if sc.get("kind") == "title": continue                     # title cards are drawn by render.py
        prompt = full_prompt(data, sc); seed = int(sc.get("seed", -1))
        yield sc, {"prompt": prompt, "negative": neg, "width": w, "height": h, "seed": seed}, \
            job_key(provider_name, prompt, neg, w, h, seed)


def needs_work(p, m, n, key, retry_only):
    e = m["scenes"].get(str(n))
    if e and e.get("status") in STATUS_DONE and e.get("key") == key and (paths(p)["images"] / e["file"]).is_file():
        return False
    return not retry_only or bool(e and e.get("status") == "failed")


# ---------------------------------------------------------------- ffmpeg image handling

def need_ffmpeg():
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe): raise Fail(f"{exe} is not installed", fatal=True)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        w, h = (int(x) for x in r.stdout.strip().split(",")[:2]); return w, h
    except ValueError:
        raise Fail("not a readable image")


def save_png(data, dest, aspect=None):
    """Any image bytes -> PNG at a fixed name, centre-cropped to the video's aspect (never stretched), atomic."""
    need_ffmpeg()
    dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.img"; src.write_bytes(data)
        w, h = probe(src)
        vf = []
        if aspect:
            r = aspect[0] / aspect[1]
            if abs(w / h - r) > 0.01:
                vf = ["-vf", f"crop={round(h * r) // 2 * 2}:{h}" if w / h > r else f"crop={w}:{round(w / r) // 2 * 2}"]
        tmp = dest.with_name(f".tmp-{dest.name}")
        res = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), *vf, "-frames:v", "1",
                              "-f", "image2", "-c:v", "png", str(tmp)], capture_output=True, text=True)
        if res.returncode or not tmp.is_file(): raise Fail(f"could not convert the image ({res.stderr.strip()[:120]})")
        os.replace(tmp, dest)
    return probe(dest)


# ---------------------------------------------------------------- providers

def read_key(path=None):
    f = Path(os.path.expanduser(path or os.environ.get("OPENLUX_KEY_FILE") or KEY_FILE))
    if not f.is_file(): raise Fail(f"no key file at {f} (see SKILL.md: save it there, chmod 600)", fatal=True)
    if f.stat().st_mode & 0o077: raise Fail(f"{f} is readable by other users - run: chmod 600 {f}", fatal=True)
    key = f.read_text(encoding="utf-8").strip()
    if not key: raise Fail(f"{f} is empty", fatal=True)
    return key


def http_post(url, headers, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise Fail(f"OpenLux HTTP {e.code}: {detail}", fatal=e.code in (401, 402, 403, 404, 429)) from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise Fail(f"OpenLux request failed ({type(e).__name__}: {str(e)[:160]})") from e


def http_get(url, timeout=120):
    if not url.startswith("https://"): raise Fail("the provider returned a non-https image link; refusing it")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r: return r.read(40_000_001)
    except (urllib.error.URLError, TimeoutError) as e: raise Fail(f"could not download the image ({type(e).__name__})") from e


def aspect_name(w, h):
    g = math.gcd(w, h); a = f"{w // g}:{h // g}"
    return a if a in ("1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2", "4:5", "5:4", "21:9") else ("16:9" if w > h else "9:16" if h > w else "1:1")


class OpenLux:
    """Endpoints as documented at https://doc.openlux.ai (checked 2026-10-19): Gemini-native models use
    /v1beta/models/<model>:generateContent; the rest (gpt-image-*, doubao-seedream-*, qwen-image-*) /v1/images/generations."""
    def __init__(self, model, *, size=None, image_size="1K", max_images=5, key=None, post=http_post, get=http_get, timeout=180):
        self.model, self.size, self.image_size, self.max_images, self.n = model, size, image_size, max_images, 0
        self.key = key if key is not None else read_key()
        self.post, self.get, self.timeout = post, get, timeout
        self.name = f"openlux:{model}"

    def generate(self, req):
        if self.n >= self.max_images: raise Fail(f"stopped at the {self.max_images}-image cap for this run", fatal=True)
        self.n += 1
        hdr = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "Accept": "application/json"}
        prompt = req["prompt"] + (f". Avoid: {req['negative']}" if req.get("negative") else "")
        if self.model.startswith(("gemini", "nano-banana")):
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "response_format": "base64",
                    "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {
                        "aspectRatio": aspect_name(req["width"], req["height"]), "imageSize": self.image_size}}}
            data = self.post(f"{OPENLUX}/v1beta/models/{self.model}:generateContent", hdr, body, self.timeout)
            for cand in data.get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"): return base64.b64decode(inline["data"]), None
            why = (data.get("candidates") or [{}])[0].get("finishReason") or data.get("promptFeedback") or "no image in reply"
            raise Fail(f"{self.model}: {str(why)[:200]}")
        body = {"model": self.model, "prompt": prompt}
        if self.size: body["size"] = self.size
        if self.model.startswith("doubao-seedream"):
            body.update(output_format="png", response_format="url", watermark=False)
            if req["seed"] >= 0: body["seed"] = req["seed"]
        data = self.post(f"{OPENLUX}/v1/images/generations", hdr, body, self.timeout)
        items = data.get("data") or []
        if not items: raise Fail(f"{self.model}: no image in reply ({str(data.get('error') or data)[:200]})")
        if items[0].get("b64_json"): return base64.b64decode(items[0]["b64_json"]), None
        if items[0].get("url"): return self.get(items[0]["url"]), None
        raise Fail(f"{self.model}: reply had neither b64_json nor url")


class Local:
    """Your own generator: a command list with {prompt} {negative} {width} {height} {seed} {out}; it writes {out}."""
    name = "local"

    def __init__(self, command):
        if not command or not any("{out}" in c for c in command):
            raise Fail("set local_command in <project>/yt-images.json, with {out} where the image is written", fatal=True)
        self.command = command

    def generate(self, req):
        with tempfile.TemporaryDirectory() as td:
            out = str(Path(td) / "out.img")
            argv = [c.format(out=out, **req) for c in self.command]
            try: r = subprocess.run(argv, capture_output=True, text=True, timeout=900)
            except (OSError, subprocess.TimeoutExpired) as e: raise Fail(f"local command failed to run ({type(e).__name__})")
            if r.returncode or not Path(out).is_file():
                tail = ((r.stderr or r.stdout).strip().splitlines() or ["no output"])[-1]
                raise Fail(f"local command exit {r.returncode}: {tail[:160]}")
            return Path(out).read_bytes(), (req["seed"] if req["seed"] >= 0 else None)


class Fake:
    """Offline, free, deterministic test images (ffmpeg colour + noise). Never use in a real video."""
    name = "fake"

    def generate(self, req):
        need_ffmpeg()
        seed = req["seed"] if req["seed"] >= 0 else int(hashlib.sha256(req["prompt"].encode()).hexdigest()[:6], 16)
        colour = f"0x{seed % 0xFFFFFF:06x}"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "f.png"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"color=c={colour}:s=1536x1024,noise=alls=40:allf=u", "-frames:v", "1", str(out)], check=True)
            return out.read_bytes(), seed


def make_provider(name, cfg, model=None, max_images=None):
    cap = int(max_images or cfg.get("max_images_per_run", 5))
    if name == "fake": return Fake()
    if name == "local": return Local(cfg.get("local_command") or [])
    if name == "openlux":
        m = model or cfg["model"]; mc = cfg["models"].get(m, {})
        return OpenLux(m, size=mc.get("size"), image_size=mc.get("image_size", "1K"), max_images=cap)
    raise Fail(f"unknown provider {name!r} (openlux, local, fake)", fatal=True)


def estimate(cfg, model, n, image_size="1K"):
    price = {**PRICES, **cfg.get("prices", {})}.get(model)
    if price is None: return None
    mult = {"1K": 1.0, "2K": 1.5, "4K": 3.375}.get(image_size, 1.0) if model.startswith("gemini") else 1.0
    return round(price * mult * n, 4)


def spend_check(cfg, a, provider, model, n):
    """Paid providers: print the estimate and refuse without, or above, the creator's --max-spend."""
    if provider != "openlux": return
    m = model or cfg["model"]
    cost = estimate(cfg, m, n, cfg["models"].get(m, {}).get("image_size", "1K"))
    if cost is None: die(f"no price known for {m!r} - add it under \"prices\" in <project>/yt-images.json")
    print(f"{n} image(s) with {m}: estimated {cost:.3f} (billed prices; your console is the truth)")
    if a.get("max_spend") is None: die("paid provider: pass --max-spend <amount the creator approved>")
    if cost > a["max_spend"] + 1e-9: die(f"estimate {cost:.3f} is above --max-spend {a['max_spend']}; nothing was sent")


# ---------------------------------------------------------------- commands

def cmd_generate(p, a, retry_only=False):
    cfg = load_cfg(p); data = load_prompts(p); m = load_manifest(p)
    prov_name = a.get("provider") or cfg["provider"]; model = a.get("model")
    pname = f"openlux:{model or cfg['model']}" if prov_name == "openlux" else prov_name
    only = a.get("scenes"); limit = a.get("limit")
    if limit is None and not retry_only and not any(e.get("status") in STATUS_DONE for e in m["scenes"].values()):
        die("first run on this project: pass --limit 3 so a small batch is checked before the rest")
    todo = [(sc, req, key) for sc, req, key in jobs(p, data, pname)
            if (not only or sc["scene"] in only) and needs_work(p, m, sc["scene"], key, retry_only)]
    if limit is not None: todo = todo[:limit]
    spend_check(cfg, a, prov_name, model, len(todo))
    if not todo: print("nothing to generate - every scene already has its image"); return 0
    try: provider = make_provider(prov_name, cfg, model, a.get("max_images"))
    except Fail as e: die(str(e))
    stats = {"generated": 0, "failed": 0, "stopped": False}
    for sc, req, key in todo:
        n = sc["scene"]; e = m["scenes"].get(str(n))
        ver = (e.get("version", 1) + 1) if e and e.get("status") in STATUS_DONE else (e.get("version", 1) if e else 1)
        rec = {"scene": n, "file": image_name(n, ver), "version": ver, "prompt": req["prompt"], "negative": req["negative"],
               "script_line": sc.get("script_line", ""), "start_line": sc.get("start_line"), "provider": pname, "key": key,
               "label": LABEL, "licence": LICENCE,
               "history": (e or {}).get("history", []) + ([{k: e.get(k) for k in ("file", "prompt", "status", "approved_at")}]
                                                          if e and e.get("status") in STATUS_DONE else [])}
        print(f"scene {n:03d}: generating with {pname} ...", flush=True)
        t0 = time.monotonic()
        try:
            raw, seed = provider.generate(req)
            w, h = save_png(raw, paths(p)["images"] / rec["file"], (req["width"], req["height"]))
            rec.update(status="done", seed=seed, width=w, height=h, seconds=round(time.monotonic() - t0, 1), created=now(), error=None)
            stats["generated"] += 1; print(f"scene {n:03d}: ok -> visuals/images/{rec['file']}")
        except Fail as err:
            rec.update(status="failed", error=str(err), created=now())
            if e and e.get("status") in STATUS_DONE: rec["file"] = e["file"]
            stats["failed"] += 1; print(f"scene {n:03d}: FAILED: {err}")
            m["scenes"][str(n)] = rec; save_manifest(p, m)
            if err.fatal:
                stats["stopped"] = True; print("stopping the batch - the provider refused or is unreachable; not asking again"); break
            continue
        m["scenes"][str(n)] = rec; save_manifest(p, m)
    m["last_run"] = {"at": now(), "provider": pname, **stats}; save_manifest(p, m)
    print(json.dumps(stats)); write_sheet(p)
    return 1 if stats["failed"] else 0


def write_sheet(p):
    m = load_manifest(p); rv = load_review(p)
    cards = []
    for k in sorted(m["scenes"], key=int):
        e = m["scenes"][k]; r = rv.get(int(k), {})
        img = (f'<img src="images/{html.escape(e["file"])}" alt="scene {k}">' if e.get("status") in STATUS_DONE else
               f'<div class="none">{html.escape(e.get("status", ""))}: {html.escape(str(e.get("error") or ""))}</div>')
        verdict = (f'<br><b class="{html.escape(r.get("verdict", ""))}">review: {html.escape(r.get("verdict", ""))}</b> '
                   f'{html.escape("; ".join(r.get("problems", [])))}' if r else "")
        cards.append(f'<figure>{img}<figcaption><b>scene {int(k):03d}</b> [{html.escape(e.get("status", ""))}] {LABEL}{verdict}<br>'
                     f'<i>{html.escape(e.get("script_line", ""))}</i><br><small>{html.escape(e["prompt"])}</small></figcaption></figure>')
    page = ("<!doctype html><meta charset=utf-8><title>Contact sheet</title><style>body{font:14px sans-serif;margin:20px}"
            "figure{display:inline-block;width:380px;vertical-align:top;margin:8px}img{width:100%}.none{padding:40px;background:#eee}"
            ".redo{color:#b00}.ok{color:#070}</style><h1>Scene images - for your approval</h1>"
            "<p>AI-generated illustrations, not photographs or archival images.</p>" + "".join(cards))
    atomic_write(paths(p)["sheet"], page)
    return paths(p)["sheet"]


def load_review(p):
    f = paths(p)["review"]
    if not f.is_file(): return {}
    try: d = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError: return {}
    return {r["scene"]: r for r in d.get("scenes", []) if isinstance(r, dict) and isinstance(r.get("scene"), int)}


def cmd_approve(p, scenes, statement):
    if not statement or len(statement.strip()) < 2: die("approval needs the creator's own words: --statement \"...\"")
    m = load_manifest(p); rv = load_review(p); n = 0
    for k, e in m["scenes"].items():
        if (scenes is None or int(k) in scenes) and e.get("status") == "done":
            if rv.get(int(k), {}).get("verdict") == "redo":
                print(f"note: scene {int(k):03d} was marked redo by the image review - approved anyway on the creator's word")
            e.update(status="approved", approved_at=now(), approval_statement=statement.strip()); n += 1
    save_manifest(p, m); write_sheet(p)
    print(f"approved {n} scene(s)")


def cmd_plan(p):
    """visuals/plan.json for render.py. Approved images, designed title cards, and placeholder cards for the rest.
    The previous plan is kept as plan.json.bak-<time>."""
    data = load_prompts(p); m = load_manifest(p); P = paths(p)
    missing = [s["scene"] for s in data["scenes"] if not isinstance(s.get("start_line"), int)]
    if missing: die(f"scenes without start_line (narration line from render.py --list-lines): {missing}")
    entries = []
    for sc in sorted(data["scenes"], key=lambda s: s["start_line"]):
        card = str(sc.get("card") or sc.get("script_line") or f"Scene {sc['scene']}")[:70]
        e = m["scenes"].get(str(sc["scene"]), {})
        base = {"start_line": sc["start_line"], "scene": sc["scene"], "card": card}
        if sc.get("motion"): base["motion"] = sc["motion"]
        if sc.get("kind") == "title":
            entries.append({**base, "kind": "title", "image": None, **({"subtitle": sc["subtitle"]} if sc.get("subtitle") else {})})
        elif e.get("status") == "approved" and (P["images"] / e["file"]).is_file():
            entries.append({**base, "image": f"visuals/images/{e['file']}", "licence": f"{LICENCE} ({e['provider']})",
                            "attribution": "", "source_url": ""})
        else:
            entries.append({**base, "image": None})
    starts = [e["start_line"] for e in entries]
    if starts[0] != 0: die("the first scene must have start_line 0")
    if len(set(starts)) != len(starts): die("two scenes share a start_line - each needs its own narration line")
    if P["plan"].exists():
        bak = P["plan"].with_name(f"plan.json.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        os.replace(P["plan"], bak); print(f"kept the previous plan as {bak.name}")
    atomic_write(P["plan"], json.dumps(entries, indent=1, ensure_ascii=False) + "\n")
    ph = sum(1 for e in entries if not e["image"] and e.get("kind") != "title")
    print(f"wrote {P['plan']} ({len(entries)} segments, {ph} placeholder card(s))")


def cmd_thumb(p, a):
    words = (a.get("text") or "").split()
    if not 1 <= len(words) <= 3: die("--text needs 1 to 3 words (/yt-package: a fourth word is unreadable at feed size)")
    cfg = load_cfg(p); out = Path(p) / "package"; out.mkdir(exist_ok=True)
    bg = out / "thumbnail-bg.png"; meta = {"text": " ".join(words), "label": LABEL, "created": now()}
    if a.get("from_scene"):
        e = load_manifest(p)["scenes"].get(str(a["from_scene"]), {})
        src = paths(p)["images"] / e.get("file", "-")
        if e.get("status") not in STATUS_DONE or not src.is_file(): die(f"scene {a['from_scene']} has no image yet")
        shutil.copyfile(src, bg); meta.update(source=f"scene {a['from_scene']}", prompt=e["prompt"], provider=e["provider"])
    else:
        if not a.get("prompt"): die("give --prompt (what the thumbnail shows, no text) or --from-scene N")
        data = json.loads(paths(p)["prompts"].read_text()) if paths(p)["prompts"].is_file() else {}
        prompt = ". ".join(x for x in (data.get("style", ""), a["prompt"], "bold simple composition, one clear subject, "
                                       "strong contrast, empty space on one side for large text") if x)
        prov_name = a.get("provider") or cfg["provider"]
        spend_check(cfg, a, prov_name, a.get("model"), 1)
        try:
            raw, _ = make_provider(prov_name, cfg, a.get("model"), 1).generate(
                {"prompt": prompt, "negative": "text, letters, words, watermark, logo", "width": 1280, "height": 720, "seed": -1})
            save_png(raw, bg, (16, 9))
        except Fail as e: die(str(e))
        meta.update(source="generated", prompt=prompt, provider=prov_name if prov_name != "openlux" else f"openlux:{a.get('model') or cfg['model']}")
    font = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                             "/Library/Fonts/Arial Bold.ttf") if Path(f).is_file()), None)
    with tempfile.TemporaryDirectory() as td:
        text = " ".join(words).upper()
        lines = [text] if len(text) <= 12 else [" ".join(words[:2]).upper(), " ".join(words[2:]).upper()] if len(words) == 3 \
            else [words[0].upper(), " ".join(words[1:]).upper()]
        lines = [l for l in lines if l]
        tf = Path(td) / "t.txt"; tf.write_text("\n".join(lines))
        fs = int(min(720 / 5.5, 1280 * 0.6 / (0.62 * max(len(l) for l in lines)), 720 * 0.7 / (1.15 * len(lines))))
        side = "w-text_w-w*0.06" if (a.get("side") or "left") == "right" else "w*0.06"
        draw = (f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
                f"drawtext={'fontfile=' + font + ':' if font else ''}textfile='{tf}':fontsize={fs}:line_spacing={fs // 8}:fontcolor=white:"
                f"borderw=10:bordercolor=black:x={side}:y=(h-text_h)/2")
        res = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bg), "-vf", draw, "-frames:v", "1",
                              str(out / "thumbnail.png")], capture_output=True, text=True)
        if res.returncode: die(f"ffmpeg failed: {res.stderr.strip()[:300]}")
    atomic_write(out / "thumbnail.json", json.dumps(meta, indent=1) + "\n")
    print(f"wrote {out / 'thumbnail.png'} (1280x720, text: {' '.join(words).upper()})")


def cmd_import(p, files):
    data = load_prompts(p); m = load_manifest(p); w, h = data.get("size", [1920, 1080])
    scenes = [s for s in sorted(data["scenes"], key=lambda s: s["scene"]) if s.get("kind") != "title"]
    todo = [s["scene"] for s in scenes if m["scenes"].get(str(s["scene"]), {}).get("status") not in STATUS_DONE]
    n_ok = 0
    for f in map(Path, files):
        mt = re.search(r"scene[_-]?(\d+)", f.name, re.I)
        n = int(mt.group(1)) if mt else (todo.pop(0) if todo else None)
        sc = next((s for s in scenes if s["scene"] == n), None)
        if sc is None: print(f"skip {f.name}: no scene to match"); continue
        if m["scenes"].get(str(n), {}).get("status") in STATUS_DONE: print(f"skip {f.name}: scene {n} already has an image"); continue
        try: iw, ih = save_png(f.read_bytes(), paths(p)["images"] / image_name(n, 1), (w, h))
        except (OSError, Fail) as e: print(f"skip {f.name}: {e}"); continue
        m["scenes"][str(n)] = {"scene": n, "file": image_name(n, 1), "version": 1, "prompt": full_prompt(data, sc),
                               "negative": data.get("negative", ""), "script_line": sc.get("script_line", ""),
                               "start_line": sc.get("start_line"), "provider": "creator-import", "key": "import",
                               "width": iw, "height": ih, "status": "done", "label": LABEL, "licence": LICENCE,
                               "created": now(), "error": None, "history": []}
        save_manifest(p, m); n_ok += 1; print(f"scene {n:03d}: imported {f.name}")
    write_sheet(p)
    return 0 if n_ok else 1


def parse_scenes(spec):
    if not spec or spec.strip().lower() == "all": return None
    out = set()
    for part in spec.split(","):
        x, _, y = part.strip().partition("-"); out.update(range(int(x), int(y or x) + 1))
    return out


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ("-h", "--help"): print(__doc__); sys.exit(0 if not a else 2)
    cmd, p = a[0], Path(a[1]).expanduser()
    rest = a[2:]
    def opt(flag, cast=str):
        if flag not in rest: return None
        i = rest.index(flag)
        if i + 1 >= len(rest): die(f"{flag} needs a value")
        try: return cast(rest[i + 1])
        except ValueError: die(f"{flag}: bad value {rest[i + 1]!r}")
    o = {"provider": opt("--provider"), "model": opt("--model"), "limit": opt("--limit", int),
         "max_spend": opt("--max-spend", float), "max_images": opt("--max-images", int),
         "scenes": parse_scenes(opt("--scenes")), "text": opt("--text"), "prompt": opt("--prompt"),
         "from_scene": opt("--from-scene", int), "side": opt("--side")}
    if not p.is_dir(): die(f"{p} is not a project folder")
    if cmd == "init":
        style = opt("--style") or "natural"; f = STYLES / f"{style}.json"
        if not f.is_file(): die(f"no style {style!r}; have: {', '.join(x.stem for x in sorted(STYLES.glob('*.json')))}")
        if paths(p)["prompts"].exists(): die(f"{paths(p)['prompts']} exists - not overwriting it", 1)
        atomic_write(paths(p)["prompts"], f.read_text()); print(f"wrote {paths(p)['prompts']} (style: {style})")
    elif cmd == "check":
        data = load_prompts(p)
        for sc in sorted(data["scenes"], key=lambda s: s["scene"]):
            what = f"TITLE CARD: {sc['card']}" if sc.get("kind") == "title" else full_prompt(data, sc)[:140]
            print(f"scene {sc['scene']:03d} line {sc.get('start_line', '?')}: {what}")
        n = sum(1 for s in data["scenes"] if s.get("kind") != "title"); cfg = load_cfg(p)
        est = estimate(cfg, cfg["model"], n)
        print(f"\n{n} image(s) to generate" + (f", about {est:.2f} with {cfg['model']}" if est is not None else ""))
    elif cmd in ("generate", "retry"): sys.exit(cmd_generate(p, o, retry_only=cmd == "retry"))
    elif cmd == "sheet": print(write_sheet(p))
    elif cmd == "approve": cmd_approve(p, o["scenes"], opt("--statement"))
    elif cmd == "plan": cmd_plan(p)
    elif cmd == "thumb": cmd_thumb(p, o)
    elif cmd == "import": sys.exit(cmd_import(p, rest))
    elif cmd == "status":
        m = load_manifest(p); rv = load_review(p)
        for k in sorted(m["scenes"], key=int):
            e = m["scenes"][k]; r = rv.get(int(k), {}).get("verdict", "")
            print(f"scene {int(k):03d} {e['status']:9} {e['file']:22} {('review: ' + r) if r else ''} {e.get('error') or ''}")
        if not m["scenes"]: print("no images yet")
    else: die(f"unknown command {cmd!r}\n\n{__doc__}")


if __name__ == "__main__":
    main()
