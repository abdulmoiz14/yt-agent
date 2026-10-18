#!/usr/bin/env python3
"""collect.py - turn yt-dlp channel listings into the input /yt-viral's swipe.py expects. Local only.

    yt-dlp --flat-playlist -J --playlist-end 30 "https://www.youtube.com/@SomeChannel/videos" > research/niche/somechannel.json
    python3 collect.py research/niche/*.json -o research/niche/collected.json
    python3 ../yt-viral/swipe.py research/niche/collected.json --min 2.0

Reads public listing data that yt-dlp already saved; it makes no network calls itself and never
logs in. Rows without a view count are dropped and counted, never guessed. swipe.py needs at
least four videos per channel; channels with fewer are reported here too.
"""
import json, sys
from pathlib import Path


def rows_from(path):
    d = json.loads(Path(path).read_text())
    channel = d.get("channel") or d.get("uploader") or d.get("title") or Path(path).stem
    out, dropped = [], 0
    for e in d.get("entries") or []:
        if not isinstance(e, dict): continue
        views = e.get("view_count")
        if not isinstance(views, (int, float)): dropped += 1; continue
        url = e.get("url") or (f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") else "")
        if url and not url.startswith("http"): url = f"https://www.youtube.com/watch?v={url}"
        out.append({"channel": e.get("channel") or channel, "title": e.get("title") or "", "views": int(views),
                    "url": url, "duration": e.get("duration")})
    return channel, out, dropped


def main():
    a = sys.argv[1:]
    out = Path(a[a.index("-o") + 1]) if "-o" in a else None
    files = [x for i, x in enumerate(a) if x != "-o" and (i == 0 or a[i - 1] != "-o")]
    if not files or not out: print(__doc__); sys.exit(2)
    allrows = []
    for f in files:
        try: ch, rows, dropped = rows_from(f)
        except (OSError, json.JSONDecodeError) as e: print(f"skip {f}: {e.__class__.__name__}"); continue
        note = f"{len(rows)} videos" + (f", {dropped} without a view count dropped" if dropped else "")
        if len(rows) < 4: note += " - fewer than 4, swipe.py will skip this channel"
        print(f"{ch}: {note}")
        allrows += rows
    out.write_text(json.dumps(allrows, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(allrows)} videos)")
    sys.exit(0 if allrows else 1)


if __name__ == "__main__":
    main()
