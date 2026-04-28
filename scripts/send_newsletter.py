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
  --track-opens / --no-track-opens
                         Embed a visible Agroverse logo (tracking URL via Edgar).
                         **Default ON.** A forgotten flag must not silently
                         produce an untracked send — pass --no-track-opens
                         only for an explicit one-off untracked test.
  --track-clicks / --no-track-clicks
                         Rewrite outbound links through Edgar so each click is
                         logged back to the sheet row. **Default ON.**
  --exclude-buyers-of-substring TEXT
                         Repeatable. Drop any recipient whose email appears in
                         the 'Agroverse QR codes' tab as Owner Email on a row
                         whose Currency contains TEXT (case-insensitive
                         substring match) AND whose status matches
                         --exclude-buyers-status (default: SOLD). Avoid
                         pitching a SKU to someone who already bought it.
  --exclude-buyers-status STATUS
                         Repeatable. Statuses that count as 'already bought'
                         for the exclusion above (default: SOLD).
  --edgar-base-url URL   Base for tracking endpoints (default https://edgar.truesight.me)

Body markdown supports a tiny vocabulary:
  **bold**                          → <strong>bold</strong>
  *italic*                          → <em>italic</em>
  [text](https://url)               → <a href="…">text</a>
  ![alt](https://image-url)         → <img src="…" alt="…" width="280" …>
  Blank lines separate paragraphs.

Sheet log columns (appended to Agroverse News Letter Emails):
  message_uuid, gmail_message_id, campaign, subject, recipient_email,
  sent_at_utc, status, opened, first_opened_at_utc, last_opened_at_utc, open_count,
  clicked, first_clicked_at_utc, last_clicked_at_utc, click_count, last_clicked_url

`message_uuid` is our own identifier embedded in the tracking image URL; `gmail_message_id`
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

  # Full list live send (tracking on by default; skip recipients who
  # already hold either of the two bars in the campaign):
  python3 scripts/send_newsletter.py \
      --mode send --recipients-from-sheet \
      --subject "Two Bahia farms, two very different chocolates" \
      --body-md newsletter_drafts/2026-04-20_two_bahia_bars.md \
      --campaign two_bahia_bars \
      --label "Newsletter/2 Chocolate Bars" \
      --exclude-buyers-of-substring "Oscar Fazenda, Brazil 2024" \
      --exclude-buyers-of-substring "Santa Anna Fazenda, Brazil 2023"
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

# Top-level audience label applied to every newsletter send alongside the
# per-campaign label (e.g. "Newsletter/2 Chocolate Bars"). Lets the operator
# filter "all consumer-facing email I've sent, across every campaign, ever"
# with a single Gmail click. Parallel to the per-campaign label — both
# applied; nothing renamed; existing per-campaign saved searches keep working.
AUDIENCE_LABEL_DTC = "DTC"

# Main Ledger: "Agroverse QR codes" tab — used by --exclude-buyers-of-substring
# to skip recipients who already hold a QR for the SKU(s) the campaign is about
# (don't pitch a bar to someone who already bought it). Column layout:
#   col D (idx 3) = status (SOLD, MINTED, ON CONSIGNMENT, SAMPLE, …)
#   col I (idx 8) = Currency (the SKU/product string we substring-match)
#   col L (idx 11) = Owner Email (the buyer's address; the join key)
QR_CODES_WS = "Agroverse QR codes"
QR_STATUS_COL_INDEX = 3
QR_CURRENCY_COL_INDEX = 8
QR_OWNER_EMAIL_COL_INDEX = 11
DEFAULT_BUYER_STATUSES = ["SOLD"]

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


def load_qr_buyer_emails(
    sh: gspread.Spreadsheet,
    currency_substrings: list[str],
    statuses: list[str],
) -> tuple[set[str], int]:
    """Read `Agroverse QR codes` tab and return (lowercased Owner Emails of
    rows whose Currency contains any of the given substrings AND whose status
    is in the given statuses, count of matching QR rows).

    `Agroverse QR codes` is the canonical record of which contributor email
    holds which serialized SKU; we treat any matching row as evidence the
    address has already received the SKU and therefore should not be pitched
    that SKU again. Used by `--exclude-buyers-of-substring`.
    """
    if not currency_substrings:
        return set(), 0
    needles = [s.strip().lower() for s in currency_substrings if s.strip()]
    if not needles:
        return set(), 0
    valid_statuses = {s.strip().upper() for s in statuses if s.strip()}
    ws = sh.worksheet(QR_CODES_WS)
    rows = ws.get_all_values()
    emails: set[str] = set()
    matched = 0
    for r in rows[1:]:
        if len(r) <= QR_OWNER_EMAIL_COL_INDEX:
            continue
        currency = r[QR_CURRENCY_COL_INDEX].strip().lower()
        status = r[QR_STATUS_COL_INDEX].strip().upper()
        email = normalize_email(r[QR_OWNER_EMAIL_COL_INDEX])
        if not email or status not in valid_statuses:
            continue
        if any(n in currency for n in needles):
            matched += 1
            emails.add(email)
    return emails, matched


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
# Standard markdown image syntax `![alt](src)`. Must be substituted BEFORE the
# link regex sees it, otherwise `![alt](src)` becomes `<a href="src">alt</a>`
# (the link regex doesn't lookbehind for the leading `!`).
_MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _img_html_substitution(match: re.Match) -> str:
    # 280px default + 4px margin. Two iterations behind us: 480px (cluttered),
    # 320px (still felt heavy when stacked 3-deep with default <p> margins
    # of ~16px above + below each image). Now the image is tighter to the
    # surrounding paragraphs; the paragraph margins themselves provide all
    # the breathing room. max-width:100% scales down on narrow viewports;
    # margin:0 auto centers horizontally.
    alt = match.group(1).replace('"', '&quot;')
    src = match.group(2)
    return (
        f'<img src="{src}" alt="{alt}" width="280" '
        f'style="max-width:100%;height:auto;display:block;'
        f'border-radius:8px;margin:4px auto;" />'
    )


def markdown_to_plain(md: str) -> str:
    # Strip markdown image syntax first (so the link regex doesn't pick it up
    # as `[alt](src)`); then drop bold/italic markers; convert [text](url) to
    # "text (url)". Finally, gracefully degrade any raw HTML the body contains
    # — bodies sometimes embed table/div blocks (e.g. side-by-side comparison
    # cards) which the simple converter passes through to the HTML alternative
    # but which would render as gibberish in plain text. Rewrite <a href="X">Y</a>
    # to "Y (X)", then drop remaining tags and collapse whitespace.
    out = md
    out = _MD_IMG_RE.sub(
        lambda m: f"[image: {m.group(1)}]" if m.group(1) else "[image]", out
    )
    out = _MD_LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", out)
    out = re.sub(
        r'<a\s+[^>]*href\s*=\s*"([^"]+)"[^>]*>([^<]*)</a>',
        lambda m: f"{m.group(2).strip()} ({m.group(1)})",
        out,
        flags=re.IGNORECASE,
    )
    # Block-level tags become paragraph breaks; everything else just drops.
    out = re.sub(r"</(?:p|div|tr|li|h[1-6])>", "\n", out, flags=re.IGNORECASE)
    out = re.sub(r"<br\s*/?>", "\n", out, flags=re.IGNORECASE)
    out = re.sub(r"<[^>]+>", "", out)
    # Collapse runs of inline whitespace, but keep paragraph breaks intact.
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
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
        # Images first — `![alt](src)` → <img>. Without this step the link
        # regex below treats it as `[alt](src)` and emits an <a> instead.
        converted = _MD_IMG_RE.sub(_img_html_substitution, line)
        converted = _MD_LINK_RE.sub(
            lambda m: f'<a href="{rewrite(m.group(2))}">{m.group(1)}</a>', converted
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
        '<div style="margin-top:20px;padding-top:10px;border-top:1px solid #eee;">'
        '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
        'font-size:12px;color:#666;margin-bottom:6px;">Agroverse</div>'
        f'<img src="{url}" alt="Agroverse logo" width="160" '
        'style="display:block;border:0;width:160px;height:auto;" />'
        '</div>'
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
    p.add_argument(
        "--track-opens",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Embed the visible Agroverse-logo open pixel via Edgar. Default ON "
            "(every newsletter send is tracked unless explicitly opted out); "
            "pass --no-track-opens for a one-off untracked test send."
        ),
    )
    p.add_argument(
        "--track-clicks",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Rewrite outbound markdown links through Edgar so each click is "
            "logged. Default ON; pass --no-track-clicks to disable."
        ),
    )
    p.add_argument(
        "--exclude-buyers-of-substring",
        action="append",
        default=[],
        metavar="TEXT",
        help=(
            "Repeatable. Drop any recipient whose email appears in the "
            "'Agroverse QR codes' tab as Owner Email on a row whose Currency "
            "contains TEXT (case-insensitive substring match) AND whose status "
            "is in --exclude-buyers-status. Use this to avoid pitching a SKU "
            "to someone who already bought it. Example for the two-Bahia-bars "
            "campaign: --exclude-buyers-of-substring \"Oscar Fazenda, Brazil "
            "2024\" --exclude-buyers-of-substring \"Santa Anna Fazenda, Brazil "
            "2023\"."
        ),
    )
    p.add_argument(
        "--exclude-buyers-status",
        action="append",
        default=None,
        metavar="STATUS",
        help=(
            f"Repeatable. QR statuses that count as 'already bought' for "
            f"--exclude-buyers-of-substring. Default: "
            f"{','.join(DEFAULT_BUYER_STATUSES)}. Pass extra statuses (e.g. "
            f"SAMPLE) to broaden the exclusion."
        ),
    )
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

    # Subtract buyers of the SKU(s) this campaign is about. The 'Agroverse QR
    # codes' tab is the canonical record of which contributor email holds
    # which serialized SKU; if a recipient already shows up there for the
    # campaign's SKU, don't pitch them the SKU they already own.
    buyer_statuses = args.exclude_buyers_status or list(DEFAULT_BUYER_STATUSES)
    excluded_count = 0
    matched_qr_rows = 0
    if args.exclude_buyers_of_substring:
        buyer_emails, matched_qr_rows = load_qr_buyer_emails(
            ledger_sh, args.exclude_buyers_of_substring, buyer_statuses,
        )
        before = len(recipients)
        recipients = [r for r in recipients if r not in buyer_emails]
        excluded_count = before - len(recipients)

    if not recipients:
        sys.stderr.write("No recipients. Pass --to or --recipients-from-sheet.\n")
        sys.exit(1)

    if args.max_recipients > 0 and len(recipients) > args.max_recipients:
        sys.stderr.write(
            f"Refusing: {len(recipients)} recipients exceeds --max-recipients {args.max_recipients}.\n"
        )
        sys.exit(2)

    label_id: str | None = None
    audience_label_id: str | None = None
    if not args.dry_run:
        if args.label:
            label_id = ensure_user_label_id(gsvc, args.label)
        # Audience label is applied unconditionally (every send through this
        # script is by definition DTC — goes to the consumer subscriber
        # list). Skip in dry-run since we're not creating any messages.
        audience_label_id = ensure_user_label_id(gsvc, AUDIENCE_LABEL_DTC)

    print(f"Mailbox:     {me}")
    print(f"Mode:        {args.mode}")
    print(f"Subject:     {subject}")
    print(f"Campaign:    {args.campaign}")
    print(f"Label:       {args.label or '(none)'}")
    print(f"Track opens: {args.track_opens}")
    print(f"Track clicks: {args.track_clicks}")
    if args.exclude_buyers_of_substring:
        print(
            f"Excluded buyers: {excluded_count} recipient(s) dropped "
            f"({matched_qr_rows} matching QR row(s); statuses="
            f"{','.join(buyer_statuses)}; substrings="
            f"{args.exclude_buyers_of_substring})"
        )
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

        label_ids_to_apply = [lid for lid in (label_id, audience_label_id) if lid]
        if label_ids_to_apply and gmail_msg_id:
            try:
                gsvc.users().messages().modify(
                    userId="me", id=gmail_msg_id,
                    body={"addLabelIds": label_ids_to_apply},
                ).execute()
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
