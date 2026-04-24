#!/usr/bin/env python3
"""
Set **Email Agent Drafts** rows from ``pending_review`` → ``sent`` when the stored
``gmail_draft_id`` resolves in Gmail to a message that has **SENT** and no **DRAFT**
(the sheet was never updated after Send).

Also marks **discarded** when ``drafts.get`` returns **404** (deleted draft), with an
audit note appended to **notes** (same style as cadence reconcile).

Run **after** ``sync_email_agent_followup.py`` when possible so **Email Agent Follow Up**
already reflects the send.

Usage:
  cd market_research
  python3 scripts/reconcile_email_agent_drafts_stale_sent.py --dry-run
  python3 scripts/reconcile_email_agent_drafts_stale_sent.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as sm
from googleapiclient.errors import HttpError
from gspread.utils import rowcol_to_a1


def _append_note(existing: str, suffix: str) -> str:
    base = (existing or "").rstrip()
    if base:
        return base + suffix
    return suffix.lstrip()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Reconcile Email Agent Drafts pending_review rows against Gmail SENT / missing drafts."
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--expected-mailbox",
        default=sm.EXPECTED_MAILBOX,
        help="Abort if Gmail profile != this address.",
    )
    args = p.parse_args()

    gcreds = sm.get_gmail_creds()
    gsvc = sm.build("gmail", "v1", credentials=gcreds, cache_discovery=False)
    me = sm.gmail_profile_email(gsvc)
    exp = args.expected_mailbox.strip().lower()
    if me != exp:
        sys.stderr.write(
            f"Gmail profile is {me!r}, expected {exp!r}. Sign in with the ops mailbox or pass --expected-mailbox.\n"
        )
        sys.exit(1)

    sa = sm.get_sheets_client()
    sh = sa.open_by_key(sm.SPREADSHEET_ID)
    sugg_ws = sm.ensure_suggestions_worksheet(sh)
    rows = sugg_ws.get_all_values()
    if len(rows) < 2:
        print("No rows on Email Agent Drafts.")
        return

    hdr = sm.header_map(rows[0])
    for k in ("suggestion_id", "to_email", "gmail_draft_id", "status", "notes"):
        if k not in hdr:
            raise SystemExit(f"Email Agent Drafts row 1 missing column {k!r}.")

    si = hdr["suggestion_id"]
    te = hdr["to_email"]
    gi = hdr["gmail_draft_id"]
    st = hdr["status"]
    ni = hdr["notes"]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    n_sent = 0
    n_discard = 0
    n_skip = 0

    for sheet_row, row in enumerate(rows[1:], start=2):
        if sm.cell(row, st).lower() != "pending_review":
            continue
        draft_id = sm.cell(row, gi).strip()
        if not draft_id:
            continue

        try:
            dr = gsvc.users().drafts().get(userId="me", id=draft_id, format="metadata").execute()
        except HttpError as e:
            code = getattr(getattr(e, "resp", None), "status", None)
            if code == 404:
                new_status = "discarded"
                suffix = f" [{now}] reconcile: Gmail draft id missing (HTTP 404); set {new_status}."
                n_discard += 1
            else:
                print(f"  error row {sheet_row} draft={draft_id!r}: {e}")
                continue

            notes = _append_note(sm.cell(row, ni), suffix)
            if args.dry_run:
                print(
                    f"  dry-run row {sheet_row} → {new_status} "
                    f"to={sm.cell(row, te)!r} draft={draft_id!r}"
                )
                continue

            sugg_ws.update(
                [[new_status]],
                range_name=rowcol_to_a1(sheet_row, st + 1),
                value_input_option="USER_ENTERED",
            )
            sugg_ws.update(
                [[notes]],
                range_name=rowcol_to_a1(sheet_row, ni + 1),
                value_input_option="USER_ENTERED",
            )
            print(f"  row {sheet_row}: {new_status} (404) draft={draft_id!r}")
            continue

        msg = dr.get("message") or {}
        labels = {str(x).upper() for x in (msg.get("labelIds") or [])}
        if "DRAFT" in labels and "SENT" not in labels:
            n_skip += 1
            continue
        if "SENT" in labels and "DRAFT" not in labels:
            new_status = "sent"
            suffix = f" [{now}] reconcile: Gmail shows SENT without DRAFT; set sent."
            n_sent += 1
        else:
            # e.g. only DRAFT, or TRASH without clear sent — leave alone
            n_skip += 1
            continue

        notes = _append_note(sm.cell(row, ni), suffix)
        if args.dry_run:
            print(
                f"  dry-run row {sheet_row} → {new_status} "
                f"to={sm.cell(row, te)!r} labels={sorted(labels)}"
            )
            continue

        sugg_ws.update(
            [[new_status]],
            range_name=rowcol_to_a1(sheet_row, st + 1),
            value_input_option="USER_ENTERED",
        )
        sugg_ws.update(
            [[notes]],
            range_name=rowcol_to_a1(sheet_row, ni + 1),
            value_input_option="USER_ENTERED",
        )
        print(f"  row {sheet_row}: {new_status} labels={sorted(labels)}")

    print(
        f"DONE dry_run={args.dry_run} sent={n_sent} discarded_404={n_discard} skipped_open_draft={n_skip}"
    )


if __name__ == "__main__":
    main()
