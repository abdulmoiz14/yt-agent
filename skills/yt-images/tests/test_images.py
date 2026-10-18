#!/usr/bin/env python3
"""Tests for images.py. Standard library + ffmpeg, no network (the OpenLux client is driven with fakes).

    python3 skills/yt-images/tests/test_images.py -v
"""
import base64, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
IMAGES = HERE / "images.py"
sys.path.insert(0, str(HERE))
import images  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def png(w=64, h=48):
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "x.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=red:s={w}x{h}", "-frames:v", "1", str(f)], check=True)
        return f.read_bytes()


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg")
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = Path(self.tmp.name) / "proj"; self.p.mkdir()

    def tearDown(self): self.tmp.cleanup()

    def run_py(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(IMAGES), *args], capture_output=True, text=True, timeout=120)
        if ok is True: self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        if ok is False: self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def prompts(self, n=3, **extra):
        if not (self.p / "visuals/prompts.json").exists(): self.run_py("init", str(self.p), "--style", "comic")
        d = json.loads((self.p / "visuals/prompts.json").read_text())
        d["characters"] = {"Marcus": "a Roman legionary with a red tunic and a bronze helmet"}
        d["scenes"] = [{"scene": i, "start_line": (i - 1) * 2, "prompt": f"scene {i}", "script_line": f"line {i}",
                        "characters": ["Marcus"] if i == 2 else []} for i in range(1, n + 1)]
        d.update(extra)
        (self.p / "visuals/prompts.json").write_text(json.dumps(d))
        return d

    def manifest(self): return json.loads((self.p / "visuals/manifest.json").read_text())


class TestPrompts(Base):
    def test_init_never_overwrites_and_rejects_unknown_style(self):
        self.run_py("init", str(self.p), "--style", "natural")
        self.assertIn("Painterly", (self.p / "visuals/prompts.json").read_text())
        self.run_py("init", str(self.p), "--style", "natural", ok=False)
        q = Path(self.tmp.name) / "q"; q.mkdir()
        self.assertIn("no style", self.run_py("init", str(q), "--style", "nope", ok=False).stderr)

    def test_check_refuses_empty_and_undefined_character(self):
        self.run_py("init", str(self.p))
        self.assertIn("non-empty list", self.run_py("check", str(self.p), ok=False).stderr)
        d = self.prompts(); d["scenes"][0]["characters"] = ["Nobody"]
        (self.p / "visuals/prompts.json").write_text(json.dumps(d))
        self.assertIn("not defined", self.run_py("check", str(self.p), ok=False).stderr)

    def test_full_prompt_puts_style_and_character_first(self):
        d = self.prompts()
        fp = images.full_prompt(d, d["scenes"][1])
        self.assertTrue(fp.startswith("Hand-drawn webcomic")); self.assertIn("Marcus: a Roman legionary", fp)
        self.assertIn("about", self.run_py("check", str(self.p)).stdout)


class TestGenerate(Base):
    def test_first_run_needs_limit_then_names_manifest_and_crop(self):
        self.prompts()
        self.assertIn("--limit", self.run_py("generate", str(self.p), "--provider", "fake", ok=False).stderr)
        self.run_py("generate", str(self.p), "--provider", "fake", "--limit", "3")
        for i in (1, 2, 3):
            f = self.p / f"visuals/images/scene_{i:03d}.png"
            self.assertTrue(f.is_file()); self.assertEqual(images.probe(f), (1536, 864))     # 1536x1024 cropped to 16:9
        e = self.manifest()["scenes"]["2"]
        self.assertEqual((e["status"], e["label"]), ("done", "AI illustration")); self.assertIn("Marcus:", e["prompt"])
        self.assertIn("scene 002", (self.p / "visuals/contact-sheet.html").read_text())

    def test_no_duplicates_and_changed_prompt_makes_new_version(self):
        d = self.prompts(1)
        self.run_py("generate", str(self.p), "--provider", "fake", "--limit", "1")
        self.assertIn("nothing to generate", self.run_py("generate", str(self.p), "--provider", "fake").stdout)
        d["scenes"][0]["prompt"] = "a different scene"; (self.p / "visuals/prompts.json").write_text(json.dumps(d))
        self.run_py("generate", str(self.p), "--provider", "fake")
        self.assertEqual(sorted(x.name for x in (self.p / "visuals/images").iterdir()), ["scene_001.png", "scene_001.v2.png"])
        self.assertEqual(len(self.manifest()["scenes"]["1"]["history"]), 1)

    def test_title_cards_are_not_generated(self):
        d = self.prompts(2); d["scenes"].append({"scene": 3, "start_line": 5, "kind": "title", "card": "753 BC", "subtitle": "Rome is founded"})
        (self.p / "visuals/prompts.json").write_text(json.dumps(d))
        self.run_py("generate", str(self.p), "--provider", "fake", "--limit", "5")
        self.assertNotIn("3", self.manifest()["scenes"])

    def test_paid_provider_needs_max_spend_and_respects_it(self):
        self.prompts(3)
        r = self.run_py("generate", str(self.p), "--limit", "3", ok=False)       # default provider is openlux
        self.assertIn("estimated 0.026", r.stdout); self.assertIn("--max-spend", r.stderr)
        self.assertIn("above --max-spend", self.run_py("generate", str(self.p), "--limit", "3", "--max-spend", "0.01", ok=False).stderr)
        self.assertIn("no price known", self.run_py("generate", str(self.p), "--model", "mystery", "--limit", "1",
                                                   "--max-spend", "9", ok=False).stderr)
        self.assertFalse((self.p / "visuals/manifest.json").exists())        # nothing sent, nothing recorded


class TestReviewApprovePlan(Base):
    def setUp(self):
        super().setUp(); self.prompts(3)
        self.run_py("generate", str(self.p), "--provider", "fake", "--limit", "3")

    def test_approval_needs_words_and_review_shows_on_sheet(self):
        self.run_py("approve", str(self.p), "--scenes", "1", ok=False)
        (self.p / "visuals/review.json").write_text(json.dumps({"checked_by": "yt-image-reviewer", "scenes": [
            {"scene": 1, "verdict": "ok", "problems": []}, {"scene": 2, "verdict": "redo", "problems": ["six fingers"]}]}))
        out = self.run_py("approve", str(self.p), "--scenes", "1-2", "--statement", "these work").stdout
        self.assertIn("marked redo", out); self.assertIn("approved 2", out)
        self.assertIn("six fingers", (self.p / "visuals/contact-sheet.html").read_text())
        self.assertEqual(self.manifest()["scenes"]["1"]["approval_statement"], "these work")

    def test_plan_uses_only_approved_images_and_title_cards(self):
        d = json.loads((self.p / "visuals/prompts.json").read_text())
        d["scenes"].append({"scene": 4, "start_line": 7, "kind": "title", "card": "44 BC", "subtitle": "The Ides of March"})
        d["scenes"][2]["card"] = "The Senate"; (self.p / "visuals/prompts.json").write_text(json.dumps(d))
        self.run_py("approve", str(self.p), "--scenes", "1,2", "--statement", "ok")
        self.run_py("plan", str(self.p))
        plan = json.loads((self.p / "visuals/plan.json").read_text())
        self.assertEqual([e["start_line"] for e in plan], [0, 2, 4, 7])
        self.assertEqual(plan[0]["image"], "visuals/images/scene_001.png"); self.assertIn("AI illustration", plan[0]["licence"])
        self.assertIsNone(plan[2]["image"]); self.assertEqual(plan[2]["card"], "The Senate")
        self.assertEqual((plan[3]["kind"], plan[3]["subtitle"]), ("title", "The Ides of March"))
        self.run_py("plan", str(self.p))
        self.assertTrue(any(x.name.startswith("plan.json.bak-") for x in (self.p / "visuals").iterdir()))

    def test_plan_errors(self):
        d = json.loads((self.p / "visuals/prompts.json").read_text())
        d["scenes"][0]["start_line"] = 1; (self.p / "visuals/prompts.json").write_text(json.dumps(d))
        self.assertIn("start_line 0", self.run_py("plan", str(self.p), ok=False).stderr)
        del d["scenes"][1]["start_line"]; (self.p / "visuals/prompts.json").write_text(json.dumps(d))
        self.assertIn("without start_line", self.run_py("plan", str(self.p), ok=False).stderr)

    def test_thumbnail_from_scene_text_rules(self):
        self.assertIn("1 to 3 words", self.run_py("thumb", str(self.p), "--text", "one two three four", "--from-scene", "1", ok=False).stderr)
        self.run_py("thumb", str(self.p), "--text", "Rome fell", "--from-scene", "1")
        self.assertEqual(images.probe(self.p / "package/thumbnail.png"), (1280, 720))
        self.assertEqual(json.loads((self.p / "package/thumbnail.json").read_text())["text"], "Rome fell")

    def test_import_by_name(self):
        q = Path(self.tmp.name) / "q"; q.mkdir(); self.p = q; self.prompts(2)
        src = Path(self.tmp.name) / "scene_002.jpg"; src.write_bytes(png(400, 300))
        self.run_py("import", str(q), str(src))
        self.assertEqual(images.probe(q / "visuals/images/scene_002.png"), (400, 224))


class TestOpenLux(unittest.TestCase):
    def setUp(self): self.b64 = base64.b64encode(png()).decode() if HAVE_FFMPEG else ""

    def test_gpt_image_request_shape(self):
        seen = {}
        def post(url, hdr, body, t): seen.update(url=url, hdr=hdr, body=body); return {"data": [{"b64_json": self.b64}]}
        pr = images.OpenLux("gpt-image-2-c", size="1536x1024", key="sk-test", post=post)
        raw, _ = pr.generate({"prompt": "a forum", "negative": "text", "width": 1920, "height": 1080, "seed": -1})
        self.assertTrue(seen["url"].endswith("/v1/images/generations"))
        self.assertEqual((seen["body"]["model"], seen["body"]["size"]), ("gpt-image-2-c", "1536x1024"))
        self.assertIn("Avoid: text", seen["body"]["prompt"]); self.assertEqual(seen["hdr"]["Authorization"], "Bearer sk-test")
        self.assertEqual(pr.name, "openlux:gpt-image-2-c")

    def test_gemini_shape_and_no_image_reason(self):
        seen = {}
        def post(url, hdr, body, t):
            seen.update(url=url, body=body)
            return {"candidates": [{"content": {"parts": [{"inlineData": {"data": self.b64}}]}}]}
        images.OpenLux("gemini-nano-banana-2.1", key="k", post=post).generate({"prompt": "x", "negative": "", "width": 1920, "height": 1080, "seed": -1})
        self.assertTrue(seen["url"].endswith(":generateContent"))
        self.assertEqual(seen["body"]["generationConfig"]["imageConfig"]["aspectRatio"], "16:9")
        pr = images.OpenLux("gemini-nano-banana-2.1", key="k", post=lambda *a: {"candidates": [{"finishReason": "SAFETY"}]})
        with self.assertRaises(images.Fail) as cm: pr.generate({"prompt": "x", "negative": "", "width": 16, "height": 9, "seed": -1})
        self.assertIn("SAFETY", str(cm.exception))

    def test_cap_and_fatal_http_codes(self):
        pr = images.OpenLux("gpt-image-2-c", key="k", max_images=1, post=lambda *a: {"data": [{"b64_json": self.b64}]})
        pr.generate({"prompt": "x", "negative": "", "width": 16, "height": 9, "seed": -1})
        with self.assertRaises(images.Fail) as cm: pr.generate({"prompt": "x", "negative": "", "width": 16, "height": 9, "seed": -1})
        self.assertTrue(cm.exception.fatal)
        import io, urllib.error, urllib.request
        from unittest import mock
        for code, fatal in ((401, True), (402, True), (429, True), (500, False)):
            with mock.patch.object(urllib.request, "urlopen", side_effect=urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"no"))):
                with self.assertRaises(images.Fail) as cm: images.http_post("https://api.openlux.ai/x", {}, {}, 1)
                self.assertEqual(cm.exception.fatal, fatal)

    def test_key_file_must_be_private(self):
        d = Path(tempfile.mkdtemp()); f = d / "k"
        with self.assertRaises(images.Fail): images.read_key(str(f))
        f.write_text("sk-1\n"); os.chmod(f, 0o644)
        with self.assertRaises(images.Fail): images.read_key(str(f))
        os.chmod(f, 0o600); self.assertEqual(images.read_key(str(f)), "sk-1")

    def test_estimates_use_billed_prices(self):
        cfg = images.load_cfg(Path(tempfile.mkdtemp()))
        self.assertEqual(images.estimate(cfg, "gpt-image-2-c", 100), 0.882)
        self.assertEqual(images.estimate(cfg, "qwen-image-3.0", 5), 0.106)
        self.assertIsNone(images.estimate(cfg, "unknown", 1))


class TestSafety(unittest.TestCase):
    def test_no_upload_or_publishing_code_and_key_never_printed(self):
        src = IMAGES.read_text()
        for bad in ("youtube", "googleapis", "upload_video", "print(self.key", "print(key"):
            self.assertNotIn(bad, src.lower() if bad == "youtube" else src, bad)
        self.assertIn("api.openlux.ai", src)


if __name__ == "__main__":
    unittest.main()
