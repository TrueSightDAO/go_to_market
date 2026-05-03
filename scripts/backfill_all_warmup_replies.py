#!/usr/bin/env python3
"""
Expanded backfill: find ALL shops that ever replied to a warm-up email
and ensure they have DApp Remarks entries.

Checks every Hit List shop with an email + a logged sent warm-up,
searches Gmail for replies, backfills DApp Remarks if reply exists
but no "AI: Prospect replied" remark is present.

Usage:
  cd market_research
  python3 scripts/backfill_all_warmup_replies.py --dry-run --limit 10
  python3 scripts/backfill_all_warmup_replies.py
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf
from gmail_plain_body import extract_plain_body_from_payload
from hit_list_dapp_remarks_sheet import append_dapp_remark_and_apply, gspread_retry

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
DAPP_REMARKS_WS = "DApp Remarks"
EMAIL_AGENT_FOLLOW_UP_WS = "Email Agent Follow Up"

HIT_STATUS_REPLIED = "AI: Prospect replied"
HIT_STATUS_WARMUP = "AI: Warm up prospect"
BODY_PREVIEW = 2000
MAX_CHARS = 45000


def _message_internal_ms(full: dict) -> int:
    try:
        return int(full.get("internalDate", 0) or 0)
    except (TypeError, ValueError):
        return 0


def find_last_sent_warmup(gsvc, partner_email: str, max_scan: int = 30) -> dict | None:
    q = f"to:{partner_email}"
    page_token = None
    scanned = 0
    candidates = []
    while scanned < max_scan:
        req = (
            gsvc.users()
            .messages()
            .list(userId="me", q=q, maxResults=min(15, max_scan - scanned), pageToken=page_token)
        )
        resp = req.execute()
        for m in resp.get("messages") or []:
            mid = m.get("id")
            if not mid:
                continue
            try:
                full = gsvc.users().messages().get(userId="me", id=mid, format="full").execute()
            except HttpError:
                continue
            ms = _message_internal_ms(full)
            pl = full.get("payload") or {}
            body = extract_plain_body_from_payload(pl, max_total=BODY_PREVIEW)
            if not body:
                body = (full.get("snippet") or "").replace("\n", " ").strip()
            date_iso = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
            candidates.append({
                "message_id": mid,
                "subject": _header_value(full, "subject"),
                "date": date_iso,
                "body": body,
                "ms": ms,
            })
        scanned += len(resp.get("messages") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["ms"], reverse=True)
    return candidates[0]


def find_prospect_reply(gsvc, partner_email: str, after_ms: int, max_scan: int = 30) -> dict | None:
    q = f"from:{partner_email}"
    page_token = None
    scanned = 0
    while scanned < max_scan:
        req = (
            gsvc.users()
            .messages()
            .list(userId="me", q=q, maxResults=min(15, max_scan - scanned), pageToken=page_token)
        )
        resp = req.execute()
        for m in resp.get("messages") or []:
            mid = m.get("id")
            if not mid:
                continue
            try:
                full = gsvc.users().messages().get(userId="me", id=mid, format="full").execute()
            except HttpError:
                continue
            ms = _message_internal_ms(full)
            if ms <= after_ms:
                continue
            pl = full.get("payload") or {}
            body = extract_plain_body_from_payload(pl, max_total=BODY_PREVIEW)
            if not body:
                body = (full.get("snippet") or "").replace("\n", " ").strip()
            date_iso = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
            return {
                "message_id": mid,
                "subject": _header_value(full, "subject"),
                "date": date_iso,
                "body": body,
                "ms": ms,
            }
        scanned += len(resp.get("messages") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return None


def _header_value(full: dict, name: str) -> str:
    pl = full.get("payload") or {}
    for h in pl.get("headers") or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value") or ""
    return ""


def has_prospect_replied_remark(remarks_ws, shop_name: str) -> bool:
    """Check if DApp Remarks already has an 'AI: Prospect replied' row for this shop."""
    try:
        vals = gspread_retry(lambda: remarks_ws.get_all_values())
        if len(vals) < 2:
            return False
        hdr = {h: i for i, h in enumerate(vals[0])}
        shop_i = hdr.get("Shop Name")
        status_i = hdr.get("Status")
        if shop_i is None or status_i is None:
            return False
        for row in vals[1:]:
            if (row[shop_i] or "").strip() == shop_name and (row[status_i] or "").strip() == HIT_STATUS_REPLIED:
                return True
    except Exception:
        pass
    return False


def build_remarks_text(sent: dict | None, reply: dict | None) -> str:
    parts = ["Prospect replied to warm-up email.\n"]
    if reply:
        parts.append(f"Reply subject: {reply['subject']}")
        parts.append(f"Reply date: {reply['date']}")
        parts.append(f"Reply body:\n{reply['body']}")
    else:
        parts.append("Reply: (could not fetch from Gmail)")
    parts.append("")
    if sent:
        parts.append(f"Original warm-up sent: {sent['date']}")
        parts.append(f"Original warm-up subject: {sent['subject']}")
        parts.append(f"Original warm-up body:\n{sent['body']}")
    else:
        parts.append("Original warm-up: (could not fetch from Gmail)")
    text = "\n".join(parts)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS - 100] + "\n\n[truncated for Sheets cell limit]"
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill DApp Remarks for all warmup reply shops.")
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not write.")
    parser.add_argument("--limit", type=int, default=0, help="Max shops to process (0 = all).")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    gcreds = smf.get_gmail_creds()
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)

    sa = smf.get_sheets_client()
    sh = sa.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)
    remarks_ws = smf.open_dapp_remarks_worksheet(sh)
    log_ws = smf.open_follow_up_worksheet(sh)

    if remarks_ws is None:
        print("ERROR: DApp Remarks worksheet not found.")
        return 1

    # Get last sent times from Email Agent Follow Up
    last_sent = smf.last_sent_utctime_per_to_email(log_ws)

    values = gspread_retry(lambda: hit_ws.get_all_values())
    if len(values) < 2:
        print("Hit List is empty.")
        return 0

    hdr = smf.header_map(values[0])
    status_i = hdr.get("Status")
    email_i = hdr.get("Email")
    shop_i = hdr.get("Shop Name")
    if status_i is None or email_i is None:
        print("ERROR: Hit List missing Status or Email column.")
        return 1

    # Build list of shops to check: any with email + a logged sent warm-up
    shops_to_check = []
    for r, row in enumerate(values[1:], start=2):
        em = smf.normalize_email(smf.cell(row, email_i))
        if not em:
            continue
        if em not in last_sent:
            continue  # No warm-up email ever sent
        shop_name = smf.cell(row, shop_i) if shop_i is not None else ""
        shops_to_check.append((r, shop_name, em))

    print(f"Shops with warm-up emails sent: {len(shops_to_check)}")

    processed = 0
    backfilled = 0
    skipped = 0

    for r, shop_name, em in shops_to_check:
        if args.limit and processed >= args.limit:
            break

        # Check if already has a DApp Remarks entry
        if not args.dry_run and has_prospect_replied_remark(remarks_ws, shop_name):
            skipped += 1
            if args.verbose:
                print(f"  SKIP row {r} ({shop_name}): already has DApp Remarks")
            continue

        prev = last_sent.get(em)
        if prev is None:
            continue
        after_ms = int(prev.timestamp() * 1000)

        reply = find_prospect_reply(gsvc, em, after_ms=after_ms, max_scan=30)
        if reply is None:
            if args.verbose:
                print(f"  No reply for row {r} ({shop_name})")
            continue

        sent = find_last_sent_warmup(gsvc, em, max_scan=30)
        if sent and reply["ms"] <= sent["ms"]:
            reply = find_prospect_reply(gsvc, em, after_ms=sent["ms"], max_scan=30)

        if reply is None:
            if args.verbose:
                print(f"  No reply after sent for row {r} ({shop_name})")
            continue

        print(f"\nRow {r}: {shop_name} | {em}")
        print(f"  Reply: {reply['subject'][:60]}... ({reply['date'][:10]})")

        if not args.dry_run:
            remarks_text = build_remarks_text(sent, reply)
            try:
                append_dapp_remark_and_apply(
                    hit_ws=hit_ws,
                    remark_ws=remarks_ws,
                    sheet_row=r,
                    name=shop_name,
                    ai_status=HIT_STATUS_REPLIED,
                    remarks=remarks_text,
                    submitted_by="warmup_reply_backfill_all",
                    submitted_at=datetime.now(timezone.utc).isoformat(),
                    submission_id=f"warmup-backfill-all-{r}",
                )
                print(f"  ✓ Backfilled")
                backfilled += 1
            except Exception as e:
                print(f"  ✗ Failed: {e}")
        else:
            print(f"  [DRY-RUN] Would backfill")

        processed += 1

    print(f"\n=== Summary ===")
    print(f"Shops checked: {len(shops_to_check)}")
    print(f"Already had DApp Remarks: {skipped}")
    print(f"Replies found + backfilled: {backfilled}")
    print(f"Dry run: {args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
