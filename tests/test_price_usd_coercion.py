"""Regression guard: `priceUsd` must never ship currency-formatted.

KAN-113 found `ceremonial-cacao-paulo-s-la-do-sitio-farm-200g` (the flagship, 170
units) publishing `"priceUsd": "$30.00"` because cell C2 of the `Agroverse SKUs`
tab was typed as *text* rather than a number. `_gas_cell_str` mirrors GAS
faithfully, so it faithfully passed the malformed value through.

Consumer impact: the dapp drops `priceUsd` into `<input type="number" id="priceInput">`,
which renders BLANK for a non-numeric string. Same bug class as go_to_market #175.
"""

import importlib.util
import os

_SPEC = importlib.util.spec_from_file_location(
    "sync_agv",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "sync_agroverse_store_inventory.py",
    ),
)
sync = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sync)

_price_usd_str = sync._price_usd_str


def test_currency_formatted_string_is_stripped():
    # The exact value found in cell C2.
    assert _price_usd_str("$30.00") == "30"
    assert _price_usd_str("$25.00") == "25"
    assert _price_usd_str("$10.00") == "10"


def test_numeric_cells_are_unchanged():
    assert _price_usd_str(30) == "30"
    assert _price_usd_str(25) == "25"
    assert _price_usd_str(60) == "60"
    assert _price_usd_str(10.5) == "10.5"


def test_numeric_float_integer_has_no_trailing_point_zero():
    assert _price_usd_str(30.0) == "30"


def test_thousands_separators_are_stripped():
    assert _price_usd_str("$1,250.00") == "1250"


def test_zero_price_publishes_empty_as_before():
    # _gas_cell_str semantics: 0 -> '' so the dapp shows "no price defined".
    assert _price_usd_str(0) == ""
    assert _price_usd_str("") == ""
    assert _price_usd_str(None) == ""


def test_unparseable_value_publishes_empty_not_malformed():
    # Absent is recoverable; malformed silently breaks the input.
    assert _price_usd_str("call for price") == ""
    assert _price_usd_str("$") == ""
    assert _price_usd_str("N/A") == ""


def test_whitespace_padded_numeric_is_handled():
    assert _price_usd_str("  30.00  ") == "30"
    assert _price_usd_str(" $45 ") == "45"


def test_result_is_always_numeric_or_empty():
    # The invariant that matters to the consumer: whatever goes into a
    # type="number" input must parse as a float, or be empty.
    for raw in ["$30.00", 30, 10.5, "$1,250", "", None, 0, "junk", "$"]:
        out = _price_usd_str(raw)
        assert out == "" or float(out) == float(out)
