# Stages after publishing (optional)

These only make sense once the creator has published the video themselves. Each one waits for
something only the creator can give; mark it `needs_input` with exactly what is needed, never
simulate it.

## retention - /yt-retention
Needs the retention CSV (Studio → the video → Analytics → Engagement → audience retention →
download). Then `python3 "$S/../yt-retention/retention.py" <csv> --transcript post/transcript.srt`
→ `post/retention.md`, following `/yt-retention`: the single biggest leak, what was being said there
(the transcript makes this exact), and one change. Feed the lesson into the next video's brief.

## comments - /yt-comment ✋
Needs the comments pasted in. Follow `/yt-comment`: four piles with counts, replies under 30 words in
the creator's voice, which one to pin → `post/comments.md`. Nothing is posted; the creator copies the replies.

## audit - /yt-audit
Needs the channel URL, and ideally the last ten titles and thumbnails (yt-dlp can list titles from
public pages if available). Follow `/yt-audit`, ending in ONE fix → `post/channel-audit.md`.
