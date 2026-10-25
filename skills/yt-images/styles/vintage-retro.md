# vintage-retro

A warm, faded vintage film still: a frame from a worn 1950s Technicolor sword-and-sandal epic, seen on an old print.
Made from the style test `_style-tests/romulus-remus-retro` (look A, `scene_001.png`). It must never look cartoonish,
comic or glossy-modern.

This is a prompt recipe, not a JSON preset (the JSON presets in this folder are unchanged). Put the **style** text in
`prompts.json` `"style"`, the **negative** text in `"negative"`, and write each scene's prompt as what happens in it.

## style

1950s Technicolor epic film still, like a frame from a classic sword-and-sandal movie: saturated but faded colours, warm golden sun, wide cinematic framing. Warm faded vintage film look: sepia and muted teal tones, soft sunlit colour, visible film grain, light dust and scratches, slightly soft focus, worn print feel. Realistic proportions and natural faces, painterly film realism. Period-correct ancient Rome, nothing modern. No castles, no heraldic banners or animal emblems, no medieval crowns (only a plain gold circlet where a king appears), no turbans, no bell towers, no crosses, no medieval or East Asian clothing

## negative

text, letters, numbers, words, captions, signs, watermark, logo, signature, extra limbs, extra arms, extra hands, extra legs, extra fingers, deformed hands, distorted face, modern objects, anachronisms, cars, drive-in, 1950s American scene, cartoon, comic book, children's book illustration, anime, thick outlines, glossy modern digital look, 3D render

## Rules kept from the earlier Rome style

- No text, letters, numbers, signs or logos anywhere in the image. Dates and names are drawn by the renderer, never inside a picture.
- Every person has exactly two arms, two hands and two legs and a normal face with both eyes open; say so in the scene prompt when hands matter ("each person has exactly two arms and two hands").
- Period-correct ancient Rome: togas, tunics, cloaks, bronze armour, stone and brick, nothing modern, nothing medieval.
- No real person's likeness; named characters come from the `characters` block, so they look the same in every scene.
- 16:9 landscape, main subject clear of the bottom fifth where captions sit.
- Every generated image is an "AI illustration". The vintage grain is a style, not a claim that the picture is an old photograph or an archive item.

## Reviewer note

The reviewer's check 8 ("misleading realism / too photographic") does not apply to this style on its own: film grain,
dust and scratches are the look. Still a redo: a picture that looks like a modern digital photo, or a real person.

## Taking only the mood from a reference

If a reference picture is used, take its colour, grain and photographic mood only, never its content.
