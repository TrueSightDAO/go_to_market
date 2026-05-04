#!/usr/bin/env python3
"""
Detect Gmail reply drafts that bypass ``suggest_warmup_prospect_drafts.py
--create-reply-drafts`` (i.e., the operator started the reply manually
in Gmail by hitting **Reply** on a prospect's inbound message), and
reconcile them so the DApp Outbound Review **Prospects** tab surfaces
them like any other staged reply:

  1. Apply the **AI/Prospect Replied** label to the draft message — it
     usually starts as ``[DRAFT]`` only because Gmail's reply UI doesn't
     carry the parent thread's labels onto the new outbound draft.
  2. Append a row to **Email Agent Drafts** (status=``pending_review``,
     label=``AI/Prospect Replied``, kind=``warmup_reply``,
     source=``manual_orphan``) so the GAS read endpoint can surface it.

Detection rule: any Gmail draft whose thread contains an inbound message
already wearing **AI/Prospect Replied**, AND whose own message id has no
matching row in Email Agent Drafts (or has a row whose label is empty
/ not yet AI/Prospect Replied) — that's an orphan reply draft.

Idempotent — re-runs are no-ops on drafts that have already been
reconciled (label present + sheet row exists).

Usage::

    cd market_research
    python3 scripts/reconcile_orphan_reply_drafts.py --dry-run
    python3 scripts/reconcile_orphan_reply_drafts.py
    python3 scripts/reconcile_orphan_reply_drafts.py --limit 5
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import gspread
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf  # noqa: E402
from gmail_plain_body import extract_plain_body_from_payload  # noqa: E402

PROSPECT_REPLIED_LABEL = "AI/Prospect Replied"
PENDING_STATUS = "pending_review"
WARMUP_REPLY_PROTOCOL = "PARTNER_OUTREACH_PROTOCOL v0.1 warmup_reply"
BODY_PREVIEW_MAX = 500


def _email_from_to_header(to_hdr: str) -> str:
    if not to_hdr:
        return ""
    s = to_hdr.strip()
    if "<" in s and ">" in s:
        s = s.split("<", 1)[1].split(">", 1)[0]
    return s.strip().lower()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would change without touching Gmail or the sheet.")
    p.add_argument("--limit", type=int, default=None,
                   help="Cap drafts processed this run (default: all orphans).")
    p.add_argument("--sleep", type=float, default=0.15,
                   help="Sleep between writes in seconds (default 0.15).")
    args = p.parse_args(argv)

    creds = smf.get_gmail_creds()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    sa = smf.get_sheets_client()
    sh = sa.open_by_key(smf.SPREADSHEET_ID)
    drafts_ws = sh.worksheet(smf.SUGGESTIONS_WS)
    hit_ws = sh.worksheet(smf.HIT_LIST_WS)

    label_id = smf.ensure_user_label_id(service, PROSPECT_REPLIED_LABEL)

    # Build sheet-side index of Email Agent Drafts by gmail_message_id so we
    # can detect orphan drafts (no row) + drafts whose row has no label set.
    drafts_values = drafts_ws.get_all_values()
    if len(drafts_values) < 2:
        sheet_by_msgid: dict[str, tuple[int, dict]] = {}
        drafts_hdr: dict[str, int] = {}
    else:
        drafts_hdr = smf.header_map(drafts_values[0])
        i_msg = drafts_hdr.get("gmail_message_id")
        if i_msg is None:
            sys.stderr.write("Email Agent Drafts missing gmail_message_id column.\n")
            return 1
        sheet_by_msgid = {}
        for r_idx, row in enumerate(drafts_values[1:], start=2):
            mid = smf.cell(row, i_msg)
            if mid:
                sheet_by_msgid[mid] = (r_idx, row)

    # Build Hit List index by email so we can populate store_key / shop_name
    # / hit_list_row when creating a fresh row.
    hit_values = hit_ws.get_all_values()
    hit_hdr = smf.header_map(hit_values[0])
    hi_email = hit_hdr["Email"]
    hi_shop = hit_hdr["Shop Name"]
    hi_storekey = hit_hdr["Store Key"]
    hit_by_email: dict[str, tuple[int, str, str]] = {}
    for hr_idx, hrow in enumerate(hit_values[1:], start=2):
        em = smf.normalize_email(smf.cell(hrow, hi_email))
        if em and em not in hit_by_email:
            hit_by_email[em] = (
                hr_idx,
                smf.cell(hrow, hi_shop),
                smf.cell(hrow, hi_storekey),
            )

    # Walk every Gmail draft. For each, fetch full content + thread metadata
    # to decide if this is a reply-to-prospect-replied scenario.
    page_token: str | None = None
    seen = 0
    orphans_found = 0
    label_applied = 0
    rows_appended = 0
    while True:
        req = service.users().drafts().list(
            userId="me",
            maxResults=100,
            pageToken=page_token,
        )
        resp = req.execute()
        for d in resp.get("drafts") or []:
            if args.limit is not None and orphans_found >= args.limit:
                break
            seen += 1
            draft_id = d.get("id") or ""
            if not draft_id:
                continue
            try:
                full = service.users().drafts().get(userId="me", id=draft_id, format="full").execute()
            except HttpError as e:
                if smf.is_missing_draft_http_error(e):
                    continue
                raise
            msg = full.get("message") or {}
            msg_id = str(msg.get("id") or "")
            thread_id = str(msg.get("threadId") or "")
            if not msg_id or not thread_id:
                continue

            draft_label_ids = msg.get("labelIds") or []
            already_labeled = label_id in draft_label_ids

            # Check the parent thread for an inbound AI/Prospect Replied message.
            try:
                thread = service.users().threads().get(
                    userId="me", id=thread_id, format="metadata"
                ).execute()
            except HttpError:
                continue
            thread_msgs = thread.get("messages") or []
            thread_has_replied = any(
                label_id in (m.get("labelIds") or []) for m in thread_msgs if m.get("id") != msg_id
            )
            if not thread_has_replied:
                continue  # not a reply to a prospect-replied thread

            # We're in scope. Decide whether this draft needs reconciling.
            in_sheet = msg_id in sheet_by_msgid
            if already_labeled and in_sheet:
                continue  # already reconciled
            orphans_found += 1

            # Pull recipient + subject + body for sheet row + logging.
            pl = msg.get("payload") or {}
            hdrs = {h.get("name", "").lower(): h.get("value", "") for h in pl.get("headers") or []}
            to_addr = _email_from_to_header(hdrs.get("to", ""))
            subject = hdrs.get("subject", "")
            body = extract_plain_body_from_payload(pl, max_total=20_000).strip()
            preview = body.replace("\n", " ")[:BODY_PREVIEW_MAX]

            print(f"orphan draft msg={msg_id[:16]}… → {to_addr}")
            print(f"  thread={thread_id}  draft_id={draft_id}")
            print(f"  subject={subject[:80]}")
            print(f"  in_sheet={in_sheet}  already_labeled={already_labeled}")

            if args.dry_run:
                continue

            # 1. Apply AI/Prospect Replied label to the draft message.
            if not already_labeled:
                try:
                    service.users().messages().modify(
                        userId="me",
                        id=msg_id,
                        body={"addLabelIds": [label_id]},
                    ).execute()
                    label_applied += 1
                    print(f"  applied {PROSPECT_REPLIED_LABEL!r} label")
                except Exception as e:
                    print(f"  WARNING: label apply failed: {e}")

            # 2. Append Email Agent Drafts row if missing.
            if not in_sheet:
                hit = hit_by_email.get(to_addr)
                if hit is None:
                    print(f"  WARNING: no Hit List row for {to_addr} — skipping sheet row append")
                else:
                    hit_row, shop, store_key = hit
                    new_row = [
                        str(uuid.uuid4()),
                        datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S"),
                        store_key, shop, to_addr, str(hit_row),
                        draft_id, subject, preview,
                        PENDING_STATUS, PROSPECT_REPLIED_LABEL,
                        WARMUP_REPLY_PROTOCOL,
                        f"kind=warmup_reply; source=manual_orphan; thread_id={thread_id}; reconciled by reconcile_orphan_reply_drafts.",
                        "0", "0", msg_id,
                    ]
                    try:
                        drafts_ws.append_row(new_row, value_input_option="USER_ENTERED")
                        rows_appended += 1
                        print(f"  appended Email Agent Drafts row (hit_list_row={hit_row}, shop={shop!r})")
                    except Exception as e:
                        print(f"  WARNING: sheet append failed: {e}")

            time.sleep(max(0.0, args.sleep))

        if args.limit is not None and orphans_found >= args.limit:
            break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print()
    print(f"Drafts scanned:        {seen}")
    print(f"Orphans detected:      {orphans_found}")
    print(f"Labels applied:        {label_applied}")
    print(f"Sheet rows appended:   {rows_appended}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
