# Stage: narration

Goal: a script that can be read aloud cleanly on the first take.

## `narration/narration.md`

From the fact-checked `script/script.md`:

- Spoken words only, in the creator's voice; `[ON SCREEN]` marks and claim ids `{C4}` removed.
- One sentence per line. Break any sentence over ~25 words.
- `/` for a short breath, `[PAUSE]` for a beat, **bold** for the word to stress - sparingly.
- Numbers and dates written the way they should be said ("fourteen fifty-three", "about eighty
  thousand"), keeping the hedges the fact-check required.
- At the top: spoken word count and runtime at 150 wpm (`qa.py` recomputes this).

## `narration/pronunciation.md`

Every name, place and foreign term, with a plain-English respelling (e.g. "Mehmed - MEH-med").
Only give a pronunciation you are confident of; otherwise write `CHECK` and, if a source gives
one, cite it by id.

## Optional scratch audio

Only if the `narration_audio` capability is `available` (local `piper` or `espeak-ng`):

```bash
espeak-ng -s 160 -f narration/narration-plain.txt -w narration/scratch.wav   # plain-text copy first
```

Record the command with `--cmd ... --exit <code>`. It is a timing guide, not a voiceover.
If unavailable, write in `narration.md`: "Scratch audio: unavailable (no local TTS). Record a
read-through yourself to check timing." Never configure a cloud or paid voice service.
