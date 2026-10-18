# Stage: visuals

Goal: a plan the creator (or an editor) can execute. This stage plans; the pictures are made later,
in the `images` stage (`/yt-images`, paid, with the creator's spending limit and approval) once the
voiceover gives exact line timings - or found as cleared public-domain images (`stages/render.md`).

## `visuals/shotlist.md`

A table built from the `[ON SCREEN: ...]` marks in `script/script.md`, one row per beat:

| beat | time (at 150 wpm) | spoken line (first words) | visual | type | source / how to get it | status |

`type`: talking head, map, diagram, archival image, text on screen, B-roll, reconstruction,
AI illustration, title card (a date or chapter: `"kind": "title"` in the images stage, drawn by render.py).
`status`: `have`, `find`, `make`, `need decision`.

Flag any beat longer than ~20 seconds with no visual change.

## `visuals/assets.md`

For every visual that is not made from scratch:

- what it is, and the exact page it came from (a URL you actually opened, e.g. a Wikimedia
  Commons file page, a museum collection record), or `TO FIND` with a search suggestion
- licence **as stated on that page** (public domain, CC BY 4.0 with required attribution, etc.),
  or `licence unknown - do not use until checked`
- attribution line if the licence requires one

Maps and diagrams: list what they must show and which claim id (`{C7}`) they illustrate, so a
visual cannot assert more than the ledger supports. Do not trace or reproduce copyrighted maps.

Thumbnail: link to `package/thumbnail-brief.md`; do not redesign it here.

AI illustrations are listed here as `AI illustration - made in the images stage`; they are never
presented as archival. Unavailable in this version (say so in the file): stock-library search with
licensing, automatic asset download.
