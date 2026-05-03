#!/usr/bin/env python3
"""
One-off backfill: populate ``gmail_message_id`` for ``pending_review``
rows in the **Email Agent Drafts** tab where the column was added after
the row was created (PR added the column 2026-05-03).

Why this exists: the DApp warm-up review page constructs deep-links of
the form ``https://mail.google.com/mail/u/0/#drafts/<message_id>`` so a
single tap from a phone jumps directly to the right draft. Existing
rows only have ``gmail_draft_id`` (an opaque draft-API handle), not the
underlying ``message.id`` Gmail's UI uses in URLs. Both ids are
available at draft-creation time — we just weren't persisting it.

Reads each row's ``gmail_draft_id``, fetches the draft via Gmail API,
extracts ``draft.message.id``, writes it to the new
``gmail_message_id`` cell. Skips rows where:

- The cell is already populated (idempotent re-runs).
- The Gmail draft no longer exists (deleted or sent — those rows will
  get reconciled to ``discarded`` by the next cron tick anyway).
- The row's status is not ``pending_review`` (sent / discarded rows
  don't need the deep-link).

Run this once after deploying the schema change. Future drafts get
``gmail_message_id`` populated at creation time by
``suggest_warmup_prospect_drafts.py`` and
``suggest_manager_followup_drafts.py``.

Usage::

    cd market_research
    python3 scripts/backfill_email_agent_drafts_message_id.py --dry-run
    python3 scripts/backfill_email_agent_drafts_message_id.py
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import gspread
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf  # noqa: E402

PENDING_STATUS = "pending_review"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would change without touching the sheet.")
    p.add_argument("--limit", type=int, default=None,
                   help="Cap rows updated this run (default: all needing backfill).")
    p.add_argument("--sleep", type=float, default=0.15,
                   help="Sleep between writes in seconds (default 0.15).")
    args = p.parse_args(argv)

    gc = smf.get_sheets_client()
    sh = gc.open_by_key(smf.SPREADSHEET_ID)
    ws = sh.worksheet(smf.SUGGESTIONS_WS)
    values = ws.get_all_values()
    if len(values) < 2:
        print("No data rows.")
        return 0

    hdr = smf.header_map(values[0])
    for col in ("status", "gmail_draft_id", "gmail_message_id"):
        if col not in hdr:
            sys.stderr.write(f"Email Agent Drafts missing column: {col}\n")
            sys.stderr.write("Run scripts/ensure_email_agent_suggestions_sheet.py first.\n")
            return 1
    i_status = hdr["status"]
    i_draft = hdr["gmail_draft_id"]
    i_msg = hdr["gmail_message_id"]

    targets: list[tuple[int, str]] = []
    for ri, raw in enumerate(values[1:], start=2):
        row = list(raw) + [""] * (len(values[0]) - len(raw))
        if (row[i_status] or "").strip() != PENDING_STATUS:
            continue
        if (row[i_msg] or "").strip():
            continue
        draft_id = (row[i_draft] or "").strip()
        if not draft_id:
            continue
        targets.append((ri, draft_id))

    print(f"Total rows: {len(values) - 1}")
    print(f"Pending rows missing gmail_message_id: {len(targets)}")
    if args.limit is not None:
        targets = targets[: args.limit]
        print(f"Limiting to first {len(targets)}.")

    if not targets:
        print("Nothing to backfill.")
        return 0

    creds = smf.get_gmail_creds()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    filled = 0
    missing = 0
    failures = 0
    for ri, draft_id in targets:
        try:
            dr = service.users().drafts().get(userId="me", id=draft_id, format="metadata").execute()
        except HttpError as e:
            if smf.is_missing_draft_http_error(e):
                missing += 1
                print(f"  [skip] row {ri} draft {draft_id!r}: missing in Gmail (will be reconciled to discarded)")
                continue
            failures += 1
            sys.stderr.write(f"  [fail] row {ri} draft {draft_id!r}: {e}\n")
            continue
        msg = dr.get("message") or {}
        msg_id = str(msg.get("id") or "").strip()
        if not msg_id:
            failures += 1
            sys.stderr.write(f"  [fail] row {ri} draft {draft_id!r}: no message.id in response\n")
            continue
        if args.dry_run:
            print(f"  [dry] row {ri} draft {draft_id!r} -> message_id={msg_id}")
            filled += 1
            continue
        try:
            ws.update_cell(ri, i_msg + 1, msg_id)
            filled += 1
            print(f"  [ok ] row {ri}: message_id={msg_id}")
        except Exception as e:
            failures += 1
            sys.stderr.write(f"  [fail] row {ri} write: {e}\n")
        time.sleep(max(0.0, args.sleep))

    print()
    print(f"Filled:    {filled}")
    print(f"Missing in Gmail (skipped): {missing}")
    print(f"Failures:  {failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
