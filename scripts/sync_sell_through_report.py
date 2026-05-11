#!/usr/bin/env python3
"""
Generate sell-through report JSON: per-inventory-type and per-partner
rates across USA partners.  Output to agroverse-inventory repo for
consumption by truesight.me and the DApp Restock Recommender.

Usage:
  python3 scripts/sync_sell_through_report.py --dry-run
  python3 scripts/sync_sell_through_report.py --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import gspread

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import sync_agroverse_store_inventory as inv
import sync_partners_velocity as vel

MAIN_SPREADSHEET_ID = inv.MAIN_SPREADSHEET_ID
DEFAULT_OUTPUT = _REPO.parent / "agroverse-inventory" / "sell-through-report.json"

USA_STATES = {
    "california", "oregon", "washington", "arizona", "nevada", "colorado",
    "new york", "texas", "new mexico", "illinois", "florida",
}


def _is_usa(location: str) -> bool:
    loc = location.lower()
    if "brazil" in loc or "switzerland" in loc:
        return False
    return any(s in loc for s in USA_STATES)


def _read_sku_inventory_types(gc: gspread.Client) -> dict[str, str]:
    """Map SKU slug → Inventory Type (Currencies column P, index 15)."""
    main_sh = gc.open_by_key(MAIN_SPREADSHEET_ID)
    ws = main_sh.worksheet("Currencies")
    rows = inv._gspread_retry(lambda: ws.get_all_values())
    mapping: dict[str, str] = {}
    for row in rows[1:]:
        if len(row) < 16:
            continue
        sku = row[12].strip() if len(row) > 12 else ""
        inv_type = row[15].strip() if len(row) > 15 else ""
        if sku and inv_type:
            mapping.setdefault(sku, inv_type)
    return mapping


def build_sell_through_report() -> dict:
    gc = inv._client()

    # Load velocity + partner metadata
    main_sh = gc.open_by_key(MAIN_SPREADSHEET_ID)
    currency_to_sku = inv.get_currency_to_sku_mapping(main_sh)
    contributor_to_partners = inv.read_partners_by_contributor(main_sh)
    partner_metadata = vel.read_partner_metadata(main_sh)

    # Read sales + restock events
    today = datetime.now(timezone.utc).date()
    qr_sales = vel.read_qr_code_sales(gc)
    movements = vel.read_inventory_movements(gc)

    sales_by_partner = vel.aggregate_events(
        qr_sales, contributor_to_partners=contributor_to_partners,
        currency_to_sku=currency_to_sku, today=today)
    restocks_by_partner = vel.aggregate_events(
        movements, contributor_to_partners=contributor_to_partners,
        currency_to_sku=currency_to_sku, today=today)

    # SKU → Inventory Type lookup
    sku_to_type = _read_sku_inventory_types(gc)

    # Per-inventory-type aggregation (USA only)
    by_type: dict[str, dict] = defaultdict(
        lambda: {"sales_monthly": 0.0, "restocks_monthly": 0.0, "partners": set(), "skus": set()})

    # Per-partner list
    partners_list: list[dict] = []

    all_ids = set(sales_by_partner) | set(restocks_by_partner)
    for pid in all_ids:
        meta = partner_metadata.get(pid, {})
        location = meta.get("location", "")
        if not _is_usa(location):
            continue

        partner_total_s = 0.0
        partner_total_r = 0.0
        skus = set(sales_by_partner.get(pid, {})) | set(restocks_by_partner.get(pid, {}))
        items: list[dict] = []

        for sku in skus:
            inv_type = sku_to_type.get(sku, "Unknown")
            s_stats = sales_by_partner.get(pid, {}).get(sku)
            r_stats = restocks_by_partner.get(pid, {}).get(sku)
            s12 = s_stats.units_365d / 12.0 if s_stats else 0.0
            r12 = r_stats.units_365d / 12.0 if r_stats else 0.0

            items.append({
                "sku": sku,
                "inventory_type": inv_type,
                "sales_monthly": round(s12, 3),
                "restocks_monthly": round(r12, 3),
            })

            partner_total_s += s12
            partner_total_r += r12

            by_type[inv_type]["sales_monthly"] += s12
            by_type[inv_type]["restocks_monthly"] += r12
            by_type[inv_type]["partners"].add(pid)
            by_type[inv_type]["skus"].add(sku)

        sell_through = (partner_total_s / partner_total_r * 100) if partner_total_r > 0 else 0.0
        partners_list.append({
            "partner_id": pid,
            "partner_name": meta.get("partner_name", pid),
            "location": location,
            "partner_type": meta.get("partner_type", "Consignment"),
            "sales_monthly": round(partner_total_s, 3),
            "restocks_monthly": round(partner_total_r, 3),
            "sell_through_pct": round(sell_through, 1),
            "items": items,
        })

    # Sort partners by sell-through descending
    partners_list.sort(key=lambda p: p["sell_through_pct"], reverse=True)

    # By-type summary
    type_summary = {}
    for itype, data in by_type.items():
        s = data["sales_monthly"]
        r = data["restocks_monthly"]
        rate = (s / r * 100) if r > 0 else 0.0
        type_summary[itype] = {
            "sales_monthly": round(s, 3),
            "restocks_monthly": round(r, 3),
            "sell_through_pct": round(rate, 1),
            "partner_count": len(data["partners"]),
            "sku_count": len(data["skus"]),
        }

    # Overall
    total_s = sum(p["sales_monthly"] for p in partners_list)
    total_r = sum(p["restocks_monthly"] for p in partners_list)
    overall_rate = (total_s / total_r * 100) if total_r > 0 else 0.0
    with_sales = sum(1 for p in partners_list if p["sales_monthly"] > 0)
    zero_sales = len(partners_list) - with_sales

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "source": "sync_sell_through_report",
        "summary": {
            "total_usa_partners": len(partners_list),
            "partners_with_sales": with_sales,
            "partners_zero_sales": zero_sales,
            "overall_sell_through_pct": round(overall_rate, 1),
            "total_sales_monthly": round(total_s, 3),
            "total_restocks_monthly": round(total_r, 3),
        },
        "by_inventory_type": type_summary,
        "partners": partners_list,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=False)
    g.add_argument("--execute", action="store_true")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args()

    report = build_sell_through_report()

    if not args.execute:
        print("\n--dry-run (default) — pass --execute to write the file.")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
