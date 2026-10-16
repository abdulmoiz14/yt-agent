# Stage: render (video assembly)

Goal: a watchable video built locally with ffmpeg from the voiceover, cleared images and captions.
No generative video, no cloud renderer, no API key. Needs `narration/voiceover.wav` (tts.py).

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

Line numbers are the order of `narration/voiceover.json` → `lines` (0-based). One entry per visual
change, in order, first at `start_line` 0:

```json
[{"start_line": 0, "image": "visuals/images/theodosian-walls.jpg", "licence": "CC BY-SA 4.0",
  "source_url": "https://commons.wikimedia.org/wiki/File:...", "attribution": "Photo: <author>, CC BY-SA 4.0",
  "card": "The Theodosian land walls"},
 {"start_line": 4, "image": null, "card": "Map: the ships hauled overland into the Golden Horn"}]
```

Aim for a change every 5-12 seconds. `card` is always required: it is what shows if the image is
missing or not cleared. A visual must not assert more than the claim it illustrates (`{C7}`).

## 3. Render

```bash
python3 "$S/render.py" <project> --dry-run          # check the timeline first
python3 "$S/render.py" <project> [--pitch 1.08]      # 1920x1080, burned captions
```

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
