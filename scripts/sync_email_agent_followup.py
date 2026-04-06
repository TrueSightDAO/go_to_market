#!/usr/bin/env python3
"""
Sync sent-mail history from Gmail into the "Email Agent Follow Up" tab on the Hit List spreadsheet.

Flow
----
1. Open "Hit List" → rows where Status == "Manager Follow-up" and Email (column K) non-empty.
2. For each distinct email address, query Gmail (in:sent to:...) via OAuth token.
3. Append new rows to "Email Agent Follow Up" keyed by gmail_message_id (no duplicates). Each row includes
   **snippet** (Gmail preview) and **body_plain** (best-effort full plain text from the sent message) for
   draft/Grok context.

Prerequisites
-------------
- Spreadsheet shared with service account in google_credentials.json (see HIT_LIST_CREDENTIALS.md).
- Gmail: local `credentials/gmail/token.json` (from `gmail_oauth_authorize.py`), or CI env **`GMAIL_TOKEN_JSON`** (full token JSON). See `scripts/gmail_user_credentials.py`.
- Tabs: "Hit List" and "Email Agent Follow Up" (created automatically if missing with header row).

Usage
-----
  cd market_research
  source venv/bin/activate
  python3 scripts/sync_email_agent_followup.py           # append new log rows
  python3 scripts/sync_email_agent_followup.py --dry-run # print plan only
  python3 scripts/sync_email_agent_followup.py --limit 5 # max distinct addresses (testing)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build

from gmail_plain_body import PLAIN_BODY_MAX_CHARS, extract_plain_body_from_payload
from gmail_user_credentials import load_gmail_user_credentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
LOG_WS = "Email Agent Follow Up"

HIT_STATUS_TARGET = "Manager Follow-up"
# Must match (or be a subset of) scopes in credentials/gmail/token.json from gmail_oauth_authorize.py
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LOG_HEADERS = [
    "gmail_message_id",
    "synced_at_utc",
    "store_key",
    "shop_name",
    "to_email",
    "subject",
    "sent_at",
    "snippet",
    "body_plain",
    "sync_source",
]


def normalize_email(raw: str) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or "@" not in s:
        return None
    return s.lower()


def header_map(row: list[str]) -> dict[str, int]:
    return {h.strip(): i for i, h in enumerate(row) if h.strip()}


def cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip() if idx < len(row) else ""


def load_hit_list_targets(ws) -> list[dict]:
    """Rows needing manager-follow-up with a usable Email."""
    values = ws.get_all_values()
    if not values:
        return []
    hdr = header_map(values[0])
    status_i = hdr.get("Status")
    email_i = hdr.get("Email")
    store_i = hdr.get("Store Key")
    shop_i = hdr.get("Shop Name")
    if status_i is None or email_i is None:
        raise SystemExit(
            "Hit List must have columns named exactly 'Status' and 'Email' in row 1."
        )

    out: list[dict] = []
    for r, row in enumerate(values[1:], start=2):
        status = cell(row, status_i)
        if status != HIT_STATUS_TARGET:
            continue
        em = normalize_email(cell(row, email_i))
        if not em:
            continue
        out.append(
            {
                "hit_list_row": r,
                "store_key": cell(row, store_i) if store_i is not None else "",
                "shop_name": cell(row, shop_i) if shop_i is not None else "",
                "to_email": em,
            }
        )
    return out


def get_gmail_creds() -> UserCredentials:
    return load_gmail_user_credentials(_GMAIL_TOKEN, GMAIL_SCOPES)


def get_sheets_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing service account {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def ensure_log_worksheet(sh):
    try:
        ws = sh.worksheet(LOG_WS)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=LOG_WS, rows=3000, cols=len(LOG_HEADERS))
        ws.append_row(LOG_HEADERS, value_input_option="USER_ENTERED")
        return ws
    vals = ws.get_all_values()
    if not vals:
        ws.append_row(LOG_HEADERS, value_input_option="USER_ENTERED")
    else:
        migrate_followup_log_add_body_plain(ws, vals[0])
    return ws


def migrate_followup_log_add_body_plain(ws: gspread.Worksheet, header_row: list[str]) -> None:
    """Insert body_plain between snippet and sync_source on legacy 9-column sheets."""
    hdr = [str(h or "").strip() for h in header_row]
    if "body_plain" in hdr:
        return
    if len(hdr) != 9 or hdr[-1] != "sync_source" or hdr[7] != "snippet":
        return
    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": 8,
                            "endIndex": 9,
                        }
                    }
                }
            ]
        }
    )
    ws.update_cell(1, 9, "body_plain")


def fetch_plain_body_for_message(service, message_id: str) -> str:
    full = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    pl = full.get("payload") or {}
    text = extract_plain_body_from_payload(pl).strip()
    if not text:
        text = (full.get("snippet") or "").replace("\n", " ").strip()
    if len(text) > PLAIN_BODY_MAX_CHARS:
        text = text[: PLAIN_BODY_MAX_CHARS - 1] + "…"
    return text


def existing_message_ids(ws) -> set[str]:
    values = ws.get_all_values()
    if len(values) < 2:
        return set()
    hdr = header_map(values[0])
    mid_i = hdr.get("gmail_message_id")
    if mid_i is None:
        return set()
    return {cell(r, mid_i) for r in values[1:] if cell(r, mid_i)}


def gmail_header(payload, name: str) -> str:
    for h in payload.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "") or ""
    return ""


def fetch_sent_for_address(service, to_addr: str, max_results: int = 100) -> list[dict]:
    q = f"in:sent to:{to_addr}"
    out: list[dict] = []
    page_token = None
    while True:
        req = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=min(100, max_results - len(out)), pageToken=page_token)
        )
        resp = req.execute()
        for m in resp.get("messages", []):
            mid = m["id"]
            full = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=mid,
                    format="metadata",
                    metadataHeaders=["Subject", "To", "Date", "From"],
                )
                .execute()
            )
            pl = full.get("payload", {})
            subj = gmail_header(pl, "Subject")
            to_h = gmail_header(pl, "To")
            date_h = gmail_header(pl, "Date")
            snippet = full.get("snippet", "") or ""
            # Confirm target address appears in To (case-insensitive)
            if to_addr.lower() not in to_h.lower():
                continue
            out.append(
                {
                    "gmail_message_id": mid,
                    "subject": subj,
                    "sent_at": date_h,
                    "snippet": snippet.replace("\n", " ")[:500],
                    "to_email": to_addr.lower(),
                }
            )
            if len(out) >= max_results:
                return out
        page_token = resp.get("nextPageToken")
        if not page_token or len(out) >= max_results:
            break
    return out


def pick_store_shop(target_rows: list[dict], to_email: str) -> tuple[str, str]:
    """Use first Hit List row that matches this email for store_key / shop_name."""
    for t in target_rows:
        if t["to_email"] == to_email:
            return t.get("store_key", ""), t.get("shop_name", "")
    return "", ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Gmail sent mail into Email Agent Follow Up.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Sheets.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max distinct recipient emails to scan (0 = no limit).",
    )
    parser.add_argument(
        "--per-address-cap",
        type=int,
        default=200,
        help="Max Gmail messages to pull per recipient address.",
    )
    args = parser.parse_args()

    sa = get_sheets_client()
    sh = sa.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)
    log_ws = ensure_log_worksheet(sh)

    targets = load_hit_list_targets(hit_ws)
    distinct_emails: list[str] = []
    seen: set[str] = set()
    for t in targets:
        e = t["to_email"]
        if e not in seen:
            seen.add(e)
            distinct_emails.append(e)

    if args.limit:
        distinct_emails = distinct_emails[: args.limit]

    print(f"Hit List '{HIT_STATUS_TARGET}' rows with Email: {len(targets)}")
    print(f"Distinct recipient emails to scan: {len(distinct_emails)}")
    if not distinct_emails:
        print("Nothing to scan.")
        return

    known_ids = existing_message_ids(log_ws)
    print(f"Existing log rows (message ids): {len(known_ids)}")

    gcreds = get_gmail_creds()
    service = build("gmail", "v1", credentials=gcreds, cache_discovery=False)

    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_rows: list[list[str]] = []

    for addr in distinct_emails:
        msgs = fetch_sent_for_address(service, addr, max_results=args.per_address_cap)
        sk, sn = pick_store_shop(targets, addr)
        for m in msgs:
            mid = m["gmail_message_id"]
            if mid in known_ids:
                continue
            if args.dry_run:
                body_plain = ""
            else:
                body_plain = fetch_plain_body_for_message(service, mid)
            new_rows.append(
                [
                    mid,
                    synced_at,
                    sk,
                    sn,
                    m["to_email"],
                    m["subject"],
                    m["sent_at"],
                    m["snippet"],
                    body_plain,
                    "gmail_sent_sync",
                ]
            )
            known_ids.add(mid)

    print(f"New messages to append: {len(new_rows)}")
    if args.dry_run:
        for row in new_rows[:20]:
            print("  ", row[0], row[4], row[5][:60] if row[5] else "")
        if len(new_rows) > 20:
            print(f"  ... and {len(new_rows) - 20} more")
        return

    if new_rows:
        log_ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"Appended {len(new_rows)} rows to '{LOG_WS}'.")


if __name__ == "__main__":
    main()
