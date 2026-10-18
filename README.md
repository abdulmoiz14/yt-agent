# The YouTube agent skill

Thirteen Claude skills that run a YouTube channel. MIT. Twelve of them are free, need no signup and no
API key. The thirteenth, `/yt-images`, makes scene images with an image model you pay for (your own
key, your own spending limit) - skip it and everything else still works.

One of them writes your script off 21 hook formulas and scores the hook before you waste a take on
it. One lints the title and the thumbnail as a single pairing, because writing them separately is
why half of your click surface says the same thing twice. One reads your audience-retention export
and tells you the exact second people left and what you were saying when they did. One turns a
transcript into an edit decision list. One finds the Shorts already hiding inside a long video. One
goes and finds what is working in your niche and ranks it by how far each video beat its own
channel, not by how big the channel is.

**Nothing gets published until you do it.** These skills write. You upload.

## Install

Paste this into Claude:

```
https://github.com/abdulmoiz14/yt-agent

Install this skill, then confirm /yt-script works.
```

Or do it yourself, in Claude Code:

```bash
git clone https://github.com/abdulmoiz14/yt-agent.git
cp -r yt-agent/skills/yt-* ~/.claude/skills/
mkdir -p ~/.claude/agents && cp yt-agent/agents/*.md ~/.claude/agents/   # for /yt-produce
```

Or as a plugin:

```
/plugin marketplace add abdulmoiz14/yt-agent
/plugin install youtube-agent
```

Project-local instead of global: copy the same folders into your repo's `.claude/skills/`. No Claude
Code at all? Paste any single `SKILL.md` at the top of a chat and it runs as a mode. You lose the six
Python tools, which is most of the point of `/yt-script`, `/yt-retention` and `/yt-edit`, but the
rest works.

Then spend ten minutes on [`templates/voice.md`](templates/voice.md). Copy it to
`~/.claude/youtube/voice.md` and fill it in, or send Claude three of your own videos and say "write
my voice.md from these". Every skill reads that file. It matters more here than anywhere else,
because you have to say the words out loud.

## The thirteen

| command | what it does |
| --- | --- |
| `/yt-script` | One idea into a script. Five hooks off [21 formulas](skills/yt-script/hooks.json), scored, then the spoken script with the retention beats marked. |
| `/yt-package` | Title and thumbnail as one pairing, linted for truncation, duplication and vagueness. |
| `/yt-edit` | A transcript into an edit decision list: dead air, filler cues, retakes, with timecodes. |
| `/yt-comment` | The comment section triaged into four piles, then replies in your voice. Says which one to pin. |
| `/yt-plan` | A week that fits the hours you actually have. One anchor, one cheap one, three Shorts. |
| `/yt-viral` | What is working in your niche, ranked by multiple over each channel's own median. |
| `/yt-retention` | Your retention export read properly: hook leak, the cliffs, the slide, and what to change. |
| `/yt-shorts` | The Shorts already inside a long video, with a new first line written for each. |
| `/yt-seo` | The description, the tags that are worth having, and the three queries this should win. |
| `/yt-chapters` | Chapters from a transcript, validated against YouTube's own rules so they render. |
| `/yt-audit` | The whole channel, ending in ONE fix rather than twenty. |
| `/yt-images` | Scene images and the thumbnail for a faceless video: prompts from the narration, one style and fixed characters, a spending limit, three test images first, an independent image review, your approval. Default model gpt-image-2-c (OpenLux). Labelled "AI illustration" everywhere. |
| `/yt-produce` | One video end to end in its own folder: research, verified sources, an independent fact-check, then the skills above in order - voiceover, images and a slideshow render with crossfades, camera moves and title cards. Resumable. Stops at an upload pack that waits for you. |

## The producer

`/yt-produce <topic>` runs one video through every stage and keeps it in
`~/youtube-productions/<date>-<slug>/`, with `project.json` and `STATUS.md` recording what is done,
what is waiting on you, and what could not be done on this machine. `/yt-produce resume` picks up
where it stopped. It writes nothing the other skills already write - it calls them.

Research, source verification and fact-checking are three separate passes. The fact-check is done by
a separate agent (`agents/yt-fact-checker.md`) that did not write the script, and generated images are
checked by another (`agents/yt-image-reviewer.md`) that did not write the prompts. The outline, hooks
and script come from `agents/yt-writer.md`. The writer and fact-checker are pinned to Opus and the image
reviewer to Sonnet in their own files, so you can run the session itself on Sonnet
(`claude --model sonnet`) and never switch by hand. Stages that need a
tool you do not have (local TTS, whisper, yt-dlp, an image-model key) are marked unavailable with the
manual alternative, never reported as done.

For a faceless, narrated channel: [`templates/voice-narrator.md`](templates/voice-narrator.md) is the
voice profile shape, `hookscore.py --set history` scores documentary hooks
([formulas](skills/yt-script/hooks-history.json)), and `render.py` makes the slideshow - slow pans and
zooms, crossfades, designed date/chapter cards, optional transition sounds and a ducked music bed.

```bash
python3 skills/yt-produce/state.py check-tools                 # what this machine can do
python3 skills/yt-produce/qa.py [project]                      # the pre-handoff checks
python3 skills/yt-produce/tests/test_produce.py                # tests
python3 skills/yt-images/tests/test_images.py                  # tests (images, no network)
```

It ends at `publish/upload-pack.md` marked NOT UPLOADED and waits for your explicit approval. Even
then, you upload.

## The six tools

Every one of these runs on a clean Python 3 with no dependencies. They are the reason the skills are
not just prompts.

```bash
python3 skills/yt-script/hookscore.py --hook "one line"        # 5-property hook panel
python3 skills/yt-package/title.py --title "..." --thumb "..." # title + thumbnail linter
python3 skills/yt-edit/deadair.py transcript.srt               # edit decision list
python3 skills/yt-chapters/chapters.py transcript.srt          # validated chapters
python3 skills/yt-retention/retention.py retention.csv         # where they left, and why
python3 skills/yt-viral/swipe.py collected.json --min 2.0      # outliers by own-channel multiple
```

## The fine print

The part most packs leave out.

**It does not publish.** YouTube's Data API would allow it with your own OAuth, which makes this
pack different from the LinkedIn and Instagram ones, where posting is not available at all. It is
still not built here: every skill ends in a block you copy and a question — ship it, or change it?
Anything that claims to run your channel unattended should be read with that distinction in mind.

**`hookscore.py` is a heuristic, not a predictor.** The panel was built and calibrated against 74
real short-form hooks (the first 15 seconds of auto-captions, top-8 and bottom-8 by views across
five channels). It separates deliberately bad hooks from real ones well. It separates a given
creator's hits from their own misses barely at all. A low score is a reason to look again; a high
score is not a promise.

**The formula classifier is about the words, not the result.** When `/yt-viral` says a title used
The Statistic, that is a judgement about the title you can see, not a claim about why the video got
its views.

**`/yt-viral` reads, it does not scrape.** Public listings only. It never logs in as you and never
touches your credentials.

**Tags barely matter** and this pack says so instead of selling you a tag generator.

**AI images are labelled, and they cost money.** `/yt-images` sends prompts to the image service you
chose with the key you saved in `~/.config/yt-claude/yt-images/openlux.key` (never in a repo, never in
chat). Every run prints its estimate and refuses to go above the spending limit you gave it. The
images are illustrations: the video carries an "AI illustration" label, the description says so, and
QA fails if either is missing.

**Nothing invents a number.** If a skill wants a figure it does not have, it asks you for it or
writes the line without it.

## Licence

MIT. Use it, change it, ship it.
