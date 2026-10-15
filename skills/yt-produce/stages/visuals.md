# Stage: visuals

Goal: a plan the creator (or an editor) can execute. Planning only - no image generation is
available in this version, and none is pretended.

## `visuals/shotlist.md`

A table built from the `[ON SCREEN: ...]` marks in `script/script.md`, one row per beat:

| beat | time (at 150 wpm) | spoken line (first words) | visual | type | source / how to get it | status |

`type`: talking head, map, diagram, archival image, text on screen, B-roll, reconstruction.
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

Unavailable in this version (say so in the file): image generation, stock-library search with
licensing, automatic asset download.
