"""Tests for the display-vs-cart price consistency guard.

The guard exists because a price edit touches several unrelated static surfaces
with no server-side price table, so a miss is silently expensive in both
directions (show $30/charge $25, or show $25/charge $30).

Run: python3 -m pytest tests/test_check_product_price_consistency.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_product_price_consistency.py"

_spec = importlib.util.spec_from_file_location("check_price_consistency", SCRIPT)
m = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = m
_spec.loader.exec_module(m)

PRODUCTS_JS = """
window.PRODUCTS = {
  'paulo-200g': {
    productId: 'paulo-200g',
    productPageSlug: 'paulo-200g',
    name: 'Paulo',
    price: 30.00,
    category: 'retail'
  },
  'sub-only-bar': {
    productId: 'sub-only-bar',
    productPageSlug: 'sub-only-bar',
    name: 'Subscription bar',
    price: 10.00,
    category: 'retail',
    subscribable: true,
    subscriptionSlug: 'chocolate-bar'
  },
  'wholesale-beans': {
    productId: 'wholesale-beans',
    productPageSlug: 'wholesale-beans',
    name: 'Wholesale',
    price: 0.00,
    category: 'wholesale'
  }
};
"""

PDP_OK = """<html><head>
<script type="application/ld+json">{"offers": {"price": "30.00"}}</script>
</head><body>
<div class="product-price">$30.00</div>
<button data-product-id="paulo-200g" data-product-price="30.00">Add to Cart - $30.00</button>
</body></html>
"""

LANDING_OK = """<html><body>
<button data-product-id="paulo-200g" data-product-name="Paulo" data-product-price="30.00">Add to Cart - $30.00</button>
</body></html>
"""


SUB_PDP = """<html><body><div class="product-price">$10.00</div>
<button>Subscribe</button></body></html>"""

WHOLESALE_PDP = """<html><body><p>Wholesale only. Contact us.</p></body></html>"""


def make_tree(
    tmp_path: Path,
    pdp_html: str = PDP_OK,
    landing: str = LANDING_OK,
    products_js: str = PRODUCTS_JS,
) -> Path:
    """Build a minimal shop tree. Only the retail slug gets ``pdp_html``.

    The subscription-only and wholesale slugs get their own realistic PDPs --
    giving every slug the same $30 markup would make the fixture contradict its
    own products.js prices ($10 and $0) and fail for the wrong reason.
    """
    root = tmp_path / "shop"
    (root / "js").mkdir(parents=True)
    (root / "js" / "products.js").write_text(products_js)
    (root / "index.html").write_text(landing)
    pages = {
        "paulo-200g": pdp_html,
        "sub-only-bar": SUB_PDP,
        "wholesale-beans": WHOLESALE_PDP,
    }
    for slug, html in pages.items():
        d = root / "product-page" / slug
        d.mkdir(parents=True)
        (d / "index.html").write_text(html)
    return root


# --- parsing -----------------------------------------------------------------
def test_parse_products_js_extracts_price_and_slug():
    products = m.parse_products_js(PRODUCTS_JS)
    assert set(products) == {"paulo-200g", "sub-only-bar", "wholesale-beans"}
    assert products["paulo-200g"].price == 30.00
    assert products["paulo-200g"].product_page_slug == "paulo-200g"


def test_parse_products_js_detects_subscribable():
    products = m.parse_products_js(PRODUCTS_JS)
    assert products["sub-only-bar"].subscribable is True
    assert products["paulo-200g"].subscribable is False


# --- the happy path ----------------------------------------------------------
def test_consistent_tree_passes(tmp_path):
    problems, _notes, checked = m.run(make_tree(tmp_path))
    assert problems == []
    assert checked >= 2


# --- each failure direction --------------------------------------------------
def test_pdp_cart_price_mismatch_fails(tmp_path):
    """Cart input disagrees with the reference -> a real charge mismatch."""
    bad = PDP_OK.replace('data-product-price="30.00"', 'data-product-price="25.00"')
    problems, _n, _c = m.run(make_tree(tmp_path, pdp_html=bad))
    assert any("CART CHARGES A DIFFERENT PRICE" in p for p in problems)


def test_displayed_price_mismatch_fails(tmp_path):
    """Page displays $25 while the cart would charge $30 -> undercharge-on-page."""
    bad = PDP_OK.replace(
        '<div class="product-price">$30.00</div>',
        '<div class="product-price">$25.00</div>',
    )
    problems, _n, _c = m.run(make_tree(tmp_path, pdp_html=bad))
    assert any("displayed .product-price" in p for p in problems)


def test_jsonld_price_mismatch_fails(tmp_path):
    """Google indexes JSON-LD; a stale value is a real problem."""
    bad = PDP_OK.replace('"price": "30.00"', '"price": "25.00"')
    problems, _n, _c = m.run(make_tree(tmp_path, pdp_html=bad))
    assert any("JSON-LD" in p for p in problems)


def test_button_label_mismatch_fails(tmp_path):
    bad = PDP_OK.replace("Add to Cart - $30.00", "Add to Cart - $25.00")
    problems, _n, _c = m.run(make_tree(tmp_path, pdp_html=bad))
    assert any("button label" in p for p in problems)


def test_landing_card_mismatch_fails(tmp_path):
    bad_landing = LANDING_OK.replace(
        'data-product-price="30.00"', 'data-product-price="25.00"'
    )
    problems, _n, _c = m.run(make_tree(tmp_path, landing=bad_landing))
    assert any("landing card" in p for p in problems)


def test_missing_pdp_folder_fails(tmp_path):
    root = make_tree(tmp_path)
    import shutil

    shutil.rmtree(root / "product-page" / "paulo-200g")
    problems, _n, _c = m.run(root)
    assert any("PDP folder missing" in p for p in problems)


# --- scoping -----------------------------------------------------------------
def test_subscription_only_pdp_without_cart_button_is_not_a_failure(tmp_path):
    """A subscribable SKU has no one-off cart button; that is by design."""
    problems, notes, _c = m.run(make_tree(tmp_path))
    assert not any(
        "sub-only-bar" in p and "no data-product-price" in p for p in problems
    )
    assert any("sub-only-bar" in n and "subscription-only" in n for n in notes)


def test_wholesale_zero_price_is_note_not_failure(tmp_path):
    problems, notes, _c = m.run(make_tree(tmp_path))
    assert not any("wholesale-beans" in p for p in problems)
    assert any("wholesale-beans" in n for n in notes)


def test_wholesale_pdp_with_nonzero_jsonld_is_flagged_as_warning(tmp_path):
    """Wholesale PDP publishing a retail JSON-LD price is worth flagging."""
    ws_pdp = '<html><body><script>{"price": "25.00"}</script></body></html>'
    root = make_tree(tmp_path)
    (root / "product-page" / "wholesale-beans" / "index.html").write_text(ws_pdp)
    problems, notes, _c = m.run(root)
    assert not any("wholesale-beans" in p for p in problems)
    assert any("wholesale-beans" in n and "WARN" in n for n in notes)


def test_missing_products_js_reports_cleanly(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    problems, _n, checked = m.run(root)
    assert problems and checked == 0


def test_tolerance_accepts_formatting_difference(tmp_path):
    """'10' vs '10.00' must not trip the guard."""
    ok = PDP_OK.replace('data-product-price="30.00"', 'data-product-price="30"')
    problems, _n, _c = m.run(make_tree(tmp_path, pdp_html=ok))
    assert problems == []
