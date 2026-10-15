#!/usr/bin/env python3
"""Tests for state.py and qa.py. Standard library only, no network.

    python3 skills/yt-produce/tests/test_produce.py -v
"""
import json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
STATE, QA = SKILL / "state.py", SKILL / "qa.py"
SECRET = "ZEBRA-SENTINEL-voice-line"   # must never leak out of the voice file

VOICE_OK = f"""# voice.md
## Who I am talking to
History fans who want the real story. {SECRET}
## How I actually talk
Plain, short sentences. I ask questions and answer them. I like a date and a name.
## Words I never use
"dive in", "game-changer", "unlock"
## Words I do use
"here's the thing"
## What I will not claim
Numbers without a source.
## My format
Ten to fifteen minutes, narrated, maps.
"""

HOOKS = """You've been told one giant cannon broke the walls of Constantinople in 1453. It didn't, and the real reason cost the city everything.
On the morning of May 29, 1453, a city that had survived sieges since the fifth century fell in a single day. Why did it finally break?
The great land walls of Constantinople had stopped army after army for a thousand years. In 1453, they didn't. What changed?
Before the Ottomans ever reached the walls, one engineer had already left the Byzantines. He went to the sultan instead.
Two months of siege, and the city was still standing. Then, according to some accounts, a gate was found open. Was it?
For about a thousand years, the walls had held, and in 1453 a twenty-one-year-old sultan brought a cannon big enough to test them.
"""
TITLES = "Why the Walls of Constantinople Fell in 1453\nThe Day Constantinople Fell\nHow a Cannon Ended Byzantium\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "productions"
        self.voice = Path(self.tmp.name) / "voice.md"
        self.env = {**os.environ, "YT_PRODUCTIONS_DIR": str(self.root), "YT_VOICE_FILE": str(self.voice)}

    def tearDown(self): self.tmp.cleanup()

    def run_py(self, script, *args, ok=True):
        r = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, env=self.env, timeout=60)
        if ok is True: self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        if ok is False: self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def st(self, *a, ok=True): return self.run_py(STATE, *a, ok=ok)

    def new(self, topic="The fall of Constantinople", minutes="1"):
        return Path(self.st("new", topic, "--minutes", minutes).stdout.strip())

    def data(self, p): return json.loads((p / "project.json").read_text())

    def w(self, p, rel, text):
        f = p / rel; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text); return f

    def web_ok(self, p):
        self.st("capability", p.name, "web_research", "available", "--note", "test: WebSearch+WebFetch ok")

    def sources(self, p):
        self.w(p, "research/sources.json", json.dumps([
            {"id": "S1", "title": "Fall of Constantinople", "publisher": "Example Encyclopedia",
             "url": "https://example.org/fall", "retrieved": "2026-10-16", "accessed_via": "web_fetch",
             "tier": "scholarly", "quote": "The city fell on 29 May 1453."},
            {"id": "S2", "title": "Siege notes", "citation": "Creator's own copy of a book, p. 12",
             "retrieved": "2026-10-16", "accessed_via": "user_provided", "tier": "secondary",
             "quote": "The siege lasted from April to May."}]))
        self.w(p, "research/sources.md", "S1, S2\n")

    def claims(self, p, status="supported", checker="yt-fact-checker"):
        self.w(p, "factcheck/claims.json", json.dumps({"checked_by": checker, "checked_at": "2026-10-16",
            "claims": [{"id": "C1", "text": "The city fell on 29 May 1453.", "status": status, "sources": ["S1"],
                        "note": "hedged" if status != "supported" else ""}]}))
        self.w(p, "factcheck/claims.md", "1 supported\n")

    def complete(self, p, narration_words=150):
        """Drive a project through every pre-production stage up to qa."""
        self.voice.write_text(VOICE_OK)
        self.w(p, "brief.md", "brief\n"); self.st("set", p.name, "intake", "done")
        self.st("check-tools", p.name); self.web_ok(p); self.st("set", p.name, "tools", "done")
        self.w(p, "research/notes.md", "notes\n"); self.st("set", p.name, "research", "done")
        self.sources(p); self.st("set", p.name, "sources", "done")
        self.w(p, "outline.md", "outline\n"); self.st("set", p.name, "outline", "done")
        self.w(p, "hooks/hooks.txt", HOOKS)
        out = self.run_py(SKILL.parent / "yt-script" / "hookscore.py", "--json", str(p / "hooks/hooks.txt")).stdout
        self.w(p, "hooks/hookscore.json", out)
        self.w(p, "hooks/chosen.txt", HOOKS.splitlines()[0] + "\n")
        self.st("set", p.name, "hooks", "done", "--cmd", "hookscore.py --json hooks/hooks.txt", "--exit", "0")
        self.w(p, "script/script.md", "The city fell {C1}. [ON SCREEN: map]\n"); time.sleep(1.1)
        self.st("set", p.name, "script", "done")
        self.claims(p); self.st("set", p.name, "factcheck", "done")
        self.w(p, "package/titles.txt", TITLES)
        out = self.run_py(SKILL.parent / "yt-package" / "title.py", "--json", str(p / "package/titles.txt")).stdout
        self.w(p, "package/title-lint.json", out)
        self.w(p, "package/chosen-title.txt", TITLES.splitlines()[0])
        self.w(p, "package/chosen-thumb.txt", "THEY BROKE")
        self.w(p, "package/thumbnail-brief.md", "brief\n"); self.st("set", p.name, "package", "done")
        self.w(p, "visuals/shotlist.md", "x\n"); self.w(p, "visuals/assets.md", "x\n"); self.st("set", p.name, "visuals", "done")
        self.w(p, "narration/narration.md", "# Narration\n" + ("word " * narration_words) + "\n")
        self.w(p, "narration/pronunciation.md", "Mehmed - MEH-med\n"); self.st("set", p.name, "narration", "done")
        self.w(p, "seo/description.md", "Why the walls fell.\nSource: https://example.org/fall\n")
        self.w(p, "seo/tags.txt", "constantinople\n")
        self.w(p, "seo/chapters-provisional.txt", "PROVISIONAL\n00:00 The walls\n00:20 The cannon\n00:40 The fall\n")
        self.st("set", p.name, "seo", "done")


class TestState(Base):
    def test_new_creates_folder_and_files(self):
        p = self.new()
        self.assertTrue(p.name.endswith("-the-fall-of-constantinople"))
        self.assertTrue((p / "STATUS.md").exists())
        self.assertTrue(all(s["status"] == "pending" for s in self.data(p)["stages"].values()))
        self.assertEqual(p.parent, self.root)

    def test_duplicate_project_refused(self):
        self.new(); self.st("new", "The fall of Constantinople", ok=False)

    def test_missing_voice_marks_intake_needs_input(self):
        p = self.new(); self.st("check-tools", p.name)
        s = self.data(p)["stages"]["intake"]
        self.assertEqual(s["status"], "needs_input"); self.assertIn("missing", s["notes"][-1])

    def test_template_voice_marks_intake_needs_input(self):
        # Self-contained: the repo's templates/ folder is not copied when the skill is installed.
        tpl = ("# voice.md\n\nCopy this to `~/.claude/youtube/voice.md` and fill it in.\n\n"
               "## How I actually talk\n\nPaste the transcript of your best-performing video here, "
               "or three of them. Not what you wish you sounded like.\n") * 3
        self.voice.write_text(tpl); p = self.new(); self.st("check-tools", p.name)
        self.assertEqual(self.data(p)["stages"]["intake"]["status"], "needs_input")
        self.assertIn("template", self.data(p)["capabilities"]["voice_profile"]["detail"])

    def test_filled_voice_ok_and_contents_never_leak(self):
        self.voice.write_text(VOICE_OK); p = self.new()
        out = self.st("check-tools", p.name).stdout
        self.assertEqual(self.data(p)["stages"]["intake"]["status"], "pending")
        for f in p.rglob("*"):
            if f.is_file(): self.assertNotIn(SECRET, f.read_text(errors="replace"), f)
        self.assertNotIn(SECRET, out)

    def test_done_refused_without_outputs(self):
        p = self.new(); r = self.st("set", p.name, "intake", "done", ok=False)
        self.assertIn("brief.md", r.stderr)

    def test_done_refused_after_failed_command(self):
        p = self.new(); self.w(p, "brief.md", "x")
        self.st("set", p.name, "intake", "done", "--cmd", "something", "--exit", "1", ok=False)

    def test_retry_after_in_progress_clears_old_failure(self):
        p = self.new(); self.w(p, "brief.md", "x")
        self.st("set", p.name, "intake", "needs_input", "--cmd", "x", "--exit", "1", "--note", "failed")
        time.sleep(1.1); self.st("set", p.name, "intake", "in_progress")
        self.st("set", p.name, "intake", "done", "--cmd", "x", "--exit", "0")

    def test_unavailable_needs_a_reason(self):
        p = self.new()
        self.st("set", p.name, "visuals", "unavailable", ok=False)
        self.st("set", p.name, "visuals", "unavailable", "--note", "no image tool")

    def test_tools_done_refused_until_web_verified(self):
        self.voice.write_text(VOICE_OK); p = self.new(); self.w(p, "brief.md", "x")
        self.st("set", p.name, "intake", "done")
        self.st("set", p.name, "tools", "done", ok=False)          # check-tools not run
        self.st("check-tools", p.name)
        r = self.st("set", p.name, "tools", "done", ok=False)       # web unverified
        self.assertIn("web_research", r.stderr)
        self.web_ok(p); self.st("set", p.name, "tools", "done")

    def test_next_reports_blockers(self):
        p = self.new(); self.st("check-tools", p.name)
        nxt = json.loads(self.st("next", p.name).stdout)
        self.assertEqual(nxt["stage"], "intake"); self.assertIn("needs input", nxt["reason"])

    def test_unavailable_stage_blocks_dependents_honestly(self):
        self.voice.write_text(VOICE_OK); p = self.new(); self.w(p, "brief.md", "x")
        self.st("set", p.name, "intake", "done")
        self.st("set", p.name, "tools", "unavailable", "--note", "test")
        nxt = json.loads(self.st("next", p.name).stdout)
        self.assertEqual(nxt["stage"], "research"); self.assertIn("blocked", nxt["reason"])

    def test_resolve_by_slug_and_latest(self):
        p = self.new()
        self.assertIn(p.name, self.st("status", "fall-of-constantinople").stdout)
        self.assertIn(p.name, self.st("status").stdout)


class TestGates(Base):
    def test_sources_gate(self):
        p = self.new(); self.sources(p)
        self.run_py(QA, p.name, "--gate", "sources")
        bad = json.loads((p / "research/sources.json").read_text()); del bad[0]["url"]
        self.w(p, "research/sources.json", json.dumps(bad))
        r = self.run_py(QA, p.name, "--gate", "sources", ok=False); self.assertIn("url", r.stdout)

    def test_sources_gate_needs_quote(self):
        p = self.new(); self.sources(p)
        bad = json.loads((p / "research/sources.json").read_text()); bad[1]["quote"] = ""
        self.w(p, "research/sources.json", json.dumps(bad))
        self.run_py(QA, p.name, "--gate", "sources", ok=False)

    def test_factcheck_rejects_unsupported(self):
        p = self.new(); self.sources(p); self.w(p, "script/script.md", "x"); time.sleep(1.1)
        self.claims(p, status="unsupported")
        r = self.run_py(QA, p.name, "--gate", "factcheck", ok=False); self.assertIn("UNSUPPORTED", r.stdout)

    def test_factcheck_rejects_self_check(self):
        p = self.new(); self.sources(p); self.w(p, "script/script.md", "x"); time.sleep(1.1)
        self.claims(p, checker="me")
        self.run_py(QA, p.name, "--gate", "factcheck", ok=False)

    def test_factcheck_rejects_unknown_source(self):
        p = self.new(); self.sources(p); self.w(p, "script/script.md", "x"); time.sleep(1.1)
        self.claims(p); c = json.loads((p / "factcheck/claims.json").read_text())
        c["claims"][0]["sources"] = ["S99"]; self.w(p, "factcheck/claims.json", json.dumps(c))
        self.run_py(QA, p.name, "--gate", "factcheck", ok=False)

    def test_factcheck_stale_after_script_edit(self):
        p = self.new(); self.sources(p); self.w(p, "script/script.md", "x"); time.sleep(1.1)
        self.claims(p); self.run_py(QA, p.name, "--gate", "factcheck")
        time.sleep(1.1); self.w(p, "script/script.md", "edited")
        r = self.run_py(QA, p.name, "--gate", "factcheck", ok=False); self.assertIn("re-run", r.stdout)


class TestFullRun(Base):
    def test_complete_project_passes_and_handoff_needs_explicit_approval(self):
        p = self.new(); self.complete(p)
        r = self.run_py(QA, p.name); self.assertIn("PASS", r.stdout)
        self.st("set", p.name, "handoff", "awaiting_approval", ok=False)   # qa stage not marked done yet
        self.st("set", p.name, "qa", "done")
        self.st("set", p.name, "handoff", "approved", "--user-statement", "yes", ok=False)  # not awaiting
        self.w(p, "publish/upload-pack.md", "NOT UPLOADED.\n")
        self.st("set", p.name, "handoff", "awaiting_approval")
        self.assertIn("approval", json.loads(self.st("next", p.name).stdout)["reason"])
        self.st("set", p.name, "handoff", "approved", ok=False)            # no user statement
        self.st("set", p.name, "handoff", "approved", "--user-statement", "Approved, ship it")
        d = self.data(p); self.assertEqual(d["approval"]["user_statement"], "Approved, ship it")
        self.assertIn("uploaded, scheduled or published by /yt-produce", (p / "STATUS.md").read_text())

    def test_placeholder_fails(self):
        p = self.new(); self.complete(p)
        self.w(p, "seo/description.md", "Why the walls fell. TODO add link\n")
        r = self.run_py(QA, p.name, ok=False); self.assertIn("TODO", r.stdout)
        self.st("set", p.name, "qa", "done", ok=False)

    def test_banned_word_fails_without_printing_voice(self):
        p = self.new(); self.complete(p)
        self.w(p, "narration/narration.md", "Let's dive in. " + "word " * 148)
        r = self.run_py(QA, p.name, ok=False)
        self.assertIn("'dive in'", r.stdout); self.assertNotIn(SECRET, r.stdout)
        self.assertNotIn(SECRET, (p / "qa/report.md").read_text())

    def test_weak_hook_fails(self):
        p = self.new(); self.complete(p)
        self.w(p, "hooks/hooks.txt", HOOKS + "hey guys welcome back to the channel\n")
        self.w(p, "hooks/chosen.txt", "hey guys welcome back to the channel\n")
        r = self.run_py(QA, p.name, ok=False); self.assertIn("WEAK", r.stdout)

    def test_weak_hook_kept_with_creator_reason_is_warning(self):
        p = self.new(); self.complete(p)
        weak = HOOKS.splitlines()[1]
        self.w(p, "hooks/chosen.txt", weak + "\n")
        self.w(p, "hooks/override.txt", "Narrated history; I prefer the date-first open.\n")
        r = self.run_py(QA, p.name); self.assertRegex(r.stdout, r"WARN\s+hook score.*kept by the creator")

    def test_runtime_warning(self):
        p = self.new(minutes="10"); self.complete(p)
        r = self.run_py(QA, p.name); self.assertRegex(r.stdout, r"WARN\s+runtime")

    def test_reviewer_notes_survive_rerun(self):
        p = self.new(); self.complete(p); self.run_py(QA, p.name)
        rp = p / "qa/report.md"; rp.write_text(rp.read_text() + "\n## Reviewer notes\nkeep me\n")
        self.run_py(QA, p.name); self.assertIn("keep me", rp.read_text())

    def test_unavailable_stage_is_reported_not_hidden(self):
        p = self.new(); self.complete(p)
        d = self.data(p); d["stages"]["visuals"]["status"] = "unavailable"
        d["stages"]["visuals"]["notes"].append("no image tool"); (p / "project.json").write_text(json.dumps(d))
        r = self.run_py(QA, p.name); self.assertIn("unavailable: no image tool", r.stdout)

    def test_bad_provisional_chapters_block_seo(self):
        p = self.new(); self.complete(p)
        self.w(p, "seo/chapters-provisional.txt", "00:05 a\n00:20 b\n")
        self.run_py(QA, p.name, "--gate", "seo", ok=False)


class TestSafety(unittest.TestCase):
    def test_no_upload_or_network_code(self):
        src = "".join((SKILL / f).read_text() for f in ("state.py", "qa.py"))
        for bad in ("urllib", "requests", "http.client", "socket", "googleapiclient", "youtube.upload",
                    "ANTHROPIC_API_KEY", "api_key"):
            self.assertNotIn(bad, src, bad)

    def test_no_reference_to_yt_project(self):
        for f in SKILL.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".py") and f.name != "test_produce.py":
                self.assertNotIn("~/yt/", f.read_text(), f)


if __name__ == "__main__":
    unittest.main()
