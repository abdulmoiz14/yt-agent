#!/usr/bin/env python3
"""quotecheck.py - does this quote actually appear in this saved page? Local and deterministic.

    curl -sL --max-time 30 -A "Mozilla/5.0" "<url>" -o research/pages/S1.html   # download first
    python3 quotecheck.py research/pages/S1.html "the exact quote"
    python3 quotecheck.py research/pages/S1.html --file quote.txt

Exit 0 and prints MATCH if the quote is on the page; exit 1 and prints NO MATCH with the closest
passage otherwise. HTML is reduced to visible text. Matching ignores case, whitespace, curly vs
straight quotes, dash style and footnote markers like [12]. It does not paraphrase-match: a
summary of the page is not the page. No network: it only reads the file you give it.
"""
import difflib, html, re, sys
from html.parser import HTMLParser
from pathlib import Path


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "template"}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out, self.depth = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.depth += 1
    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth: self.depth -= 1
    def handle_data(self, d):
        if not self.depth: self.out.append(d)


def page_text(path):
    raw = Path(path).read_text(errors="replace")
    if re.search(r"<(html|body|p|div)\b", raw[:5000], re.I):
        p = _Text(); p.feed(raw); raw = " ".join(p.out)
    return html.unescape(raw)


def norm(t):
    t = t.lower()
    t = re.sub(r"\[\s*(\d+|[a-z]|citation needed|note \d+)\s*\]", " ", t)   # footnote markers
    t = t.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " "}))
    t = re.sub(r"\s*-\s*", "-", t)
    return re.sub(r"\s+", " ", t).strip()


def check(page_path, quote):
    """Return (matched: bool, closest: str)."""
    text, q = norm(page_text(page_path)), norm(quote).strip(" .\"'")
    if not q: return False, ""
    if q in text: return True, q
    m = difflib.SequenceMatcher(None, text, q, autojunk=False).find_longest_match(0, len(text), 0, len(q))
    start = max(0, m.a - m.b)
    return False, text[start:start + len(q) + 40]


def main():
    a = sys.argv[1:]
    if len(a) < 2: print(__doc__); sys.exit(2)
    quote = Path(a[2]).read_text() if a[1] == "--file" and len(a) > 2 else a[1]
    if not Path(a[0]).exists(): print(f"NO PAGE  {a[0]} does not exist - download it first"); sys.exit(2)
    ok, closest = check(a[0], quote)
    if ok: print("MATCH"); sys.exit(0)
    print("NO MATCH\n  closest passage on the page:\n  " + (closest or "(nothing similar)")); sys.exit(1)


if __name__ == "__main__":
    main()
