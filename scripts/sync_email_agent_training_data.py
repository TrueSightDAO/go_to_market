#!/usr/bin/env python3
"""
Build "Email Agent Training Data" from Hit List rows with Status = Partnered and Email set,
plus Gmail threads touching that address (sent and received).

Purpose: chronological message rows per store for human review — extract patterns that led to
"yes" on consignment / partnership so we can define a repeatable human-in-the-loop follow-up protocol.

Sheets: service account (google_credentials.json). Gmail: local token.json or env **GMAIL_TOKEN_JSON**; see `gmail_user_credentials.py`.

Usage:
  cd market_research
  python3 scripts/sync_email_agent_training_data.py
  python3 scripts/sync_email_agent_training_data.py --dry-run
  python3 scripts/sync_email_agent_training_data.py --limit 3
  python3 scripts/sync_email_agent_training_data.py --no-format
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build

from gmail_user_credentials import load_gmail_user_credentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
TRAINING_WS = "Email Agent Training Data"

PARTNERED_STATUS = "Partnered"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TRAINING_HEADERS = [
    "synced_at_utc",
    "store_key",
    "shop_name",
    "partner_email",
    "gmail_message_id",
    "thread_id",
    "direction",
    "message_date",
    "subject",
    "from_header",
    "to_header",
    "snippet",
    "hit_list_row",
    "analysis_notes",
]

_EMAIL_IN_HEADER = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def normalize_email(raw: str) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or "@" not in s:
        return None
    return s.lower()


def emails_in_header(h: str) -> set[str]:
    return {m.group(0).lower() for m in _EMAIL_IN_HEADER.finditer(h or "")}


def header_map(row: list[str]) -> dict[str, int]:
    return {h.strip(): i for i, h in enumerate(row) if h.strip()}


def cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip() if idx < len(row) else ""


def load_partnered_with_email(ws) -> list[dict]:
    values = ws.get_all_values()
    if not values:
        return []
    hdr = header_map(values[0])
    status_i = hdr.get("Status")
    email_i = hdr.get("Email")
    store_i = hdr.get("Store Key")
    shop_i = hdr.get("Shop Name")
    if status_i is None or email_i is None:
        raise SystemExit("Hit List row 1 must include 'Status' and 'Email'.")

    out: list[dict] = []
    for r, row in enumerate(values[1:], start=2):
        if cell(row, status_i) != PARTNERED_STATUS:
            continue
        em = normalize_email(cell(row, email_i))
        if not em:
            continue
        out.append(
            {
                "hit_list_row": r,
                "store_key": cell(row, store_i) if store_i is not None else "",
                "shop_name": cell(row, shop_i) if shop_i is not None else "",
                "partner_email": em,
            }
        )
    return out


def pick_store_meta(rows: list[dict], partner_email: str) -> tuple[str, str, str]:
    """First Hit List row wins for store_key / shop_name; min row for hit_list_row tag."""
    matches = [x for x in rows if x["partner_email"] == partner_email]
    if not matches:
        return "", "", ""
    first = min(matches, key=lambda x: x["hit_list_row"])
    rows_str = ",".join(str(m["hit_list_row"]) for m in sorted(matches, key=lambda x: x["hit_list_row"]))
    return first.get("store_key", ""), first.get("shop_name", ""), rows_str


def get_gmail_creds() -> UserCredentials:
    return load_gmail_user_credentials(_GMAIL_TOKEN, GMAIL_SCOPES)


def get_sheets_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing service account {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def gmail_user_email(service) -> str:
    prof = service.users().getProfile(userId="me").execute()
    return str(prof.get("emailAddress", "")).lower()


def list_message_ids(service, partner_addr: str, max_messages: int) -> list[str]:
    q = f"(from:{partner_addr} OR to:{partner_addr})"
    out: list[str] = []
    page_token = None
    while len(out) < max_messages:
        n = min(100, max_messages - len(out))
        if n <= 0:
            break
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=n, pageToken=page_token)
            .execute()
        )
        for m in resp.get("messages", []):
            mid = m.get("id")
            if mid and mid not in out:
                out.append(mid)
            if len(out) >= max_messages:
                return out
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def gmail_header(payload: dict, name: str) -> str:
    for h in payload.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "") or ""
    return ""


def fetch_message_meta(service, message_id: str) -> dict | None:
    full = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "To", "Date", "Cc"],
        )
        .execute()
    )
    pl = full.get("payload", {})
    internal = full.get("internalDate")
    try:
        ms = int(internal) if internal is not None else 0
    except (TypeError, ValueError):
        ms = 0
    date_hdr = gmail_header(pl, "Date")
    iso = ""
    if ms:
        iso = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message_date = date_hdr or iso
    snippet = (full.get("snippet") or "").replace("\n", " ")
    return {
        "gmail_message_id": message_id,
        "thread_id": full.get("threadId", "") or "",
        "internal_ms": ms,
        "subject": gmail_header(pl, "Subject"),
        "from_header": gmail_header(pl, "From"),
        "to_header": gmail_header(pl, "To"),
        "cc_header": gmail_header(pl, "Cc"),
        "message_date": message_date,
        "snippet": snippet[:2000],
    }


def direction_for(my_email: str, from_header: str) -> str:
    frm = emails_in_header(from_header)
    if my_email in frm:
        return "outbound"
    return "inbound"


def ensure_training_worksheet(sh: gspread.Spreadsheet):
    try:
        return sh.worksheet(TRAINING_WS)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=TRAINING_WS, rows=4000, cols=len(TRAINING_HEADERS))


def run_formatter() -> None:
    fmt = _REPO / "scripts" / "format_email_agent_training_data_sheet.py"
    r = subprocess.run([sys.executable, str(fmt)], cwd=str(_REPO), check=False)
    if r.returncode != 0:
        sys.stderr.write(
            f"Formatting script exited {r.returncode}; run manually: python3 scripts/format_email_agent_training_data_sheet.py\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate Email Agent Training Data from Partnered + Gmail.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max distinct partner emails to fetch (0=all).")
    parser.add_argument(
        "--max-messages-per-address",
        type=int,
        default=200,
        help="Cap Gmail messages pulled per partner email (default 200).",
    )
    parser.add_argument("--no-format", action="store_true", help="Skip running the layout formatter after write.")
    args = parser.parse_args()

    sa = get_sheets_client()
    sh = sa.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)
    partnered = load_partnered_with_email(hit_ws)

    distinct: list[str] = []
    seen: set[str] = set()
    for p in partnered:
        e = p["partner_email"]
        if e not in seen:
            seen.add(e)
            distinct.append(e)

    if args.limit:
        distinct = distinct[: args.limit]

    print(f"Hit List '{PARTNERED_STATUS}' rows with Email: {len(partnered)}", flush=True)
    print(f"Distinct partner emails: {len(distinct)}", flush=True)

    if not distinct:
        print("No partnered rows with email — wrote header row only.")
        training_ws = ensure_training_worksheet(sh)
        table = [TRAINING_HEADERS]
        if not args.dry_run:
            training_ws.clear()
            training_ws.resize(rows=500, cols=len(TRAINING_HEADERS))
            training_ws.update(values=table, range_name="A1", value_input_option="USER_ENTERED")
            if not args.no_format:
                run_formatter()
        return

    gcreds = get_gmail_creds()
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
    my_email = gmail_user_email(gsvc)
    if not my_email:
        sys.stderr.write("Could not read Gmail profile emailAddress.\n")
        sys.exit(1)

    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows_by_id: dict[str, dict] = {}

    for addr in distinct:
        ids = list_message_ids(gsvc, addr, max_messages=args.max_messages_per_address)
        sk, sn, rows_str = pick_store_meta(partnered, addr)
        for mid in ids:
            if mid in rows_by_id:
                continue
            meta = fetch_message_meta(gsvc, mid)
            if not meta:
                continue
            to_h = meta["to_header"]
            if meta.get("cc_header"):
                to_h = f"{to_h}; Cc: {meta['cc_header']}" if to_h else f"Cc: {meta['cc_header']}"
            rows_by_id[mid] = {
                "partner_email": addr,
                "store_key": sk,
                "shop_name": sn,
                "hit_rows": rows_str,
                "meta": meta,
                "to_header": to_h[:2000],
            }

    bundles = list(rows_by_id.values())
    bundles.sort(key=lambda b: (b["partner_email"], b["meta"].get("internal_ms") or 0))

    out_rows: list[list[str]] = []
    for bundle in bundles:
        m = bundle["meta"]
        dirn = direction_for(my_email, m["from_header"])
        out_rows.append(
            [
                synced_at,
                bundle["store_key"],
                bundle["shop_name"],
                bundle["partner_email"],
                m["gmail_message_id"],
                m["thread_id"],
                dirn,
                m["message_date"],
                m["subject"],
                (m["from_header"] or "")[:1500],
                (bundle["to_header"] or "")[:1500],
                m["snippet"],
                bundle["hit_rows"],
                "",
            ]
        )

    table = [TRAINING_HEADERS] + out_rows
    print(f"Unique Gmail messages in export: {len(out_rows)}")
    if args.dry_run:
        for row in out_rows[:20]:
            subj = (row[8] or "")[:55]
            print(f"  {row[3]} | {row[6]} | {row[7]} | {subj}")
        if len(out_rows) > 20:
            print(f"  ... {len(out_rows) - 20} more")
        return

    training_ws = ensure_training_worksheet(sh)
    training_ws.clear()
    training_ws.resize(rows=max(600, len(table) + 50), cols=len(TRAINING_HEADERS))
    training_ws.update(values=table, range_name="A1", value_input_option="USER_ENTERED")
    print(f"Wrote {len(out_rows)} data rows + header to {TRAINING_WS!r}.")

    if not args.no_format:
        run_formatter()


if __name__ == "__main__":
    main()