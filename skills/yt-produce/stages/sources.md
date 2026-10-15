# Stage: sources (verification)

Goal: a list of sources that has been checked one by one, so every later claim can point at
something real. This is a separate pass from research: re-open each source rather than trusting
your notes.

## For each source you intend to cite

1. WebFetch it again (or read the file the creator gave you).
2. If it does not load, is paywalled, or does not say what the notes say, drop it or downgrade it.
   Record what happened in `research/sources.md` under "Dropped".
3. Copy the exact passage that supports the point - a sentence or two, verbatim - into `quote`.
4. Assign a tier honestly: `primary`, `scholarly`, `secondary`, `weak`.

## `research/sources.json`

```json
[
 {"id": "S1",
  "title": "Page or work title, as it appears",
  "publisher": "Who published it",
  "url": "https://the exact url you fetched",
  "retrieved": "2026-10-16",
  "accessed_via": "web_fetch",
  "tier": "scholarly",
  "quote": "Verbatim passage copied from the fetched page.",
  "notes": "Anything relevant: author, date, bias, what it does not cover."}
]
```

`accessed_via`: `web_fetch` (url required), `user_provided` or `local_file` (url, `path` or full
`citation` required). `qa.py --gate sources` enforces the shape. It cannot check that the quote is
on the page - that is your job here and the fact-checker's job later.

`research/sources.md`: the same list for humans - id, title, tier, one line on what it supports -
plus a "Dropped" section.

## Never

Invent, guess or "reconstruct" a URL, title, author, date or quote. A source you cannot re-open
does not go in the list.
