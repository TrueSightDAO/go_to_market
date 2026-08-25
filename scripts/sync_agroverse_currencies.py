#!/usr/bin/env python3
"""
Regenerate TrueSightDAO/agroverse-inventory/currencies.json from the live
"Currencies" tab of the Main Ledger (Google Sheets).

Mirrors the output shape of
`agroverse-inventory/gas/repackaging-currency-ingest/Code.gs`
(`readCurrencyStringsFromSheet_()` + `publishCurrenciesJsonToGitHub_()`) - same
{generatedAt, source, currencies} envelope and the same trim -> skip-empty ->
dedupe-first-wins -> sort transform on column A rows 2..last - but decoupled
from the repackaging-ingest event path: any edit to the Currencies tab (manual,
QR-code minting flow, or any other pathway) reaches the published file on the
next scheduled run, instead of only when a [REPACKAGING BATCH...] event happens
to fire the GAS publisher. See
agentic_ai_context/plans/CURRENCY_CONVERSION_STALE_CURRENCIES_JSON_PLAN.md.

`source` is set to "sync_agroverse_currencies" (the GAS publisher uses
"repackaging_currency_ingest"). Safe to differ: currency_conversion.html only
reads `data.currencies` (and `generatedAt` for its freshness caption) - it never
inspects `source`.

Requires `market_research/google_credentials.json` with access to the Main
workbook 1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU (Currencies tab,
gid 1552160318).

Usage:
  python3 scripts/sync_agroverse_currencies.py --dry-run
  python3 scripts/sync_agroverse_currencies.py --execute
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials as SACredentials

REPO = Path(__file__).resolve().parents[1]
SA_CREDS = REPO / "google_credentials.json"

MAIN_SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
CURRENCIES_SHEET_NAME = "Currencies"
CURRENCIES_SHEET_GID = 1552160318  # stable key, matches the plan-of-record section 1

SHEETS_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
)


def _client() -> gspread.Client:
    creds = SACredentials.from_service_account_file(str(SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def _gspread_retry(fn, *, max_attempts: int = 6) -> object:
    """Retry transient Sheets API 429s with backoff (same as the sibling
    sync_agroverse_store_inventory.py)."""
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


def read_currencies(sh: gspread.Spreadsheet) -> list[str]:
    """Read column A rows 2..last from the Currencies tab.

    Mirrors the GAS `readCurrencyStringsFromSheet_()` exactly: trim -> skip
    empty -> dedupe (first occurrence wins) -> sort. Plain code-point sort keeps
    the output byte-stable with the one-time PR1 catch-up republish, so the first
    scheduled run does not churn the file's order.
    """
    ws = sh.worksheet(CURRENCIES_SHEET_NAME)
    vals = _gspread_retry(lambda: ws.get_values("A2:A"))
    out: list[str] = []
    seen: set[str] = set()
    for row in vals:
        if not row:
            continue
        s = str(row[0]).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    out.sort()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync currencies.json from the live Main Ledger Currencies tab."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write currencies.json (default is dry-run).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPO.parent / "agroverse-inventory" / "currencies.json",
        help="Path to currencies.json",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    if not SA_CREDS.exists():
        raise SystemExit(f"Missing {SA_CREDS}")

    gc = _client()
    sh = _gspread_retry(lambda: gc.open_by_key(MAIN_SPREADSHEET_ID))

    currencies = read_currencies(sh)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "source": "sync_agroverse_currencies",
        "currencies": currencies,
    }

    print(f"Currencies read from live sheet: {len(currencies)}")
    if dry_run:
        print("\nDry run: no file writes. Re-run with --execute to apply.")
        print(json.dumps(payload, indent=2)[:2000])
        return

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.json_out} "
        f"({len(currencies)} currencies, generatedAt={payload['generatedAt']})"
    )


if __name__ == "__main__":
    main()
