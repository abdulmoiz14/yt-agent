#!/usr/bin/env python3
"""settings.py - the creator's explicit per-project / per-channel options that render.py and qa.py both honour.

ai_label: on | off   whether the on-screen "AI illustration" label is burned into the video (default: on).
    Written as a line anywhere in the project's brief.md ("project notes") or in the channel notes file, e.g.
        ai_label: off - 2026-10-22, creator's decision; disclosure is in the description
    The project's brief.md wins over the channel notes; a line in brief.md `channel_notes: ~/path/to/CLAUDE.md` names the
    channel file. Off never removes the disclosure line from the description - qa.py still requires that.

    python3 settings.py <project folder>     prints the setting, where it came from and the note
"""
import re, sys
from pathlib import Path

# Every description draft and upload pack carries this line, followed by the sources (qa.py checks both).
DISCLOSURE = "Narration and illustrations in this video are AI-generated. The script is researched from the sources listed below."
LINE = re.compile(r"(?im)^[ \t>*\-]*ai_label[ \t]*:[ \t]*(on|off)\b[ \t]*[-:,;]?[ \t]*(.*)$")
CHANNEL = re.compile(r"(?im)^[ \t>*\-]*channel_notes[ \t]*:[ \t]*(\S.*?)[ \t]*$")


def _read(p):
    try: return Path(p).expanduser().read_text(errors="replace")
    except OSError: return ""


def ai_label(pdir):
    """(value, source, note): value is 'on' or 'off'. Not set anywhere means 'on' - the label is the default and must be present."""
    pdir = Path(pdir)
    brief = _read(pdir / "brief.md")
    m = LINE.search(brief)
    if m: return m.group(1).lower(), "brief.md", m.group(2).strip()
    c = CHANNEL.search(brief)
    if c:
        path = Path(c.group(1)).expanduser()
        m = LINE.search(_read(path))
        if m: return m.group(1).lower(), str(path), m.group(2).strip()
    return "on", "default", ""


def disclosure_problem(text):
    """None when `text` has the disclosure line followed by at least one source link, otherwise what is missing."""
    flat = re.sub(r"\s+", " ", text)
    i = flat.find(DISCLOSURE)
    if i < 0: return f"the line '{DISCLOSURE}' is missing"
    if not re.search(r"https?://", flat[i + len(DISCLOSURE):]): return "no source link follows the disclosure line"
    return None


if __name__ == "__main__":
    if len(sys.argv) != 2: print(__doc__); sys.exit(2)
    v, src, note = ai_label(sys.argv[1]); print(f"ai_label: {v}  (from {src})" + (f" - {note}" if note else ""))

