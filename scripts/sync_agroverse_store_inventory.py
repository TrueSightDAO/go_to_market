#!/usr/bin/env python3
"""
Port of `agroverse_shop/google-app-script/update_store_inventory.gs` (Python).

1. Reads store managers, currency→SKU mapping, main-ledger inventory, and managed-ledger balances.
2. Writes computed totals to **Agroverse SKUs** column **I** (Store inventory).
3. Writes `store-inventory.json` for the public GitHub snapshot (same shape as today).

Requires `market_research/google_credentials.json` with access to:
- Main workbook `1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU`
- Every managed-ledger spreadsheet linked from **Shipment Ledger Listing** column **AB**

Usage:
  python3 scripts/sync_agroverse_store_inventory.py --dry-run
  python3 scripts/sync_agroverse_store_inventory.py --execute
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials as SACredentials

REPO = Path(__file__).resolve().parents[1]
SA_CREDS = REPO / "google_credentials.json"

MAIN_SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"

SKUS_SHEET_NAME = "Agroverse SKUs"
CURRENCIES_SHEET_NAME = "Currencies"
CONTRIBUTORS_SHEET_NAME = "Contributors contact information"
PARTNERS_SHEET_NAME = "Agroverse Partners"
OFFCHAIN_ASSET_LOCATION_SHEET_NAME = "offchain asset location"
SHIPMENT_LEDGER_SHEET_NAME = "Shipment Ledger Listing"
BALANCE_SHEET_NAME = "Balance"

SHEETS_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
)

_SPREADSHEET_ID_RE = re.compile(r"/d/([a-zA-Z0-9-_]+)")


def _truthy_store_manager(val: object) -> bool:
    if val is True:
        return True
    s = str(val).strip().lower()
    return s in ("true", "1", "yes")


def _to_float(val: object) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _extract_spreadsheet_id(url: str) -> str | None:
    m = _SPREADSHEET_ID_RE.search(url or "")
    return m.group(1) if m else None


def _client() -> gspread.Client:
    creds = SACredentials.from_service_account_file(str(SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def _gspread_retry(fn, *, max_attempts: int = 6) -> object:
    delay = 10.0
    for attempt in range(max_attempts):
        try:
            return fn()
        except APIError as e:
            msg = str(e)
            if ("429" in msg or "Quota" in msg) and attempt < max_attempts - 1:
                time.sleep(delay)
                delay = min(delay * 1.5, 120.0)
                continue
            raise


def get_store_managers(sh: gspread.Spreadsheet) -> list[str]:
    ws = sh.worksheet(CONTRIBUTORS_SHEET_NAME)
    rows = _gspread_retry(lambda: ws.get_values("A2:T"))
    managers: list[str] = []
    for row in rows:
        if len(row) < 20:
            continue
        name = row[0].strip() if row[0] else ""
        if name and _truthy_store_manager(row[19]):
            managers.append(name)
    return managers


def get_currency_to_sku_mapping(sh: gspread.Spreadsheet) -> dict[str, str]:
    ws = sh.worksheet(CURRENCIES_SHEET_NAME)
    rows = _gspread_retry(lambda: ws.get_values("A2:M"))
    mapping: dict[str, str] = {}
    for row in rows:
        if len(row) < 13:
            continue
        currency = row[0].strip() if row[0] else ""
        sku = row[12].strip() if row[12] else ""
        if currency and sku:
            mapping[currency] = sku
    return mapping


def _last_filled_row_in_col_a(ws: gspread.Worksheet) -> int:
    """Approximate Sheets `getLastRow()` for column A."""
    vals = ws.col_values(1)
    return len(vals)


def get_main_ledger_inventory(sh: gspread.Spreadsheet, store_managers: set[str]) -> dict[str, dict[str, float]]:
    ws = sh.worksheet(OFFCHAIN_ASSET_LOCATION_SHEET_NAME)
    last_row = _last_filled_row_in_col_a(ws)
    if last_row < 5:
        return {}
    # Match Apps Script behavior: rows 5 .. (lastRow - 4), inclusive end row.
    end_row = max(4, last_row - 4)
    if end_row < 5:
        return {}
    rng = f"A5:C{end_row}"
    rows = _gspread_retry(lambda: ws.get_values(rng))
    inv: dict[str, dict[str, float]] = {}
    for row in rows:
        if len(row) < 3:
            continue
        currency = row[0].strip() if row[0] else ""
        location = row[1].strip() if row[1] else ""
        amount = _to_float(row[2])
        if not currency or not location or location not in store_managers or amount <= 0:
            continue
        inv.setdefault(currency, {})
        inv[currency][location] = inv[currency].get(location, 0.0) + amount
    return inv


def get_managed_ledger_urls(sh: gspread.Spreadsheet) -> list[str]:
    ws = sh.worksheet(SHIPMENT_LEDGER_SHEET_NAME)
    rows = _gspread_retry(lambda: ws.get_values("A2:AB"))
    seen: set[str] = set()
    urls: list[str] = []
    for row in rows:
        if len(row) < 28:
            continue
        url = row[27].strip() if row[27] else ""
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def get_managed_ledger_inventory(
    gc: gspread.Client, ledger_url: str, store_managers: set[str]
) -> dict[str, dict[str, float]]:
    sid = _extract_spreadsheet_id(ledger_url)
    if not sid:
        return {}
    inv: dict[str, dict[str, float]] = {}
    try:
        msh = _gspread_retry(lambda: gc.open_by_key(sid))
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] Could not open managed ledger {ledger_url!r}: {e}")
        return inv
    try:
        mws = msh.worksheet(BALANCE_SHEET_NAME)
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] No Balance tab in {ledger_url!r}: {e}")
        return inv
    # One read for H:J (avoid extra `col_values` quota).
    rows = _gspread_retry(lambda: mws.get_values("H2:J"))
    while rows and not any(str(c).strip() for c in rows[-1]):
        rows.pop()
    for row in rows:
        if len(row) < 3:
            continue
        location = row[0].strip() if row[0] else ""
        amount = _to_float(row[1])
        currency = row[2].strip() if row[2] else ""
        if not currency or not location or location not in store_managers or amount <= 0:
            continue
        inv.setdefault(currency, {})
        inv[currency][location] = inv[currency].get(location, 0.0) + amount
    return inv


def calculate_sku_inventory(
    gc: gspread.Client, sh: gspread.Spreadsheet, *, managers: list[str] | None = None
) -> dict[str, float]:
    if managers is None:
        managers = get_store_managers(sh)
    if not managers:
        raise RuntimeError("No store managers found (Contributors contact information column T).")
    ms = set(managers)
    cur_to_sku = get_currency_to_sku_mapping(sh)
    if not cur_to_sku:
        raise RuntimeError("No currency→SKU mappings found (Currencies columns A and M).")

    sku_totals: dict[str, float] = {}

    main = get_main_ledger_inventory(sh, ms)
    for currency, by_mgr in main.items():
        sku = cur_to_sku.get(currency)
        if not sku:
            continue
        sku_totals[sku] = sku_totals.get(sku, 0.0) + sum(by_mgr.values())

    for url in get_managed_ledger_urls(sh):
        led = get_managed_ledger_inventory(gc, url, ms)
        for currency, by_mgr in led.items():
            sku = cur_to_sku.get(currency)
            if not sku:
                continue
            sku_totals[sku] = sku_totals.get(sku, 0.0) + sum(by_mgr.values())

    return sku_totals


def read_partners_by_contributor(sh: gspread.Spreadsheet) -> dict[str, list[str]]:
    """Map contributor_contact_id -> [partner_id, ...] from Agroverse Partners."""
    try:
        ws = sh.worksheet(PARTNERS_SHEET_NAME)
    except Exception:
        return {}
    rows = _gspread_retry(lambda: ws.get_all_values())
    if not rows:
        return {}
    header = [c.strip().lower() for c in rows[0]]

    def _idx(name: str, fallback: int) -> int:
        try:
            return header.index(name)
        except ValueError:
            return fallback

    partner_idx = _idx("partner_id", 0)
    contributor_idx = _idx("contributor_contact_id", 4)
    status_idx = _idx("status", 3)

    out: dict[str, list[str]] = {}
    for row in rows[1:]:
        if not row:
            continue
        partner_id = row[partner_idx].strip() if len(row) > partner_idx and row[partner_idx] else ""
        contributor = (
            row[contributor_idx].strip() if len(row) > contributor_idx and row[contributor_idx] else ""
        )
        status = row[status_idx].strip().lower() if len(row) > status_idx and row[status_idx] else "active"
        if not partner_id or not contributor or status == "inactive":
            continue
        out.setdefault(contributor, [])
        if partner_id not in out[contributor]:
            out[contributor].append(partner_id)
    return out


def read_sku_metadata(sh: gspread.Spreadsheet) -> dict[str, dict[str, str]]:
    """Read key SKU fields used for partner product snippets."""
    ws = sh.worksheet(SKUS_SHEET_NAME)
    rows = _gspread_retry(lambda: ws.get_all_values())
    if not rows:
        return {}
    header = [c.strip().lower() for c in rows[0]]

    def _idx(name: str, fallback: int) -> int:
        try:
            return header.index(name)
        except ValueError:
            return fallback

    id_idx = _idx("product id", 0)
    name_idx = _idx("product name", 1)
    price_idx = _idx("price (usd)", 2)
    category_idx = _idx("category", 4)
    shipment_idx = _idx("shipment", 5)
    farm_idx = _idx("farm", 6)
    image_idx = _idx("image path", 7)
    gtin_idx = _idx("gtin", 9)

    out: dict[str, dict[str, str]] = {}
    for row in rows[1:]:
        if not row:
            continue
        pid = row[id_idx].strip() if len(row) > id_idx and row[id_idx] else ""
        if not pid:
            continue
        out[pid] = {
            "productId": pid,
            "productName": row[name_idx].strip() if len(row) > name_idx and row[name_idx] else "",
            "priceUsd": row[price_idx].strip() if len(row) > price_idx and row[price_idx] else "",
            "category": row[category_idx].strip() if len(row) > category_idx and row[category_idx] else "",
            "shipment": row[shipment_idx].strip() if len(row) > shipment_idx and row[shipment_idx] else "",
            "farm": row[farm_idx].strip() if len(row) > farm_idx and row[farm_idx] else "",
            "imagePath": row[image_idx].strip() if len(row) > image_idx and row[image_idx] else "",
            "gtin": row[gtin_idx].strip() if len(row) > gtin_idx and row[gtin_idx] else "",
        }
    return out


def calculate_partner_sku_inventory(
    gc: gspread.Client, sh: gspread.Spreadsheet, *, managers: list[str] | None = None
) -> dict[str, dict[str, float]]:
    """Aggregate inventory by partner_id and sku using contributor mappings."""
    if managers is None:
        managers = get_store_managers(sh)
    ms = set(managers)
    if not ms:
        return {}

    contributor_to_partners = read_partners_by_contributor(sh)
    if not contributor_to_partners:
        return {}

    cur_to_sku = get_currency_to_sku_mapping(sh)
    if not cur_to_sku:
        return {}

    partner_totals: dict[str, dict[str, float]] = {}

    def accumulate(currency_map: dict[str, dict[str, float]]) -> None:
        for currency, by_mgr in currency_map.items():
            sku = cur_to_sku.get(currency)
            if not sku:
                continue
            for manager, qty in by_mgr.items():
                if manager not in ms:
                    continue
                partner_ids = contributor_to_partners.get(manager, [])
                for partner_id in partner_ids:
                    partner_totals.setdefault(partner_id, {})
                    partner_totals[partner_id][sku] = partner_totals[partner_id].get(sku, 0.0) + qty

    accumulate(get_main_ledger_inventory(sh, ms))
    for url in get_managed_ledger_urls(sh):
        accumulate(get_managed_ledger_inventory(gc, url, ms))

    return partner_totals


def read_sku_product_ids(sh: gspread.Spreadsheet) -> list[str]:
    ws = sh.worksheet(SKUS_SHEET_NAME)
    last = _last_filled_row_in_col_a(ws)
    if last < 2:
        return []
    col = _gspread_retry(lambda: ws.get_values(f"A2:A{last}"))
    out: list[str] = []
    for r in col:
        if not r:
            continue
        pid = r[0].strip() if r[0] else ""
        if pid:
            out.append(pid)
    return out


def read_current_inventory_column(sh: gspread.Spreadsheet) -> dict[str, float]:
    ws = sh.worksheet(SKUS_SHEET_NAME)
    last = _last_filled_row_in_col_a(ws)
    if last < 2:
        return {}
    rows = _gspread_retry(lambda: ws.get_values(f"A2:I{last}"))
    cur: dict[str, float] = {}
    for row in rows:
        if not row:
            continue
        pid = row[0].strip() if row[0] else ""
        if not pid:
            continue
        inv = _to_float(row[8]) if len(row) > 8 else 0.0
        cur[pid] = inv
    return cur


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write Agroverse SKUs column I and store-inventory.json (default is dry-run).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPO.parent / "agroverse-inventory" / "store-inventory.json",
        help="Path to store-inventory.json",
    )
    parser.add_argument(
        "--partner-json-out",
        type=Path,
        default=REPO.parent / "agroverse-inventory" / "partners-inventory.json",
        help="Path to partner inventory JSON payload.",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    if not SA_CREDS.exists():
        raise SystemExit(f"Missing {SA_CREDS}")

    gc = _client()
    sh = _gspread_retry(lambda: gc.open_by_key(MAIN_SPREADSHEET_ID))

    managers = get_store_managers(sh)
    sku_totals = calculate_sku_inventory(gc, sh, managers=managers)
    partner_totals = calculate_partner_sku_inventory(gc, sh, managers=managers)
    sku_meta = read_sku_metadata(sh)
    product_ids = read_sku_product_ids(sh)
    if not product_ids:
        raise SystemExit("No product IDs found in Agroverse SKUs column A.")

    # Full snapshot: every SKU row gets a value (0 if not present in ledger-derived totals).
    snapshot: dict[str, int] = {}
    updates: list[list[int]] = []
    for pid in product_ids:
        qty = int(round(sku_totals.get(pid, 0.0)))
        snapshot[pid] = qty
        updates.append([qty])

    current = read_current_inventory_column(sh)
    changed = [pid for pid in product_ids if int(round(current.get(pid, 0.0))) != snapshot[pid]]

    print(f"Store managers: {len(managers)}")
    print(f"SKUs on sheet: {len(product_ids)}")
    print(f"Ledger-derived SKUs with >0 qty: {sum(1 for k, v in snapshot.items() if v > 0)}")
    if changed:
        print(f"Column I changes vs sheet: {len(changed)}")
        for pid in sorted(changed)[:30]:
            print(f"  {pid}: {int(round(current.get(pid, 0.0)))} -> {snapshot[pid]}")
        if len(changed) > 30:
            print(f"  ... and {len(changed) - 30} more")
    else:
        print("Column I already matches calculated inventory for all listed SKUs.")

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "source": "sync_agroverse_store_inventory",
        "inventory": snapshot,
    }

    partner_payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "source": "sync_agroverse_store_inventory",
        "partners": {},
    }
    for partner_id, sku_map in sorted(partner_totals.items()):
        items = []
        for sku, qty in sorted(sku_map.items()):
            q_int = int(round(qty))
            if q_int <= 0:
                continue
            online_qty = int(round(snapshot.get(sku, 0.0)))
            item = {
                "productId": sku,
                "inventory": q_int,
                "venueInventory": q_int,
                "onlineInventory": online_qty,
                "availableOnline": online_qty > 0,
            }
            meta = sku_meta.get(sku, {})
            item.update({k: v for k, v in meta.items() if k != "productId" and v})
            items.append(item)
        if items:
            partner_payload["partners"][partner_id] = {"items": items}

    if dry_run:
        print("\nDry run: no sheet or JSON writes. Re-run with --execute to apply.")
        print(
            f"Partner inventory payload (partners with items): "
            f"{len(partner_payload['partners'])}"
        )
        return

    ws = sh.worksheet(SKUS_SHEET_NAME)
    n = len(updates)
    ws.update(values=updates, range_name=f"I2:I{1 + n}", value_input_option="USER_ENTERED")

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.partner_json_out.parent.mkdir(parents=True, exist_ok=True)
    args.partner_json_out.write_text(json.dumps(partner_payload, indent=2) + "\n", encoding="utf-8")

    print(f"\nWrote Agroverse SKUs column I (rows 2..{1 + n}).")
    print(f"Wrote JSON: {args.json_out}")
    print(f"Wrote partner JSON: {args.partner_json_out}")


if __name__ == "__main__":
    main()
