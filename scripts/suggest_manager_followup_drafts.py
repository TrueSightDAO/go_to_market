#!/usr/bin/env python3
"""
Create Gmail **drafts** for Hit List rows with Status = Manager Follow-up and Email set,
append a row to **Email Agent Suggestions**, and apply label **Email Agent suggestions**.

**Cadence (anti-spam):**
- At most **one pending draft per recipient** (`to_email`): skips if **Email Agent Suggestions**
  has `status=pending_review` for that address.
- Next draft only after **Email Agent Follow Up** shows a prior **sent** to that address older than
  `--min-days-since-sent` (default **7** calendar days). Recipients with **no** log row are eligible
  immediately (treat as “no recorded send yet” for cadence).
- **Source of truth for “last sent”:** the latest `sent_at` in **Email Agent Follow Up** for that
  `to_email`. Run **`sync_email_agent_followup.py` before this script** (e.g. in the same CI job)
  so the tab reflects Gmail **sent** mail; cadence is **not** tied to how often this script runs—only
  to time since that logged send.

**Ordering:** Never-logged recipients first; then oldest `sent_at` first (most “due” for follow-up).

Intended mailbox: **garyjob@agroverse.shop** (verified against Gmail profile before any write).

Requires OAuth scope **gmail.modify**.

Usage:
  cd market_research
  python3 scripts/suggest_manager_followup_drafts.py --dry-run
  python3 scripts/suggest_manager_followup_drafts.py --max-drafts 1
  python3 scripts/suggest_manager_followup_drafts.py --min-days-since-sent 10
  python3 scripts/suggest_manager_followup_drafts.py --skip-label

Grok (optional):
  **API key resolution:** `GROK_API_KEY` is read from the process environment after loading
  `market_research/.env` if present. `python-dotenv` does **not** override variables already set
  (e.g. inject **GitHub Actions** `secrets.GROK_API_KEY` via `env:` on the job). Locally, use
  `.env` or `export GROK_API_KEY=...`.

  **Gmail OAuth:** use local `credentials/gmail/token.json`, or set **`GMAIL_TOKEN_JSON`** to the
  full JSON string (GitHub secret) — see `scripts/gmail_user_credentials.py` and
  `GMAIL_OAUTH_WORKFLOW.md`.

  python3 scripts/suggest_manager_followup_drafts.py --use-grok --max-drafts 1

`--use-grok` loads **full** Gmail messages (plain/HTML) between you and the recipient, caps size,
then asks Grok for JSON with keys `subject` and `body`. On API/format errors, falls back to the template.
`--dry-run` with `--use-grok` does **not** call Grok (prints template preview only).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

import gspread
import requests
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build

from gmail_user_credentials import load_gmail_user_credentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
SUGGESTIONS_WS = "Email Agent Suggestions"
LOG_WS = "Email Agent Follow Up"

DEFAULT_MIN_DAYS_SINCE_SENT = 7

EXPECTED_MAILBOX = "garyjob@agroverse.shop"
HIT_STATUS_TARGET = "Manager Follow-up"
PROTOCOL_VERSION = "PARTNER_OUTREACH_PROTOCOL v0.1"
DEFAULT_GMAIL_LABEL = "Email Agent suggestions"
BODY_PREVIEW_MAX = 500

GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
DEFAULT_GROK_MODEL = "grok-3"
DEFAULT_GROK_MAX_MESSAGES = 50
DEFAULT_GROK_MAX_CONTEXT_CHARS = 120_000
PER_MESSAGE_BODY_CAP = 14_000

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


def normalize_email(raw: str) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or "@" not in s:
        return None
    return s.lower()


def header_map(row: list[str]) -> dict[str, int]:
    return {h.strip(): i for i, h in enumerate(row) if h.strip()}


def cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip() if idx < len(row) else ""


def load_hit_list_targets(ws) -> list[dict]:
    values = ws.get_all_values()
    if not values:
        return []
    hdr = header_map(values[0])
    status_i = hdr.get("Status")
    email_i = hdr.get("Email")
    store_i = hdr.get("Store Key")
    shop_i = hdr.get("Shop Name")
    if status_i is None or email_i is None:
        raise SystemExit("Hit List row 1 must include 'Status' and 'Email'.")

    out: list[dict] = []
    for r, row in enumerate(values[1:], start=2):
        if cell(row, status_i) != HIT_STATUS_TARGET:
            continue
        em = normalize_email(cell(row, email_i))
        if not em:
            continue
        out.append(
            {
                "hit_list_row": r,
                "store_key": cell(row, store_i) if store_i is not None else "",
                "shop_name": cell(row, shop_i) if shop_i is not None else "",
                "to_email": em,
            }
        )
    return out


def pick_primary_store(targets: list[dict], partner_email: str) -> tuple[str, str, str]:
    matches = [t for t in targets if t["to_email"] == partner_email]
    if not matches:
        return "", "", ""
    first = min(matches, key=lambda x: x["hit_list_row"])
    rows_str = ",".join(str(m["hit_list_row"]) for m in sorted(matches, key=lambda x: x["hit_list_row"]))
    return first.get("store_key", ""), first.get("shop_name", ""), rows_str


def get_gmail_creds() -> UserCredentials:
    return load_gmail_user_credentials(_GMAIL_TOKEN, GMAIL_SCOPES)


def get_sheets_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing service account {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def gmail_profile_email(service) -> str:
    prof = service.users().getProfile(userId="me").execute()
    return str(prof.get("emailAddress", "") or "").strip().lower()


def ensure_suggestions_worksheet(sh: gspread.Spreadsheet):
    try:
        return sh.worksheet(SUGGESTIONS_WS)
    except gspread.WorksheetNotFound:
        sys.stderr.write(
            f"Missing worksheet {SUGGESTIONS_WS!r}. Run: python3 scripts/ensure_email_agent_suggestions_sheet.py\n"
        )
        sys.exit(1)


def open_follow_up_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet | None:
    try:
        return sh.worksheet(LOG_WS)
    except gspread.WorksheetNotFound:
        return None


def parse_sent_at_header(raw: str) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def last_sent_utctime_per_to_email(log_ws: gspread.Worksheet | None) -> dict[str, datetime]:
    """Latest logged outbound `sent_at` per recipient (lowercase email)."""
    if log_ws is None:
        return {}
    values = log_ws.get_all_values()
    if len(values) < 2:
        return {}
    hdr = header_map(values[0])
    to_i = hdr.get("to_email")
    sent_i = hdr.get("sent_at")
    if to_i is None or sent_i is None:
        return {}
    best: dict[str, datetime] = {}
    for row in values[1:]:
        to = normalize_email(cell(row, to_i))
        if not to:
            continue
        dt = parse_sent_at_header(cell(row, sent_i))
        if dt is None:
            continue
        prev = best.get(to)
        if prev is None or dt > prev:
            best[to] = dt
    return best


def pending_to_emails_from_suggestions(ws: gspread.Worksheet) -> set[str]:
    """Recipients that already have an in-flight draft (do not spam)."""
    values = ws.get_all_values()
    if len(values) < 2:
        return set()
    hdr = header_map(values[0])
    em_i = hdr.get("to_email")
    st_i = hdr.get("status")
    if em_i is None or st_i is None:
        return set()
    pending: set[str] = set()
    for row in values[1:]:
        if cell(row, st_i).lower() != "pending_review":
            continue
        em = normalize_email(cell(row, em_i))
        if em:
            pending.add(em)
    return pending


def days_since_utc(last: datetime, now: datetime) -> float:
    return (now - last.astimezone(timezone.utc)).total_seconds() / 86400.0


def list_message_ids(service, partner_addr: str, max_list: int = 40) -> list[str]:
    q = f"(from:{partner_addr} OR to:{partner_addr})"
    out: list[str] = []
    page_token = None
    while len(out) < max_list:
        n = min(40, max_list - len(out))
        if n <= 0:
            break
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=n, pageToken=page_token)
            .execute()
        )
        for m in resp.get("messages", []):
            mid = m.get("id")
            if mid and mid not in out:
                out.append(mid)
            if len(out) >= max_list:
                return out
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def latest_thread_snippets(service, partner_addr: str, max_snippets: int = 3) -> list[str]:
    ids = list_message_ids(service, partner_addr, max_list=60)
    metas: list[tuple[int, str]] = []
    for mid in ids:
        full = service.users().messages().get(userId="me", id=mid, format="metadata").execute()
        internal = full.get("internalDate")
        try:
            ms = int(internal) if internal is not None else 0
        except (TypeError, ValueError):
            ms = 0
        sn = (full.get("snippet") or "").replace("\n", " ").strip()
        if sn:
            metas.append((ms, sn))
    metas.sort(key=lambda x: x[0])
    tail = metas[-max_snippets:]
    return [t[1] for t in tail]


def _load_dotenv() -> None:
    """Load market_research/.env into os.environ only for keys not already set (CI-safe)."""
    try:
        from dotenv import load_dotenv

        p = _REPO / ".env"
        if p.is_file():
            load_dotenv(p, override=False)
    except ImportError:
        pass


def get_grok_api_key() -> str | None:
    """Return Grok API key: prefer existing env (GitHub Actions, `export`), else .env after load."""
    _load_dotenv()
    k = os.environ.get("GROK_API_KEY", "").strip()
    return k or None


def _decode_gmail_body_data(data: str) -> str:
    if not data:
        return ""
    pad = "=" * ((4 - len(data) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(data + pad)
        return raw.decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def _html_to_plain(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", "", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:PER_MESSAGE_BODY_CAP]


def extract_plain_body_from_payload(payload: dict) -> str:
    plain_chunks: list[str] = []
    html_chunks: list[str] = []

    def walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data:
            text = _decode_gmail_body_data(data)
            if not text:
                return
            if "text/plain" in mime:
                plain_chunks.append(text)
            elif "text/html" in mime:
                html_chunks.append(text)
        for p in part.get("parts") or []:
            walk(p)

    walk(payload)
    if plain_chunks:
        return "\n\n".join(plain_chunks).strip()[:PER_MESSAGE_BODY_CAP]
    if html_chunks:
        return _html_to_plain("\n\n".join(html_chunks))[:PER_MESSAGE_BODY_CAP]
    return ""


def format_full_message_block(
    my_email: str,
    full: dict,
) -> str:
    pl = full.get("payload") or {}
    headers_raw = pl.get("headers") or []
    headers = {h.get("name", "").lower(): h.get("value", "") for h in headers_raw}
    subj = headers.get("subject", "")
    frm = headers.get("from", "")
    to = headers.get("to", "")
    date = headers.get("date", "")
    body_text = extract_plain_body_from_payload(pl).strip()
    if not body_text:
        body_text = (full.get("snippet") or "").replace("\n", " ").strip()
    body_text = body_text[:PER_MESSAGE_BODY_CAP]
    frm_l = frm.lower()
    direction = "outbound" if my_email in frm_l else "inbound"
    return (
        f"---\n"
        f"Date: {date}\n"
        f"Direction: {direction}\n"
        f"Subject: {subj}\n"
        f"From: {frm}\n"
        f"To: {to}\n\n"
        f"{body_text}\n"
    )


def fetch_conversation_history(
    service,
    partner_email: str,
    my_email: str,
    *,
    max_messages: int,
    max_total_chars: int,
) -> str:
    ids = list_message_ids(service, partner_email, max_list=max_messages)
    enriched: list[tuple[int, str]] = []
    for mid in ids:
        full = service.users().messages().get(userId="me", id=mid, format="full").execute()
        try:
            ms = int(full.get("internalDate", 0) or 0)
        except (TypeError, ValueError):
            ms = 0
        block = format_full_message_block(my_email.lower(), full)
        enriched.append((ms, block))
    enriched.sort(key=lambda x: x[0])
    parts: list[str] = []
    total = 0
    for _, block in enriched:
        if total + len(block) > max_total_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts)


def grok_system_prompt() -> str:
    return (
        "You draft short, professional follow-up emails for Gary at Agroverse (ceremonial cacao, "
        "retail consignment conversations).\n"
        "Rules:\n"
        "- Output **only** valid JSON: an object with keys \"subject\" and \"body\" (plain text, use \\n for newlines).\n"
        "- No markdown fences, no preamble or explanation.\n"
        "- Be warm and specific; reference the conversation history when relevant.\n"
        "- Do not invent prices, terms, legal commitments, or promises Gary did not make.\n"
        "- If history is thin, keep the note concise and invite a clear next step (call, samples, paperwork).\n"
        "- Sign off as Gary.\n"
    )


def grok_generate_followup(
    *,
    api_key: str,
    model: str,
    shop_name: str,
    store_key: str,
    to_email: str,
    hit_list_row: str,
    conversation_history: str,
) -> tuple[str, str]:
    user = (
        f"Lead context (from our CRM):\n"
        f"- shop_name: {shop_name}\n"
        f"- store_key: {store_key}\n"
        f"- hit_list_row(s): {hit_list_row}\n"
        f"- recipient_email: {to_email}\n"
        f"- hit_list_status: {HIT_STATUS_TARGET}\n\n"
        f"Email thread history (chronological; may be truncated). Use only what is supported by this text:\n\n"
        f"{conversation_history or '(No prior messages in export — write a concise first-style follow-up after an in-person visit.)'}\n"
    )
    payload = {
        "model": model,
        "temperature": 0.55,
        "messages": [
            {"role": "system", "content": grok_system_prompt()},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    r = requests.post(GROK_ENDPOINT, headers=headers, json=payload, timeout=120)
    if not r.ok:
        raise RuntimeError(f"Grok HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Grok returned no choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    content = content.strip()
    if "```json" in content:
        a = content.find("```json") + 7
        b = content.find("```", a)
        content = content[a:b].strip()
    elif content.startswith("```"):
        a = content.find("```") + 3
        b = content.find("```", a)
        content = content[a:b].strip()
    parsed = json.loads(content)
    subj = str(parsed.get("subject", "")).strip()
    body = str(parsed.get("body", "")).strip()
    if not subj or not body:
        raise RuntimeError("Grok JSON missing subject or body")
    return subj, body


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


def build_message_raw(sender: str, to: str, subject: str, body: str) -> dict:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def draft_body_template(shop_name: str, snippets: list[str]) -> str:
    shop = shop_name or "there"
    lines = [
        f"Hi —",
        "",
        f"Following up after our visit and conversation about carrying Agroverse ceremonial cacao (consignment-friendly terms). "
        f"If it helps, I’m happy to confirm next steps, samples, or paperwork for {shop}.",
        "",
    ]
    if snippets:
        lines.append("(Recent thread context for you — edit freely:)")
        for s in snippets:
            lines.append(f"— {s[:400]}{'…' if len(s) > 400 else ''}")
        lines.append("")
    lines.extend(
        [
            "Thanks,",
            "Gary",
        ]
    )
    return "\n".join(lines)


def draft_subject(shop_name: str) -> str:
    s = (shop_name or "Following up").strip()
    return f"Following up — {s} & Agroverse cacao"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Gmail follow-up drafts for Manager Follow-up leads.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-drafts", type=int, default=1, help="Max new drafts this run (default 1).")
    parser.add_argument(
        "--min-days-since-sent",
        type=float,
        default=DEFAULT_MIN_DAYS_SINCE_SENT,
        help=f"Min days since last logged send in {LOG_WS!r} before drafting again (default {DEFAULT_MIN_DAYS_SINCE_SENT}).",
    )
    parser.add_argument("--skip-label", action="store_true", help="Do not create/apply Gmail label.")
    parser.add_argument(
        "--expected-mailbox",
        default=EXPECTED_MAILBOX,
        help=f"Abort if Gmail profile != this (default: {EXPECTED_MAILBOX}).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print skip reason per Manager-follow-up recipient (cadence / pending).",
    )
    parser.add_argument(
        "--use-grok",
        action="store_true",
        help="Generate subject/body via Grok from full Gmail thread (needs GROK_API_KEY). Ignored with --dry-run.",
    )
    parser.add_argument("--grok-model", default=DEFAULT_GROK_MODEL, help="xAI chat model name (default grok-3).")
    parser.add_argument(
        "--grok-max-messages",
        type=int,
        default=DEFAULT_GROK_MAX_MESSAGES,
        help="Max Gmail messages to pull (full bodies) per recipient.",
    )
    parser.add_argument(
        "--grok-max-context-chars",
        type=int,
        default=DEFAULT_GROK_MAX_CONTEXT_CHARS,
        help="Max total characters of thread text sent to Grok.",
    )
    args = parser.parse_args()

    if args.use_grok and not args.dry_run:
        if not get_grok_api_key():
            sys.stderr.write(
                "GROK_API_KEY is not set. Export it or add to market_research/.env (see HIT_LIST_CREDENTIALS.md).\n"
            )
            sys.exit(1)

    gcreds = get_gmail_creds()
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
    me = gmail_profile_email(gsvc)
    exp = args.expected_mailbox.strip().lower()
    if me != exp:
        sys.stderr.write(
            f"Gmail profile is {me!r}, expected {exp!r}. Sign in with the correct account or pass --expected-mailbox.\n"
        )
        sys.exit(1)

    sa = get_sheets_client()
    sh = sa.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)
    sugg_ws = ensure_suggestions_worksheet(sh)
    log_ws = open_follow_up_worksheet(sh)
    last_sent = last_sent_utctime_per_to_email(log_ws)
    pending_to = pending_to_emails_from_suggestions(sugg_ws)
    now = datetime.now(timezone.utc)

    targets = load_hit_list_targets(hit_ws)
    if not targets:
        print("No Hit List rows match Manager Follow-up with Email.")
        return

    by_email: dict[str, list[dict]] = {}
    for t in targets:
        by_email.setdefault(t["to_email"], []).append(t)

    candidates: list[str] = []
    skipped_pending = 0
    skipped_cadence = 0
    for em in sorted(by_email.keys()):
        if em in pending_to:
            skipped_pending += 1
            if args.verbose:
                print(f"  skip {em}: pending_review draft already in {SUGGESTIONS_WS!r}")
            continue
        prev = last_sent.get(em)
        if prev is not None:
            d = days_since_utc(prev, now)
            if d < args.min_days_since_sent:
                skipped_cadence += 1
                if args.verbose:
                    print(
                        f"  skip {em}: last logged send {d:.1f}d ago "
                        f"(need >= {args.min_days_since_sent}d; sent_at={prev.date().isoformat()})"
                    )
                continue
        candidates.append(em)

    def sort_key(email: str) -> tuple:
        dt = last_sent.get(email)
        if dt is None:
            return (0, email)
        return (1, dt.timestamp(), email)

    candidates.sort(key=sort_key)

    print(f"Mailbox: {me}")
    print(f"Cadence: min {args.min_days_since_sent} days since last row in {LOG_WS!r} for same to_email.")
    print(f"Manager-follow-up rows: {len(targets)} | distinct recipients: {len(by_email)}")
    print(f"Logged last-sent recipients: {len(last_sent)} | pending draft recipients: {len(pending_to)}")
    print(f"Skipped: {skipped_pending} (pending draft) | {skipped_cadence} (too soon since last send)")
    print(f"Eligible: {len(candidates)} | will create up to {args.max_drafts} draft(s)")

    if args.max_drafts <= 0 or not candidates:
        return

    label_id: str | None = None
    if not args.dry_run and not args.skip_label:
        label_id = ensure_user_label_id(gsvc, DEFAULT_GMAIL_LABEL)

    created_rows: list[list[str]] = []
    n_made = 0
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for to_addr in candidates:
        if n_made >= args.max_drafts:
            break
        sk, shop, rows_str = pick_primary_store(targets, to_addr)
        prev = last_sent.get(to_addr)
        prev_s = prev.strftime("%Y-%m-%d UTC") if prev else "none"

        snippets = latest_thread_snippets(gsvc, to_addr, max_snippets=3)
        source = "template"
        subj: str
        body: str

        if args.use_grok and not args.dry_run:
            grok_key = get_grok_api_key()
            hist = fetch_conversation_history(
                gsvc,
                to_addr,
                me.lower(),
                max_messages=args.grok_max_messages,
                max_total_chars=args.grok_max_context_chars,
            )
            try:
                subj, body = grok_generate_followup(
                    api_key=grok_key or "",
                    model=args.grok_model,
                    shop_name=shop,
                    store_key=sk,
                    to_email=to_addr,
                    hit_list_row=rows_str,
                    conversation_history=hist,
                )
                source = "grok"
            except Exception as e:
                sys.stderr.write(f"Grok failed for {to_addr}: {e}\n")
                subj = draft_subject(shop)
                body = draft_body_template(shop, snippets)
                source = "template_fallback"
        else:
            subj = draft_subject(shop)
            body = draft_body_template(shop, snippets)

        raw = build_message_raw(me, to_addr, subj, body)

        if args.dry_run:
            print(f"\n--- dry-run draft → {to_addr} ({shop}) ---")
            if args.use_grok:
                print("(Note: --dry-run skips Grok; preview below is the template fallback.)")
            print(f"Subject: {subj}")
            print(body[:800] + ("…" if len(body) > 800 else ""))
            n_made += 1
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
                sys.stderr.write(f"Warning: could not apply label to draft message {msg_id}: {e}\n")

        sug_id = str(uuid.uuid4())
        preview = body.replace("\n", " ")[:BODY_PREVIEW_MAX]
        notes = (
            f"Auto draft ({source}); cadence min_days={args.min_days_since_sent}; "
            f"last_logged_send={prev_s}; grok_model={args.grok_model if args.use_grok else 'n/a'}. "
            "Edit in Gmail before Send."
        )
        row = [
            sug_id,
            synced_at,
            sk,
            shop,
            to_addr,
            rows_str,
            draft_id,
            subj,
            preview,
            "pending_review",
            DEFAULT_GMAIL_LABEL if not args.skip_label else "",
            PROTOCOL_VERSION,
            notes,
        ]
        created_rows.append(row)
        n_made += 1
        print(f"Created draft {draft_id!r} → {to_addr} ({shop})")

    if args.dry_run:
        return

    if created_rows:
        sugg_ws.append_rows(created_rows, value_input_option="USER_ENTERED")
        print(f"Appended {len(created_rows)} row(s) to {SUGGESTIONS_WS!r}. Review Drafts in Gmail (label: {DEFAULT_GMAIL_LABEL!r}).")


if __name__ == "__main__":
    main()
