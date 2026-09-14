"""Parse eCFR XML into structured regulatory units.

eCFR structure relevant here:
  DIV5  = PART      (e.g. part 1607)
  DIV7  = SUBJGRP   (optional grouping, passed through)
  DIV8  = SECTION   (e.g. 1607.4) — carries a citation in hierarchy_metadata
  P     = paragraph

Lettered subsections (A., B., C., D.) are NOT separate XML elements. They appear
as a leading marker inside a <P>, e.g. "D. <I>Adverse impact...</I> A selection
rate for any race...". So subsection boundaries must be recovered from the text,
not from the tree. Continuation paragraphs carry no marker and attach to the
subsection that precedes them.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import xml.etree.ElementTree as ET

# The corpus uses two numbering conventions and both must be recognised:
#
#   1978-era parts (UGESP, OFCCP 60-3):  "A. ", "D. "
#   Modern parts (ADA at 1630, ADEA):    "(a) ", "(b) "
#
# In both, the top level is alphabetic. Numeric markers — "(1)", "(2)" — are
# nested *under* an alphabetic one, so they are treated as continuations rather
# than boundaries. Splitting on them as well fragments a subsection into pieces
# that no longer carry the condition they depend on.
#
# The uppercase form requires an uppercase letter or quote after it, so a
# cross-reference like "see section 4D. the agencies..." is not mistaken for a
# subsection marker.
SUBSECTION_RE = re.compile(
    r"^(?:([A-Z])\.\s+(?=[A-Z(“])"      # 1978 style:  "D. Adverse impact..."
    r"|\(([a-z])\)\s+)"                    # modern style: "(a) Commission means..."
)


@dataclasses.dataclass
class Unit:
    """One regulatory subsection — the smallest independently citable unit."""

    source_id: str
    part: str
    part_title: str
    section: str
    section_heading: str
    citation: str
    subsection: str | None
    text: str

    @property
    def full_citation(self) -> str:
        if self.subsection:
            return f"{self.citation}({self.subsection})"
        return self.citation


def _element_text(el: ET.Element) -> str:
    """Flatten an element's text, including inline <I>/<E> runs."""
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _citation_of(el: ET.Element, fallback: str) -> str:
    raw = el.get("hierarchy_metadata")
    if not raw:
        return fallback
    try:
        return json.loads(raw).get("citation", fallback)
    except (json.JSONDecodeError, AttributeError):
        return fallback


def parse_part(path: pathlib.Path, source_id: str) -> list[Unit]:
    root = ET.parse(path).getroot()
    part = root.get("N", "")
    part_head = root.find("HEAD")
    part_title = _element_text(part_head) if part_head is not None else ""

    units: list[Unit] = []
    for sec in root.iter("DIV8"):
        if sec.get("TYPE") != "SECTION":
            continue
        number = sec.get("N", "")
        head = sec.find("HEAD")
        heading = _element_text(head) if head is not None else ""
        citation = _citation_of(sec, f"{part} {number}")

        current_letter: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            if not buffer:
                return
            units.append(
                Unit(
                    source_id=source_id,
                    part=part,
                    part_title=part_title,
                    section=number,
                    section_heading=heading,
                    citation=citation,
                    subsection=current_letter,
                    text=" ".join(buffer).strip(),
                )
            )
            buffer.clear()

        for para in sec.iter("P"):
            text = _element_text(para)
            if not text:
                continue
            match = SUBSECTION_RE.match(text)
            if match:
                flush()
                # exactly one of the two alternatives captures
                current_letter = match.group(1) or match.group(2)
                text = text[match.end():]
            buffer.append(text)
        flush()

    return units
