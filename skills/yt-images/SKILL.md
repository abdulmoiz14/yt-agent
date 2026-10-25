---
name: yt-images
description: >-
  Make the scene images and thumbnail for a faceless video with an image model the creator pays for
  (default gpt-image-2-c via OpenLux) - prompts from the script, one style and fixed characters across
  every scene, a spending limit, a small test batch first, an independent image review, the creator's
  approval, and a render plan. Every image is labelled "AI illustration". Use for "make the images",
  "illustrate the script", "thumbnail", or the images stage of /yt-produce.
---

# yt-images

Pictures for a narrated video, made the slow-is-fast way: three first, look, then the rest.

```bash
python3 images.py init <project> --style natural          # natural | comic | roundhead | stickman
python3 images.py check <project>                         # every prompt as it will be sent + the estimate
python3 images.py generate <project> --limit 3 --max-spend 0.03
python3 images.py generate <project> --max-images 120 --max-spend 1.20
python3 images.py review-todo <project>                  # scenes the review still has to look at (new, not hashed, changed)
python3 images.py review-stamp <project> --scenes 1-6     # after a review run: store the hash of the scenes it finished
python3 images.py approve <project> --scenes all --statement "<the creator's words>"
python3 images.py plan <project>                          # visuals/plan.json for ../yt-produce/render.py
python3 images.py thumb <project> --text "ROME FELL" --from-scene 4
```

## Money and the key

- The images cost real money. Price per image: gpt-image-2-c 0.00882 (billed). `check` prints the estimate.
- **Ask the creator for a spending limit and wait.** Pass it as `--max-spend`. Never raise it yourself;
  the tool refuses a run whose estimate is above it, and stops on a key, credit or rate-limit error
  (401/402/403/429) without retrying.
- The key lives in `~/.config/yt-claude/yt-images/openlux.key` (chmod 600), outside every repo. Never ask
  for it in chat, never print it, never copy it anywhere. If it is missing, tell the creator how to save it:
  `mkdir -p ~/.config/yt-claude/yt-images && read -rs -p "Key: " K && printf '%s' "$K" > ~/.config/yt-claude/yt-images/openlux.key && unset K && chmod 600 ~/.config/yt-claude/yt-images/openlux.key`

## Writing `visuals/prompts.json`

After the voiceover exists, list its lines: `python3 ../yt-produce/render.py <project> --list-lines`.

- **One scene every 6-10 seconds** of narration (a 12-minute video is about 90-110 scenes). Each scene:
  `scene` (1, 2, 3...), `start_line` (the narration line where it appears; the first is 0; one scene per line),
  `prompt`, `script_line`, `card` (a short title shown if the image is not used).
- **The prompt says what is in the frame**, concretely: who, doing what, where, what time of day, how far away
  (wide shot, close-up). No style words - the preset's `style` is added in front by code.
- **Consistency.** Recurring people go in `characters` once (age, build, hair, clothing colours, one prop) and
  each scene lists who appears. Keep the era's architecture, clothing and lighting in the style or the scene text.
- **Vary the shots** - wide establishing, medium action, close detail - so 100 images do not look like one.
- **Title cards** for dates and chapters are scenes with `"kind": "title"`, `card` ("753 BC") and `subtitle`
  ("Rome is founded"). They are drawn by render.py, cost nothing, and break up the slideshow.
- **Never** ask for text, labelled maps, documents, coins with inscriptions, or a real person's likeness; a map
  or a name on screen becomes a title card. An image may not show more than the fact-check ledger supports.
- Optional `motion` per scene: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`.

## Order

1. `check`, then the estimate and the spending question to the creator. Stop until they answer.
2. `generate --limit 3`. Run the **yt-image-reviewer** agent on those three (it looks at each image; you
   do not grade your own pictures). Show the creator `visuals/contact-sheet.html` and the review. Ask: keep
   this look, or change it? Change the style or prompts, regenerate only what they name (`--scenes 2`).
3. `generate` the rest with `--max-images` set to the scene count. Failed scenes: show the error, and run
   `retry` only if they agree.
4. yt-image-reviewer on everything new. Run `review-todo` to list the scenes that need review (new, not
   hashed, or changed). Give the reviewer at most 6 per run, each run in a fresh session, and repeat until none
   are left. After each run, `review-stamp --scenes N-M` for exactly the scenes it finished. Scenes marked
   `redo`: fix the prompt and regenerate (a new version is made; the old file is kept), within the spending limit.
   The review says "look here", it is not approval: the creator checks close-ups with hands in the foreground
   themselves, on a contact sheet of the flagged images.
5. The creator approves - their own words, recorded with `approve --statement`. Unapproved scenes become cards.
6. `plan` writes `visuals/plan.json` for render.py.

## Honesty

Generated images are illustrations. They are recorded as "AI illustration - creator-generated", render.py
burns that label into the video, and the description must say the illustrations are AI-generated. Never
call them photographs, artefacts or archival images. Real public-domain art (Wikimedia Commons, licence
read on the file page) can sit alongside them - see `../yt-produce/stages/render.md`.

## The gate

Nothing here uploads or publishes. Images and thumbnail go to the creator for approval, and the last line
of the producer's run is still the question: **ship it, or change it?**
