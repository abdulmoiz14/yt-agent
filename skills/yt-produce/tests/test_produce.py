#!/usr/bin/env python3
"""Tests for state.py and qa.py. Standard library only, no network.

    python3 skills/yt-produce/tests/test_produce.py -v
"""
import json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
STATE, QA, QC = SKILL / "state.py", SKILL / "qa.py", SKILL / "quotecheck.py"
PAGE = """<html><head><title>x</title><script>var hidden = "The city fell on 29 May 1453.";</script></head>
<body><nav>menu</nav><p>After a siege of 53 days, the city fell on 29&nbsp;May 1453.[12] Mehmed&rsquo;s
cannon &mdash; built by Orban &mdash; had battered the walls.</p></body></html>"""
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
        self.w(p, "research/pages/S1.html", PAGE)
        self.w(p, "research/sources.json", json.dumps([
            {"id": "S1", "title": "Fall of Constantinople", "publisher": "Example Encyclopedia",
             "url": "https://example.org/fall", "retrieved": "2026-10-16", "accessed_via": "web_fetch",
             "tier": "scholarly", "quote": "the city fell on 29 May 1453.",
             "quote_check": "raw_text_match", "page": "research/pages/S1.html"},
            {"id": "S2", "title": "Siege notes", "citation": "Creator's own copy of a book, p. 12",
             "retrieved": "2026-10-16", "accessed_via": "user_provided", "tier": "secondary",
             "quote": "The siege lasted from April to May.", "quote_check": "user_provided_unchecked"}]))
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

    def _prev(self, p, status, **extra):
        self.claims(p, status=status)
        (p / "factcheck/claims.json").rename(p / "factcheck/claims.prev.json")

    def test_ruling_flip_without_reason_fails(self):
        p = self.new(); self.sources(p); self.w(p, "script/script.md", "x"); time.sleep(1.1)
        self._prev(p, "supported"); self.claims(p, status="partly_supported")
        r = self.run_py(QA, p.name, "--gate", "factcheck", ok=False); self.assertIn("ruling changed", r.stdout)

    def test_ruling_flip_with_reason_or_new_wording_passes(self):
        p = self.new(); self.sources(p); self.w(p, "script/script.md", "x"); time.sleep(1.1)
        self._prev(p, "supported"); self.claims(p, status="partly_supported")
        c = json.loads((p / "factcheck/claims.json").read_text())
        c["claims"][0]["change_reason"] = "Re-read S1 in context: the date is the Julian calendar."
        self.w(p, "factcheck/claims.json", json.dumps(c)); self.run_py(QA, p.name, "--gate", "factcheck")
        del c["claims"][0]["change_reason"]; c["claims"][0]["text"] = "The city fell in late May 1453."
        self.w(p, "factcheck/claims.json", json.dumps(c)); self.run_py(QA, p.name, "--gate", "factcheck")

    def test_factcheck_stale_after_script_edit(self):
        p = self.new(); self.sources(p); self.w(p, "script/script.md", "x"); time.sleep(1.1)
        self.claims(p); self.run_py(QA, p.name, "--gate", "factcheck")
        time.sleep(1.1); self.w(p, "script/script.md", "edited")
        r = self.run_py(QA, p.name, "--gate", "factcheck", ok=False); self.assertIn("re-run", r.stdout)


class TestQuoteCheck(Base):
    def test_match_ignores_html_entities_footnotes_and_dashes(self):
        f = self.w(Path(self.tmp.name), "p.html", PAGE)
        self.assertIn("MATCH", self.run_py(QC, str(f), "the city fell on 29 May 1453.").stdout)
        self.run_py(QC, str(f), "Mehmed's cannon - built by Orban - had battered the walls")

    def test_paraphrase_does_not_match(self):
        f = self.w(Path(self.tmp.name), "p.html", PAGE)
        r = self.run_py(QC, str(f), "Constantinople was captured on 29 May 1453", ok=False)
        self.assertIn("NO MATCH", r.stdout)

    def test_script_tag_text_is_not_page_text(self):
        f = self.w(Path(self.tmp.name), "p.html", PAGE.replace("the city fell on 29&nbsp;May 1453.", "it ended."))
        self.run_py(QC, str(f), "The city fell on 29 May 1453.", ok=False)

    def test_gate_rejects_claimed_match_not_on_page(self):
        p = self.new(); self.sources(p)
        bad = json.loads((p / "research/sources.json").read_text()); bad[0]["quote"] = "The walls were never breached."
        self.w(p, "research/sources.json", json.dumps(bad))
        r = self.run_py(QA, p.name, "--gate", "sources", ok=False); self.assertIn("NOT on the saved page", r.stdout)

    def test_gate_requires_quote_check_and_page(self):
        p = self.new(); self.sources(p)
        bad = json.loads((p / "research/sources.json").read_text()); del bad[1]["quote_check"]; del bad[0]["page"]
        self.w(p, "research/sources.json", json.dumps(bad))
        r = self.run_py(QA, p.name, "--gate", "sources", ok=False)
        self.assertIn("quote_check", r.stdout); self.assertIn("needs 'page'", r.stdout)


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
        self.w(p, "hooks/override.txt", f"HOOK: {weak}\nREASON: Narrated history; I prefer the date-first open.\n")
        r = self.run_py(QA, p.name); self.assertRegex(r.stdout, r"WARN\s+hook score.*kept by the creator: Narrated")

    def test_override_for_different_wording_fails(self):
        p = self.new(); self.complete(p)
        weak = HOOKS.splitlines()[1]
        self.w(p, "hooks/chosen.txt", weak + "\n")
        self.w(p, "hooks/override.txt", "HOOK: an older wording of the hook\nREASON: mine\n")
        r = self.run_py(QA, p.name, ok=False); self.assertIn("different wording", r.stdout)

    def test_legacy_override_without_hook_line_is_warned(self):
        p = self.new(); self.complete(p)
        self.w(p, "hooks/chosen.txt", HOOKS.splitlines()[1] + "\n")
        self.w(p, "hooks/override.txt", "My reason in my words.\n")
        r = self.run_py(QA, p.name); self.assertIn("does not say which wording", r.stdout)

    def test_unchecked_quotes_and_weak_sources_are_warned(self):
        p = self.new(); self.complete(p)
        r = self.run_py(QA, p.name)
        self.assertRegex(r.stdout, r"WARN\s+quote checks.*S2 \(user_provided_unchecked\)")
        d = json.loads((p / "research/sources.json").read_text()); d[0]["tier"] = "secondary"
        self.w(p, "research/sources.json", json.dumps(d))
        self.assertRegex(self.run_py(QA, p.name).stdout, r"WARN\s+source strength")

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


TTS = SKILL / "tts.py"
NARRATION = """# Narration
Spoken words: 20 (about 0.1 min)

The land walls of Constantinople were built in the fifth century. {C1}
[ON SCREEN: map of the walls]
In 1453, / cannons made for the **sultan** were aimed at them.
[PAUSE]
Sphrantzes counted the defenders.
"""
STUB = """class KPipeline:
    def __init__(self, lang_code): self.lang = lang_code
    def __call__(self, text, voice, speed, split_pattern=None):
        open(__file__ + '.log', 'a').write(text + '\\n')
        yield text, None, [0.1] * int(24000 * 0.2 * len(text.split()))
"""


class TestTTS(Base):
    def stub_env(self):
        d = Path(self.tmp.name) / "stub" / "kokoro"; d.mkdir(parents=True)
        (d / "__init__.py").write_text(STUB)
        return {**self.env, "PYTHONPATH": str(d.parent)}, d / "__init__.py.log"

    def proj(self):
        p = self.new()
        self.w(p, "narration/narration.md", NARRATION)
        self.w(p, "narration/pronunciation.md", "Sphrantzes - SFRANT-zess\n")
        self.w(p, "narration/tts-lexicon.txt", "Sphrantzes = Sfrant-zess\n")
        return p

    def test_dry_run_strips_cues_tags_and_marks_pauses(self):
        p = self.proj()
        out = self.run_py(TTS, str(p / "narration/narration.md"), "--dry-run", "--lexicon", str(p / "narration/tts-lexicon.txt")).stdout
        for gone in ("ON SCREEN", "{C1}", "**", "# Narration", "Spoken words"):
            self.assertNotIn(gone, out)
        self.assertIn("[0.25s]", out); self.assertIn("[0.7s]", out); self.assertIn("Sfrant-zess", out)

    def test_voiceover_with_stub_engine_writes_wav_and_timings(self):
        import wave
        p = self.proj(); env, log = self.stub_env()
        r = subprocess.run([sys.executable, str(TTS), str(p / "narration/narration.md"), "-o", str(p / "narration/voiceover.wav"),
                            "--lexicon", str(p / "narration/tts-lexicon.txt")], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        with wave.open(str(p / "narration/voiceover.wav")) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getsampwidth()), (24000, 1, 2)); self.assertGreater(w.getnframes(), 24000)
        meta = json.loads((p / "narration/voiceover.json").read_text())
        self.assertFalse(meta["scratch"]); self.assertEqual(len(meta["lines"]), 4)
        self.assertTrue(all(a["end"] >= a["start"] for a in meta["lines"]))
        spoken = log.read_text(); self.assertIn("Sfrant-zess", spoken); self.assertNotIn("ON SCREEN", spoken)
        self.st("set", p.name, "narration", "in_progress")
        r = self.run_py(QA, p.name, ok=None); self.assertRegex(r.stdout, r"PASS\s+voiceover")

    def test_unresolved_check_refuses_final_but_allows_scratch(self):
        p = self.proj(); env, _ = self.stub_env()
        self.w(p, "narration/pronunciation.md", "Orban - CHECK\n")
        args = [sys.executable, str(TTS), str(p / "narration/narration.md")]
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 4); self.assertIn("CHECK", r.stderr)
        r = subprocess.run(args + ["--allow-check"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads((p / "narration/voiceover.json").read_text())["scratch"])
        self.assertRegex(self.run_py(QA, p.name, ok=None).stdout, r"WARN\s+voiceover.*SCRATCH")

    def test_stale_voiceover_is_warned(self):
        p = self.proj(); env, _ = self.stub_env()
        subprocess.run([sys.executable, str(TTS), str(p / "narration/narration.md")], env=env, capture_output=True)
        time.sleep(1.1); self.w(p, "narration/narration.md", NARRATION + "One more line.\n")
        self.assertRegex(self.run_py(QA, p.name, ok=None).stdout, r"WARN\s+voiceover.*regenerate")

    def test_missing_kokoro_is_reported_not_faked(self):
        p = self.proj()
        r = subprocess.run([sys.executable, "-I", str(TTS), str(p / "narration/narration.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 3); self.assertIn("not installed", r.stderr)
        self.assertFalse((p / "narration/voiceover.wav").exists())

    def test_check_tools_detects_kokoro_venv(self):
        env, _ = self.stub_env()
        wrapper = Path(self.tmp.name) / "venv-python"
        wrapper.write_text(f"#!/bin/sh\nPYTHONPATH={env['PYTHONPATH']} exec {sys.executable} \"$@\"\n"); wrapper.chmod(0o755)
        self.env["YT_TTS_PYTHON"] = str(wrapper)
        out = self.st("check-tools").stdout
        self.assertRegex(out, r"tts:kokoro\s+available"); self.assertRegex(out, r"narration_audio\s+available.*kokoro")
        self.env["YT_TTS_PYTHON"] = str(Path(self.tmp.name) / "nope")
        self.assertRegex(self.st("check-tools").stdout, r"tts:kokoro\s+unavailable")


QWEN_STUB = """import json, os
LOG = __file__ + '.log'
def _log(**kw): open(LOG, 'a').write(json.dumps(kw) + '\\n')
class Qwen3TTSModel:
    @classmethod
    def from_pretrained(cls, model_id, **kw):
        _log(call='load', model=model_id, kw=sorted(kw)); m = cls(); m.model_id = model_id; return m
    def _audio(self, text): return [[0.05] * int(24000 * 0.15 * len(text.split()))], 24000
    def generate_voice_design(self, text, language, instruct):
        _log(call='design', text=text, instruct=instruct); return self._audio(text)
    def generate_custom_voice(self, text, language, speaker, instruct=None):
        _log(call='custom', text=text, speaker=speaker); return self._audio(text)
    def create_voice_clone_prompt(self, ref_audio, ref_text):
        _log(call='prompt', ref_audio=os.path.basename(ref_audio), ref_text=ref_text); return 'PROMPT'
    def generate_voice_clone(self, text, language, voice_clone_prompt=None, ref_audio=None, ref_text=None):
        _log(call='clone', text=text, prompt=voice_clone_prompt); return self._audio(text)
"""


class TestQwen(Base):
    def qenv(self):
        d = Path(self.tmp.name) / "qstub" / "qwen_tts"; d.mkdir(parents=True)
        (d / "__init__.py").write_text(QWEN_STUB)
        return {**self.env, "PYTHONPATH": str(d.parent)}, d / "__init__.py.log"

    def calls(self, log): return [json.loads(l) for l in log.read_text().splitlines()]

    def proj(self):
        p = self.new()
        self.w(p, "narration/narration.md", NARRATION)
        self.w(p, "narration/pronunciation.md", "Sphrantzes - SFRANT-zess\n")
        self.w(p, "narration/tts-lexicon.txt", "Sphrantzes = Sfrant-zess\n")
        return p

    def tts(self, env, *args):
        return subprocess.run([sys.executable, str(TTS), *args], capture_output=True, text=True, env=env)

    def test_design_ref_then_clone_keeps_one_voice(self):
        import wave
        p = self.proj(); env, log = self.qenv(); ref = p / "narration/voice-ref.wav"
        r = self.tts(env, "design-ref", str(ref), "--instruct", "warm higher-pitched male narrator")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(ref.exists()); self.assertIn("turning points", (p / "narration/voice-ref.txt").read_text())
        r = self.tts(env, str(p / "narration/narration.md"), "--engine", "qwen", "--qwen-mode", "clone",
                     "--ref-audio", str(ref), "--lexicon", str(p / "narration/tts-lexicon.txt"), "-o", str(p / "narration/voiceover.wav"))
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("extra words or laughter", r.stdout)
        c = self.calls(log)
        self.assertEqual([x["model"] for x in c if x["call"] == "load"],
                         ["Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "Qwen/Qwen3-TTS-12Hz-0.6B-Base"])
        self.assertIn("device_map", c[0]["kw"])
        prompt = [x for x in c if x["call"] == "prompt"][0]; self.assertIn("turning points", prompt["ref_text"])
        clones = [x for x in c if x["call"] == "clone"]
        self.assertEqual(len(clones), 3)                              # one call per spoken line, "/" kept inside
        self.assertTrue(all(x["prompt"] == "PROMPT" for x in clones))
        self.assertIn("In 1453, cannons", clones[1]["text"]); self.assertIn("Sfrant-zess", clones[2]["text"])
        meta = json.loads((p / "narration/voiceover.json").read_text())
        self.assertIn("qwen3-tts", meta["engine"]); self.assertIn("cloned from", meta["voice"]); self.assertEqual(meta["sample_rate"], 24000)
        self.assertTrue(all(b["start"] >= a["end"] - 0.01 for a, b in zip(meta["lines"], meta["lines"][1:])))
        with wave.open(str(p / "narration/voiceover.wav")) as w: self.assertEqual(w.getframerate(), 24000)

    def test_mode_requirements_are_enforced(self):
        p = self.proj(); env, _ = self.qenv(); n = str(p / "narration/narration.md")
        self.assertIn("--speaker", self.tts(env, n, "--engine", "qwen", "--qwen-mode", "custom").stderr)
        self.assertIn("--ref-audio", self.tts(env, n, "--engine", "qwen", "--qwen-mode", "clone").stderr)
        self.assertIn("--instruct", self.tts(env, n, "--engine", "qwen", "--qwen-mode", "design").stderr)
        self.assertIn("--instruct", self.tts(env, "design-ref", str(p / "x.wav")).stderr)
        self.w(p, "narration/clip.wav", "x")
        self.assertIn("transcript", self.tts(env, n, "--engine", "qwen", "--ref-audio", str(p / "narration/clip.wav")).stderr)

    def test_custom_preset_voice(self):
        p = self.proj(); env, log = self.qenv()
        r = self.tts(env, str(p / "narration/narration.md"), "--engine", "qwen", "--qwen-mode", "custom", "--speaker", "Ryan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(all(x["speaker"] == "Ryan" for x in self.calls(log) if x["call"] == "custom"))

    def test_missing_qwen_is_reported(self):
        p = self.proj()
        r = subprocess.run([sys.executable, "-I", str(TTS), str(p / "narration/narration.md"), "--engine", "qwen",
                            "--qwen-mode", "custom", "--speaker", "Ryan"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 3); self.assertIn("qwen-tts is not installed", r.stderr)

    def test_check_tools_detects_qwen(self):
        env, _ = self.qenv()
        wrapper = Path(self.tmp.name) / "qwen-python"
        wrapper.write_text(f"#!/bin/sh\nPYTHONPATH={env['PYTHONPATH']} exec {sys.executable} \"$@\"\n"); wrapper.chmod(0o755)
        self.env["YT_QWEN_PYTHON"] = str(wrapper)
        out = self.st("check-tools").stdout
        self.assertRegex(out, r"tts:qwen\s+available"); self.assertRegex(out, r"narration_audio\s+available.*tts:qwen")


RENDER = SKILL / "render.py"
VO_JSON = {"voice": "am_michael", "duration_sec": 6.0, "lines": [
    {"line": "The land walls were built in the fifth century.", "start": 0, "end": 2.0},
    {"line": "In 1453, / cannons were aimed at them.", "start": 2.0, "end": 4.0},
    {"line": "Sphrantzes counted the defenders.", "start": 4.0, "end": 6.0}]}


@unittest.skipUnless(__import__("shutil").which("ffmpeg"), "ffmpeg not installed")
class TestRender(Base):
    def proj(self, prefix=""):
        p = self.new()
        (p / "narration").mkdir(exist_ok=True); (p / "visuals/images").mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=6",
                        "-ar", "24000", "-ac", "1", str(p / f"narration/{prefix}voiceover.wav")], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=640x480",
                        "-frames:v", "1", str(p / "visuals/images/walls.png")], check=True)
        self.w(p, f"narration/{prefix}voiceover.json", json.dumps(VO_JSON))
        return p

    def plan(self, p, licence="Public domain", prefix=""):
        self.w(p, f"visuals/{prefix}plan.json", json.dumps([
            {"start_line": 0, "image": "visuals/images/walls.png", "licence": licence,
             "source_url": "https://commons.wikimedia.org/wiki/File:Example.png", "card": "The walls"},
            {"start_line": 2, "image": None, "card": "Sphrantzes' count"}]))

    def test_dry_run_shows_cards_for_uncleared(self):
        p = self.proj(); self.plan(p, licence="unknown")
        out = self.run_py(RENDER, str(p), "--dry-run").stdout
        self.assertIn('CARD "The walls" (licence not cleared)', out); self.assertIn("2 placeholder card(s)", out)

    def test_render_draft_with_captions_credits_and_pitch(self):
        p = self.proj(); self.plan(p)
        out = self.run_py(RENDER, str(p), "--size", "640x360", "--pitch", "1.08").stdout
        self.assertIn("DRAFT: 1 placeholder", out)
        self.assertTrue((p / "render/draft.mp4").stat().st_size > 1000); self.assertFalse((p / "render/video.mp4").exists())
        self.assertIn("The land walls", (p / "render/captions.srt").read_text())
        self.assertIn("commons.wikimedia.org", (p / "render/credits.txt").read_text())
        rep = json.loads((p / "render/render.json").read_text())
        self.assertEqual(rep["placeholders"], 1); self.assertEqual(rep["pitch"], 1.08)
        self.assertFalse((p / "render/work").exists())
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(p / "render/draft.mp4")], capture_output=True, text=True)
        self.assertAlmostEqual(float(r.stdout), 6.0, delta=0.3)
        self.assertRegex(self.run_py(QA, p.name, ok=None).stdout, r"WARN\s+render render\s+render/draft.mp4 is a DRAFT")

    def test_all_cleared_gives_final_and_removes_stale_draft(self):
        p = self.proj(); self.plan(p); self.run_py(RENDER, str(p), "--size", "640x360")
        d = json.loads((p / "visuals/plan.json").read_text()); d[1]["image"] = "visuals/images/walls.png"; d[1]["licence"] = "Public domain"
        self.w(p, "visuals/plan.json", json.dumps(d)); self.run_py(RENDER, str(p), "--size", "640x360", "--no-captions")
        self.assertTrue((p / "render/video.mp4").exists()); self.assertFalse((p / "render/draft.mp4").exists())
        self.assertRegex(self.run_py(QA, p.name, ok=None).stdout, r"PASS\s+render render\s+render/video.mp4")

    def test_vertical_short_variant(self):
        p = self.proj(prefix="short-"); self.plan(p, prefix="short-")
        self.run_py(RENDER, str(p), "--variant", "short", "--vertical", "--no-captions")
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(p / "render/short/draft.mp4")], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "1080,1920")

    def test_unlicensed_image_in_report_fails_qa_and_stale_render_warns(self):
        p = self.proj(); self.plan(p); self.run_py(RENDER, str(p), "--size", "640x360", "--no-captions")
        rep = json.loads((p / "render/render.json").read_text()); rep["segments"][0]["licence"] = None
        self.w(p, "render/render.json", json.dumps(rep))
        self.assertRegex(self.run_py(QA, p.name, ok=False).stdout, r"FAIL\s+render render\s+segments \[0\]")
        self.run_py(RENDER, str(p), "--size", "640x360", "--no-captions"); time.sleep(1.1)
        (p / "narration/voiceover.wav").touch()
        self.assertRegex(self.run_py(QA, p.name, ok=None).stdout, r"WARN\s+render render\s+the voiceover changed")

    def test_bad_plan_is_refused(self):
        p = self.proj()
        self.w(p, "visuals/plan.json", json.dumps([{"start_line": 1, "image": None, "card": "x"}]))
        self.assertIn("start_line 0", self.run_py(RENDER, str(p), "--dry-run", ok=False).stderr)

    def test_old_project_gains_render_stage(self):
        p = self.new(); d = self.data(p); del d["stages"]["render"]
        (p / "project.json").write_text(json.dumps(d))
        self.assertIn("Video assembly", self.st("status", p.name).stdout)


class TestSafety(unittest.TestCase):
    def test_skill_rules_present(self):
        s = (SKILL / "SKILL.md").read_text()
        self.assertIn("Never\nassume or infer the answer", s)
        self.assertIn("reserved for the\nfinal upload pack", s)
        self.assertIn("ask for it and wait", s)

    def test_no_upload_or_network_code(self):
        src = "".join((SKILL / f).read_text() for f in ("state.py", "qa.py", "quotecheck.py", "tts.py", "render.py"))
        for bad in ("urllib", "requests", "http.client", "socket", "googleapiclient", "youtube.upload",
                    "ANTHROPIC_API_KEY", "api_key"):
            self.assertNotIn(bad, src, bad)

    def test_no_reference_to_yt_project(self):
        for f in SKILL.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".py") and f.name != "test_produce.py":
                self.assertNotIn("~/yt/", f.read_text(), f)


if __name__ == "__main__":
    unittest.main()
