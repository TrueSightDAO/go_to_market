#!/usr/bin/env python3
"""
Auto-send the **linter-clean** tier of AI/Warm-up Gmail drafts.

Graduation of the operator review loop documented in
``agentic_ai_context/HIT_LIST_STATE_MACHINE.md`` (§ Operator review loop) and
``agentic_ai_context/WARMUP_AUTOSEND_PLAN.md``: warm-up drafts with **zero red
and zero yellow lint flags** no longer wait for a human send-click — they are
sent directly via the Gmail API, capped per run, oldest first. Everything with
any flag at all stays in the human review queue exactly as before
(``preview_warmup_drafts.py`` + Gmail ``AI/Warm-up`` label).

Evidence gate for this graduation (see WARMUP_AUTOSEND_PLAN.md §1): ~6%
genuine reply rate across 232 audited threads, zero copy complaints, while the
pending_review backlog sat a median 24 days on the human click.

Safety posture
--------------
- Same lint pass as ``preview_warmup_drafts.py`` (including the
  ``email_domain_mismatch`` red rule). Clean = no red AND no yellow.
- **Hosts Circles=Yes prospects are excluded by default** — high-leverage rows
  keep human eyes (``--include-hosts-circles`` to override).
- ``--dry-run`` is the **default**; pass ``--execute`` to actually send.
- ``--max-sends`` caps each run (default 12) — drip cadence protects sender
  reputation vs the historical 90+ one-day bursts.
- After each send the ``Email Agent Drafts`` row flips
  ``pending_review → sent`` immediately (plus ``gmail_message_id`` /
  ``thread_id`` and an audit note); the hourly
  ``email-agent-sync-followup.yml`` run completes the Gmail label swap
  (``AI/Warm-up`` → ``AI/Sent Warm-up``) and the ``Email Agent Follow Up``
  log row via its existing reconcile paths.

Usage::

    cd market_research
    python3 scripts/send_clean_warmup_drafts.py                 # dry-run listing
    python3 scripts/send_clean_warmup_drafts.py --execute
    python3 scripts/send_clean_warmup_drafts.py --execute --max-sends 5
"""
from __future__ import annotations

import argparse
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

import preview_warmup_drafts as pw  # noqa: E402  (lint rules + loaders)
import suggest_manager_followup_drafts as smf  # noqa: E402  (creds + sheet helpers)

DRAFTS_WS = "Email Agent Drafts"
AUTOSEND_NOTE = "auto-sent by send_clean_warmup_drafts"
# Gmail label maintained on exactly the drafts the operator needs to look at —
# the human review queue, self-updating each run. AI/Warm-up alone can't serve
# as the queue because it also holds the clean tier the auto-sender will drain.
REVIEW_QUEUE_LABEL = "AI/Needs Review"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify(draft: dict, service, by_email: dict, by_store: dict, dapp_counts: dict) -> dict:
    """Fetch the Gmail draft, lint it, and return a decision payload."""
    subject, body, _to_hdr, message_id = pw._fetch_draft(service, draft["draft_id"])
    hit = by_email.get(draft["to_email"]) or by_store.get(draft["store_key"])
    dapp_count = dapp_counts.get((draft["shop_name"] or "").lower(), 0)
    flags = pw._lint(draft, body, subject, hit, dapp_count)
    reds = [f for f in flags if f[0] == pw.SEV_RED]
    yellows = [f for f in flags if f[0] == pw.SEV_YELLOW]
    hosts_circles = bool(hit and hit.get("hosts_circles"))
    return {
        **draft,
        "subject": subject,
        "body_len": len(body),
        "message_id": message_id,
        "flags": flags,
        "reds": reds,
        "yellows": yellows,
        "hosts_circles": hosts_circles,
    }


def _flip_rows_sent(ws, decisions: list[dict]) -> int:
    """Batch-flip Email Agent Drafts rows for sent drafts: status, ids, note.
    Mirrors the cell-batch pattern of sync_email_agent_followup.py
    ``reconcile_drafts_status_to_sent``."""
    values = ws.get_all_values()
    hdr = smf.header_map(values[0])
    i_status = hdr.get("status")
    i_msg = hdr.get("gmail_message_id")
    i_thread = hdr.get("thread_id")
    i_notes = hdr.get("notes")
    if i_status is None:
        sys.stderr.write("Email Agent Drafts missing 'status' column\n")
        return 0
    cells: list[gspread.Cell] = []
    for d in decisions:
        r = d["sheet_row"]
        cells.append(gspread.Cell(r, i_status + 1, "sent"))
        if i_msg is not None and d.get("sent_message_id"):
            cells.append(gspread.Cell(r, i_msg + 1, d["sent_message_id"]))
        if i_thread is not None and d.get("sent_thread_id"):
            cells.append(gspread.Cell(r, i_thread + 1, d["sent_thread_id"]))
        if i_notes is not None:
            prior = smf.cell(values[r - 1], i_notes) if r - 1 < len(values) else ""
            note = f"{AUTOSEND_NOTE} {d['sent_at']}"
            cells.append(gspread.Cell(r, i_notes + 1, f"{prior} | {note}".strip(" |")))
    if cells:
        ws.update_cells(cells, value_input_option="RAW")
    return len(decisions)


def _reconcile_review_label(service, skipped: list[dict]) -> None:
    """Keep the AI/Needs Review Gmail label in sync with the flagged cohort:
    add it to every skipped draft, strip it from anything that is no longer
    in the queue (became clean, was sent, or was discarded). Diff-based, so
    re-runs are cheap no-ops."""
    label_id = smf.ensure_user_label_id(service, REVIEW_QUEUE_LABEL)
    want = {d["message_id"] for d in skipped if d.get("message_id")}
    have: set[str] = set()
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", labelIds=[label_id], maxResults=500, pageToken=page_token,
        ).execute()
        have |= {m["id"] for m in resp.get("messages") or []}
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    for mid in want - have:
        try:
            service.users().messages().modify(
                userId="me", id=mid, body={"addLabelIds": [label_id]}).execute()
        except HttpError as e:
            sys.stderr.write(f"  WARNING: review-label add failed for {mid}: {e}\n")
    for mid in have - want:
        try:
            service.users().messages().modify(
                userId="me", id=mid, body={"removeLabelIds": [label_id]}).execute()
        except HttpError as e:
            sys.stderr.write(f"  WARNING: review-label remove failed for {mid}: {e}\n")
    if want - have or have - want:
        print(f"review label '{REVIEW_QUEUE_LABEL}': +{len(want - have)} "
              f"-{len(have - want)} (queue now {len(want)})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--execute", action="store_true",
                    help="Actually send. Default is a dry-run listing.")
    ap.add_argument("--max-sends", type=int, default=12,
                    help="Cap sends per run (default 12 — drip cadence).")
    ap.add_argument("--include-hosts-circles", action="store_true",
                    help="Also auto-send Hosts Circles=Yes prospects "
                         "(default: excluded — they keep human review).")
    args = ap.parse_args(argv)

    sa = smf.get_sheets_client()
    sh = sa.open_by_key(smf.SPREADSHEET_ID)
    hit_ws = sh.worksheet(smf.HIT_LIST_WS)
    drafts_ws = sh.worksheet(DRAFTS_WS)
    remarks_ws = smf.open_dapp_remarks_worksheet(sh)

    service = build("gmail", "v1", credentials=smf.get_gmail_creds(), cache_discovery=False)

    by_email, by_store, _aw = pw._load_hit_list_index(hit_ws)
    dapp_counts = pw._load_dapp_remarks_counts(remarks_ws) if remarks_ws else {}
    pending = pw._load_pending_warmup_drafts(drafts_ws)
    pending.sort(key=lambda d: d.get("created_at") or "")  # oldest first

    clean: list[dict] = []
    skipped: list[dict] = []
    for draft in pending:
        d = _classify(draft, service, by_email, by_store, dapp_counts)
        if d["reds"] or d["yellows"]:
            d["skip_reason"] = "; ".join(c for _s, c, _m in d["reds"] + d["yellows"])
            skipped.append(d)
        elif d["hosts_circles"] and not args.include_hosts_circles:
            d["skip_reason"] = "hosts_circles (human review by default)"
            skipped.append(d)
        elif not d["body_len"]:
            d["skip_reason"] = "gmail draft missing"
            skipped.append(d)
        else:
            clean.append(d)

    to_send = clean[: max(args.max_sends, 0)]
    overflow = clean[len(to_send):]

    print(f"pending_review AI/Warm-up drafts: {len(pending)}")
    print(f"  clean tier: {len(clean)}  (sending {len(to_send)}, "
          f"{len(overflow)} deferred to next run by --max-sends)")
    print(f"  kept for human review: {len(skipped)}")
    for d in skipped:
        print(f"    REVIEW  {d['shop_name'][:40]:40} <{d['to_email']}>  [{d['skip_reason']}]")
    for d in to_send:
        print(f"    {'SEND' if args.execute else 'WOULD SEND':10} "
              f"{d['shop_name'][:40]:40} <{d['to_email']}>  created {d['created_at']}")

    if not args.execute:
        print("\ndry-run (default) — pass --execute to send.")
        return 0

    _reconcile_review_label(service, skipped)

    sent: list[dict] = []
    for d in to_send:
        try:
            resp = service.users().drafts().send(
                userId="me", body={"id": d["draft_id"]}
            ).execute()
        except HttpError as e:
            if smf.is_missing_draft_http_error(e):
                sys.stderr.write(f"draft vanished, skipping: {d['shop_name']} <{d['to_email']}>\n")
                continue
            raise
        d["sent_message_id"] = str(resp.get("id") or "")
        d["sent_thread_id"] = str(resp.get("threadId") or "")
        d["sent_at"] = _now_iso()
        sent.append(d)
        print(f"sent: {d['shop_name']} <{d['to_email']}> message_id={d['sent_message_id']}")

    flipped = _flip_rows_sent(drafts_ws, sent)
    print(f"\nsent {len(sent)} drafts; flipped {flipped} Email Agent Drafts rows to status=sent.")
    print("label swap + Email Agent Follow Up logging completes on the next "
          "email-agent-sync-followup.yml run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
