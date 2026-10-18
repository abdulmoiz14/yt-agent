---
name: yt-produce
description: >-
  Produce one YouTube video end to end in its own project folder - research,
  source verification, independent fact-check, hooks, script, packaging,
  visual plan, voiceover, scene images, slideshow render, SEO and QA - by coordinating the other yt-*
  skills, tracking every stage so it can resume, and stopping at an upload
  pack that waits for the creator's approval. Use for "produce a video about
  X", "/yt-produce", "resume my video", "where is my video up to".
argument-hint: "<topic> | resume [project] | status [project] | full [project] | coverage [project] | redo <stage> [project] | list"
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

- Projects: `~/youtube-productions/<date>-<slug>/`. This is outside the current working directory,
  so Claude Code may ask permission to write there - **ask for it and wait**. Never move projects
  elsewhere, or set `$YT_PRODUCTIONS_DIR`, on your own judgement; only the creator chooses a
  different location.
- Python (`state.py`, `qa.py`, the sibling tools) is for deterministic local work only: state,
  scoring, linting, QA. All research, judgement and writing is you, in this Claude Code session.
- No API keys in chat or in any project or repo file, and never read `~/yt`. The one paid service is
  image generation (`/yt-images`), using the key the creator saved themselves in
  `~/.config/yt-claude/yt-images/openlux.key`. Never ask for the key, never print it, and never spend
  without a spending limit the creator gave you for this video.
- **Faceless history channel?** If the voice profile's format says narrated/faceless, write hooks with
  `--set history` (see `hooks`) and make the thumbnail with `images.py thumb` instead of a face brief.

## Commands

| invocation | do this |
| --- | --- |
| `/yt-produce <topic>` | `state.py new "<topic>" --minutes N` (ask the length if not given), then run stages from `intake` |
| `/yt-produce resume [project]` | `state.py status`, then `state.py next` and continue from that stage |
| `/yt-produce status [project]` | print `state.py status` and stop |
| `/yt-produce redo <stage> [project]` | `state.py set <p> <stage> in_progress`, redo it, then re-run every later stage that used its output |
| `/yt-produce list` | `state.py list` |
| `/yt-produce coverage [project]` | `state.py coverage` - which of the 11 original skills this video has used, and what each unused one is waiting for (plus `/yt-images`, the twelfth tool, in the `images` stage) |
| `/yt-produce full [project]` | Run EVERY stage, optional ones too, in order, through the post-voiceover stages; mark each after-publishing stage `needs_input` with exactly what is missing; finish with `coverage` |

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
At a stage marked ✋, show the creator the result, ask, and **stop until they answer**. Never
assume or infer the answer: "continue", "go ahead" or "looks fine" without the actual choice
(which angle, which hook, which title) is not a choice - ask again, briefly. If you are about to
write "I went with..." at a checkpoint, stop instead.

## Stages

| stage | how | outputs |
| --- | --- | --- |
| `intake` | Ask topic, angle, who it is for, target minutes. Read the voice profile (rules below). Write `brief.md`. | `brief.md` |
| `tools` | `state.py check-tools <p>`. Then verify web research for real: run one WebSearch and one WebFetch on a page it returns. Record `state.py capability <p> web_research available --note "WebSearch+WebFetch ok: <url>"` or `unavailable` with the error. | `project.json` capabilities |
| `niche` (optional) | `stages/niche.md`: `/yt-viral` on 3-6 channels via yt-dlp + `collect.py`. Unavailable without yt-dlp or a list. | `research/niche.md` |
| `research` ✋ | `stages/research.md`. If `web_research` is unavailable, mark `needs_input` and ask the creator for sources. Optional niche check with `/yt-viral` only if `niche_research` is available or they give a list. Show the angle; get it approved. | `research/notes.md` |
| `sources` | `stages/sources.md`. Separate pass: download each page with `curl`, confirm each quote with `python3 "$S/quotecheck.py"`. WebFetch output is a summary, never a verbatim quote. | `research/sources.json`, `research/sources.md` |
| `outline` | Beats in order, and under each the factual claims it will make, each tagged with candidate source ids. | `outline.md` |
| `hooks` ✋ | Follow `/yt-script` step 1: five hooks off `$S/../yt-script/hooks.json` (narrated history/documentary: `hooks-history.json`), write to `hooks/hooks.txt`, run `python3 "$S/../yt-script/hookscore.py" --json [--set history] hooks/hooks.txt > hooks/hookscore.json`. Show the top two with scores. Their pick goes in `hooks/chosen.txt`. If they keep a WEAK hook, write `hooks/override.txt` as two lines: `HOOK: <the exact chosen hook>` and `REASON: <their words>` (QA fails a WEAK hook without one; never write the reason for them). If the chosen hook's wording changes later (e.g. after the fact-check), re-score it, add it to `hooks/hooks.txt` keeping the old file as `hooks.vN.txt`, and **ask the creator** whether their override still applies; update the HOOK line only after they say yes. Hooks make claims too - only ones the sources support. | `hooks/*` |
| `script` | Follow `/yt-script` steps 2-5 from the chosen hook and `outline.md`: every beat gets `[ON SCREEN: ...]`; runtime at 150 wpm. Mark each factual sentence with its claim id, e.g. `{C4}`. | `script/script.md` (keep `script.vN.md` on rewrites) |
| `factcheck` ✋ | `stages/factcheck.md`: the `yt-fact-checker` agent, not you. Unsupported claims go back into the script; re-run until the gate passes. Show the ledger summary; get the script approved. | `factcheck/claims.json`, `factcheck/claims.md` |
| `package` ✋ | Follow `/yt-package`: ten titles in `package/titles.txt`, `python3 "$S/../yt-package/title.py" --json package/titles.txt > package/title-lint.json`, re-lint finalists with `--thumb`. Show top three; their pick goes in `chosen-title.txt` / `chosen-thumb.txt`; write `thumbnail-brief.md` (faceless: the illustrated subject, not an expression). Titles may not claim more than the ledger supports. The thumbnail image itself is made in the `images` stage. | `package/*` |
| `visuals` | `stages/visuals.md`. | `visuals/shotlist.md`, `visuals/assets.md` |
| `narration` | `stages/narration.md`. If a local TTS engine is available (Kokoro, or Qwen3-TTS on a capable machine), ask: final voiceover or scratch track, and which engine/voice? Then `tts.py` (local) → `narration/voiceover.wav`. | `narration/narration.md`, `narration/pronunciation.md` (+ `voiceover.wav` if chosen) |
| `images` ✋ (optional) | Scene pictures with the creator's paid image model: follow `$S/../yt-images/SKILL.md` - prompts from the narration lines and one style, **spending limit from the creator**, 3 test images, the **yt-image-reviewer** agent (not you) checks every image, the creator approves in their own words, `images.py plan` writes `visuals/plan.json`, `images.py thumb` makes `package/thumbnail.png`. Skip it (`skipped`, with their reason) if they only want public-domain images. | `visuals/prompts.json`, `manifest.json`, `review.json`, `plan.json` |
| `render` ✋ (optional) | Only when the creator wants the video assembled here (synthetic voiceover). `stages/render.md`: `visuals/plan.json` (from `images.py plan`, or cleared public-domain images with licences read on each file page) → `python3 "$S/render.py" <p>` (crossfades and slow camera moves by default; ask whether they want `--sfx whoosh` and a music bed - only a track they have the rights to, with `--music-licence`). AI images get an on-screen label automatically. Placeholder cards for anything not cleared; it is a draft until none remain. Ask the creator to watch it. | `render/*` |
| `seo` | Follow `/yt-seo` → `seo/description.md` (if the video uses AI illustrations, add: "Illustrations in this video are AI-generated and are not historical images." - QA fails without it), `seo/tags.txt`. Chapters from the script beats at 150 wpm → `seo/chapters-provisional.txt`, headed `PROVISIONAL - regenerate from the real transcript`. | `seo/*` |
| `qa` | `stages/qa.md`: `python3 "$S/qa.py" <p>`, fix FAILs, re-run until PASS, then your own read-through. | `qa/report.md` |
| `handoff` ✋ | `stages/handoff.md`. Mark `awaiting_approval`. Stop. | `publish/upload-pack.md` |

After the voiceover or recording (run with `state.py next <p> --post`; full instructions in
`stages/postproduction.md`). A synthetic voiceover comes with an exact transcript
(`narration/voiceover.srt`), so these run without a recording:

| stage | how |
| --- | --- |
| `post_transcript` | Synthetic voiceover: copy `narration/voiceover.srt`. Own recording: local whisper if available, else `needs_input` for an .srt/.vtt. Never invent timings. |
| `post_edit` | `/yt-edit`: `python3 "$S/../yt-edit/deadair.py" post/transcript.srt > post/edl.txt` (a synthetic voiceover usually has nothing to cut - that is the expected result, say so) |
| `post_chapters` | `/yt-chapters`: `python3 "$S/../yt-chapters/chapters.py" post/transcript.srt` then retitle → `post/chapters.txt`; update the description and pack, and re-open approval if the pack was approved |
| `post_shorts` | `/yt-shorts` on the transcript, with line numbers for cutting → `post/shorts.md` |
| `post_short_render` ✋ (optional) | New first line voiced with the same voice, then `render.py --clip A B --intro-audio ... --hook-text ...` → vertical Shorts in `render/shorts/` |
| `schedule` ✋ (optional) | `/yt-plan`: ask hours and best day, then the week with this video as anchor and its Shorts → `publish/plan.md`. Nothing is scheduled on YouTube |

After publishing (`stages/after-publish.md`, all optional, each waits for the creator's data):
`retention` (`/yt-retention` on the Studio CSV + transcript), `comments` (`/yt-comment` on pasted
comments), `audit` (`/yt-audit` on the channel).



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
blocked or unavailable and why, and the next stage. At a checkpoint, the last line is the one
decision you need ("Pick an angle: 1, 2 or 3?"). **Ship it, or change it?** is reserved for the
final upload pack at handoff.
