#!/usr/bin/env python3
"""
Create Gmail drafts with a PDF attachment, mirroring suggest_manager_followup_drafts.py:
same mailbox check, same label, append Email Agent Suggestions.

Use for one-off cases (e.g. wholesale overview PDF) without running the full manager-follow-up
pipeline.

Usage:
  cd market_research
  python3 scripts/create_manager_followup_drafts_with_pdf.py --dry-run
  python3 scripts/create_manager_followup_drafts_with_pdf.py --replace   # drop old “price sheet attached” drafts first
  python3 scripts/create_manager_followup_drafts_with_pdf.py
"""

from __future__ import annotations

import argparse
import base64
import re
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
SUGGESTIONS_WS = "Email Agent Suggestions"
EXPECTED_MAILBOX = "garyjob@agroverse.shop"
DEFAULT_GMAIL_LABEL = "Email Agent suggestions"
PROTOCOL_VERSION = "PARTNER_OUTREACH_PROTOCOL v0.1"
BODY_PREVIEW_MAX = 500

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SUGGESTIONS_HEADERS = [
    "suggestion_id",
    "created_at_utc",
    "store_key",
    "shop_name",
    "to_email",
    "hit_list_row",
    "gmail_draft_id",
    "subject",
    "body_preview",
    "status",
    "gmail_label",
    "protocol_version",
    "notes",
]

# Defaults for Rochester bulk-focused follow-ups (Mar 2026)
DEFAULT_PDF = _REPO / "retail_price_list" / "agroverse_wholesale_retail_overview_2026.pdf"
DEFAULT_ATTACH_NAME = "Agroverse_wholesale_retail_overview_2026.pdf"

DRAFT_SPECS: list[dict] = [
    {
        "to_email": "mike@prettyapothecary.com",
        "store_key": "pretty-apothecary__720-university-avenue__rochester__ny",
        "shop_name": "Pretty Apothecary",
        "hit_list_row": "237",
        "subject": "Pretty Apothecary - Follow-Up on Ceremonial Cacao & Tea Samples (price sheet attached)",
        "body": """Hi Mike,

I hope you're doing well! I wanted to follow up on our recent conversation at Pretty Apothecary in Rochester. It was great to hear your thoughts on the ceremonial cacao and cacao tea samples from Paul's farm that I left with you. I'm thrilled you liked the quality and are interested in potentially buying the cacao tea in bulk, as well as exploring additional brands for your store.

I've attached a brief two-page overview: pricing and retail-pack terms on page 1, farm taste profiles on page 2 (bulk per-pound pricing including cacao tea, 200g bag wholesale, traceability links).

I'd love to hear more about your thoughts on the samples and discuss how we can move forward with a potential order or bulk purchase for the cacao tea. Could you reply to this email with your feedback or let me know a good time for a quick phone call to chat about next steps? I'm happy to provide any additional details or arrange for more samples if needed.

Looking forward to hearing from you soon!

Gary
Agroverse | ceremonial cacao for retail
garyjob@agroverse.shop
""",
    },
    {
        "to_email": "rob@oneworldgoods.org",
        "store_key": "one-world-goods__3349-monroe-avenue__rochester__ny",
        "shop_name": "One World Goods",
        "hit_list_row": "240",
        "subject": "One World Goods - Agroverse Cacao Bulk Purchase (price sheet attached)",
        "body": """Hi Rob,

It was great connecting with you during my recent visit to One World Goods in Rochester, NY. I appreciated learning about your approach to bulk purchases and your interest in exploring options with Agroverse's ceremonial cacao. Noticing the chocolate bars you already carry, I think our product could be a unique addition to your lineup.

I've attached a brief two-page overview: pricing on page 1 and farm profiles on page 2—flexible order sizes, no large minimums implied on this sheet.

I'd love to hear your thoughts after you've had a chance to research further. Could you reply to this email with any questions or to confirm your interest in moving forward? If it's easier, I'm also happy to set up a quick phone or video call to discuss details and ensure everything aligns with your store's needs.

Looking forward to hearing from you!

Gary
Agroverse | ceremonial cacao for retail
garyjob@agroverse.shop
""",
    },
]


def ensure_user_label_id(service, label_name: str) -> str:
    resp = service.users().labels().list(userId="me").execute()
    for lab in resp.get("labels", []):
        if lab.get("name") == label_name:
            return str(lab["id"])
    body = {
        "name": label_name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    created = service.users().labels().create(userId="me", body=body).execute()
    return str(created["id"])


def _draft_metadata_headers(service, draft_id: str) -> dict[str, str]:
    dr = service.users().drafts().get(userId="me", id=draft_id, format="metadata").execute()
    msg = dr.get("message") or {}
    pl = msg.get("payload") or {}
    return {h.get("name", "").lower(): h.get("value", "") for h in pl.get("headers", [])}


def _to_header_has_email(to_header: str, want_lower: str) -> bool:
    if not want_lower or not to_header:
        return False
    tl = to_header.lower()
    if want_lower in tl:
        return True
    for m in re.finditer(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", tl):
        if m.group(0) == want_lower:
            return True
    return False


def delete_drafts_matching(
    service,
    *,
    to_email: str,
    subject_substring: str,
    dry_run: bool,
) -> int:
    """Remove open drafts whose To includes *to_email* and Subject contains *subject_substring* (case-insensitive)."""
    want = to_email.strip().lower()
    needle = (subject_substring or "").strip().lower()
    n = 0
    page_token: str | None = None
    while True:
        kwargs: dict = {"userId": "me", "maxResults": 100}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().drafts().list(**kwargs).execute()
        for d in resp.get("drafts", []):
            did = d.get("id")
            if not did:
                continue
            hdrs = _draft_metadata_headers(service, did)
            to_h = hdrs.get("to", "") or ""
            subj = (hdrs.get("subject", "") or "").lower()
            if not _to_header_has_email(to_h, want):
                continue
            if needle and needle not in subj:
                continue
            if dry_run:
                print(f"  [dry-run] would delete draft {did!r} subj={hdrs.get('subject', '')!r}")
            else:
                service.users().drafts().delete(userId="me", id=did).execute()
                print(f"  Deleted prior draft {did!r} (→ {want}) subj={hdrs.get('subject', '')!r}")
            n += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return n


def build_raw_with_attachment(
    sender: str,
    to: str,
    subject: str,
    body: str,
    pdf_path: Path,
    attachment_filename: str,
) -> dict:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")
    pdf_bytes = pdf_path.read_bytes()
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_filename,
    )
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Gmail drafts with PDF attachment + sheet log row.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-label", action="store_true")
    parser.add_argument(
        "--pdf-path",
        type=Path,
        default=DEFAULT_PDF,
        help=f"Path to PDF (default: {DEFAULT_PDF})",
    )
    parser.add_argument(
        "--attachment-filename",
        default=DEFAULT_ATTACH_NAME,
        help="Filename as seen by recipient",
    )
    parser.add_argument(
        "--expected-mailbox",
        default=EXPECTED_MAILBOX,
        help=f"Abort if Gmail profile != this (default: {EXPECTED_MAILBOX})",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing open drafts to the same recipients whose subject contains “(price sheet attached)” "
        "before creating new ones (avoids duplicate drafts when refreshing the PDF).",
    )
    args = parser.parse_args()

    pdf_path: Path = args.pdf_path.resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")

    import sys

    sys.path.insert(0, str(_REPO / "scripts"))
    from gmail_user_credentials import load_gmail_user_credentials

    gcreds = load_gmail_user_credentials(_GMAIL_TOKEN, GMAIL_SCOPES)
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
    prof = gsvc.users().getProfile(userId="me").execute()
    me = (prof.get("emailAddress") or "").strip().lower()
    exp = args.expected_mailbox.strip().lower()
    if me != exp:
        raise SystemExit(f"Gmail is {me!r}, expected {exp!r}.")

    sa = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    gc = gspread.authorize(sa)
    sh = gc.open_by_key(SPREADSHEET_ID)
    sugg_ws = sh.worksheet(SUGGESTIONS_WS)
    hdr = sugg_ws.row_values(1)
    if not hdr or hdr[: len(SUGGESTIONS_HEADERS)] != SUGGESTIONS_HEADERS:
        print("Warning: first row of suggestions sheet may not match expected headers.")

    label_id: str | None = None
    if not args.dry_run and not args.skip_label:
        label_id = ensure_user_label_id(gsvc, DEFAULT_GMAIL_LABEL)

    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    created_rows: list[list[str]] = []

    print("ROCH_WHOLESALE_DRAFTS mailbox=%s pdf=%s replace=%s" % (me, pdf_path, args.replace))
    if args.replace:
        subj_mark = "(price sheet attached)"
        for spec in DRAFT_SPECS:
            n_del = delete_drafts_matching(
                gsvc,
                to_email=spec["to_email"],
                subject_substring=subj_mark,
                dry_run=args.dry_run,
            )
            if n_del:
                print(f"  Replace: removed {n_del} prior draft(s) for {spec['to_email']}")
    for spec in DRAFT_SPECS:
        to_addr = spec["to_email"]
        subj = spec["subject"]
        body = spec["body"]
        raw = build_raw_with_attachment(
            me, to_addr, subj, body, pdf_path, args.attachment_filename
        )
        if args.dry_run:
            print(f"\n--- dry-run → {to_addr} ({spec['shop_name']}) ---")
            print("Subject:", subj)
            print(body[:600] + ("…" if len(body) > 600 else ""))
            continue

        draft = gsvc.users().drafts().create(userId="me", body={"message": raw}).execute()
        draft_id = draft.get("id", "") or ""
        msg = draft.get("message") or {}
        msg_id = msg.get("id", "") or ""

        if label_id and msg_id:
            try:
                gsvc.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"addLabelIds": [label_id]},
                ).execute()
            except Exception as e:
                print(f"Warning: could not label message {msg_id}: {e}")

        sug_id = str(uuid.uuid4())
        preview = body.replace("\n", " ")[:BODY_PREVIEW_MAX]
        notes = (
            f"PDF attachment draft ({pdf_path.name}); create_manager_followup_drafts_with_pdf.py"
            f"{' --replace' if args.replace else ''}; Edit in Gmail before Send."
        )
        row = [
            sug_id,
            synced_at,
            spec["store_key"],
            spec["shop_name"],
            to_addr,
            spec["hit_list_row"],
            draft_id,
            subj,
            preview,
            "pending_review",
            DEFAULT_GMAIL_LABEL if not args.skip_label else "",
            PROTOCOL_VERSION,
            notes,
        ]
        created_rows.append(row)
        print(f"Created draft id={draft_id!r} → {to_addr} ({spec['shop_name']})")

    if args.dry_run:
        print("DRAFT_PDF_RESULT mode=dry_run (no Gmail/Sheets writes)")
        return

    if created_rows:
        sugg_ws.append_rows(created_rows, value_input_option="USER_ENTERED")
        print(f"Appended {len(created_rows)} row(s) to {SUGGESTIONS_WS!r}.")
    print(f"DRAFT_PDF_RESULT count={len(created_rows)} mode=live")


if __name__ == "__main__":
    main()
