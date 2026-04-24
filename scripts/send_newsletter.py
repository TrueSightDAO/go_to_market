#!/usr/bin/env python3
"""
Send (or draft) an Agroverse newsletter to a list of recipients, logging each
message to the "Agroverse News Letter Emails" tab on the dedicated newsletter
workbook (same ID as Edgar's Gdrive::NewsletterEmails). Subscriber pulls still
use the Main Ledger when using --recipients-from-sheet.

Two modes:
  --mode draft   Create Gmail drafts for human review (default)
  --mode send    Actually send the message via Gmail API

Two sources for recipient list:
  --to user@example.com [--to more@example.com ...]
  --recipients-from-sheet   Pull CONFIRMED rows from "Agroverse News Letter Subscribers"

Inputs:
  --subject TEXT
  --body-md FILE         Plain markdown/text body. A minimal HTML part is generated.
  --campaign NAME        Free-form campaign tag for the sheet log (e.g. "two_bahia_bars")
  --label LABEL          Gmail label applied to each draft/sent message (e.g. "Newsletter/2 Chocolate Bars")
  --track-opens          Embed a 1x1 tracking pixel pointing at Edgar. Off by default.
  --track-clicks         Rewrite outbound links through Edgar so each click is logged
                         back to the sheet row. Off by default.
  --edgar-base-url URL   Base for tracking endpoints (default https://edgar.truesight.me)

Sheet log columns (appended to Agroverse News Letter Emails):
  message_uuid, gmail_message_id, campaign, subject, recipient_email,
  sent_at_utc, status, opened, first_opened_at_utc, last_opened_at_utc, open_count,
  clicked, first_clicked_at_utc, last_clicked_at_utc, click_count, last_clicked_url

`message_uuid` is our own identifier embedded in the tracking pixel URL; `gmail_message_id`
is what Gmail assigns when the draft/message is created.

Usage examples:
  cd market_research
  # Copy review drafts to 2 reviewers (no tracking)
  python3 scripts/send_newsletter.py \
      --mode draft \
      --to kirsten@kikiscocoa.com --to fatoledojob@gmail.com \
      --subject "Review: Two Bahia farms, two very different chocolates" \
      --body-md newsletter_drafts/2026-04-20_two_bahia_bars.md \
      --campaign two_bahia_bars_review \
      --label "Newsletter/2 Chocolate Bars"

  # Full list live send with open + click tracking
  python3 scripts/send_newsletter.py \
      --mode send --recipients-from-sheet \
      --subject "Two Bahia farms, two very different chocolates" \
      --body-md newsletter_drafts/2026-04-20_two_bahia_bars.md \
      --campaign two_bahia_bars \
      --label "Newsletter/2 Chocolate Bars" \
      --track-opens --track-clicks
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build

from gmail_user_credentials import load_gmail_user_credentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

# Main Ledger: "Agroverse News Letter Subscribers" for --recipients-from-sheet.
MAIN_LEDGER_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
# Newsletter send log + Edgar open/click tracking (must match sentiment_importer
# Gdrive::NewsletterEmails::SPREADSHEET_ID).
NEWSLETTER_LOG_SPREADSHEET_ID = "1ed3q3SJ8ztGwfWit6Wxz_S72Cn5jKQFkNrHpeOVXP8s"
SUBSCRIBERS_WS = "Agroverse News Letter Subscribers"
EMAILS_WS = "Agroverse News Letter Emails"

EXPECTED_MAILBOX = "garyjob@agroverse.shop"
DEFAULT_EDGAR_BASE = "https://edgar.truesight.me"

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EMAIL_LOG_HEADERS = [
    "message_uuid",
    "gmail_message_id",
    "campaign",
    "subject",
    "recipient_email",
    "sent_at_utc",
    "status",
    "opened",
    "first_opened_at_utc",
    "last_opened_at_utc",
    "open_count",
    "clicked",
    "first_clicked_at_utc",
    "last_clicked_at_utc",
    "click_count",
    "last_clicked_url",
]


def normalize_email(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if "@" not in s:
        return None
    return s.lower()


def get_sheets_client():
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def ensure_emails_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        ws = sh.worksheet(EMAILS_WS)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=EMAILS_WS, rows=2000, cols=len(EMAIL_LOG_HEADERS))
    vals = ws.get_all_values()
    last_col_letter = _col_letter(len(EMAIL_LOG_HEADERS))
    if not vals:
        ws.append_row(EMAIL_LOG_HEADERS, value_input_option="USER_ENTERED")
        ws.format(f"A1:{last_col_letter}1", {"textFormat": {"bold": True}})
        ws.spreadsheet.batch_update({
            "requests": [{
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            }]
        })
    else:
        existing = [h.strip() for h in vals[0]]
        # If the header row is a prefix of the expected headers (older version
        # of the script), fill in just the missing trailing columns so new
        # rows have labelled destinations without stomping on anything.
        if (
            len(existing) < len(EMAIL_LOG_HEADERS)
            and existing == EMAIL_LOG_HEADERS[: len(existing)]
        ):
            start = _col_letter(len(existing) + 1)
            end = last_col_letter
            missing = EMAIL_LOG_HEADERS[len(existing):]
            ws.update(
                f"{start}1:{end}1", [missing], value_input_option="USER_ENTERED"
            )
            ws.format(f"{start}1:{end}1", {"textFormat": {"bold": True}})
        elif existing != EMAIL_LOG_HEADERS:
            # Don't auto-overwrite — surface mismatch so the operator notices.
            sys.stderr.write(
                f"WARNING: {EMAILS_WS!r} row 1 doesn't match expected headers.\n"
                f"  expected: {EMAIL_LOG_HEADERS}\n"
                f"  found:    {existing}\n"
                f"  Appending rows anyway; fix headers manually if needed.\n"
            )
    return ws


def _col_letter(idx_1based: int) -> str:
    """A,B,...,Z,AA,AB,... for spreadsheet column indexes."""
    s = ""
    n = idx_1based
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def load_recipients_from_sheet(sh: gspread.Spreadsheet) -> list[str]:
    ws = sh.worksheet(SUBSCRIBERS_WS)
    vals = ws.get_all_values()
    if len(vals) < 2:
        return []
    hdr = {h.strip(): i for i, h in enumerate(vals[0]) if h.strip()}
    email_i = hdr.get("Email")
    status_i = hdr.get("Status")
    if email_i is None:
        raise SystemExit(f"{SUBSCRIBERS_WS!r} missing required 'Email' column")
    out: list[str] = []
    seen = set()
    for row in vals[1:]:
        em = normalize_email(row[email_i] if email_i < len(row) else "")
        if not em or em in seen:
            continue
        if status_i is not None and status_i < len(row):
            status = (row[status_i] or "").strip().upper()
            if status and status != "CONFIRMED":
                continue
        seen.add(em)
        out.append(em)
    return out


def gmail_profile_email(service) -> str:
    prof = service.users().getProfile(userId="me").execute()
    return str(prof.get("emailAddress", "") or "").strip().lower()


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


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def markdown_to_plain(md: str) -> str:
    # Drop bold/italic markers; convert [text](url) to "text (url)".
    out = md
    out = _MD_LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", out)
    return out.strip() + "\n"


def markdown_to_html(md: str, link_transform=None) -> str:
    # Simple, explicit HTML rendering — avoids pulling in a markdown dep.
    # `link_transform(url) -> url` rewrites the href of each markdown link;
    # None leaves links untouched.
    lines = md.splitlines()
    html_lines: list[str] = []
    in_para: list[str] = []

    def rewrite(url: str) -> str:
        return link_transform(url) if link_transform else url

    def flush_para():
        if in_para:
            text = " ".join(in_para).strip()
            if text:
                html_lines.append(f"<p>{text}</p>")
            in_para.clear()

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            continue
        converted = _MD_LINK_RE.sub(
            lambda m: f'<a href="{rewrite(m.group(2))}">{m.group(1)}</a>', line
        )
        converted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", converted)
        converted = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", converted)
        in_para.append(converted)
    flush_para()
    return "\n".join(html_lines) + "\n"


def load_body_and_subject(body_md_path: Path) -> tuple[str | None, str]:
    """Read a markdown body file. If it starts with a `# ...` title then a `**Subject:** ...`
    line, the subject is returned from the file; otherwise subject is None."""
    text = body_md_path.read_text(encoding="utf-8")
    subject = None
    m = re.search(r"^\*\*Subject:\*\*\s*(.+)$", text, re.MULTILINE)
    if m:
        subject = m.group(1).strip()
    # Strip everything up to the first `---` divider (the file's preamble header).
    parts = text.split("\n---\n", 1)
    body = parts[1] if len(parts) == 2 else text
    return subject, body.strip() + "\n"


def build_tracking_pixel_html(message_uuid: str, recipient: str, edgar_base: str) -> str:
    # recipient is b64-urlsafe encoded to avoid querystring quoting issues.
    r = base64.urlsafe_b64encode(recipient.encode("utf-8")).decode("ascii").rstrip("=")
    url = f"{edgar_base.rstrip('/')}/newsletter/open.gif?mid={message_uuid}&r={r}"
    return (
        f'<img src="{url}" alt="" width="1" height="1" '
        f'style="display:block;border:0;width:1px;height:1px;" />'
    )


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def build_tracked_link(
    original_url: str, message_uuid: str, recipient: str, edgar_base: str
) -> str:
    # Only wrap http(s) links. mailto:, tel:, anchors, etc. stay untouched —
    # Edgar's click endpoint refuses to redirect to anything else anyway.
    if not original_url or not original_url.lower().startswith(("http://", "https://")):
        return original_url
    r = _b64url(recipient)
    to = _b64url(original_url)
    return (
        f"{edgar_base.rstrip('/')}/newsletter/click"
        f"?mid={message_uuid}&r={r}&to={to}"
    )


def build_mime_message(
    sender: str,
    recipient: str,
    subject: str,
    plain_body: str,
    html_body: str,
) -> dict:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(plain_body, charset="utf-8")
    msg.add_alternative(html_body, subtype="html")
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")}


def apply_label(service, message_id: str, label_id: str) -> None:
    service.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": [label_id]}
    ).execute()


def main() -> None:
    p = argparse.ArgumentParser(description="Newsletter sender / drafter.")
    p.add_argument("--mode", choices=["draft", "send"], default="draft")
    p.add_argument("--subject", help="Override subject (else parsed from --body-md frontmatter)")
    p.add_argument("--body-md", required=True, type=Path)
    p.add_argument("--campaign", required=True)
    p.add_argument("--label")
    p.add_argument("--to", action="append", default=[], help="Explicit recipient (repeatable)")
    p.add_argument(
        "--recipients-from-sheet",
        action="store_true",
        help=f"Load CONFIRMED subscribers from {SUBSCRIBERS_WS!r}",
    )
    p.add_argument("--track-opens", action="store_true")
    p.add_argument("--track-clicks", action="store_true")
    p.add_argument("--edgar-base-url", default=DEFAULT_EDGAR_BASE)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--expected-mailbox", default=EXPECTED_MAILBOX)
    p.add_argument(
        "--max-recipients",
        type=int,
        default=0,
        help="Safety cap; 0 = no cap. If the derived recipient list exceeds this, abort.",
    )
    args = p.parse_args()

    if not args.body_md.is_file():
        sys.stderr.write(f"--body-md file not found: {args.body_md}\n")
        sys.exit(1)

    parsed_subject, body_md = load_body_and_subject(args.body_md)
    subject = args.subject or parsed_subject
    if not subject:
        sys.stderr.write(
            "Subject not provided. Pass --subject or include `**Subject:** ...` in the body file.\n"
        )
        sys.exit(1)

    plain_body = markdown_to_plain(body_md)
    # If click tracking is on, link rewriting happens per-recipient so the
    # tracking URL can embed that recipient's message_uuid; skip the shared
    # base_html path in that case.
    base_html = None if args.track_clicks else markdown_to_html(body_md)

    gcreds = load_gmail_user_credentials(_GMAIL_TOKEN, GMAIL_SCOPES)
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
    me = gmail_profile_email(gsvc)
    if me != args.expected_mailbox.strip().lower():
        sys.stderr.write(f"Gmail profile is {me!r}, expected {args.expected_mailbox!r}\n")
        sys.exit(1)

    sa = get_sheets_client()
    ledger_sh = sa.open_by_key(MAIN_LEDGER_ID)
    log_sh = sa.open_by_key(NEWSLETTER_LOG_SPREADSHEET_ID)
    emails_ws = ensure_emails_worksheet(log_sh)

    recipients: list[str] = [normalize_email(r) for r in args.to if normalize_email(r)]
    if args.recipients_from_sheet:
        recipients = recipients + load_recipients_from_sheet(ledger_sh)
    # De-dupe preserving order
    seen = set()
    deduped: list[str] = []
    for r in recipients:
        if r and r not in seen:
            seen.add(r)
            deduped.append(r)
    recipients = deduped

    if not recipients:
        sys.stderr.write("No recipients. Pass --to or --recipients-from-sheet.\n")
        sys.exit(1)

    if args.max_recipients > 0 and len(recipients) > args.max_recipients:
        sys.stderr.write(
            f"Refusing: {len(recipients)} recipients exceeds --max-recipients {args.max_recipients}.\n"
        )
        sys.exit(2)

    label_id: str | None = None
    if args.label and not args.dry_run:
        label_id = ensure_user_label_id(gsvc, args.label)

    print(f"Mailbox:     {me}")
    print(f"Mode:        {args.mode}")
    print(f"Subject:     {subject}")
    print(f"Campaign:    {args.campaign}")
    print(f"Label:       {args.label or '(none)'}")
    print(f"Track opens: {args.track_opens}")
    print(f"Track clicks: {args.track_clicks}")
    print(f"Recipients:  {len(recipients)}")
    for r in recipients[:10]:
        print(f"  - {r}")
    if len(recipients) > 10:
        print(f"  ... and {len(recipients) - 10} more")

    if args.dry_run:
        print("\n--- plain body preview ---")
        print(plain_body)
        print("EMAIL_RESULT mode=dry_run count=0")
        return

    log_rows: list[list[str]] = []
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_done = 0

    for recipient in recipients:
        mid_uuid = str(uuid.uuid4())
        if args.track_clicks:
            html_body = markdown_to_html(
                body_md,
                link_transform=lambda u: build_tracked_link(
                    u, mid_uuid, recipient, args.edgar_base_url
                ),
            )
        else:
            html_body = base_html
        if args.track_opens:
            html_body = html_body + build_tracking_pixel_html(
                mid_uuid, recipient, args.edgar_base_url
            )
        raw = build_mime_message(me, recipient, subject, plain_body, html_body)

        if args.mode == "draft":
            resp = gsvc.users().drafts().create(userId="me", body={"message": raw}).execute()
            gmail_msg_id = ((resp.get("message") or {}).get("id")) or ""
            status = "draft"
            print(f"Draft created: {gmail_msg_id!r} -> {recipient}")
        else:
            resp = gsvc.users().messages().send(userId="me", body=raw).execute()
            gmail_msg_id = resp.get("id", "") or ""
            status = "sent"
            print(f"Sent: {gmail_msg_id!r} -> {recipient}")

        if label_id and gmail_msg_id:
            try:
                apply_label(gsvc, gmail_msg_id, label_id)
            except Exception as e:
                sys.stderr.write(f"Warning: label apply failed for {gmail_msg_id}: {e}\n")

        log_rows.append([
            mid_uuid,
            gmail_msg_id,
            args.campaign,
            subject,
            recipient,
            now_iso,
            status,
            "FALSE",
            "",
            "",
            "0",
            "FALSE",
            "",
            "",
            "0",
            "",
        ])
        n_done += 1

    if log_rows:
        emails_ws.append_rows(log_rows, value_input_option="USER_ENTERED")
        print(
            f"Appended {len(log_rows)} row(s) to {EMAILS_WS!r} "
            f"(spreadsheet {NEWSLETTER_LOG_SPREADSHEET_ID})"
        )

    print(
        f"EMAIL_RESULT mode={args.mode} count={n_done} campaign={args.campaign!r} "
        f"opens={'on' if args.track_opens else 'off'} "
        f"clicks={'on' if args.track_clicks else 'off'} label={args.label!r}"
    )


if __name__ == "__main__":
    main()
