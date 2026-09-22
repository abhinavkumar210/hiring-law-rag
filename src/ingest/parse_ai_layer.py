"""Parse the AI-specific layer into the same Unit shape as the eCFR tier.

These sources are plain text extracted from HTML and PDF, so there is no
hierarchy to exploit. Boundaries are recovered from section markers where the
document has them and from paragraph breaks where it does not.

Every unit carries `jurisdiction` and `status`. Status matters: the EEOC Title VII
AI guidance was removed from eeoc.gov in January 2025, and quoting withdrawn
guidance as if it were current would be a serious error in a compliance tool.
The status travels with the text from ingestion all the way into the answer.
"""
from __future__ import annotations

import json
import pathlib
import re

from ingest.parse_ecfr import Unit
from ingest.text_normalize import normalize, reflow

# "§ 5-300", "Section 10.", "SECTION 3-", "5-301 Definitions." etc.
SECTION_RE = re.compile(
    r"^(?:§+\s*|Sec(?:tion)?\.?\s+)?"
    r"((?:\d+[-.]\d+(?:[-.]\d+)*)|(?:\d{1,3}))\s*[.:—-]?\s+(?=[A-Z])"
)
MIN_UNIT_CHARS = 200
MAX_UNIT_CHARS = 2200


def _blocks(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    parts = [re.sub(r"[ \t]+", " ", b).strip() for b in text.split("\n\n")]
    return [p for p in parts if p]


def parse_ai_source(txt_path: pathlib.Path) -> list[Unit]:
    meta = json.loads(
        txt_path.with_suffix("").with_suffix(".meta.json").read_text(encoding="utf8")
    )
    raw = txt_path.read_text(encoding="utf8")
    cleaned, residual = normalize(raw)
    if residual:
        print(f"  note: {txt_path.stem} had {residual} unresolved glyph gaps")
    text = reflow(cleaned)
    source_id = meta["id"]

    units: list[Unit] = []
    current_label: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = " ".join(buffer).strip()
        buffer.clear()
        if len(body) < MIN_UNIT_CHARS and units:
            # too small to stand alone; fold into the previous unit
            units[-1].text = f"{units[-1].text} {body}".strip()
            return
        # very long blocks are split on sentence boundaries so no unit is
        # unreadably large; the citation stays the same across the pieces
        while len(body) > MAX_UNIT_CHARS:
            cut = body.rfind(". ", 0, MAX_UNIT_CHARS)
            cut = cut + 1 if cut > MAX_UNIT_CHARS // 2 else MAX_UNIT_CHARS
            units.append(_unit(meta, source_id, current_label, body[:cut].strip()))
            body = body[cut:].strip()
        if body:
            units.append(_unit(meta, source_id, current_label, body))

    for block in _blocks(text):
        m = SECTION_RE.match(block)
        if m and len(block) > 80:
            flush()
            current_label = m.group(1)
        buffer.append(block)
    flush()
    return units


def _unit(meta: dict, source_id: str, label: str | None, body: str) -> Unit:
    cite = meta["name"]
    if label:
        cite = f"{cite} § {label}"
    return Unit(
        source_id=source_id,
        part=meta["id"],
        part_title=meta["name"],
        section=label or "",
        section_heading="",
        citation=cite,
        subsection=None,
        text=body,
        jurisdiction=meta.get("jurisdiction", "unknown"),
        status=meta.get("status", "in_force"),
    )


def parse_all(raw_dir: pathlib.Path) -> list[Unit]:
    units: list[Unit] = []
    for txt in sorted(raw_dir.glob("*.txt")):
        units.extend(parse_ai_source(txt))
    return units
