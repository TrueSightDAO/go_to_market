"""Tests for the 81% bar wholesale price list commercial terms."""

import importlib.util
import os

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


def test_flight_is_four_origins_and_twelve_bars():
    assert bar.FLIGHT_BARS == 12
    assert bar.ORIGINS_PER_FLIGHT == 4
    assert len(bar.ORIGINS) == bar.ORIGINS_PER_FLIGHT
    # 12 bars split evenly across 4 origins -> a 3-of-each flight.
    assert bar.FLIGHT_BARS % bar.ORIGINS_PER_FLIGHT == 0


def test_flight_fits_the_usps_two_pound_bracket():
    # 12 x 1.76 oz = 21.12 oz of product; 12 x 50g = 600g.
    # Both must stay under 32 oz (2 lb) so postage does not step up a bracket.
    assert bar.BAR_WEIGHT_G * bar.FLIGHT_BARS <= 907  # 2 lb in grams
    assert bar.FREE_SHIPPING_BARS > bar.FLIGHT_BARS


def test_no_fabricated_taste_profiles():
    # Every origin must carry either a real taste profile or an honest note.
    for origin in bar.ORIGINS:
        assert origin.get("taste") or origin.get("note"), origin["name"]
