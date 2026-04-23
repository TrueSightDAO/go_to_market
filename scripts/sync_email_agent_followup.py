#!/usr/bin/env python3
"""
Sync sent-mail history from Gmail into the "Email Agent Follow Up" tab on the Hit List spreadsheet.

Flow
----
1. Open "Hit List" → rows where Status is one of the outreach sync statuses (Manager Follow-up,
   Bulk Info Requested, AI: Warm up prospect, AI: Prospect replied) and Email (column K) non-empty.
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
  python3 scripts/sync_email_agent_followup.py              # migrate tab if needed, append new log rows
  python3 scripts/sync_email_agent_followup.py --migrate-only  # insert body_plain header only (no Gmail)
  python3 scripts/sync_email_agent_followup.py --backfill-body-plain  # fill empty body_plain for existing rows
  python3 scripts/sync_email_agent_followup.py --backfill-status       # fill status (warmup|bulk|follow_up|unknown)
  python3 scripts/sync_email_agent_followup.py --backfill-status --force-backfill-status  # overwrite existing status
  python3 scripts/sync_email_agent_followup.py --dry-run
  python3 scripts/sync_email_agent_followup.py --limit 5
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
SUGGESTIONS_WS = "Email Agent Drafts"

HIT_STATUSES_FOR_SYNC = (
    "Manager Follow-up",
    "Bulk Info Requested",
    "AI: Warm up prospect",
    "AI: Prospect replied",
)
# Must match (or be a subset of) scopes in credentials/gmail/token.json from gmail_oauth_authorize.py
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

REVIEW_LABEL_FOLLOWUP = "AI/Follow-up"
REVIEW_LABEL_WARMUP = "AI/Warm-up"
SENT_LABEL_FOLLOWUP = "AI/Sent Follow-up"
SENT_LABEL_WARMUP = "AI/Sent Warm-up"

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
    # Pipeline kind for this outbound (Gmail Sent row). Not the same as Email Agent Drafts status.
    "status",
    "sync_source",
    # Engagement (defaults 0 on append). Intended to be updated by Edgar (or similar) when a
    # tracking pixel / redirect fires — see scripts/email_agent_tracking.py and HIT_LIST_CREDENTIALS.md.
    "Open",
    "Click through",
]


def touch_kind_from_protocol(proto: str) -> str:
    """Map Email Agent Drafts protocol_version to a coarse outbound kind."""
    p = (proto or "").lower()
    if "warmup" in p:
        return "warmup"
    if "bulk" in p:
        return "bulk"
    return "follow_up"


def parse_sent_at_header(raw: str) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def load_suggestions_touch_kinds(sa) -> dict[str, list[dict]]:
    """{to_email: [{created, subject, kind}]} where kind is warmup|bulk|follow_up."""
    sh = sa.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SUGGESTIONS_WS)
    except gspread.WorksheetNotFound:
        return {}
    values = ws.get_all_values()
    if len(values) < 2:
        return {}
    hdr = header_map(values[0])
    em_i = hdr.get("to_email")
    subj_i = hdr.get("subject")
    proto_i = hdr.get("protocol_version")
    created_i = hdr.get("created_at_utc")
    if em_i is None:
        return {}
    out: dict[str, list[dict]] = {}
    for row in values[1:]:
        em = normalize_email(cell(row, em_i))
        if not em:
            continue
        proto = cell(row, proto_i) if proto_i is not None else ""
        subject = cell(row, subj_i) if subj_i is not None else ""
        created = parse_sent_at_header(cell(row, created_i)) if created_i is not None else None
        out.setdefault(em, []).append(
            {
                "created": created,
                "subject": subject,
                "kind": touch_kind_from_protocol(proto),
            }
        )
    for em in out:
        out[em].sort(key=lambda x: x["created"] or datetime.min.replace(tzinfo=timezone.utc))
    return out


def pick_touch_kind_from_suggestions(
    suggestions: list[dict], sent_at: datetime | None, subject: str
) -> str | None:
    if not suggestions:
        return None
    kinds = {s["kind"] for s in suggestions}
    if len(kinds) == 1:
        return kinds.pop()
    if sent_at is not None:
        prior = [s for s in suggestions if s["created"] and s["created"] <= sent_at]
        if prior:
            return prior[-1]["kind"]
    subj = (subject or "").strip()
    for s in suggestions:
        if s["subject"].strip() == subj:
            return s["kind"]
    return suggestions[-1]["kind"]


def label_names_for_ids(label_ids: list[str], id_to_name: dict[str, str]) -> set[str]:
    return {id_to_name.get(i, "") for i in (label_ids or []) if i}


def infer_followup_log_status(
    *,
    label_ids: list[str],
    id_to_name: dict[str, str],
    to_email: str,
    sent_at_raw: str,
    subject: str,
    sug_by_email: dict[str, list[dict]],
) -> str:
    """Return warmup | bulk | follow_up | unknown for one Gmail Sent log row."""
    names = label_names_for_ids(label_ids, id_to_name)
    if SENT_LABEL_WARMUP in names or REVIEW_LABEL_WARMUP in names:
        return "warmup"
    sug_kind = pick_touch_kind_from_suggestions(
        sug_by_email.get(to_email, []),
        parse_sent_at_header(sent_at_raw),
        subject,
    )
    if SENT_LABEL_FOLLOWUP in names or REVIEW_LABEL_FOLLOWUP in names:
        return sug_kind if sug_kind else "follow_up"
    if sug_kind:
        return sug_kind
    return "unknown"


def _get_or_create_label_id(service, name: str, label_map: dict[str, str]) -> str:
    """Return Gmail label id for name, creating it if absent. Updates label_map in place."""
    if name in label_map:
        return label_map[name]
    body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    created = service.users().labels().create(userId="me", body=body).execute()
    lid = str(created["id"])
    label_map[name] = lid
    print(f"  Created Gmail label: {name!r}")
    return lid


def build_label_id_map(service) -> dict[str, str]:
    resp = service.users().labels().list(userId="me").execute()
    return {l["name"]: l["id"] for l in resp.get("labels", [])}


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
    """Hit List rows in configured outreach statuses with Email set."""
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
        if status not in HIT_STATUSES_FOR_SYNC:
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
        hdr = vals[0]
        if migrate_followup_log_add_body_plain(ws, hdr):
            vals = ws.get_all_values()
            hdr = vals[0] if vals else []
        migrate_followup_log_add_status(ws, hdr)
        vals = ws.get_all_values()
        hdr = vals[0] if vals else []
        migrate_followup_log_add_open_click(ws, hdr)
    return ws


def migrate_followup_log_add_open_click(ws: gspread.Worksheet, header_row: list[str]) -> bool:
    """Append **Open** and **Click through** at the end of row 1 if missing (columns L–M after K)."""
    hm = header_map(header_row)
    if hm.get("Open") is not None and hm.get("Click through") is not None:
        return False

    last_used = 0
    for i, cell in enumerate(header_row):
        if str(cell or "").strip():
            last_used = i + 1
    insert_at = last_used  # 0-based column index to insert before (append at end)

    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": insert_at,
                            "endIndex": insert_at + 2,
                        }
                    }
                }
            ]
        }
    )
    ws.update_cell(1, insert_at + 1, "Open")
    ws.update_cell(1, insert_at + 2, "Click through")
    print(
        "Migrated sheet: appended columns 'Open' and 'Click through' "
        f"(inserted at 1-based columns {insert_at + 1}–{insert_at + 2})."
    )
    return True


def migrate_followup_log_add_body_plain(ws: gspread.Worksheet, header_row: list[str]) -> bool:
    """Insert **body_plain** immediately before **sync_source** if missing. Returns True if modified."""
    hm = header_map(header_row)
    if "body_plain" in hm:
        return False
    sync_i = hm.get("sync_source")
    if sync_i is None:
        print(
            "migrate: no 'sync_source' column on Email Agent Follow Up — "
            "set row 1 to match scripts/sync_email_agent_followup.py LOG_HEADERS or add columns manually.",
            file=sys.stderr,
        )
        return False

    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": sync_i,
                            "endIndex": sync_i + 1,
                        }
                    }
                }
            ]
        }
    )
    # 1-based column index: inserted column is at sync_i + 1
    ws.update_cell(1, sync_i + 1, "body_plain")
    print(f"Migrated sheet: inserted column 'body_plain' before former column {sync_i + 1} (sync_source).")
    return True


def migrate_followup_log_add_status(ws: gspread.Worksheet, header_row: list[str]) -> bool:
    """Insert **status** immediately before **sync_source** if missing. Returns True if modified."""
    hm = header_map(header_row)
    if "status" in hm:
        return False
    sync_i = hm.get("sync_source")
    if sync_i is None:
        print(
            "migrate: no 'sync_source' column on Email Agent Follow Up — "
            "cannot insert status; fix headers manually.",
            file=sys.stderr,
        )
        return False

    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": sync_i,
                            "endIndex": sync_i + 1,
                        }
                    }
                }
            ]
        }
    )
    ws.update_cell(1, sync_i + 1, "status")
    print(f"Migrated sheet: inserted column 'status' before former column {sync_i + 1} (sync_source).")
    return True


def backfill_empty_body_plain(
    service: object | None,
    log_ws: gspread.Worksheet,
    *,
    dry_run: bool,
    limit: int,
) -> int:
    """Fill **body_plain** for rows that have **gmail_message_id** but empty body. Returns rows updated."""
    if not dry_run and service is None:
        raise SystemExit("backfill: internal error (Gmail service missing).")
    values = log_ws.get_all_values()
    if len(values) < 2:
        return 0
    hdr = header_map(values[0])
    mid_i = hdr.get("gmail_message_id")
    body_i = hdr.get("body_plain")
    if mid_i is None or body_i is None:
        print(
            "backfill: sheet needs columns gmail_message_id and body_plain "
            "(run once with current script to migrate, or add header body_plain before sync_source).",
            file=sys.stderr,
        )
        return 0

    todo: list[tuple[int, str]] = []
    for r, row in enumerate(values[1:], start=2):
        mid = cell(row, mid_i)
        if not mid:
            continue
        existing = cell(row, body_i) if body_i < len(row) else ""
        if existing.strip():
            continue
        todo.append((r, mid))
        if limit > 0 and len(todo) >= limit:
            break

    print(f"backfill: {len(todo)} row(s) with empty body_plain and a message id.")
    if not todo:
        return 0
    if dry_run:
        for r, mid in todo[:20]:
            print(f"  dry-run row {r} gmail_message_id={mid[:16]}...")
        if len(todo) > 20:
            print(f"  ... and {len(todo) - 20} more")
        return 0

    col = body_i + 1
    updated = 0
    chunk: list[gspread.Cell] = []

    def flush_chunk() -> None:
        nonlocal chunk, updated
        if not chunk:
            return
        log_ws.update_cells(chunk, value_input_option="USER_ENTERED")
        updated += len(chunk)
        chunk = []

    for r, mid in todo:
        try:
            body_plain = fetch_plain_body_for_message(service, mid)  # type: ignore[arg-type]
        except Exception as e:
            print(f"  row {r} id={mid[:20]}... skip: {e}", file=sys.stderr)
            continue
        chunk.append(gspread.Cell(row=r, col=col, value=body_plain))
        if len(chunk) >= 25:
            flush_chunk()
            print(f"  backfilled {updated}/{len(todo)}...")
    flush_chunk()
    print(f"backfill: wrote body_plain for {updated} row(s).")
    return updated


def backfill_followup_status(
    service: object,
    log_ws: gspread.Worksheet,
    sa,
    *,
    dry_run: bool,
    limit: int,
    force: bool,
) -> int:
    """Fill **status** on Email Agent Follow Up using Gmail labels + Email Agent Drafts protocols."""
    values = log_ws.get_all_values()
    if len(values) < 2:
        return 0
    hdr = header_map(values[0])
    mid_i = hdr.get("gmail_message_id")
    st_i = hdr.get("status")
    em_i = hdr.get("to_email")
    subj_i = hdr.get("subject")
    sent_i = hdr.get("sent_at")
    if mid_i is None or st_i is None or em_i is None:
        print(
            "backfill-status: sheet needs gmail_message_id, status, to_email columns.",
            file=sys.stderr,
        )
        return 0

    label_map = build_label_id_map(service)
    id_to_name = {str(v): str(k) for k, v in label_map.items()}
    sug_by_email = load_suggestions_touch_kinds(sa)

    todo: list[tuple[int, str, str, str, str]] = []
    for r, row in enumerate(values[1:], start=2):
        mid = cell(row, mid_i)
        if not mid:
            continue
        existing = cell(row, st_i) if st_i < len(row) else ""
        if existing.strip() and not force:
            continue
        em = normalize_email(cell(row, em_i)) or ""
        subj = cell(row, subj_i) if subj_i is not None else ""
        sent_raw = cell(row, sent_i) if sent_i is not None else ""
        todo.append((r, mid, em, subj, sent_raw))
        if limit > 0 and len(todo) >= limit:
            break

    print(f"backfill-status: {len(todo)} row(s) to classify.")
    if not todo:
        return 0
    if dry_run:
        for item in todo[:15]:
            print(f"  dry-run row {item[0]} id={item[1][:16]}… to={item[2]}")
        if len(todo) > 15:
            print(f"  ... and {len(todo) - 15} more")
        return 0

    updated = 0
    col = st_i + 1
    chunk: list[gspread.Cell] = []

    def flush_chunk() -> None:
        nonlocal chunk, updated
        if not chunk:
            return
        log_ws.update_cells(chunk, value_input_option="USER_ENTERED")
        updated += len(chunk)
        chunk = []

    for r, mid, em, subj, sent_raw in todo:
        try:
            meta = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="metadata", metadataHeaders=["Subject"])
                .execute()
            )
            lids = meta.get("labelIds") or []
            status_val = infer_followup_log_status(
                label_ids=[str(x) for x in lids],
                id_to_name=id_to_name,
                to_email=em,
                sent_at_raw=sent_raw,
                subject=subj,
                sug_by_email=sug_by_email,
            )
        except Exception as e:
            print(f"  row {r} id={mid[:16]}… skip: {e}", file=sys.stderr)
            continue
        chunk.append(gspread.Cell(row=r, col=col, value=status_val))
        if len(chunk) >= 30:
            flush_chunk()
            print(f"  backfilled status {updated}/{len(todo)}...")
    flush_chunk()
    print(f"backfill-status: wrote status for {updated} row(s).")
    return updated


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
                    "label_ids": full.get("labelIds") or [],
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
        "--migrate-only",
        action="store_true",
        help="Only ensure worksheet + run column migrations (body_plain, status) if missing (no Gmail).",
    )
    parser.add_argument(
        "--backfill-body-plain",
        action="store_true",
        help="Fetch full message bodies from Gmail for rows with empty body_plain.",
    )
    parser.add_argument(
        "--backfill-only",
        action="store_true",
        help="With --backfill-body-plain: do not scan Hit List / append new rows after backfill.",
    )
    parser.add_argument(
        "--backfill-limit",
        type=int,
        default=0,
        help="Max rows to backfill (0 = all rows that qualify).",
    )
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
    parser.add_argument(
        "--backfill-status",
        action="store_true",
        help="Classify and fill Email Agent Follow Up **status** (warmup|bulk|follow_up|unknown) using Gmail labels + Email Agent Drafts.",
    )
    parser.add_argument(
        "--force-backfill-status",
        action="store_true",
        help="With --backfill-status: overwrite non-empty status cells too.",
    )
    args = parser.parse_args()

    sa = get_sheets_client()
    sh = sa.open_by_key(SPREADSHEET_ID)
    log_ws = ensure_log_worksheet(sh)

    if args.migrate_only:
        print(f"'{LOG_WS}' worksheet ensured (body_plain + status migrations applied if needed). Done.")
        return

    service = None
    if args.backfill_body_plain:
        if not args.dry_run:
            gcreds = get_gmail_creds()
            service = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
        backfill_empty_body_plain(
            service, log_ws, dry_run=args.dry_run, limit=args.backfill_limit
        )
        if args.backfill_only:
            return

    if args.backfill_status:
        if service is None:
            gcreds = get_gmail_creds()
            service = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
        backfill_followup_status(
            service,
            log_ws,
            sa,
            dry_run=args.dry_run,
            limit=args.backfill_limit,
            force=args.force_backfill_status,
        )
        if args.backfill_only:
            return

    hit_ws = sh.worksheet(HIT_LIST_WS)
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

    print(f"Hit List rows (status in {HIT_STATUSES_FOR_SYNC!r}) with Email: {len(targets)}")
    print(f"Distinct recipient emails to scan: {len(distinct_emails)}")
    if not distinct_emails:
        print("Nothing to scan.")
        return

    known_ids = existing_message_ids(log_ws)
    print(f"Existing log rows (message ids): {len(known_ids)}")

    if service is None:
        gcreds = get_gmail_creds()
        service = build("gmail", "v1", credentials=gcreds, cache_discovery=False)

    label_map = build_label_id_map(service)
    id_to_name = {str(v): str(k) for k, v in label_map.items()}
    sug_by_email = load_suggestions_touch_kinds(sa)

    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_rows: list[list[str]] = []
    # Track label_ids per new message for the review→sent label swap below.
    new_msg_label_ids: dict[str, list[str]] = {}

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
            status_val = infer_followup_log_status(
                label_ids=[str(x) for x in (m.get("label_ids") or [])],
                id_to_name=id_to_name,
                to_email=m["to_email"],
                sent_at_raw=m.get("sent_at") or "",
                subject=m.get("subject") or "",
                sug_by_email=sug_by_email,
            )
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
                    status_val,
                    "gmail_sent_sync",
                    "0",
                    "0",
                ]
            )
            new_msg_label_ids[mid] = m.get("label_ids") or []
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

    # Ensure all 4 AI labels exist in Gmail, then swap review → sent labels.
    # Gmail carries draft labels onto the sent message automatically, so once
    # we detect a sent message still wearing a review label we swap it out so
    # the review queue (AI/Follow-up, AI/Warm-up) only shows unsent drafts.
    for name in [REVIEW_LABEL_FOLLOWUP, REVIEW_LABEL_WARMUP,
                 SENT_LABEL_FOLLOWUP, SENT_LABEL_WARMUP]:
        _get_or_create_label_id(service, name, label_map)

    review_to_sent = {
        REVIEW_LABEL_FOLLOWUP: SENT_LABEL_FOLLOWUP,
        REVIEW_LABEL_WARMUP: SENT_LABEL_WARMUP,
    }
    swapped = 0
    for mid, label_ids in new_msg_label_ids.items():
        for review_label, sent_label in review_to_sent.items():
            review_id = label_map.get(review_label)
            if not review_id or review_id not in label_ids:
                continue
            sent_id = label_map[sent_label]
            service.users().messages().modify(
                userId="me",
                id=mid,
                body={"addLabelIds": [sent_id], "removeLabelIds": [review_id]},
            ).execute()
            print(f"  Label swap: {mid[:16]}… {review_label!r} → {sent_label!r}")
            swapped += 1
    if swapped:
        print(f"Label swaps completed: {swapped}")


if __name__ == "__main__":
    main()
