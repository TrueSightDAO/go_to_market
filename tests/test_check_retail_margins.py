"""Tests for the retail gross-margin guard (scripts/check_retail_margins.py).

The fixtures below are the REAL numbers pulled from the main ledger on
2026-10-26, not invented values -- so if the guard's arithmetic or its
cheapest-vs-highest-batch logic ever drifts, these tests fail.

Run: python3 -m pytest tests/test_check_retail_margins.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_retail_margins.py"

_spec = importlib.util.spec_from_file_location("check_retail_margins", SCRIPT)
m = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass resolves annotations via sys.modules[__module__].
sys.modules[_spec.name] = m
_spec.loader.exec_module(m)

parse_money = m.parse_money
build_skus = m.build_skus
evaluate = m.evaluate
Sku = m.Sku

# --- fixtures mirroring the live tabs (header row excluded) -------------------
SKU_HEADER = [
    "Product ID",
    "Product Name",
    "Price (USD)",
    "Weight (oz)",
    "Category",
    "Shipment",
    "Farm",
    "Image Path",
    "Store inventory",
    "GTIN",
]

SKU_ROWS = [
    # Paulo 200g ceremonial: $30 after the governor's price change.
    [
        "ceremonial-cacao-paulo-s-la-do-sitio-farm-200g",
        "Paulo",
        "$30.00",
        "7.05",
        "retail",
        "AGL8",
    ],
    # São Jorge bar: $10 vs a $5.62 cost -> ~44% GM, the worst in the catalogue.
    [
        "organic-81-dark-chocolate-bar-50g-fazenda-sao-jorge-bahia-2024",
        "Sao Jorge",
        "$10.00",
        "1.76",
        "retail",
        "AGL4",
    ],
    # Santa Ana 200g: $25 vs $2.40 cost -> ~90% GM. Must never be flagged.
    [
        "ceremonial-cacao-fazenda-santa-ana-2023-200g",
        "Santa Ana",
        "$25.00",
        "7.05",
        "retail",
        "AGL2",
    ],
    # Wholesale rows carry $0.00 and are out of scope.
    [
        "premium-organic-cacao-beans-la-do-sitio",
        "Wholesale",
        "$0.00",
        "",
        "wholesale",
        "AGL8",
    ],
    # A retail row whose Currencies costs are all missing.
    ["unpriced-retail-sku", "No cost", "$12.00", "", "retail", "AGL4"],
]

CURRENCY_ROWS = [
    # Paulo has THREE batch costs; cheapest $9.1754, highest $13.78.
    [
        "Paulo batch A",
        "$9.175446849",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "200",
        "",
        "ceremonial-cacao-paulo-s-la-do-sitio-farm-200g",
    ],
    [
        "Paulo batch B",
        "$$10.37",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "200",
        "",
        "ceremonial-cacao-paulo-s-la-do-sitio-farm-200g",
    ],
    [
        "Paulo batch C",
        "$13.78",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "200",
        "",
        "ceremonial-cacao-paulo-s-la-do-sitio-farm-200g",
    ],
    [
        "Sao Jorge bar",
        "$5.6241",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "50",
        "",
        "organic-81-dark-chocolate-bar-50g-fazenda-sao-jorge-bahia-2024",
    ],
    [
        "Santa Ana 200g",
        "$2.404364361",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "200",
        "",
        "ceremonial-cacao-fazenda-santa-ana-2023-200g",
    ],
    # A zero cost is missing data, not free product.
    [
        "Unpriced",
        "$0",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "200",
        "",
        "unpriced-retail-sku",
    ],
    # Cost row for a SKU that is not in the SKUs tab at all.
    [
        "Orphan cost",
        "$4.00",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "200",
        "",
        "not-a-real-sku",
    ],
]


def build():
    return build_skus(SKU_ROWS, CURRENCY_ROWS)


# --- parse_money -------------------------------------------------------------
def test_parse_money_plain():
    assert parse_money("$30.00") == 30.0
    assert parse_money("10") == 10.0
    assert parse_money(25.5) == 25.5


def test_parse_money_double_dollar_sign():
    """Currencies row 112 really does read '$$10.37' -- must not raise or skip."""
    assert parse_money("$$10.37") == 10.37


def test_parse_money_blank_and_garbage_are_none_not_zero():
    """A missing cost must never be read as 0.0 (which would fake a 100% margin)."""
    assert parse_money("") is None
    assert parse_money("   ") is None
    assert parse_money(None) is None
    assert parse_money("N/A") is None


# --- build_skus --------------------------------------------------------------
def test_build_skus_joins_costs_by_col_m():
    skus = build()
    paulo = skus["ceremonial-cacao-paulo-s-la-do-sitio-farm-200g"]
    assert len(paulo.costs) == 3
    assert paulo.min_cost == 9.175446849
    assert paulo.max_cost == 13.78


def test_build_skus_ignores_zero_cost_and_unknown_sku():
    skus = build()
    assert skus["unpriced-retail-sku"].costs == []
    assert "not-a-real-sku" not in skus


def test_category_case_insensitive():
    rows = [["x-sku", "X", "$10.00", "", "Retail", "AGL4"]]
    assert build_skus(rows, [])["x-sku"].is_retail


# --- margin arithmetic -------------------------------------------------------
def test_gross_margin_math():
    sku = Sku(sku_id="p", price=30.0, costs=[9.175446849])
    assert round(sku.gross_margin(9.175446849), 4) == round((30 - 9.175446849) / 30, 4)


def test_price_for_margin_roundtrip():
    sku = Sku(sku_id="p", price=30.0, costs=[9.175446849])
    target = 0.65
    p = sku.price_for_margin(9.175446849, target)
    assert round((p - 9.175446849) / p, 10) == target


def test_tree_charge_reduces_margin():
    sku = Sku(sku_id="p", price=30.0, costs=[10.0], tree_charge=1.5)
    assert sku.gross_margin(10.0) == (30.0 - 10.0 - 1.5) / 30.0


# --- evaluate ----------------------------------------------------------------
def test_sao_jorge_fails_at_55pct_floor():
    """~44% GM at the only known cost -> must fail."""
    failing, _ = evaluate(build(), 0.55)
    ids = [f.sku_id for f in failing]
    assert "organic-81-dark-chocolate-bar-50g-fazenda-sao-jorge-bahia-2024" in ids


def test_paulo_at_25_clears_55pct_on_cheapest_cost_but_warns_on_highest():
    """Honest note on the guard's semantics.

    At $25, Paulo's CHEAPEST batch cost ($9.1754) yields 63.3% GM, which clears a
    55% floor -- so the $30 change was not *forced* by this guard at that floor.
    What actually motivated it is the highest batch cost ($13.78 -> 44.9% at $25),
    which the guard surfaces as a warning rather than a failure. Pinned here so
    nobody later reads a green build as "the old $25 was fine".
    """
    failing, warnings = evaluate(build(), 0.55)
    assert not [f for f in failing if f.sku_id.startswith("ceremonial-cacao-paulo")]
    paulo_warn = [w for w in warnings if w["sku"].startswith("ceremonial-cacao-paulo")]
    assert paulo_warn, "expected a highest-cost-batch warning for Paulo"


def test_paulo_at_25_fails_a_65pct_floor():
    """At a 65% floor the pre-change $25 price does fail on cheapest cost.

    63.3% GM at $9.1754 vs a 65% floor -> a real failure, not just a warning.
    """
    skus = build()
    for sku in skus.values():
        if sku.sku_id.startswith("ceremonial-cacao-paulo"):
            sku.price = 25.0
    failing, _ = evaluate(skus, 0.65)
    assert [f for f in failing if f.sku_id.startswith("ceremonial-cacao-paulo")]


def test_paulo_at_30_clears_a_65pct_floor():
    skus = build()
    for sku in skus.values():
        if sku.sku_id.startswith("ceremonial-cacao-paulo"):
            sku.price = 30.0
    failing, _ = evaluate(skus, 0.65)
    assert not [f for f in failing if f.sku_id.startswith("ceremonial-cacao-paulo")]


def test_santa_ana_90pct_never_flagged():
    failing, warnings = evaluate(build(), 0.55)
    for bucket in (failing, warnings):
        for item in bucket:
            key = item.sku_id if hasattr(item, "sku_id") else item["sku"]
            assert key != "ceremonial-cacao-fazenda-santa-ana-2023-200g"


def test_wholesale_and_unpriced_out_of_scope():
    failing, warnings = evaluate(build(), 0.55)
    ids = [f.sku_id for f in failing]
    assert "premium-organic-cacao-beans-la-do-sitio" not in ids
    # $12 retail with no cost anywhere -> warning, never a failure
    assert "unpriced-retail-sku" not in ids
    assert any(w["sku"] == "unpriced-retail-sku" for w in warnings)


def test_highest_batch_warns_but_does_not_fail():
    """Paulo at $30: min-cost GM 69.4% ok, max-cost GM 54.1% -> warn only."""
    failing, warnings = evaluate(build(), 0.55)
    assert not [f for f in failing if f.sku_id.startswith("ceremonial-cacao-paulo")]
    assert any(w["sku"].startswith("ceremonial-cacao-paulo") for w in warnings)


def test_allowlist_suppresses_failure():
    failing, _ = evaluate(
        build(),
        0.55,
        allow={
            "organic-81-dark-chocolate-bar-50g-fazenda-sao-jorge-bahia-2024": "legacy"
        },
    )
    assert not [f for f in failing if "sao-jorge" in f.sku_id]


def test_failures_sorted_worst_first():
    failing, _ = evaluate(build(), 0.55)
    gms = [f.gm_at_min_cost for f in failing]
    assert gms == sorted(gms)


def test_render_names_the_price_needed():
    failing, warnings = evaluate(build(), 0.55)
    out = m.render(failing, warnings, 0.55)
    assert "FAIL" in out
    assert "sao-jorge" in out
    assert "price@floor" in out


def test_allowlist_requires_reason(tmp_path):
    p = tmp_path / "allow.json"
    p.write_text('{"some-sku": ""}')
    try:
        m.load_allowlist(p)
    except ValueError as exc:
        assert "reason" in str(exc)
    else:
        raise AssertionError("expected ValueError for empty reason")
