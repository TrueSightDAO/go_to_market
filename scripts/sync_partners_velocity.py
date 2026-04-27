#!/usr/bin/env python3
"""
Compute per-(partner, product) historical sales velocity and emit
``partners-velocity.json`` to the sibling ``agroverse-inventory`` repo.

This is the *velocity* counterpart to ``sync_agroverse_store_inventory.py``
(which produces the *current snapshot* ``partners-inventory.json``). Both
scripts share the same partner_id ↔ contributor_contact_id ↔ store-manager
join chain.

Background and decisions: ``agentic_ai_context/PARTNER_VELOCITY_PROPOSAL.md``.

What it produces (per partner_id × SKU):
- ``sales_30d`` / ``sales_90d`` / ``sales_12m_monthly_avg`` — sell-through
  events from ``QR Code Sales`` (Telegram & Submissions spreadsheet) where
  ``Sold by`` resolves to one of the partner's contributor names. **Trustworthy
  for `Consignment` partners** (they report each sale via `[SALES EVENT]`).
  **Sparse for `Wholesale` partners** (they don't report individual sales).
- ``restocks_30d_units`` / ``restocks_90d_units`` / ``restocks_12m_monthly_avg_units``
  — units shipped TO the partner, summed from ``Inventory Movement`` rows
  where ``RECIPIENT NAME`` resolves to one of the partner's contributor
  names. **Trustworthy for every partner type** (lagged proxy for sell-through).
- ``last_sale_date`` / ``last_restock_date`` — most recent event timestamps
  (so consumers can flag dormant partners).
- ``sample_size_sales`` / ``sample_size_restocks`` — count of contributing
  rows (low N = low confidence).
- ``partner_type`` — from ``Agroverse Partners`` column **I** (added 2026-04-27),
  validated against the canonical enum on ``States`` column **Z** (Wholesale,
  Consignment, Operator, Supplier, Manufacturer). The Restock Recommender
  picks ``sales_*`` for Consignment partners and ``restocks_*`` for Wholesale;
  Operator / Supplier / Manufacturer rows are emitted but should be skipped
  by retail consumers.

Cold-start / category fallback:
- ``category_medians`` block at the top level — for each SKU, the median
  ``*_12m_monthly_avg`` (across **all** partners that have a non-zero value).
  Per Gary's §9 Q4 decision, the median is computed across all partners,
  not gated to 12-month-tenured ones.

Refresh cadence: weekly (per §9 Q2).

Requires ``market_research/google_credentials.json`` with read access to:
- Main workbook ``1GE7PUq-…`` (Agroverse Partners, Contributors contact
  information, Currencies).
- Telegram & Submissions workbook ``1qbZZhf-…`` (QR Code Sales, Inventory
  Movement).

Usage:
  python3 scripts/sync_partners_velocity.py --dry-run
  python3 scripts/sync_partners_velocity.py --execute
  python3 scripts/sync_partners_velocity.py --execute --output ../agroverse-inventory/partners-velocity.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import gspread

# Reuse helpers + constants from the inventory sync script — same join chain.
_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import sync_agroverse_store_inventory as inv  # noqa: E402

MAIN_SPREADSHEET_ID = inv.MAIN_SPREADSHEET_ID
TELEGRAM_SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"

# Tab names on the Telegram & Submissions workbook.
QR_CODE_SALES_SHEET_NAME = "QR Code Sales"
INVENTORY_MOVEMENT_SHEET_NAME = "Inventory Movement"

# QR Code Sales column indices (0-based) — see tokenomics/SCHEMA.md.
QRS_COL_SALES_DATE = 7   # H — YYYYMMDD
QRS_COL_CURRENCY = 8     # I — product / currency
QRS_COL_STATUS = 9       # J — TOKENIZED / ACCOUNTED / PROCESSING / IGNORED / empty
QRS_COL_SOLD_BY = 15     # P — resolved store-manager display name

# Inventory Movement column indices (0-based) — see tokenomics/SCHEMA.md.
INV_COL_STATUS_DATE = 6  # G
INV_COL_RECIPIENT = 8    # I — uppercase header "RECIPIENT NAME"
INV_COL_CURRENCY = 9     # J — uppercase header "CURRENCY"
INV_COL_AMOUNT = 10      # K — uppercase header "AMOUNT"
INV_COL_STATUS = 13      # N — STATUS

# Statuses considered "real" sales / movements (skip everything else).
QRS_VALID_STATUSES = {"TOKENIZED", "ACCOUNTED"}
# Inventory Movement: NEW = authorized + pending application to ledgers;
# PROCESSED = already applied. Both count for velocity. `unauthorized` (and
# any other non-empty value) is skipped. Empty STATUS on rare legacy rows is
# treated as authorized.
INV_VALID_STATUSES = {"NEW", "PROCESSED"}

# Time windows (days) — proposal §4.
WINDOW_30 = 30
WINDOW_90 = 90
WINDOW_365 = 365

# Default output location.
DEFAULT_OUTPUT = _REPO.parent / "agroverse-inventory" / "partners-velocity.json"


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_date(raw: str) -> date | None:
    """Best-effort date parse for ledger cells.

    QR Code Sales H is documented as YYYYMMDD. Inventory Movement G is
    formatted by GAS as a normal date. Accept both plus a few common
    fallbacks; return None for anything we can't parse.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # YYYYMMDD (no separators)
    if len(s) == 8 and s.isdigit():
        try:
            return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    # Common separator-bearing formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Sheets sometimes returns ISO with time
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _months_between(d: date, today: date) -> float:
    return (today - d).days / 30.4375


# ---------------------------------------------------------------------------
# Sheet readers
# ---------------------------------------------------------------------------

def read_partner_types(sh: gspread.Spreadsheet) -> dict[str, str]:
    """Map partner_id -> partner_type from `Agroverse Partners`!I.

    Validated values per canonical `States`!Z enum: `Wholesale`,
    `Consignment`, `Operator`, `Supplier`, `Manufacturer`. Anything else
    (or empty) is mapped to `Consignment` per the 2026-04-27 default.
    """
    ALLOWED = {"Wholesale", "Consignment", "Operator", "Supplier", "Manufacturer"}
    ws = sh.worksheet(inv.PARTNERS_SHEET_NAME)
    rows = inv._gspread_retry(lambda: ws.get_all_values())
    if not rows:
        return {}
    header = [c.strip().lower() for c in rows[0]]

    def _idx(name: str, fallback: int) -> int:
        try:
            return header.index(name)
        except ValueError:
            return fallback

    partner_idx = _idx("partner_id", 0)
    type_idx = _idx("partner_type", 8)  # Column I = 8 (0-based)

    out: dict[str, str] = {}
    for row in rows[1:]:
        if not row or len(row) <= partner_idx:
            continue
        partner_id = (row[partner_idx] or "").strip()
        if not partner_id:
            continue
        ptype_raw = ""
        if len(row) > type_idx and row[type_idx]:
            ptype_raw = row[type_idx].strip()
        # Default unset / unknown values to Consignment (operator-defined default).
        ptype = ptype_raw if ptype_raw in ALLOWED else "Consignment"
        out[partner_id] = ptype
    return out


@dataclass
class _Event:
    when: date
    quantity: float
    currency: str  # raw Currency string from the sheet


def read_qr_code_sales(gc: gspread.Client) -> list[tuple[str, _Event]]:
    """Return [(sold_by_contributor_name, Event), ...] for valid sales rows."""
    sh = inv._gspread_retry(lambda: gc.open_by_key(TELEGRAM_SPREADSHEET_ID))
    ws = sh.worksheet(QR_CODE_SALES_SHEET_NAME)
    rows = inv._gspread_retry(lambda: ws.get_all_values())
    if not rows or len(rows) < 2:
        return []
    out: list[tuple[str, _Event]] = []
    for row in rows[1:]:
        if not row or len(row) <= QRS_COL_STATUS:
            continue
        status = (row[QRS_COL_STATUS] if len(row) > QRS_COL_STATUS else "").strip().upper()
        if status not in QRS_VALID_STATUSES:
            continue
        sold_by = (row[QRS_COL_SOLD_BY] if len(row) > QRS_COL_SOLD_BY else "").strip()
        if not sold_by:
            continue
        currency = (row[QRS_COL_CURRENCY] if len(row) > QRS_COL_CURRENCY else "").strip()
        if not currency:
            continue
        d = _parse_date(row[QRS_COL_SALES_DATE] if len(row) > QRS_COL_SALES_DATE else "")
        if not d:
            continue
        out.append((sold_by, _Event(when=d, quantity=1.0, currency=currency)))
    return out


def read_inventory_movements(gc: gspread.Client) -> list[tuple[str, _Event]]:
    """Return [(recipient_name, Event), ...] for NEW (authorized) movements."""
    sh = inv._gspread_retry(lambda: gc.open_by_key(TELEGRAM_SPREADSHEET_ID))
    ws = sh.worksheet(INVENTORY_MOVEMENT_SHEET_NAME)
    rows = inv._gspread_retry(lambda: ws.get_all_values())
    if not rows or len(rows) < 2:
        return []
    out: list[tuple[str, _Event]] = []
    for row in rows[1:]:
        if not row or len(row) <= INV_COL_AMOUNT:
            continue
        # STATUS column may be missing on older rows — treat as NEW (legacy authorized).
        status = (row[INV_COL_STATUS] if len(row) > INV_COL_STATUS else "NEW").strip().upper()
        if status and status not in INV_VALID_STATUSES:
            continue
        recipient = (row[INV_COL_RECIPIENT] if len(row) > INV_COL_RECIPIENT else "").strip()
        if not recipient:
            continue
        currency = (row[INV_COL_CURRENCY] if len(row) > INV_COL_CURRENCY else "").strip()
        if not currency:
            continue
        amount = inv._to_float(row[INV_COL_AMOUNT] if len(row) > INV_COL_AMOUNT else 0)
        if amount <= 0:
            continue
        d = _parse_date(row[INV_COL_STATUS_DATE] if len(row) > INV_COL_STATUS_DATE else "")
        if not d:
            continue
        out.append((recipient, _Event(when=d, quantity=amount, currency=currency)))
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

@dataclass
class _SkuStats:
    units_30d: float = 0.0
    units_90d: float = 0.0
    units_365d: float = 0.0
    last_event: date | None = None
    sample_size: int = 0
    # For 12m monthly avg we only count events within the 365-day window.

    def add(self, ev: _Event, today: date) -> None:
        days = (today - ev.when).days
        if days < 0:
            return  # future-dated row, skip
        if days <= WINDOW_30:
            self.units_30d += ev.quantity
        if days <= WINDOW_90:
            self.units_90d += ev.quantity
        if days <= WINDOW_365:
            self.units_365d += ev.quantity
            self.sample_size += 1
        if self.last_event is None or ev.when > self.last_event:
            self.last_event = ev.when


def aggregate_events(
    events: list[tuple[str, _Event]],
    *,
    contributor_to_partners: dict[str, list[str]],
    currency_to_sku: dict[str, str],
    today: date,
) -> dict[str, dict[str, _SkuStats]]:
    """Bucket events into partner_id → sku → _SkuStats."""
    by_partner: dict[str, dict[str, _SkuStats]] = defaultdict(lambda: defaultdict(_SkuStats))
    for actor, ev in events:
        partner_ids = contributor_to_partners.get(actor)
        if not partner_ids:
            continue
        sku = currency_to_sku.get(ev.currency)
        if not sku:
            # Unknown currency → skip (consumer can't join to a SKU).
            continue
        for pid in partner_ids:
            by_partner[pid][sku].add(ev, today=today)
    return by_partner


def stats_to_dict(stats: _SkuStats, *, prefix: str) -> dict:
    """Convert _SkuStats → JSON dict with the requested field prefix."""
    monthly_avg = stats.units_365d / 12.0 if stats.units_365d else 0.0
    return {
        f"{prefix}_30d": stats.units_30d,
        f"{prefix}_90d": stats.units_90d,
        f"{prefix}_12m_monthly_avg": round(monthly_avg, 3),
    }


def build_partners_block(
    *,
    sales_by_partner: dict[str, dict[str, _SkuStats]],
    restocks_by_partner: dict[str, dict[str, _SkuStats]],
    partner_types: dict[str, str],
) -> dict[str, dict]:
    """Merge sales + restocks → partners block keyed by partner_id."""
    all_partner_ids = set(sales_by_partner) | set(restocks_by_partner) | set(partner_types)
    out: dict[str, dict] = {}
    for pid in sorted(all_partner_ids):
        items: dict[str, dict] = {}
        skus = set(sales_by_partner.get(pid, {})) | set(restocks_by_partner.get(pid, {}))
        for sku in sorted(skus):
            s = sales_by_partner.get(pid, {}).get(sku)
            r = restocks_by_partner.get(pid, {}).get(sku)
            entry: dict = {}
            if s:
                entry.update(stats_to_dict(s, prefix="sales"))
                entry["last_sale_date"] = s.last_event.isoformat() if s.last_event else None
                entry["sample_size_sales"] = s.sample_size
            else:
                entry.update({"sales_30d": 0, "sales_90d": 0, "sales_12m_monthly_avg": 0,
                              "last_sale_date": None, "sample_size_sales": 0})
            if r:
                entry.update(stats_to_dict(r, prefix="restocks"))
                entry["last_restock_date"] = r.last_event.isoformat() if r.last_event else None
                entry["sample_size_restocks"] = r.sample_size
            else:
                entry.update({"restocks_30d": 0, "restocks_90d": 0, "restocks_12m_monthly_avg": 0,
                              "last_restock_date": None, "sample_size_restocks": 0})
            items[sku] = entry
        out[pid] = {
            "partner_type": partner_types.get(pid, "Consignment"),
            "items": items,
        }
    return out


def compute_category_medians(
    sales_by_partner: dict[str, dict[str, _SkuStats]],
    restocks_by_partner: dict[str, dict[str, _SkuStats]],
) -> dict[str, dict[str, float]]:
    """Median 12m monthly velocity per SKU across **all** partners (per §9 Q4).

    For each SKU, gather the per-partner ``*_12m_monthly_avg`` from both
    sales and restocks (the larger of the two for a given partner is taken
    as their canonical "monthly throughput" for that SKU). Median across
    non-zero contributions.
    """
    by_sku: dict[str, list[float]] = defaultdict(list)
    all_partner_ids = set(sales_by_partner) | set(restocks_by_partner)
    for pid in all_partner_ids:
        skus = set(sales_by_partner.get(pid, {})) | set(restocks_by_partner.get(pid, {}))
        for sku in skus:
            s_units = (sales_by_partner.get(pid, {}).get(sku) or _SkuStats()).units_365d
            r_units = (restocks_by_partner.get(pid, {}).get(sku) or _SkuStats()).units_365d
            best = max(s_units, r_units) / 12.0
            if best > 0:
                by_sku[sku].append(best)
    out: dict[str, dict[str, float]] = {}
    for sku, vals in by_sku.items():
        if vals:
            out[sku] = {"monthly": round(statistics.median(vals), 3), "sample_size": len(vals)}
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="Print summary without writing the JSON (default).")
    g.add_argument("--execute", action="store_true",
                   help="Write partners-velocity.json to disk.")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help=f"Output path (default: {DEFAULT_OUTPUT})")
    p.add_argument("--today", type=str, default=None,
                   help="Override 'today' for testing (YYYY-MM-DD).")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    today = (
        datetime.strptime(args.today, "%Y-%m-%d").date()
        if args.today else date.today()
    )

    gc = inv._client()
    main_sh = inv._gspread_retry(lambda: gc.open_by_key(MAIN_SPREADSHEET_ID))

    print(f"Reading partner / contributor / currency mappings from {MAIN_SPREADSHEET_ID}…")
    contributor_to_partners = inv.read_partners_by_contributor(main_sh)
    if not contributor_to_partners:
        raise SystemExit("No active partners found in `Agroverse Partners` — abort.")
    partner_types = read_partner_types(main_sh)
    currency_to_sku = inv.get_currency_to_sku_mapping(main_sh)
    if not currency_to_sku:
        raise SystemExit("No currency→SKU mappings found in `Currencies` — abort.")

    print(f"Reading sales + movements from Telegram & Submissions ({TELEGRAM_SPREADSHEET_ID})…")
    qr_sales_events = read_qr_code_sales(gc)
    movement_events = read_inventory_movements(gc)
    print(f"  {len(qr_sales_events)} QR Code Sales rows (TOKENIZED/ACCOUNTED)")
    print(f"  {len(movement_events)} Inventory Movement rows (NEW/PROCESSED)")

    sales_by_partner = aggregate_events(
        qr_sales_events,
        contributor_to_partners=contributor_to_partners,
        currency_to_sku=currency_to_sku,
        today=today,
    )
    restocks_by_partner = aggregate_events(
        movement_events,
        contributor_to_partners=contributor_to_partners,
        currency_to_sku=currency_to_sku,
        today=today,
    )

    partners_block = build_partners_block(
        sales_by_partner=sales_by_partner,
        restocks_by_partner=restocks_by_partner,
        partner_types=partner_types,
    )
    category_medians = compute_category_medians(sales_by_partner, restocks_by_partner)

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "source": "sync_partners_velocity",
        "windowsDays": [WINDOW_30, WINDOW_90, WINDOW_365],
        "category_medians": category_medians,
        "partners": partners_block,
    }

    if args.verbose:
        print(json.dumps(payload, indent=2)[:4000])
        print("…(truncated)…")

    print(f"\nPartners with velocity data: {sum(1 for v in partners_block.values() if v['items'])}")
    print(f"Partners by type:")
    type_counts: dict[str, int] = defaultdict(int)
    for v in partners_block.values():
        type_counts[v["partner_type"]] += 1
    for t, n in sorted(type_counts.items()):
        print(f"  {t}: {n}")
    print(f"Category medians computed for {len(category_medians)} SKUs.")

    if args.execute:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.output}")
    else:
        print("\n--dry-run (default) — pass --execute to write the file.")


if __name__ == "__main__":
    main()
