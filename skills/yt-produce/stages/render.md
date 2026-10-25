# Stage: render (video assembly)

Goal: a watchable video built locally with ffmpeg from the voiceover, cleared images and captions.
No generative video, no cloud renderer. Needs `narration/voiceover.wav` (tts.py).

**If the images stage ran**, `visuals/plan.json` already exists (`images.py plan`): skip to step 3.
It holds the approved AI illustrations (licence "AI illustration - creator-generated"), designed
title cards, and placeholder cards for anything not approved. Public-domain images from step 1 can be
added to it as extra entries.

## 1. Gather images - only ones you can clear

For each row of `visuals/shotlist.md`, look for a real image. For history, Wikimedia Commons is the
first stop: paintings, manuscripts, maps and photos whose file page states the licence.

1. Open the Commons **file page** (`https://commons.wikimedia.org/wiki/File:...`) and copy the
   licence exactly as stated there (e.g. "Public domain", "CC BY-SA 4.0") and the author/attribution
   line it asks for.
2. Download the original with curl into `visuals/images/` (the "Original file" link on that page,
   on `upload.wikimedia.org`). Record the command and exit code.
3. Add it to `visuals/assets.md` with the file page URL, licence and attribution.

Never use an image whose licence you have not read on its own page, never trace a copyrighted map,
and never generate images and present them as historical. If the creator supplies their own images
(including AI-generated ones they made), record `"licence": "creator-supplied"` and, for generated
ones, label them on screen as illustrations.

Maps and diagrams you cannot find cleared stay as title cards for now - render.py draws them.

## 2. Write `visuals/plan.json`

Line numbers come from `python3 "$S/render.py" <project> --list-lines` (0-based; `[PAUSE]` lines count). One entry per visual
change, in order, first at `start_line` 0:

```json
[{"start_line": 0, "image": "visuals/images/theodosian-walls.jpg", "licence": "CC BY-SA 4.0",
  "source_url": "https://commons.wikimedia.org/wiki/File:...", "attribution": "Photo: <author>, CC BY-SA 4.0",
  "card": "The Theodosian land walls"},
 {"start_line": 4, "image": null, "card": "Map: the ships hauled overland into the Golden Horn"}]
```

Aim for a change every 5-12 seconds. `card` is always required: it is what shows if the image is
missing or not cleared. A visual must not assert more than the claim it illustrates (`{C7}`).

Designed title cards for dates and chapters - finished parts of the video, not placeholders:
`{"start_line": 12, "kind": "title", "card": "44 BC", "subtitle": "The Ides of March"}` (add a
cleared `image` and `licence` to show it blurred behind the text). A title every few minutes
breaks up a long slideshow the way the reference channels do.

Each image gets a slow camera move, varied automatically; set one with `"motion": "zoom_in"`,
`zoom_out`, `pan_left`, `pan_right`, `pan_up` or `pan_down` when a picture needs it (pan across a
wide landscape, zoom in on a face).

## 3. Render

```bash
python3 "$S/render.py" <project> --dry-run          # check the timeline first
python3 "$S/render.py" <project> [--pitch 1.08]      # 1920x1080, burned captions, crossfades
```

Options to ask the creator about - never switch them on silently:

- `--sfx whoosh` (or `click`): a quiet sound on every picture change, made here by ffmpeg (nothing to
  license). Some viewers like it; on a calm history video a whoosh every few seconds can grate - let
  them hear a minute of each.
- `--music track.mp3 --music-licence "YouTube Audio Library, <track>, no attribution required"`: a bed
  under the voice, ducked while the narrator speaks (`--music-volume 0.12` default). Only a track they
  have the rights to, and the licence text is required - it goes into `credits.txt`.
- `--transition cut` for hard cuts instead of crossfades.

AI illustrations make render.py burn a small "AI illustration" label into the corner for the whole
video (`--label-text` rewords it). Only the creator can turn it off, by writing `ai_label: off` with the
date and the reason in the project's `brief.md` (or the channel notes it points to with `channel_notes:`;
see `settings.py`); never switch it off on your own. When it is off, the description must still say the
images are AI-generated, and `qa.py` reports "label off by creator decision".

Output: `render/draft.mp4` while any placeholder card remains, `render/video.mp4` once every segment
is a cleared image. Also `render/captions.srt` (upload it to YouTube too), `render/credits.txt` (put
it in the description) and `render/render.json`. Record the command and exit code; mark the stage
done when the files exist.

`--pitch` raises (>1) or lowers (<1) the voice without changing speed - 1.05-1.12 sounds natural.
For a different voice instead, regenerate with tts.py and another `--voice`.

## 4. Checkpoint

Tell the creator where the file is and ask them to watch it all (you cannot watch it). List every
placeholder card and every attribution. A draft with cards is a draft - say so, never call it final.

## One-minute vertical Short (optional, only when asked)

A Short needs its own narration, not a cut-down render:

1. Write `narration/short.md` (45-55 seconds, ~120 words) using ONLY claims the fact-check
   supported, with the hedges intact. Show it to the creator first.
2. `tts.py narration/short.md -o narration/short-voiceover.wav ...` (same voice and lexicon).
3. `visuals/short-plan.json`, then `render.py <project> --variant short --vertical`
   → `render/short/draft.mp4` or `video.mp4`.
