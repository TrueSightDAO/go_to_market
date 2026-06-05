#!/usr/bin/env python3
"""
Bounce handling: detect delivery failures on outreach sends and route the
Hit List row back to contact discovery instead of letting it rot.

Why (closes the gap surfaced by the first auto-send run — see
``agentic_ai_context/WARMUP_AUTOSEND_PLAN.md`` changelog): a bounced warm-up
previously fell on the floor. The reply detectors deliberately filter
``mailer-daemon`` as noise, so the row stayed in ``AI: Warm up prospect``
with a send recorded (AU>=1) — and 14 days later the aged-out cron would
promote it to ``Manager Follow-up``, where a follow-up draft gets generated
**to the same dead address**. The state machine doc always listed "message
bounced" as a terminal transition; this script finally implements it.

What it does, per bounce::

  1. Finds Gmail delivery-failure messages (``from:mailer-daemon`` /
     ``postmaster``) newer than ``--days``; extracts the failed recipient
     from the ``X-Failed-Recipients`` header (body-regex fallback).
  2. Looks up the Hit List row by that email. If the row's Email cell still
     holds the dead address:
       - appends ``bounced_email=<addr>`` to **Notes** (the enrich script
         excludes these from future candidate picks),
       - clears the **Email** cell (stops follow-up draft generation and the
         aged-out promotion),
       - sets Status -> ``AI: Enrich with contact`` (re-queues discovery for
         a different address / contact form) via the shared DApp Remarks
         apply-semantics — gated to automated-outreach statuses only,
       - discards any ``pending_review`` Email Agent Drafts rows addressed
         to the dead address and deletes their Gmail drafts.
  3. Writes a ``DApp Remarks`` audit row either way; idempotent on the
     bounce ``message_id=…`` marker.

Usage::

    cd market_research
    python3 scripts/handle_warmup_bounces.py             # dry-run
    python3 scripts/handle_warmup_bounces.py --execute
    python3 scripts/handle_warmup_bounces.py --execute --days 60 --limit 50
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf  # noqa: E402
from gmail_plain_body import extract_plain_body_from_payload  # noqa: E402
from hit_list_dapp_remarks_sheet import (  # noqa: E402
    append_dapp_remark_and_apply,
    gspread_retry,
)

SUBMITTED_BY = "handle_warmup_bounces"
STATUS_REENRICH = "AI: Enrich with contact"
# Only rows still owned by the automated outreach pipeline get re-routed;
# operator-managed states (Partnered, On Hold, …) just receive the audit remark.
REROUTABLE_STATUSES = {
    "AI: Warm up prospect", "AI: Email found", "AI: Prospect replied",
    "Manager Follow-up", "Followed Up",
}
BOUNCE_QUERY = 'from:(mailer-daemon OR postmaster) newer_than:{days}d'
# "Your message wasn't delivered to abemassage@yahoo.com because …"
BODY_ADDR_RE = re.compile(
    r"(?:delivered to|delivery to|recipient)\s+<?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})>?",
    re.IGNORECASE,
)


def _failed_recipient(msg: dict) -> str:
    hdrs = {h.get("name", "").lower(): h.get("value", "")
            for h in (msg.get("payload") or {}).get("headers") or []}
    addr = (hdrs.get("x-failed-recipients") or "").strip().lower()
    if addr and "@" in addr:
        return addr.split(",")[0].strip()
    body = extract_plain_body_from_payload(msg.get("payload") or {}, max_total=8_000)
    m = BODY_ADDR_RE.search(body or "")
    return m.group(1).strip().lower() if m else ""


def _handled_bounce_ids(remarks_ws) -> set[str]:
    vals = gspread_retry(lambda: remarks_ws.get_all_values())
    if len(vals) < 2:
        return set()
    hdr = {h: i for i, h in enumerate(vals[0])}
    i_by, i_rem = hdr.get("Submitted By"), hdr.get("Remarks")
    out: set[str] = set()
    for row in vals[1:]:
        if i_by is None or i_rem is None:
            break
        if (row[i_by] if len(row) > i_by else "") != SUBMITTED_BY:
            continue
        rem = row[i_rem] if len(row) > i_rem else ""
        if "message_id=" in rem:
            out.add(rem.split("message_id=", 1)[1].split(";", 1)[0].strip())
    return out


def _discard_pending_drafts(service, drafts_ws, dead_addr: str, stamp: str) -> int:
    """Discard pending_review Email Agent Drafts rows to the dead address and
    delete their Gmail drafts (so nothing can send to it)."""
    values = gspread_retry(lambda: drafts_ws.get_all_values())
    if len(values) < 2:
        return 0
    hdr = smf.header_map(values[0])
    i_status, i_to = hdr.get("status"), hdr.get("to_email")
    i_draft, i_notes = hdr.get("gmail_draft_id"), hdr.get("notes")
    n = 0
    for r_idx, row in enumerate(values[1:], start=2):
        if smf.cell(row, i_status) != "pending_review":
            continue
        if (smf.normalize_email(smf.cell(row, i_to)) or "") != dead_addr:
            continue
        draft_id = smf.cell(row, i_draft)
        if draft_id:
            try:
                service.users().drafts().delete(userId="me", id=draft_id).execute()
            except HttpError as e:
                if not smf.is_missing_draft_http_error(e):
                    sys.stderr.write(f"  WARNING: draft delete failed: {e}\n")
        gspread_retry(lambda: drafts_ws.update_cell(r_idx, i_status + 1, "discarded"))
        if i_notes is not None:
            prior = smf.cell(row, i_notes)
            note = f"discarded {stamp}: address bounced ({SUBMITTED_BY})"
            gspread_retry(lambda: drafts_ws.update_cell(
                r_idx, i_notes + 1, f"{prior} | {note}".strip(" |")))
        n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--execute", action="store_true",
                    help="Apply changes. Default is dry-run.")
    ap.add_argument("--days", type=int, default=30,
                    help="How far back to scan for bounce messages (default 30).")
    ap.add_argument("--limit", type=int, default=20,
                    help="Cap bounces handled per run (default 20).")
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args(argv)

    service = build("gmail", "v1", credentials=smf.get_gmail_creds(), cache_discovery=False)
    sa = smf.get_sheets_client()
    sh = sa.open_by_key(smf.SPREADSHEET_ID)
    hit_ws = sh.worksheet(smf.HIT_LIST_WS)
    drafts_ws = sh.worksheet(smf.SUGGESTIONS_WS)
    remarks_ws = smf.open_dapp_remarks_worksheet(sh)
    if remarks_ws is None:
        sys.stderr.write("DApp Remarks worksheet not found.\n")
        return 1

    hit_values = gspread_retry(lambda: hit_ws.get_all_values())
    hit_headers = hit_values[0]
    hdr = {h: i for i, h in enumerate(hit_headers)}
    by_email: dict[str, dict] = {}
    for ri, row in enumerate(hit_values[1:], start=2):
        em = smf.normalize_email(row[hdr["Email"]] if len(row) > hdr["Email"] else "")
        if em and em not in by_email:
            by_email[em] = {
                "row": ri,
                "shop": row[hdr["Shop Name"]] if len(row) > hdr["Shop Name"] else "",
                "status": row[hdr["Status"]] if len(row) > hdr["Status"] else "",
                "notes": row[hdr["Notes"]] if len(row) > hdr["Notes"] else "",
            }

    handled_ids = _handled_bounce_ids(remarks_ws)

    msgs: list[dict] = []
    page_token = None
    q = BOUNCE_QUERY.format(days=args.days)
    while True:
        resp = service.users().messages().list(
            userId="me", q=q, maxResults=100, pageToken=page_token).execute()
        msgs.extend(resp.get("messages") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    handled = 0
    actioned_addrs: set[str] = set()
    for stub in msgs:
        if handled >= args.limit:
            break
        mid = stub.get("id") or ""
        if not mid or mid in handled_ids:
            continue
        try:
            full = service.users().messages().get(userId="me", id=mid, format="full").execute()
        except HttpError:
            continue
        dead = _failed_recipient(full)
        if not dead:
            continue
        hit = by_email.get(dead)
        if hit is None and dead not in actioned_addrs:
            # Not an outreach recipient (or Email already cleared by a prior
            # run) — leave no remark; nothing to act on.
            print(f"{'SKIP':12} (no Hit List row) <{dead}>")
            continue
        shop = (hit or {}).get("shop") or dead
        status = (hit or {}).get("status", "")
        reroute = bool(hit and status in REROUTABLE_STATUSES and dead not in actioned_addrs)
        action = (f"clear email + Notes marker + status -> {STATUS_REENRICH}" if reroute
                  else ("audit remark — already actioned this run" if dead in actioned_addrs
                        else f"remark only — status {status!r} is operator-managed"))
        print(f"{'BOUNCE' if args.execute else 'WOULD HANDLE':12} {shop[:40]:40} <{dead}>  [{action}]")
        handled += 1
        if not args.execute:
            continue

        now_iso = datetime.now(timezone.utc).isoformat()
        stamp = now_iso[:19] + "Z"
        sid = f"bounce-{uuid.uuid4()}"
        remark = (
            f"[bounce {now_iso}] outcome=bounced; message_id={mid}; bad_email={dead}. "
            "Delivery failure (address not found / cannot receive mail). "
            + ("Email cleared, bounced_email marker added to Notes, row re-queued for "
               "contact discovery." if reroute else "No automated state change.")
        )

        actioned_addrs.add(dead)
        if reroute:
            # 1. Notes marker (enrich excludes bounced addresses from future picks).
            notes_now = gspread_retry(
                lambda: hit_ws.cell(hit["row"], hdr["Notes"] + 1).value) or ""
            if f"bounced_email={dead}" not in notes_now:
                new_notes = f"{notes_now.strip()}; bounced_email={dead}".strip("; ")
                gspread_retry(lambda: hit_ws.update_cell(
                    hit["row"], hdr["Notes"] + 1, new_notes))
            # 2. Clear Email (stops follow-up drafts + aged-out promotion).
            gspread_retry(lambda: hit_ws.update_cell(hit["row"], hdr["Email"] + 1, ""))
            # 3. Discard staged drafts to the dead address.
            n_disc = _discard_pending_drafts(service, drafts_ws, dead, stamp)
            if n_disc:
                print(f"    discarded {n_disc} pending draft(s) to {dead}")
            # 4. Status + Sales Process Notes + audit remark via shared apply.
            append_dapp_remark_and_apply(
                hit_ws, remarks_ws, hit["row"], shop, STATUS_REENRICH,
                remark, SUBMITTED_BY, now_iso, sid, hit_headers=hit_headers,
            )
        else:
            # Audit-only remark, pre-marked Processed.
            r_headers = gspread_retry(lambda: remarks_ws.row_values(1))
            row_out = [{
                "Submission ID": sid, "Shop Name": shop, "Status": status,
                "Remarks": remark, "Submitted By": SUBMITTED_BY,
                "Submitted At": now_iso, "Processed": "Yes", "Processed At": now_iso,
            }.get(h, "") for h in r_headers]
            gspread_retry(lambda: remarks_ws.append_row(row_out, value_input_option="USER_ENTERED"))

        handled_ids.add(mid)
        time.sleep(max(0.0, args.sleep))

    print(f"\nbounce messages scanned: {len(msgs)}; handled this run: {handled}")
    if not args.execute:
        print("dry-run (default) — pass --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
