# Stages after the voiceover or recording

Run with `state.py next <p> --post`. These need a transcript. A synthetic voiceover already has an
exact one: `tts.py` writes `narration/voiceover.srt` beside the WAV. A self-recorded video needs
the recording's transcript instead.

## post_transcript
- **Synthetic voiceover:** `cp narration/voiceover.srt post/transcript.srt`, note "transcript from
  the TTS timing - exact for the voiceover, not a recording". Regenerate it whenever the voiceover changes.
- **Own recording:** local whisper if `transcription` is available, else `needs_input` asking for an
  .srt/.vtt (YouTube's auto-captions on an unlisted upload work). Never invent timings.

## post_edit - /yt-edit
`python3 "$S/../yt-edit/deadair.py" post/transcript.srt > post/edl.txt`. On a synthetic voiceover
there are no ums or retakes; say so, and read the report as a pacing check (long pauses, abrupt
lines). On a recording, follow `/yt-edit` fully. It never touches media.

## post_chapters - /yt-chapters
`python3 "$S/../yt-chapters/chapters.py" post/transcript.srt --target 6`, then retitle every line in
the creator's voice (3-5 words, the promise of that section) → `post/chapters.txt`. It must pass the
rules (00:00 first, at least three, each 10 s or longer). Then replace the provisional chapters in
`seo/description.md` and the upload pack. If the pack was approved, that changes it:
`state.py set <p> handoff awaiting_approval --note "chapters updated from the real audio"` clears
the old approval; show the creator the change and ask again.

## post_shorts - /yt-shorts
Follow `/yt-shorts` on the transcript: spans of 20-55 s that open on a complete thought, have a
turn, and end on a line. Show the top five with time codes AND their line numbers from
`python3 "$S/render.py" <p> --list-lines` (0-based; `[PAUSE]` lines count) so they can be cut. For each: a NEW first line (only claims the
fact-check supported, hedges kept), scored with `hookscore.py`, on-screen text for the first two
seconds in different words, the loop point, and the vertical-crop note → `post/shorts.md`.

## post_short_render (optional) ✋
For the Shorts the creator picks (one to three):
1. Write the new first line to `narration/short-N-intro.md` and voice it with the SAME engine, voice
   and lexicon as the long video → `narration/short-N-intro.wav` (+ `.json`).
2. `python3 "$S/render.py" <p> --clip A B --intro-audio narration/short-N-intro.wav --hook-text "<2-second words>" --name short-N`
   (A, B = the line numbers; vertical by default) → `render/shorts/short-N/`.
3. Ask the creator to watch each. Same picture rules as the long video: cards until images are cleared.

## schedule (optional) - /yt-plan ✋
Ask the two `/yt-plan` questions first: hours available this week, and the best upload day from their
own analytics. Then the week: this video as the anchor, one cheap follow-up, the rendered Shorts as
the three Shorts → `publish/plan.md`. A plan only - nothing is scheduled on YouTube.
