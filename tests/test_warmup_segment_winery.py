"""Winery warm-up segment: routing + copy hygiene.

The warm-prospect seeder classifies every Hit List row into a copy segment.
`Winery` is the first non-wellness venue type in that list: a tasting room sells
on provenance and place, so the generic `retail_merch` "shelf variety" framing
undersells it, and ceremonial/ritual language is off-pitch entirely.

These tests pin three things that would silently break the pitch:
  1. `Winery` and `Vineyard` route to the winery segment, not `retail_merch`.
  2. The segments that already worked keep routing the same way.
  3. The winery body carries no ceremonial/ritual wording and does not inherit
     the shared close's "ceremonial cacao" tagline.

Run: python3 -m pytest tests/test_warmup_segment_winery.py -q
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "suggest_warmup_prospect_drafts.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "suggest_warmup_prospect_drafts", SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def test_winery_and_vineyard_route_to_winery_segment() -> None:
    for shop_type in ("Winery", "winery", "Vineyard", "  Winery  ", "Tasting Room"):
        assert m.classify_warmup_segment(shop_type, "") == m.SEGMENT_WINERY


def test_existing_segments_unchanged() -> None:
    # ceremonial set still wins for its own shop types
    assert (
        m.classify_warmup_segment("Yoga Studio", "") == m.SEGMENT_CEREMONIAL_SPIRITUAL
    )
    assert (
        m.classify_warmup_segment("Metaphysical/Spiritual", "")
        == m.SEGMENT_CEREMONIAL_SPIRITUAL
    )
    # everything else still falls through to retail
    assert m.classify_warmup_segment("Health Food Store", "") == m.SEGMENT_RETAIL_MERCH
    assert m.classify_warmup_segment("", "") == m.SEGMENT_RETAIL_MERCH


def test_hosts_circles_still_overrides_winery() -> None:
    """A winery that hosts circles keeps the circles framing (highest-converting)."""
    assert (
        m.classify_warmup_segment("Winery", "Yes \u2014 sound baths")
        == m.SEGMENT_CIRCLES_HOST
    )


def test_every_segment_has_a_body_and_grok_framing() -> None:
    """A missing entry is a KeyError at generation time; catch it statically."""
    for segment in m._WARMUP_BODY_BY_SEGMENT:
        assert segment in m._SEGMENT_GROK_FRAMING, f"{segment} missing grok framing"
    assert m.SEGMENT_WINERY in m._WARMUP_BODY_BY_SEGMENT
    assert m.SEGMENT_WINERY in m._SEGMENT_GROK_FRAMING


def test_winery_body_avoids_ceremonial_framing() -> None:
    body = m._warmup_body_winery("Test Winery").lower()
    for banned in (
        "ceremonial",
        "ceremony",
        "ritual",
        "spiritual",
        "moon circle",
        "wellness",
    ):
        assert banned not in body, f"winery body must not say {banned!r}"
    # and it must not inherit the cacao tagline from the shared close
    assert "ceremonial cacao for retail" not in body
    assert "single-estate brazilian cacao" in body


def test_winery_body_leads_with_terroir_and_names_the_shop() -> None:
    body = m._warmup_body_winery("Chateau Test")
    assert "Chateau Test" in body
    low = body.lower()
    for expected in ("terroir", "oscar", "paulo", "estate"):
        assert expected in low, f"winery body should mention {expected!r}"
    # the shared close must still be present (price list + packaging attachments)
    assert "wholesale price list" in low


def test_retail_body_untouched_by_winery_change() -> None:
    """Guard against the new branch leaking into the existing retail copy."""
    body = m._warmup_body_retail_merch("Shop")
    assert "ceremonial cacao for retail" in body
    assert "single-estate brazilian cacao" not in body
