# Stage: narration

Goal: a script that can be read aloud cleanly on the first take.

## `narration/narration.md`

From the fact-checked `script/script.md`:

- Spoken words only, in the creator's voice; `[ON SCREEN]` marks and claim ids `{C4}` removed.
- One sentence per line. Break any sentence over ~25 words.
- `/` for a short breath, `[PAUSE]` for a beat, **bold** for the word to stress - sparingly.
- Numbers and dates written the way they should be said ("fourteen fifty-three", "about eighty
  thousand"), keeping the hedges the fact-check required.
- At the top, as a quote line so it is never read aloud: `> Spoken words: 451 - about 3:00 at 150 wpm`
  (`qa.py` recomputes this; `tts.py` skips headings, quotes and lines like "Runtime: ...").

## `narration/pronunciation.md`

Every name, place and foreign term, with a plain-English respelling (e.g. "Mehmed - MEH-med").
History channels: Latin and Greek names are where synthetic voices fail most (Gaius = GUY-us,
Caesar = SEE-zer in English narration, Augustus = aw-GUS-tus, Cannae = KAN-ee). Pick one convention,
the usual English one, and keep it for the whole channel.
Only give a pronunciation you are confident of; otherwise write `CHECK` and, if a source gives
one, cite it by id.

## Voiceover with Kokoro (local, free, no API key)

Only if `narration_audio` shows `tts:kokoro` available (Qwen3-TTS, below, is the more natural
option on a capable machine; let the creator choose after hearing both). First ask the creator which they want -
never assume:

- **Final voiceover** - the synthetic voice IS the narration. Requires every `CHECK` in
  `pronunciation.md` resolved first. If their voice profile says they narrate themselves, point
  that out and suggest they update it.
- **Scratch track** - a timing guide they will replace with their own recording (`--allow-check`).

1. Write `narration/tts-lexicon.txt`: one `Word = respelling` line per name or term from
   `pronunciation.md`, spelled the way Kokoro should say it (e.g. `Sphrantzes = Sfrant-zess`).
2. Preview what will be spoken, then generate:
   ```bash
   python3 "$S/tts.py" narration/narration.md --dry-run --lexicon narration/tts-lexicon.txt
   ~/.local/share/yt-tts/venv/bin/python "$S/tts.py" narration/narration.md \
       -o narration/voiceover.wav --voice am_michael --lexicon narration/tts-lexicon.txt
   ```
   Record the real command and exit code with `state.py set ... --cmd ... --exit ...`.
   Voices: `am_michael`, `am_adam` (American male), `af_heart`, `af_bella` (American female),
   `bm_george`, `bm_lewis` (British male), `bf_emma` (British female). Let the creator pick after
   hearing a short sample; `--speed 0.95` slows it slightly. Want a higher or lower voice? Try
   another voice (e.g. `am_puck`, `am_liam`, `bm_fable` are lighter males), or keep this one and
   use `render.py --pitch 1.08` at assembly.
3. Tell the creator to listen to the whole file - especially every name. Fix the lexicon and
   regenerate until they are happy. `voiceover.json` has each line's start and end time.

Any edit to `narration.md` after the voiceover makes it stale (QA warns); regenerate it.

If Kokoro is not available: write in `narration.md` "Voiceover: unavailable (no local TTS). Record a
read-through yourself." Never configure a cloud or paid voice service.

## Voiceover with Qwen3-TTS (local, free, no API key)

More natural than Kokoro, and the voice can be described in words. Only if `tts:qwen` is available,
and realistically only on Apple Silicon (MPS) or an NVIDIA GPU - on CPU it can take far too long;
say so instead of leaving it running. Same rules as Kokoro: ask final or scratch, resolve every CHECK.

1. **Design the narrator once.** Ask the creator to describe the voice, then:
   ```bash
   ~/.local/share/qwen-tts/venv/bin/python "$S/tts.py" design-ref narration/voice-ref.wav \
       --instruct "<their description, e.g. warm, slightly higher-pitched male documentary narrator>"
   ```
   They listen; repeat with a changed description until they like it. This writes `voice-ref.wav`
   and `voice-ref.txt` (its transcript).
2. **Narrate in that voice** by cloning the reference with the Base model, so every line sounds
   like the same person (VoiceDesign alone re-creates the voice on every call and can drift):
   ```bash
   ~/.local/share/qwen-tts/venv/bin/python "$S/tts.py" narration/narration.md --engine qwen \
       --qwen-mode clone --ref-audio narration/voice-ref.wav --lexicon narration/tts-lexicon.txt \
       -o narration/voiceover.wav
   ```
3. Tell the creator to listen to **all** of it: Qwen has been reported to add laughter or words that
   are not in the text, and it has no pronunciation control beyond respelling in the lexicon.

Other modes: `--qwen-mode custom --speaker Ryan` uses a preset voice (whether preset voices are
cleared for monetized use is an open question upstream - prefer a designed voice or the creator's
own); `--qwen-mode clone --ref-audio their-own-voice.wav --ref-text "what they said"` clones the
creator's own recording. Never clone a voice without that person's permission.

## Installing Qwen3-TTS (only when the creator asks)

Not inside `~/yt` or the skills repo - its own environment, Python 3.12:

```bash
python3.12 -m venv ~/.local/share/qwen-tts/venv     # or: uv venv --python 3.12 ~/.local/share/qwen-tts/venv
~/.local/share/qwen-tts/venv/bin/pip install -U pip qwen-tts soundfile
# macOS: brew install sox   |   Ubuntu: sudo apt install sox   (the creator runs these)
```

Model weights (about 2.5 GB for 0.6B, 4.5 GB for 1.7B) download on first use from Hugging Face.
Check the model card's licence (Apache 2.0 at the time of writing) before first use, then re-run
`state.py check-tools <p>`.

## Installing Kokoro (only when the creator asks)

Run on the creator's machine, in a dedicated virtual environment so nothing touches system Python:

```bash
sudo apt install -y espeak-ng          # the creator runs this - it needs their password
python3 -m venv ~/.local/share/yt-tts/venv
~/.local/share/yt-tts/venv/bin/pip install --upgrade pip
# No NVIDIA GPU: the CPU build of PyTorch avoids a multi-GB CUDA download
~/.local/share/yt-tts/venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
~/.local/share/yt-tts/venv/bin/pip install "kokoro>=0.9" soundfile
```

The first synthesis downloads the free Kokoro-82M model (Apache 2.0, about 330 MB) from Hugging
Face. Then re-run `state.py check-tools <p>`. Report every failed step honestly; do not switch to
a different engine or service without asking.
