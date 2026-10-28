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
    assert "single-estate brazilian chocolate" in body


def test_winery_body_leads_with_terroir_and_names_the_shop() -> None:
    body = m._warmup_body_winery("Chateau Test")
    assert "Chateau Test" in body
    low = body.lower()
    for expected in ("terroir", "oscar", "vivi", "estate"):
        assert expected in low, f"winery body should mention {expected!r}"
    # Paulo's Farm is a Para cacao-BAG origin and is not one of the four bar estates,
    # so it must not appear in a bar pitch (guards against reverting to the bag copy).
    assert "paulo" not in low, (
        "winery bar pitch must not cite Paulo's (bag-only origin)"
    )
    # the close must reference the 81% BAR price list
    assert "81% bar wholesale price list" in low


def test_retail_body_untouched_by_winery_change() -> None:
    """Guard against the new branch leaking into the existing retail copy."""
    body = m._warmup_body_retail_merch("Shop")
    assert "ceremonial cacao for retail" in body
    assert "single-estate brazilian chocolate" not in body


def test_winery_body_pitches_bars_with_real_terms() -> None:
    """The bar pivot: prices and opening quantity must be in the copy, and the
    email must not promise packaging photos that do not exist for the bar SKU."""
    body = m._warmup_body_winery("Test Winery")
    low = body.lower()
    assert "$10 retail" in low and "$6 wholesale" in low
    assert "12-bar flight" in low and "$72" in low
    assert "81%" in low and "50 g" in low
    # no unfulfillable attachment promise
    assert "two photos" not in low
    assert "front and back" not in low


def test_winery_close_is_not_the_shared_cacao_close() -> None:
    """Shipped copy guarantee: the winery email attaches only the bar PDF, so it
    must not reuse the shared close whose body promises packaging photos."""
    assert "_WARMUP_WINERY_CLOSE" in dir(m)
    assert m._WARMUP_WINERY_CLOSE != m._WARMUP_SHARED_CLOSE
    assert "two photos" not in m._WARMUP_WINERY_CLOSE.lower()


def test_grok_attachment_contract_is_segment_aware() -> None:
    """With --use-grok, the prompt must not tell the model to promise photos for
    a winery email."""
    winery = m.grok_warmup_system_prompt("winery").lower()
    retail = m.grok_warmup_system_prompt("retail_merch").lower()
    assert "three attachments" not in winery
    assert "one attachment" in winery
    # the non-winery segments keep their original contract
    assert "three attachments" in retail
