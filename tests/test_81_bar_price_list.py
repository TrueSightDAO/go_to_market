"""Tests for the 81% bar wholesale price list commercial terms."""

import importlib.util
import os
import re

_SPEC = importlib.util.spec_from_file_location(
    "bar_price_list",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "retail_price_list",
        "generate_81_bar_price_list.py",
    ),
)
bar = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bar)


def test_retailer_margin_is_forty_percent():
    # Winery channel convention: retailer keeps 40% of the $10 RRP.
    assert bar.WHOLESALE_PER_BAR_USD == 6.00
    assert bar.RRP_PER_BAR_USD == 10.00
    margin = (bar.RRP_PER_BAR_USD - bar.WHOLESALE_PER_BAR_USD) / bar.RRP_PER_BAR_USD
    assert round(margin, 4) == 0.40


def test_cogs_is_the_ledger_derived_figure_not_the_bogus_one():
    # Regression guard: an earlier $5.62 COGS came from misreading the
    # deprecated `Cacao Almonds KG - Organic` row at $100.886/kg.
    # Real basis is Cacao Mass Bar 50g $2.154 + label $0.554 = ~$2.71.
    assert 2.60 <= bar.COGS_PER_BAR_USD <= 2.80


def test_gross_margin_at_wholesale_is_viable():
    gross = bar.WHOLESALE_PER_BAR_USD - bar.COGS_PER_BAR_USD
    assert gross > 0
    assert gross / bar.WHOLESALE_PER_BAR_USD >= 0.50


def test_opening_order_is_twelve_bars_of_the_one_stocked_estate():
    """Only Oscar's Farm is stocked as a bar right now (40 units).

    Stock direction of 2026-10-28: Vivi's is coming online later this year,
    Fazenda Sao Jorge is going out of stock, and Fazenda Santa Ana is not being
    stocked this year. The opening order is therefore 12 bars of a single estate
    - a four-origin flight would advertise bars we cannot ship.
    """
    assert bar.FLIGHT_BARS == 12
    assert bar.ORIGINS_PER_FLIGHT == 1
    assert len(bar.ORIGINS) == 1, "only one buyable bar origin may be listed"
    assert "oscar" in bar.ORIGINS[0]["name"].lower()

    # The unstockable estates must not reach the SHIPPED PDF. Source comments name
    # them on purpose (recording why they were dropped), so assert on the rendered
    # document's visible text rather than the source.
    # Normalise whitespace: pypdf returns the PDF's line wraps, so a phrase
    # like "ask us for availability" comes back as "ask us for\\navailability".
    text = re.sub(r"\s+", " ", bar._rendered_pdf_text().lower())
    # Sao Jorge and Santa Ana are unstockable and unmentionable.
    for gone in ("sao jorge", "s\u00e3o jorge", "santa ana"):
        assert gone not in text, f"{gone!r} must not appear in the shipped bar PDF"
    # Vivi's may appear ONLY as a coming-online note, never as a buyable estate.
    if "vivi" in text:
        assert "coming online" in text, "Vivi's may only be named as coming online"
        assert "ask us for availability" in text
    assert "oscar" in text


def test_flight_fits_the_usps_two_pound_bracket():
    # 12 x 1.76 oz = 21.12 oz of product; 12 x 50g = 600g.
    # Both must stay under 32 oz (2 lb) so postage does not step up a bracket.
    assert bar.BAR_WEIGHT_G * bar.FLIGHT_BARS <= 907  # 2 lb in grams
    assert bar.FREE_SHIPPING_BARS > bar.FLIGHT_BARS


def test_no_fabricated_taste_profiles():
    # Every origin must carry either a real taste profile or an honest note.
    for origin in bar.ORIGINS:
        assert origin.get("taste") or origin.get("note"), origin["name"]


def test_positioning_is_try_it_reorder_deeper() -> None:
    """The opening order is a trial size, not a volume ladder.

    Gary's positioning (2026-10-28): "try it, reorder deeper". The commercial
    claim that makes that honest is that the per-bar price does NOT fall with
    volume -- so pin both halves: the reorder language must be present, and no
    volume-tier or mixed-case offer may be advertised.
    """
    text = re.sub(r"\s+", " ", bar._rendered_pdf_text().lower())
    assert "reorder deeper" in text
    assert "no volume tiers" in text
    # A mixed case is unsellable while only one estate is in stock.
    assert "mixed case" not in text
