#!/usr/bin/env python3
"""Retail margin guard: fail CI when a retail SKU's gross margin drops too low.

Why this exists
---------------
Retail prices live in three places that can drift apart:

  * the main ledger ``Agroverse SKUs`` tab (``Price (USD)``, col C) -- the SSOT,
  * ``agroverse_shop_beta/js/products.js`` (``price:`` per SKU), which feeds the
    cart and therefore the Stripe charge, and
  * each PDP's hard-coded markup (``data-product-price``, ``.product-price``,
    JSON-LD).

Unit costs live in the ``Currencies`` tab (col B), keyed to a SKU by col M. There
is no server-side price or cost table anywhere in the checkout path -- the GAS
checkout computes ``unit_amount`` straight from the client cart payload -- so a
price change is an *editorial* act with no arithmetic check behind it.

That combination is how a product silently drifts to a sub-cost margin: nothing
prompts anyone to re-derive margin when a new freight batch lands at a higher
landed cost. This guard turns that into a build failure.

Semantics
---------
Per SKU we evaluate the *cheapest* known batch cost (the most favourable
reading). A SKU fails only when even that best-case cost yields gross margin
below the floor -- i.e. the price is unambiguously too low. The most expensive
batch's margin is reported as a warning, because a single outlier-high cost row
is more often a data-entry problem than a real pricing signal.

Gross margin here is ``(price - cost) / price`` and EXCLUDES Stripe fees and
outbound shipping, so it is an upper bound on true contribution margin.

Runpoint:
    python3 -m pytest tests/test_check_retail_margins.py -q     # offline
    python3 scripts/check_retail_margins.py --credentials google_credentials.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MIN_GROSS_MARGIN = 0.55
MAIN_LEDGER_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"

# Column indices (0-based) for the two tabs we read.
SKU_COL_ID = 0
SKU_COL_PRICE = 2
SKU_COL_WEIGHT_OZ = 3
SKU_COL_CATEGORY = 4
SKU_COL_SHIPMENT = 5

CUR_COL_COST = 1
CUR_COL_GRAMS = 10
CUR_COL_SKU = 12
CUR_COL_SALE_TYPE = 16
CUR_COL_TREE_CHARGE = 20

_retail_categories = {"retail"}

MoneyLike = str | int | float | None

_STRIP_RE = re.compile(r"[\s,$]")


def parse_money(value: MoneyLike) -> float | None:
    """Parse a sheet money cell into a float.

    Handles the real-world dirt in the ledger: ``"$30.00"``, ``"10"``,
    ``"$$10.37"`` (a doubled currency symbol that exists in row 112 of
    ``Currencies``), ``""`` and ``"N/A"``. Unparseable/blank cells return
    ``None`` rather than ``0.0`` -- a missing cost must never be read as free.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = _STRIP_RE.sub("", str(value))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


@dataclass
class Sku:
    """A row of the ``Agroverse SKUs`` tab."""

    sku_id: str
    price: float | None
    weight_oz: float | None = None
    category: str = ""
    shipment: str = ""
    costs: list[float] = field(default_factory=list)
    tree_charge: float = 0.0

    @property
    def is_retail(self) -> bool:
        return self.category.strip().lower() in _retail_categories

    @property
    def min_cost(self) -> float | None:
        return min(self.costs) if self.costs else None

    @property
    def max_cost(self) -> float | None:
        return max(self.costs) if self.costs else None

    def gross_margin(self, cost: float) -> float:
        """Gross margin fraction at ``cost``. ``price`` must be positive."""
        assert self.price  # guarded by caller
        return (self.price - cost - self.tree_charge) / self.price

    def price_for_margin(self, cost: float, target: float) -> float:
        """Price needed to hit ``target`` gross margin at ``cost``."""
        return (cost + self.tree_charge) / (1.0 - target)


def build_skus(sku_rows: list[list], currency_rows: list[list]) -> dict[str, Sku]:
    """Join ``Agroverse SKUs`` rows to their ``Currencies`` costs.

    ``sku_rows`` and ``currency_rows`` are data rows only (header excluded), as
    returned by ``gspread.Worksheet.get_all_values()[1:]``.
    """
    skus: dict[str, Sku] = {}

    for row in sku_rows:
        if not row:
            continue
        sku_id = _cell(row, SKU_COL_ID)
        if not sku_id:
            continue
        skus[sku_id] = Sku(
            sku_id=sku_id,
            price=parse_money(_cell(row, SKU_COL_PRICE)),
            weight_oz=parse_money(_cell(row, SKU_COL_WEIGHT_OZ)),
            category=_cell(row, SKU_COL_CATEGORY),
            shipment=_cell(row, SKU_COL_SHIPMENT),
        )

    for row in currency_rows:
        if not row:
            continue
        sku_id = _cell(row, CUR_COL_SKU)
        if not sku_id or sku_id not in skus:
            continue
        cost = parse_money(_cell(row, CUR_COL_COST))
        if cost is None or cost <= 0:
            # A zero/blank cost is missing data, not free product. Skipping it
            # keeps a bogus 100%-margin row from masking a real problem.
            continue
        skus[sku_id].costs.append(cost)
        tree = parse_money(_cell(row, CUR_COL_TREE_CHARGE)) or 0.0
        skus[sku_id].tree_charge = max(skus[sku_id].tree_charge, tree)

    return skus


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


@dataclass
class Finding:
    sku_id: str
    price: float
    min_cost: float
    max_cost: float
    gm_at_min_cost: float
    gm_at_max_cost: float
    tree_charge: float
    price_for_floor: float

    def to_dict(self) -> dict:
        return {
            "sku": self.sku_id,
            "price": round(self.price, 2),
            "min_cost": round(self.min_cost, 4),
            "max_cost": round(self.max_cost, 4),
            "gm_at_min_cost_pct": round(100 * self.gm_at_min_cost, 1),
            "gm_at_max_cost_pct": round(100 * self.gm_at_max_cost, 1),
            "tree_charge": round(self.tree_charge, 4),
            "price_for_floor": round(self.price_for_floor, 2),
        }


def evaluate(
    skus: dict[str, Sku],
    min_gross_margin: float = DEFAULT_MIN_GROSS_MARGIN,
    allow: dict[str, str] | None = None,
) -> tuple[list[Finding], list[dict]]:
    """Return ``(failing, warnings)`` for every comparable retail SKU.

    Failing = cheapest known batch cost still lands below ``min_gross_margin``.
    Warnings are informational and never change the exit code.
    """
    allow = allow or {}
    failing: list[Finding] = []
    warnings: list[dict] = []

    for sku in skus.values():
        if not sku.is_retail:
            continue
        if not sku.price or sku.price <= 0:
            # Wholesale / unpriced rows are out of scope: no public price exists
            # to be wrong.
            continue
        if sku.min_cost is None:
            warnings.append(
                {"sku": sku.sku_id, "issue": "no positive cost row in Currencies"}
            )
            continue
        if sku.sku_id in allow:
            continue

        finding = Finding(
            sku_id=sku.sku_id,
            price=sku.price,
            min_cost=sku.min_cost,
            max_cost=sku.max_cost,
            gm_at_min_cost=sku.gross_margin(sku.min_cost),
            gm_at_max_cost=sku.gross_margin(sku.max_cost),
            tree_charge=sku.tree_charge,
            price_for_floor=sku.price_for_margin(sku.min_cost, min_gross_margin),
        )
        if finding.gm_at_min_cost < min_gross_margin:
            failing.append(finding)
        elif finding.gm_at_max_cost < min_gross_margin:
            warnings.append(
                {
                    "sku": sku.sku_id,
                    "issue": (
                        "highest-cost batch would put margin at "
                        f"{100 * finding.gm_at_max_cost:.1f}% (floor "
                        f"{100 * min_gross_margin:.0f}%); cheapest batch is fine. "
                        "Check the outlier cost row."
                    ),
                }
            )

    failing.sort(key=lambda f: f.gm_at_min_cost)
    return failing, warnings


def render(failing: list[Finding], warnings: list[dict], floor: float) -> str:
    lines: list[str] = []
    if failing:
        lines.append(
            f"FAIL: {len(failing)} retail SKU(s) below the "
            f"{100 * floor:.0f}% gross-margin floor at their cheapest known cost"
        )
        lines.append("")
        lines.append(
            f"{'price':>8} {'min cost':>10} {'GM%':>7} {'GM%@max':>8} "
            f"{'price@floor':>12}  SKU"
        )
        for f in failing:
            lines.append(
                f"{f.price:>8.2f} {f.min_cost:>10.4f} "
                f"{100 * f.gm_at_min_cost:>6.1f}% {100 * f.gm_at_max_cost:>7.1f}% "
                f"{f.price_for_floor:>12.2f}  {f.sku_id}"
            )
        lines.append("")
        lines.append(
            "Fix: raise the price, or lower the landed cost, or add the SKU to "
            "scripts/retail_margin_allowlist.json with a reason."
        )
    else:
        lines.append(
            f"OK: all priced retail SKUs are at or above {100 * floor:.0f}% GM"
        )

    if warnings:
        lines.append("")
        lines.append(
            f"WARN ({len(warnings)}) -- informational, does not fail the build:"
        )
        for w in warnings:
            lines.append(f"  - {w['sku']}: {w['issue']}")
    return "\n".join(lines)


def load_allowlist(path: Path | None) -> dict[str, str]:
    """Load ``{sku: reason}`` grandfathering map. Each entry MUST give a reason."""
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object of sku -> reason")
    entries = {k: v for k, v in data.items() if not k.startswith("_")}
    missing = [k for k, v in entries.items() if not str(v).strip()]
    if missing:
        raise ValueError(f"{path}: entries need a non-empty reason: {missing}")
    return {k: str(v) for k, v in entries.items()}


def fetch_rows(credentials_path: str) -> tuple[list[list], list[list]]:
    """Read the two tabs from the main ledger (network + credentials)."""
    import gspread  # imported lazily so the unit tests stay offline
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    sheet = gspread.authorize(creds).open_by_key(MAIN_LEDGER_ID)
    sku_rows = sheet.worksheet("Agroverse SKUs").get_all_values()[1:]
    currency_rows = sheet.worksheet("Currencies").get_all_values()[1:]
    return sku_rows, currency_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--credentials", default="google_credentials.json")
    parser.add_argument(
        "--min-gm",
        type=float,
        default=DEFAULT_MIN_GROSS_MARGIN,
        help="gross-margin floor as a fraction (default 0.55)",
    )
    parser.add_argument(
        "--allowlist",
        default="scripts/retail_margin_allowlist.json",
        help="JSON object of sku -> reason to grandfather",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    sku_rows, currency_rows = fetch_rows(args.credentials)
    skus = build_skus(sku_rows, currency_rows)
    failing, warnings = evaluate(
        skus, args.min_gm, load_allowlist(Path(args.allowlist))
    )

    if args.json:
        print(
            json.dumps(
                {
                    "floor_pct": round(100 * args.min_gm, 1),
                    "failures": [f.to_dict() for f in failing],
                    "warnings": warnings,
                },
                indent=2,
            )
        )
    else:
        print(render(failing, warnings, args.min_gm))

    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
