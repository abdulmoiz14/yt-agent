# Stage: sources (verification)

Goal: a list of sources that has been checked one by one, so every later claim can point at
something real. This is a separate pass from research: re-open each source rather than trusting
your notes.

## Why not just WebFetch

WebFetch hands back a model-written summary of the page, not the page. A "quote" copied from that
summary may be a paraphrase. So quotes are checked against the raw page text, saved locally.

## For each source you intend to cite

1. Download the raw page (a local tool, no API key):
   ```bash
   mkdir -p research/pages
   curl -sL --max-time 30 -A "Mozilla/5.0" "<exact url>" -o research/pages/S1.html
   ```
   Record it: `state.py set <p> sources in_progress --cmd "curl ... S1" --exit <real code>`.
2. Copy the supporting passage - a sentence or two - and confirm it is on the page:
   ```bash
   python3 "$S/quotecheck.py" research/pages/S1.html "the exact passage"
   ```
   `MATCH` → `"quote_check": "raw_text_match"`, `"page": "research/pages/S1.html"`.
   `NO MATCH` → fix the quote from the closest passage it prints, or drop the source.
3. If the download fails or the page is rendered by JavaScript (empty or near-empty text), you
   may fall back to WebFetch, but mark `"quote_check": "summary_only"`. QA will warn on it and the
   fact-checker will not treat it as full support. A source the creator gave you that you cannot
   open gets `"user_provided_unchecked"`.
4. If it does not load at all, or does not say what the notes say, drop it or downgrade it and
   record what happened in `research/sources.md` under "Dropped".
5. Assign a tier honestly: `primary`, `scholarly`, `secondary`, `weak`. Wikipedia and general
   encyclopedias are `secondary`. For history, try for at least one `primary` (an eyewitness or
   contemporary account in translation) or `scholarly` source; if you cannot get one, say so.

Saved pages are for verification only. Do not quote them at length in the video or the description.

## `research/sources.json`

```json
[
 {"id": "S1",
  "title": "Page or work title, as it appears",
  "publisher": "Who published it",
  "url": "https://the exact url you downloaded",
  "retrieved": "2026-10-16",
  "accessed_via": "web_fetch",
  "tier": "secondary",
  "quote": "Verbatim passage, copied from the saved page.",
  "quote_check": "raw_text_match",
  "page": "research/pages/S1.html",
  "notes": "Author, date, bias, what it does not cover."}
]
```

`accessed_via`: `web_fetch` (url required; use it for curl downloads too), `user_provided` or
`local_file` (url, `path` or full `citation` required). `qa.py --gate sources` enforces the shape
and re-runs `quotecheck.py` on every `raw_text_match`, so a claimed match that is not on the saved
page fails the gate.

`research/sources.md`: the same list for humans - id, title, tier, quote check, one line on what it
supports - plus a "Dropped" section.

## Never

Invent, guess or "reconstruct" a URL, title, author, date or quote. A source you cannot re-open
does not go in the list.
