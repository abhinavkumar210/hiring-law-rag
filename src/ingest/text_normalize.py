"""Repair text damaged by PDF extraction.

pypdf emits NUL (0x00) where a glyph has no character mapping. In this corpus
that happens on f-ligatures — ff, fi, fl, ft — and it is not cosmetic:

    "four-fi\x00hs"  ->  "four-fifths"

appears 19 times in the EEOC Title VII AI guidance. "Four-fifths" is the central
term of this entire project. Left unrepaired, the one federal document discussing
how the four-fifths rule applies to AI would never match a query about it, and
nothing would have failed loudly enough to notice.

Repairs are table-driven on observed left/right context rather than guessed, and
anything unrepaired is counted and reported rather than silently replaced.
"""
from __future__ import annotations

import re

NUL = chr(0)

# (text before the gap, text after the gap, the missing ligature)
LIGATURE_CONTEXTS: list[tuple[str, str, str]] = [
    ("fi", "hs", "ft"),        # four-fifths
    ("so", "ware", "ft"),      # software
    ("o", "en", "ft"),         # often
    ("a", "er", "ft"),         # after
    ("di", "erent", "ff"),     # different
    ("di", "erence", "ff"),    # difference
    ("e", "ect", "ff"),        # effect
    ("e", "ort", "ff"),        # effort
    ("e", "icient", "ff"),     # efficient
    ("su", "icient", "ff"),    # sufficient
    ("o", "ice", "ff"),        # office
    ("a", "orded", "ff"),      # afforded
    ("sta", "", "ff"),         # staff
    ("arti", "cial", "fi"),    # artificial
    ("speci", "c", "fi"),      # specific
    ("classi", "cation", "fi"),
    ("identi", "ed", "fi"),
    ("justi", "ed", "fi"),
    ("bene", "t", "fi"),
    ("con", "rm", "fi"),
    ("de", "ne", "fi"),
    ("signi", "cant", "fi"),
    ("in", "uence", "fl"),     # influence
    ("re", "ect", "fl"),       # reflect
]

# Private-use bullet emitted by Symbol-font list markers.
PRIVATE_BULLET = ""


def repair_ligatures(text: str) -> tuple[str, int]:
    """Return repaired text and the count of gaps that could not be resolved."""
    if NUL not in text:
        return text, 0

    for left, right, fill in LIGATURE_CONTEXTS:
        pattern = (
            (f"(?<={re.escape(left)})" if left else "")
            + re.escape(NUL)
            + (f"(?={re.escape(right)})" if right else "")
        )
        text = re.sub(pattern, fill, text, flags=re.IGNORECASE)

    residual = text.count(NUL)
    # Unresolved gaps become "ff", the most common English f-ligature. The count
    # is returned so this stays a reported approximation, not a silent guess.
    text = text.replace(NUL, "ff")
    return text, residual


def normalize(text: str) -> tuple[str, int]:
    """Full cleanup: ligatures, private-use glyphs, whitespace."""
    text, residual = repair_ligatures(text)
    text = text.replace(PRIVATE_BULLET, "•")
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text, residual


def reflow(text: str) -> str:
    """Rejoin hard-wrapped PDF lines into paragraphs.

    PDF extraction breaks at the page's visual line width, not at paragraph
    boundaries. A line that ends mid-sentence and is followed by a lowercase
    continuation is rejoined; anything ending in sentence punctuation, or
    followed by a heading-like line, starts a new paragraph.
    """
    lines = [ln.strip() for ln in text.split("\n")]
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            out.append(" ".join(buf).strip())
            buf.clear()

    for ln in lines:
        if not ln:
            flush()
            continue
        if ln.isdigit():          # bare page number
            continue
        if buf and re.match(r"^[a-z,;)]", ln) and not re.search(r"[.:;!?]$", buf[-1]):
            buf.append(ln)        # continuation of a wrapped sentence
        else:
            if buf and re.search(r"[.:;!?]$", buf[-1]):
                flush()
            buf.append(ln)
    flush()
    return "\n\n".join(p for p in out if p)
