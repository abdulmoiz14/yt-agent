---
name: yt-produce
description: >-
  Produce one YouTube video end to end in its own project folder - research,
  source verification, independent fact-check, hooks, script, packaging,
  visual plan, narration prep, SEO and QA - by coordinating the other yt-*
  skills, tracking every stage so it can resume, and stopping at an upload
  pack that waits for the creator's approval. Use for "produce a video about
  X", "/yt-produce", "resume my video", "where is my video up to".
argument-hint: "<topic> | resume [project] | status [project] | redo <stage> [project] | list"
---

# yt-produce

The producer. It writes nothing the other skills already write: it runs them in order, saves what
they produce into one folder per video, and keeps an honest record of what is done, what is
blocked, and what could not be done with the tools on this machine.

**Nothing gets published.** This skill has no upload, scheduling or publishing step and must never
add one, call a YouTube API, or drive a browser to YouTube Studio. It ends at an upload pack and the
question **ship it, or change it?** The creator uploads.

## Setup for every run

`S` below is this skill's base directory (Claude Code shows it when the skill loads). The siblings
are `$S/../yt-script`, `$S/../yt-package` and so on. Run `python3 "$S/state.py" where` if unsure.

- Projects: `~/youtube-productions/<date>-<slug>/` (override with `$YT_PRODUCTIONS_DIR`).
- Python (`state.py`, `qa.py`, the sibling tools) is for deterministic local work only: state,
  scoring, linting, QA. All research, judgement and writing is you, in this Claude Code session.
- No API keys. Never ask for one, never configure a paid provider, never read `~/yt`.

## Commands

| invocation | do this |
| --- | --- |
| `/yt-produce <topic>` | `state.py new "<topic>" --minutes N` (ask the length if not given), then run stages from `intake` |
| `/yt-produce resume [project]` | `state.py status`, then `state.py next` and continue from that stage |
| `/yt-produce status [project]` | print `state.py status` and stop |
| `/yt-produce redo <stage> [project]` | `state.py set <p> <stage> in_progress`, redo it, then re-run every later stage that used its output |
| `/yt-produce list` | `state.py list` |

## The loop

For each stage: `state.py next <p>` → `state.py set <p> <stage> in_progress` → do the work and write
the outputs → record any command with `--cmd "..." --exit <real code>` → `state.py set <p> <stage> done`.

`state.py` refuses `done` if an output file is missing or empty, a recorded command failed, or the
stage's rules (in `qa.py`) are not met. **Do not work around a refusal.** Fix the cause, or mark the
stage honestly:

- `needs_input --note "..."` - something only the creator can give (voice profile, a choice, a recording).
- `unavailable --note "..."` - a tool or capability is not on this machine. Say what is missing and the manual alternative.
- `skipped --note "..."` - only when the creator asked to skip it.

Never write a status, score, source, quote, URL or verification result you did not actually produce.
At a stage marked ✋, show the creator the result, ask, and **stop until they answer**.

## Stages

| stage | how | outputs |
| --- | --- | --- |
| `intake` | Ask topic, angle, who it is for, target minutes. Read the voice profile (rules below). Write `brief.md`. | `brief.md` |
| `tools` | `state.py check-tools <p>`. Then verify web research for real: run one WebSearch and one WebFetch on a page it returns. Record `state.py capability <p> web_research available --note "WebSearch+WebFetch ok: <url>"` or `unavailable` with the error. | `project.json` capabilities |
| `research` ✋ | `stages/research.md`. If `web_research` is unavailable, mark `needs_input` and ask the creator for sources. Optional niche check with `/yt-viral` only if `niche_research` is available or they give a list. Show the angle; get it approved. | `research/notes.md` |
| `sources` | `stages/sources.md`. Separate pass: re-open each source, copy the exact supporting quote. | `research/sources.json`, `research/sources.md` |
| `outline` | Beats in order, and under each the factual claims it will make, each tagged with candidate source ids. | `outline.md` |
| `hooks` ✋ | Follow `/yt-script` step 1: five hooks off `$S/../yt-script/hooks.json`, write to `hooks/hooks.txt`, run `python3 "$S/../yt-script/hookscore.py" --json hooks/hooks.txt > hooks/hookscore.json`. Show the top two with scores. Their pick goes in `hooks/chosen.txt`. If they keep a WEAK hook, write their reason in their words to `hooks/override.txt` (QA fails a WEAK hook without one; never write it for them). Hooks make claims too - only ones the sources support. | `hooks/*` |
| `script` | Follow `/yt-script` steps 2-5 from the chosen hook and `outline.md`: every beat gets `[ON SCREEN: ...]`; runtime at 150 wpm. Mark each factual sentence with its claim id, e.g. `{C4}`. | `script/script.md` (keep `script.vN.md` on rewrites) |
| `factcheck` ✋ | `stages/factcheck.md`: the `yt-fact-checker` agent, not you. Unsupported claims go back into the script; re-run until the gate passes. Show the ledger summary; get the script approved. | `factcheck/claims.json`, `factcheck/claims.md` |
| `package` ✋ | Follow `/yt-package`: ten titles in `package/titles.txt`, `python3 "$S/../yt-package/title.py" --json package/titles.txt > package/title-lint.json`, re-lint finalists with `--thumb`. Show top three; their pick goes in `chosen-title.txt` / `chosen-thumb.txt`; write `thumbnail-brief.md`. Titles may not claim more than the ledger supports. | `package/*` |
| `visuals` | `stages/visuals.md`. | `visuals/shotlist.md`, `visuals/assets.md` |
| `narration` | `stages/narration.md`. | `narration/narration.md`, `narration/pronunciation.md` |
| `seo` | Follow `/yt-seo` → `seo/description.md`, `seo/tags.txt`. Chapters from the script beats at 150 wpm → `seo/chapters-provisional.txt`, headed `PROVISIONAL - regenerate from the real transcript`. | `seo/*` |
| `qa` | `stages/qa.md`: `python3 "$S/qa.py" <p>`, fix FAILs, re-run until PASS, then your own read-through. | `qa/report.md` |
| `handoff` ✋ | `stages/handoff.md`. Mark `awaiting_approval`. Stop. | `publish/upload-pack.md` |

After recording (run with `state.py next <p> --post`), each needs the creator's recording or transcript:

| stage | how |
| --- | --- |
| `post_transcript` | If `transcription` is available, local whisper on the file they name → `post/transcript.srt`. Otherwise `needs_input`: ask for an .srt/.vtt (YouTube's auto-captions on an unlisted upload work). Never invent timings. |
| `post_edit` | `/yt-edit`: `python3 "$S/../yt-edit/deadair.py" post/transcript.srt > post/edl.txt` |
| `post_chapters` | `/yt-chapters`: `python3 "$S/../yt-chapters/chapters.py" post/transcript.srt` then retitle → `post/chapters.txt`; update `seo/description.md` |
| `post_shorts` | `/yt-shorts` on the transcript → `post/shorts.md` |

Retention and comments come after publishing - point to `/yt-retention` and `/yt-comment`, nothing more.

## The voice profile

`~/.claude/youtube/voice.md` (or `$YT_VOICE_FILE`). Read it with the Read tool at runtime and use
it for every line that will be spoken or shown.

- **Never** copy it, or paste chunks of it, into the project folder, the skills repo, or chat.
  Refer to it ("per your voice profile, no 'dive in'"); quote at most the single word being enforced.
- If it is missing, unreadable, or still the template, `check-tools` marks `intake` `needs_input`.
  Tell the creator exactly which, and that they can fill it from `templates/voice.md` or send three
  of their own videos so you can draft it (then it is theirs to save - do not write it without a yes).
  Do not proceed past intake on a guessed voice.

## Approval

Only the creator's own explicit words in this conversation approve the upload pack ("approved",
"ship it"). Record them verbatim: `state.py set <p> handoff approved --user-statement "<their words>"`.
Approval still does not mean you upload anything. It means the pack is final; they upload it.
Silence, "looks good so far", or approval of an earlier checkpoint is not approval of the pack.

## Reporting

End every turn with `state.py status <p>` output trimmed to: what was done this turn, what is
blocked or unavailable and why, and the next stage. Last line, at a checkpoint or the end:
**ship it, or change it?**
