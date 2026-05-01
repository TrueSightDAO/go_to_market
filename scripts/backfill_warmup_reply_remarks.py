#!/usr/bin/env python3
"""
Backfill DApp Remarks for Hit List rows with Status = AI: Prospect replied.

For each row, finds:
  1. The last sent warm-up email (from Gmail, to the prospect)
  2. The prospect's reply (from Gmail, from the prospect)

Then appends a DApp Remarks row with both for audit + template refinement.

Usage:
  cd market_research
  python3 scripts/backfill_warmup_reply_remarks.py --dry-run --limit 5
  python3 scripts/backfill_warmup_reply_remarks.py
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


def _message_internal_ms(full: dict) -> int:
    try:
        return int(full.get("internalDate", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _header_value(full: dict, name: str) -> str:
    pl = full.get("payload") or {}
    for h in pl.get("headers") or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value") or ""
    return ""


def find_last_sent_warmup(gsvc, partner_email: str, max_scan: int = 30) -> dict | None:
    """Return the most recent sent warm-up email to partner_email."""
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
            body = extract_plain_body_from_payload(pl, max_total=5_000)
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
    # Most recent first
    candidates.sort(key=lambda x: x["ms"], reverse=True)
    return candidates[0]


def find_prospect_reply(gsvc, partner_email: str, after_ms: int, max_scan: int = 30) -> dict | None:
    """Return the first reply from partner_email after after_ms."""
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
            body = extract_plain_body_from_payload(pl, max_total=5_000)
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
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill DApp Remarks for warmup reply rows.")
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not write.")
    parser.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = all).")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    gcreds = smf.get_gmail_creds()
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)

    sa = smf.get_sheets_client()
    sh = sa.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)
    remarks_ws = smf.open_dapp_remarks_worksheet(sh)
    if remarks_ws is None:
        print("ERROR: DApp Remarks worksheet not found.")
        return 1

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

    processed = 0
    for r, row in enumerate(values[1:], start=2):
        if smf.cell(row, status_i) != HIT_STATUS_REPLIED:
            continue

        em = smf.normalize_email(smf.cell(row, email_i))
        if not em:
            continue

        shop_name = smf.cell(row, shop_i) if shop_i is not None else ""

        if args.verbose:
            print(f"\nRow {r} | {shop_name} | {em}")

        # Find the reply first, then the sent email before it
        reply = find_prospect_reply(gsvc, em, after_ms=0, max_scan=50)
        if reply is None:
            if args.verbose:
                print(f"  No reply found for {em}")
            continue

        sent = find_last_sent_warmup(gsvc, em, max_scan=50)
        if sent and reply["ms"] <= sent["ms"]:
            # Reply is older than sent — try to find a later reply
            reply = find_prospect_reply(gsvc, em, after_ms=sent["ms"], max_scan=50)

        remarks_text = build_remarks_text(sent, reply)
        if args.verbose:
            print(f"  Reply subject: {reply['subject'] if reply else 'N/A'}")
            print(f"  Sent subject:  {sent['subject'] if sent else 'N/A'}")

        if not args.dry_run:
            try:
                append_dapp_remark_and_apply(
                    hit_ws=hit_ws,
                    remark_ws=remarks_ws,
                    sheet_row=r,
                    name=shop_name,
                    ai_status=HIT_STATUS_REPLIED,
                    remarks=remarks_text,
                    submitted_by="warmup_reply_backfill",
                    submitted_at=datetime.now(timezone.utc).isoformat(),
                    submission_id=f"warmup-backfill-{r}",
                )
                print(f"  ✓ Backfilled row {r} ({shop_name})")
            except Exception as e:
                print(f"  ✗ Failed row {r}: {e}")
        else:
            print(f"  [DRY-RUN] Would backfill row {r} ({shop_name})")

        processed += 1
        if args.limit and processed >= args.limit:
            break

    print(f"\nProcessed {processed} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
