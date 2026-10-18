# Stage: niche (optional) - /yt-viral

Goal: what is already working in this video's niche, ranked by how far each video beat its own
channel's median - before choosing the angle. Read-only, public listings, never logged in.

1. Needs `niche_research` available (yt-dlp). If not: mark `unavailable` with "install yt-dlp
   (`pipx install yt-dlp` or `pip install --user yt-dlp`), or give me a list of channel videos",
   or `needs_input` if the creator will paste a list. Do not estimate view counts.
2. Ask the creator for 3-6 channels in their niche, or propose some from a web search and let them
   confirm. Then, for each:
   ```bash
   mkdir -p research/niche
   yt-dlp --flat-playlist -J --playlist-end 30 "https://www.youtube.com/@CHANNEL/videos" > research/niche/CHANNEL.json
   ```
   Record each command and exit code. A failure is reported, not retried with other tools.
3. `python3 "$S/collect.py" research/niche/*.json -o research/niche/collected.json`
   then `python3 "$S/../yt-viral/swipe.py" research/niche/collected.json --min 2.0 > research/niche/swipe.txt`
4. Follow `/yt-viral` for the write-up in `research/niche.md`: the top five with their multiples,
   the formula each title used (a judgement about the title, not why it worked - say so), the ONE
   thing they share, and which the creator could make this week. Feed it into the research angles.
