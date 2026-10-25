#!/usr/bin/env python3
"""Display-vs-cart price consistency: catch a page that shows one price and charges another.

The failure mode this prevents
------------------------------
There is NO server-side price table in the Agroverse checkout. The GAS checkout
computes ``unit_amount`` directly from the price the *client* sends:

    agroverse_shop_checkout.gs:429   var unitAmount = Math.round(priceAmount * 100);
    js/add-to-cart.js:108            price: parseFloat(button.dataset.productPrice),

Meanwhile the price a customer *reads* is baked into static markup
(``.product-price``, JSON-LD, the button label). So a price edit means touching
several unrelated places, and missing one is silently expensive:

  * edit the display only  -> page says $30, cart charges $25  (undercharge)
  * edit products.js only  -> page says $25, cart charges $30  (OVERCHARGE)

Neither raises an error. Nothing in the build checks it. This script does.

Source of truth
---------------
``js/products.js`` (``window.PRODUCTS[sku].price``) is what the cart and Stripe
actually use, so it is the reference. Every other surface is asserted against it.

Checks per SKU
--------------
1. PDP ``data-product-price`` == products.js price
2. PDP displayed ``.product-price`` == products.js price
3. PDP JSON-LD ``offers.price`` == products.js price  (Google indexes this)
4. PDP button label ``Add to Cart - $X`` == products.js price
5. Landing card ``data-product-price`` == products.js price
6. ``productPageSlug`` folder actually exists

Usage:
    python3 scripts/check_product_price_consistency.py --repo-root ../agroverse_shop_beta
    python3 scripts/check_product_price_consistency.py --repo-root ... --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PRICE_TOLERANCE = 0.005  # cents; absorbs 10 vs 10.00 formatting

_PRODUCT_ENTRY_RE = re.compile(r"^\s*'([a-z0-9\-]+)':\s*\{", re.MULTILINE)
_PRICE_RE = re.compile(r"^\s*price:\s*([0-9]+(?:\.[0-9]+)?)", re.MULTILINE)
_SLUG_RE = re.compile(r"^\s*productPageSlug:\s*'([^']+)'", re.MULTILINE)
_DATA_PRICE_RE = re.compile(r'data-product-price="([0-9]+(?:\.[0-9]+)?)"')
_DATA_ID_RE = re.compile(r'data-product-id="([^"]+)"')
_DISPLAY_RE = re.compile(r'class="product-price"[^>]*>\s*\$?([0-9]+(?:\.[0-9]+)?)')
_JSONLD_PRICE_RE = re.compile(r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?')
_BUTTON_RE = re.compile(r"Add to Cart\s*[-–]\s*\$?([0-9]+(?:\.[0-9]+)?)")
_SUBSCRIBABLE_RE = re.compile(r"^\s*subscribable:\s*true", re.MULTILINE)


@dataclass
class Product:
    """One entry from ``js/products.js``."""

    sku: str
    price: float | None
    product_page_slug: str | None
    subscribable: bool = False


def parse_products_js(text: str) -> dict[str, Product]:
    """Extract ``{sku: Product}`` from the ``window.PRODUCTS = {...}`` literal.

    Deliberately a light parser rather than ``json.loads``: products.js is a JS
    object literal with comments, trailing commas and unquoted values. We only
    need each entry's key, price and slug, which are each on their own line.
    """
    products: dict[str, Product] = {}
    entries = list(_PRODUCT_ENTRY_RE.finditer(text))
    for i, match in enumerate(entries):
        sku = match.group(1)
        start = match.end()
        end = entries[i + 1].start() if i + 1 < len(entries) else len(text)
        body = text[start:end]
        price_match = _PRICE_RE.search(body)
        slug_match = _SLUG_RE.search(body)
        products[sku] = Product(
            sku=sku,
            price=float(price_match.group(1)) if price_match else None,
            product_page_slug=slug_match.group(1) if slug_match else None,
            subscribable=bool(_SUBSCRIBABLE_RE.search(body)),
        )
    return products


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= PRICE_TOLERANCE


def _fmt(value: float | None) -> str:
    return "?" if value is None else f"{value:.2f}"


def check_pdp(repo_root: Path, product: Product) -> list[str]:
    """Return a list of problems found on one product detail page."""
    problems: list[str] = []
    if not product.product_page_slug:
        return [f"{product.sku}: no productPageSlug in products.js"]
    pdp = repo_root / "product-page" / product.product_page_slug / "index.html"
    if not pdp.exists():
        return [
            f"{product.sku}: PDP folder missing -> product-page/{product.product_page_slug}/"
        ]

    html = pdp.read_text(encoding="utf-8", errors="replace")
    expected = product.price
    if expected is None:
        return [f"{product.sku}: no price in products.js"]

    # 1. cart input
    m = _DATA_PRICE_RE.search(html)
    if not m:
        if not product.subscribable:
            problems.append(
                f"{product.sku}: PDP has no data-product-price (cart would get no price)"
            )
    elif not _close(float(m.group(1)), expected):
        problems.append(
            f"{product.sku}: data-product-price=${m.group(1)} but products.js=${_fmt(expected)} "
            "-> CART CHARGES A DIFFERENT PRICE THAN THE PAGE INTENDS"
        )

    # 2. displayed price
    m = _DISPLAY_RE.search(html)
    if m and not _close(float(m.group(1)), expected):
        problems.append(
            f"{product.sku}: displayed .product-price=${_fmt(float(m.group(1)))} "
            f"but products.js=${_fmt(expected)}"
        )

    # 3. JSON-LD
    m = _JSONLD_PRICE_RE.search(html)
    if m and not _close(float(m.group(1)), expected):
        problems.append(
            f"{product.sku}: JSON-LD price={_fmt(float(m.group(1)))} "
            f"but products.js=${_fmt(expected)} (Google indexes this)"
        )

    # 4. button label
    m = _BUTTON_RE.search(html)
    if m and not _close(float(m.group(1)), expected):
        problems.append(
            f"{product.sku}: button label says ${_fmt(float(m.group(1)))} "
            f"but products.js=${_fmt(expected)}"
        )
    return problems


def check_landing(repo_root: Path, products: dict[str, Product]) -> list[str]:
    """Return problems found on the landing page's ``Add to Cart`` buttons."""
    landing = repo_root / "index.html"
    if not landing.exists():
        return ["index.html missing"]
    html = landing.read_text(encoding="utf-8", errors="replace")

    problems: list[str] = []
    # Pair each data-product-id with the next data-product-price in the same tag block.
    for block in re.split(r"<button", html):
        id_match = _DATA_ID_RE.search(block)
        price_match = _DATA_PRICE_RE.search(block)
        if not id_match or not price_match:
            continue
        sku = id_match.group(1)
        product = products.get(sku)
        if product is None or product.price is None:
            continue
        if not _close(float(price_match.group(1)), product.price):
            problems.append(
                f"{sku}: landing card data-product-price=${price_match.group(1)} "
                f"but products.js=${_fmt(product.price)}"
            )
    return problems


def run(repo_root: Path) -> tuple[list[str], list[str], int]:
    """Return ``(problems, notes, checked_count)``."""
    products_js = repo_root / "js" / "products.js"
    if not products_js.exists():
        return ([f"js/products.js not found under {repo_root}"], [], 0)

    products = parse_products_js(
        products_js.read_text(encoding="utf-8", errors="replace")
    )
    if not products:
        return (
            ["parsed zero products from js/products.js -- parser or file changed"],
            [],
            0,
        )

    problems: list[str] = []
    notes: list[str] = []
    checked = 0

    for product in products.values():
        if product.price is None:
            notes.append(f"{product.sku}: no price field (skipped)")
            continue
        if product.price <= 0:
            # Wholesale / unpriced: there is no public retail price to enforce.
            # Still worth noting when the PDP publishes a non-zero JSON-LD price,
            # because Google indexes a number the customer can never be charged.
            notes.append(
                f"{product.sku}: price is $0.00 (wholesale/unpriced) -- not enforced"
            )
            if product.product_page_slug:
                pdp = (
                    repo_root
                    / "product-page"
                    / product.product_page_slug
                    / "index.html"
                )
                if pdp.exists():
                    html = pdp.read_text(encoding="utf-8", errors="replace")
                    m = _JSONLD_PRICE_RE.search(html)
                    if m and float(m.group(1)) > PRICE_TOLERANCE:
                        notes.append(
                            f"{product.sku}: WARN wholesale PDP publishes JSON-LD "
                            f"price={m.group(1)} but products.js=$0.00 -- Google may index "
                            "a price that cannot be charged"
                        )
            continue
        if product.subscribable:
            notes.append(
                f"{product.sku}: subscription-only (no one-off cart button) -- display price still checked"
            )
        checked += 1
        problems.extend(check_pdp(repo_root, product))

    problems.extend(check_landing(repo_root, products))
    return (problems, notes, checked)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        required=True,
        help="checkout of agroverse_shop_beta (or _prod) to inspect",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    problems, notes, checked = run(Path(args.repo_root))

    if args.json:
        print(
            json.dumps(
                {"checked": checked, "problems": problems, "notes": notes}, indent=2
            )
        )
    else:
        if problems:
            print(
                f"FAIL: {len(problems)} price-consistency problem(s) across {checked} SKUs\n"
            )
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"OK: display and cart prices agree on {checked} SKUs")
        for n in notes:
            print(f"  note: {n}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
