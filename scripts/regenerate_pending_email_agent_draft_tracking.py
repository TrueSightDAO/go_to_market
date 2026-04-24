#!/usr/bin/env python3
"""
Rewrite **pending_review** Gmail drafts that are registered on **Email Agent Drafts** so the MIME
message includes multipart **HTML** with open/click tracking (same URLs as
``suggest_*_drafts.py --track-opens --track-clicks``).

Preserves **From** (mailbox profile), **To**, **Subject**, threading headers when present, and the
first **application/pdf** attachment when the draft already had one (bytes re-fetched from Gmail).
Plain body is taken from the existing draft (``text/plain`` preferred, else HTML stripped).

Rows whose ``gmail_draft_id`` points at a Gmail message **without** the ``DRAFT`` label (for example
already **SENT** but the sheet still says ``pending_review``) are **skipped** with a log line — fix
the sheet after ``sync_email_agent_followup.py``.

Usage:
  cd market_research
  python3 scripts/regenerate_pending_email_agent_draft_tracking.py --dry-run
  python3 scripts/regenerate_pending_email_agent_draft_tracking.py --limit 5
  python3 scripts/regenerate_pending_email_agent_draft_tracking.py
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as sm
from email_agent_tracking import plain_text_to_html_for_email_agent
from gmail_plain_body import extract_plain_body_from_payload
from googleapiclient.errors import HttpError


def _headers_dict(payload: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in payload.get("headers") or []:
        name = (h.get("name") or "").strip().lower()
        if name:
            out[name] = (h.get("value") or "").strip()
    return out


def _iter_parts(part: dict) -> Any:
    yield part
    for c in part.get("parts") or []:
        yield from _iter_parts(c)


def _pdf_specs(payload: dict) -> list[tuple[str, str]]:
    """Return list of (attachment_id, filename) for application/pdf parts."""
    specs: list[tuple[str, str]] = []
    for p in _iter_parts(payload or {}):
        mt = (p.get("mimeType") or "").lower()
        if mt != "application/pdf":
            continue
        body = p.get("body") or {}
        aid = body.get("attachmentId")
        if not aid:
            continue
        fn = (p.get("filename") or "attachment.pdf").strip() or "attachment.pdf"
        specs.append((str(aid), fn))
    return specs


def _thread_headers_from_payload(payload: dict) -> dict[str, str]:
    """Copy RFC threading headers so Gmail still treats the MIME as the same draft/thread."""
    raw = _headers_dict(payload)
    out: dict[str, str] = {}
    for lower_key, canon in (
        ("message-id", "Message-ID"),
        ("in-reply-to", "In-Reply-To"),
        ("references", "References"),
    ):
        v = raw.get(lower_key, "").strip()
        if v:
            out[canon] = v
    return out


def _build_tracked_message_raw(
    sender: str,
    to: str,
    subject: str,
    body: str,
    *,
    html_body: str | None,
    attachment_path: Path | None,
    attachment_filename: str | None,
    preserve_headers: dict[str, str],
) -> dict[str, str]:
    """Same structure as ``suggest_manager_followup_drafts.build_message_raw`` plus threading headers."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    for hk, hv in preserve_headers.items():
        if hv:
            msg[hk] = hv

    if attachment_path is not None:
        if not attachment_path.is_file():
            raise FileNotFoundError(f"Attachment not found: {attachment_path}")
        data = attachment_path.read_bytes()
        fn = attachment_filename or attachment_path.name
        if html_body:
            inner = EmailMessage()
            inner.set_content(body, charset="utf-8")
            inner.add_alternative(html_body, subtype="html")
            msg.make_mixed()
            msg.attach(inner)
            msg.add_attachment(data, maintype="application", subtype="pdf", filename=fn)
        else:
            msg.make_mixed()
            msg.set_content(body, charset="utf-8")
            msg.add_attachment(data, maintype="application", subtype="pdf", filename=fn)
    elif html_body:
        msg.set_content(body, charset="utf-8")
        msg.add_alternative(html_body, subtype="html")
    else:
        msg.set_content(body, charset="utf-8")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def _fetch_attachment_bytes(service, message_id: str, attachment_id: str) -> bytes:
    att = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    data = att.get("data") or ""
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Add open/click tracking HTML to pending Email Agent Gmail drafts."
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Max drafts to update; 0 = no limit.")
    p.add_argument(
        "--no-track-opens",
        action="store_true",
        help="Omit open pixel (only useful with --no-track-clicks off for link wrapping only).",
    )
    p.add_argument(
        "--no-track-clicks",
        action="store_true",
        help="Do not rewrite http(s) links through Edgar /email_agent/click.",
    )
    p.add_argument(
        "--expected-mailbox",
        default=sm.EXPECTED_MAILBOX,
        help="Abort if Gmail profile != this address.",
    )
    args = p.parse_args()

    track_opens = not args.no_track_opens
    track_clicks = not args.no_track_clicks
    if not track_opens and not track_clicks:
        sys.stderr.write("Nothing to do: both --no-track-opens and --no-track-clicks.\n")
        sys.exit(2)

    tracking_base = (os.environ.get("EMAIL_AGENT_TRACKING_BASE_URL") or "https://edgar.truesight.me").strip()
    if not tracking_base:
        sys.stderr.write("EMAIL_AGENT_TRACKING_BASE_URL is empty.\n")
        sys.exit(2)

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
    need = ("suggestion_id", "to_email", "gmail_draft_id", "status", "subject")
    for k in need:
        if k not in hdr:
            raise SystemExit(f"Email Agent Drafts row 1 missing column {k!r}.")

    si = hdr["suggestion_id"]
    te = hdr["to_email"]
    gi = hdr["gmail_draft_id"]
    st = hdr["status"]
    sj = hdr["subject"]

    pending: list[tuple[int, list[str]]] = []
    for i, row in enumerate(rows[1:], start=2):
        if sm.cell(row, st).lower() != "pending_review":
            continue
        did = sm.cell(row, gi).strip()
        if not did:
            continue
        pending.append((i, row))

    if not pending:
        print("No pending_review rows with a gmail_draft_id.")
        return

    print(f"Mailbox: {me} | pending drafts with id: {len(pending)}")
    n_ok = 0
    n_skip = 0
    n_err = 0

    for sheet_row, row in pending:
        if args.limit > 0 and n_ok >= args.limit:
            break

        sug_id = sm.cell(row, si).strip()
        to_sheet = sm.normalize_email(sm.cell(row, te)) or ""
        draft_id = sm.cell(row, gi).strip()
        subj_sheet = sm.cell(row, sj).strip()

        if not sug_id or not to_sheet:
            print(f"  skip row {sheet_row}: missing suggestion_id or to_email")
            n_skip += 1
            continue

        try:
            dr = gsvc.users().drafts().get(userId="me", id=draft_id, format="full").execute()
        except HttpError as e:
            print(f"  error row {sheet_row} draft={draft_id!r}: {e}")
            n_err += 1
            continue

        msg = dr.get("message") or {}
        msg_id = (msg.get("id") or "").strip()
        labels = {str(x).upper() for x in (msg.get("labelIds") or [])}
        if "DRAFT" not in labels or "SENT" in labels:
            print(
                f"  skip row {sheet_row}: Gmail id {draft_id!r} is not an open draft "
                f"(labels={sorted(labels)}) — row likely stale after Send; run "
                f"sync_email_agent_followup.py and mark sheet row discarded/sent."
            )
            n_skip += 1
            continue

        payload = msg.get("payload") or {}
        hdrs = _headers_dict(payload)
        to_hdr = sm.normalize_email(hdrs.get("to", "")) or ""
        subj = hdrs.get("subject", "").strip() or subj_sheet

        if to_hdr and to_sheet and to_hdr != to_sheet:
            print(
                f"  skip row {sheet_row}: draft To {to_hdr!r} != sheet to_email {to_sheet!r}"
            )
            n_skip += 1
            continue

        plain = extract_plain_body_from_payload(payload)
        if not plain.strip():
            print(f"  skip row {sheet_row}: empty plain body for draft {draft_id!r}")
            n_skip += 1
            continue

        thread_hdrs = _thread_headers_from_payload(payload)

        html_body = plain_text_to_html_for_email_agent(
            plain,
            tracking_base,
            sug_id,
            to_sheet,
            track_opens=track_opens,
            track_clicks=track_clicks,
        )

        pdf_specs = _pdf_specs(payload)
        tmp_path: Path | None = None
        att_name: str | None = None
        try:
            if pdf_specs:
                att_id, att_name = pdf_specs[0]
                data = _fetch_attachment_bytes(gsvc, msg_id, att_id)
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(data)
                tmp.close()
                tmp_path = Path(tmp.name)

            raw_obj = _build_tracked_message_raw(
                me,
                to_sheet,
                subj,
                plain,
                html_body=html_body,
                attachment_path=tmp_path,
                attachment_filename=att_name,
                preserve_headers=thread_hdrs,
            )
        finally:
            if tmp_path is not None and tmp_path.is_file():
                tmp_path.unlink(missing_ok=True)

        if args.dry_run:
            print(
                f"  dry-run row {sheet_row} → {to_sheet!r} draft={draft_id!r} "
                f"pdf={bool(pdf_specs)} tid={sug_id[:8]}…"
            )
            n_ok += 1
            continue

        # Gmail accepts ``{"message": {"raw": ...}}`` only; avoid embedding ``threadId``/top-level
        # ``id`` — some combinations trigger ``Message not a draft`` on update.
        body: dict[str, Any] = {"message": {"raw": raw_obj["raw"]}}

        try:
            gsvc.users().drafts().update(userId="me", id=draft_id, body=body).execute()
        except HttpError as e:
            print(f"  error updating row {sheet_row} draft={draft_id!r}: {e}")
            n_err += 1
            continue

        print(f"  updated row {sheet_row} draft={draft_id!r} → {to_sheet!r}")
        n_ok += 1

    print(
        f"DONE dry_run={args.dry_run} updated={n_ok} skipped={n_skip} errors={n_err} "
        f"track_opens={track_opens} track_clicks={track_clicks}"
    )


if __name__ == "__main__":
    main()
