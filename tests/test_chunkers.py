import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

from index.chunkers import fixed_window, structural
from ingest.parse_ecfr import SUBSECTION_RE, Unit, parse_part

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / "ecfr"


@pytest.fixture(scope="module")
def ugesp():
    return parse_part(RAW / "ugesp.xml", "ugesp")


def test_four_fifths_rule_is_its_own_citable_unit(ugesp):
    """The threshold NYC LL144 depends on must be independently addressable."""
    hits = [u for u in ugesp if u.full_citation == "29 CFR 1607.4(D)"]
    assert len(hits) == 1
    assert "four-fifths" in hits[0].text.lower()
    assert "eighty percent" in hits[0].text.lower()


def test_subsection_marker_does_not_match_mid_sentence_initials():
    """'...the EEOC. A selection rate...' must not look like subsection A."""
    assert SUBSECTION_RE.match("D. Adverse impact and the rule.")
    assert not SUBSECTION_RE.match("See section 4D. the agencies will expect")
    assert not SUBSECTION_RE.match("plain paragraph text with no marker")


def test_structural_chunks_embed_their_own_citation(ugesp):
    chunks = structural(ugesp)
    target = next(c for c in chunks if c.citations == ["29 CFR 1607.4(D)"])
    assert "29 CFR 1607.4(D)" in target.embed_text
    # the header must not contaminate the stored body
    assert "29 CFR 1607.4(D)" not in target.body


def test_header_makes_shared_bodies_distinct_at_the_string_level():
    """Strategy C gives identical bodies distinct embedded text.

    NOTE ON WHAT THIS DOES *NOT* PROVE. Exact string inequality is necessary but
    nowhere near sufficient. The real failure mode is high cosine similarity, not
    byte equality: two chunks differing by a few header words can still embed
    almost identically. Measured on this corpus, strategy A also produces zero
    exact collisions, so exact-match cannot discriminate between the strategies
    at all.

    The honest test is cosine similarity between the 1607 and 60-3 chunk pairs
    under a real embedding model, and it belongs in the evaluation harness. Until
    that exists, header injection is a reasoned hypothesis, not a demonstrated fix.
    """
    a = parse_part(RAW / "ugesp.xml", "ugesp")
    b = parse_part(RAW / "ofccp_60_3.xml", "ofccp_60_3")
    shared_bodies = {c.body for c in structural(a)} & {c.body for c in structural(b)}
    assert shared_bodies, "expected identical bodies across the two parts"

    ea = {c.embed_text for c in structural(a)}
    eb = {c.embed_text for c in structural(b)}
    assert not (ea & eb), "headers must make every embedded chunk distinct"


def test_fixed_window_overlaps_and_covers_all_text(ugesp):
    chunks = fixed_window(ugesp, size=512, overlap=64)
    assert len(chunks) > 1
    total_words = sum(len(u.text.split()) for u in ugesp)
    covered = set()
    for c in chunks:
        start = int(c.chunk_id.rsplit(":", 1)[1])
        covered.update(range(start, start + len(c.embed_text.split())))
    assert len(covered) == total_words, "windows must cover the whole part"


def test_fixed_window_rejects_overlap_larger_than_size(ugesp):
    with pytest.raises(ValueError):
        fixed_window(ugesp, size=100, overlap=100)


def test_deduplicate_merges_identical_bodies_across_parts():
    """67 bodies appear verbatim in both 29 CFR 1607 and 41 CFR 60-3."""
    from index.chunkers import deduplicate

    ug = structural(parse_part(RAW / "ugesp.xml", "ugesp"))
    of = structural(parse_part(RAW / "ofccp_60_3.xml", "ofccp_60_3"))
    merged = deduplicate(ug + of)

    assert len(merged) == len({c.body for c in ug + of})
    assert len(merged) < len(ug) + len(of), "expected some bodies to merge"

    multi = [c for c in merged if len(c.citations) > 1]
    assert len(multi) == 67, f"expected 67 shared bodies, got {len(multi)}"

    # every merged chunk must name both regimes, in the vector and in metadata
    for c in multi:
        assert len(c.source_ids) == 2
        for cite in c.citations:
            assert cite in c.embed_text, "all citations must be embedded"


def test_deduplicate_leaves_unique_bodies_untouched():
    from index.chunkers import deduplicate

    ug = structural(parse_part(RAW / "ugesp.xml", "ugesp"))
    merged = deduplicate(ug)
    assert len(merged) == len({c.body for c in ug})
    assert all(len(c.citations) == 1 for c in merged if c.body in {u.body for u in ug})
