#!/usr/bin/env python3
"""
Create Gmail **drafts** for Hit List rows with Status = Manager Follow-up and Email set,
append a row to **Email Agent Drafts**, and apply label **Email Agent suggestions**.

**Cadence (anti-spam):**
- At most **one pending draft per recipient** (`to_email`): we block while **Email Agent Drafts**
  has `status=pending_review` **and** a matching **open Gmail draft** (by `gmail_draft_id`, or by scanning
  draft **To:** headers if the id cell is empty). If you **delete the draft in Gmail**, the next run
  discards that row (unless `--dry-run`) so a new draft can be created. **Discarding a draft bypasses**
  the min-days-since-sent gate until the next logged send: if reconcile marks a row discarded (or the
  sheet already records a ``[UTC] discarded:`` note **after** your latest **Email Agent Follow Up**
  ``sent_at`` for that address), you get another draft on the same or next run without waiting the
  full cadence (so you can iterate after changing prompts or templates).
- Otherwise, next draft only after **Email Agent Follow Up** shows a prior **sent** to that address older than
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
  python3 scripts/sync_email_agent_followup.py   # optional: refresh sent log before drafting
  python3 scripts/suggest_manager_followup_drafts.py --dry-run
  python3 scripts/suggest_manager_followup_drafts.py --use-grok
  python3 scripts/suggest_manager_followup_drafts.py --max-drafts 3   # optional cap
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
then asks Grok for JSON with keys `subject` and `body`. The same spreadsheet tab **`DApp Remarks`**
(rows matching **Shop Name** or **Store Key**) is included so drafts reflect field-visit / dapp notes.
**Hit List** **Notes** and city/state are passed when present. Draft rules (no in-person meeting invites;
address **owner/buyer** when context says staff routed you there) are in the model system prompt and
**`agentic_ai_context/PARTNER_OUTREACH_PROTOCOL.md`** §6. On API/format errors, falls back to the template.
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
from googleapiclient.errors import HttpError

from email_agent_tracking import plain_text_to_html_for_email_agent
from gmail_plain_body import extract_plain_body_from_payload
from gmail_user_credentials import load_gmail_user_credentials

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_SA_CREDS = _REPO / "google_credentials.json"
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
SUGGESTIONS_WS = "Email Agent Drafts"
LOG_WS = "Email Agent Follow Up"
DAPP_REMARKS_WS = "DApp Remarks"

DEFAULT_MIN_DAYS_SINCE_SENT = 7

EXPECTED_MAILBOX = "garyjob@agroverse.shop"
HIT_STATUS_TARGET = "Manager Follow-up"
PROTOCOL_VERSION = "PARTNER_OUTREACH_PROTOCOL v0.1"
DEFAULT_GMAIL_LABEL = "AI/Follow-up"
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
    "Open",
    "Click through",
    "gmail_message_id",
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
    notes_i = hdr.get("Notes")
    city_i = hdr.get("City")
    state_i = hdr.get("State")
    if status_i is None or email_i is None:
        raise SystemExit("Hit List row 1 must include 'Status' and 'Email'.")

    out: list[dict] = []
    for r, row in enumerate(values[1:], start=2):
        if cell(row, status_i) != HIT_STATUS_TARGET:
            continue
        em = normalize_email(cell(row, email_i))
        if not em:
            continue
        city = cell(row, city_i) if city_i is not None else ""
        state = cell(row, state_i) if state_i is not None else ""
        locale = ", ".join(x for x in [city, state] if x)
        out.append(
            {
                "hit_list_row": r,
                "store_key": cell(row, store_i) if store_i is not None else "",
                "shop_name": cell(row, shop_i) if shop_i is not None else "",
                "to_email": em,
                "notes": cell(row, notes_i) if notes_i is not None else "",
                "city_state": locale,
            }
        )
    return out


def normalize_shop_match_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def shop_names_align(shop_a: str, shop_b: str) -> bool:
    """True if normalized names are equal or one is a plausible substring of the other (DApp vs Hit List spelling)."""
    a = normalize_shop_match_name(shop_a)
    b = normalize_shop_match_name(shop_b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 8:
        return False
    return short in long


def pick_primary_store(targets: list[dict], partner_email: str) -> tuple[str, str, str, str, str]:
    """Returns (store_key, shop_name, hit_list_rows_csv, hit_list_notes, city_state)."""
    matches = [t for t in targets if t["to_email"] == partner_email]
    if not matches:
        return "", "", "", "", ""
    first = min(matches, key=lambda x: x["hit_list_row"])
    rows_str = ",".join(str(m["hit_list_row"]) for m in sorted(matches, key=lambda x: x["hit_list_row"]))
    return (
        first.get("store_key", ""),
        first.get("shop_name", ""),
        rows_str,
        (first.get("notes") or "").strip(),
        (first.get("city_state") or "").strip(),
    )


def open_dapp_remarks_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet | None:
    try:
        return sh.worksheet(DAPP_REMARKS_WS)
    except gspread.WorksheetNotFound:
        return None


def format_dapp_remarks_for_grok(
    remarks_ws: gspread.Worksheet | None,
    shop_name: str,
    store_key: str,
    *,
    max_chars: int = 12_000,
) -> str:
    """Collect DApp visit / status remarks for this shop (same spreadsheet tab as physical_stores scripts)."""
    if remarks_ws is None:
        return ""
    values = remarks_ws.get_all_values()
    if len(values) < 2:
        return ""
    hdr = header_map(values[0])
    shop_i = hdr.get("Shop Name")
    remarks_i = hdr.get("Remarks")
    if remarks_i is None:
        return ""
    store_i = hdr.get("Store Key")
    status_i = hdr.get("Status")
    sub_i = hdr.get("Submitted By")
    ts_i = hdr.get("Timestamp") or hdr.get("Submitted At") or hdr.get("Date") or hdr.get("Time")

    want_shop = normalize_shop_match_name(shop_name)
    want_key = (store_key or "").strip().lower()

    blocks: list[str] = []
    for row in values[1:]:
        raw_shop = cell(row, shop_i) if shop_i is not None else ""
        r_shop = normalize_shop_match_name(raw_shop)
        r_key = cell(row, store_i).strip().lower() if store_i is not None else ""
        rem = cell(row, remarks_i).strip()
        if not rem:
            continue
        matched = False
        if want_shop and r_shop == want_shop:
            matched = True
        if not matched and want_shop and r_shop and shop_names_align(shop_name, raw_shop):
            matched = True
        if want_key and r_key == want_key:
            matched = True
        if not matched:
            continue
        meta: list[str] = []
        if status_i is not None:
            st = cell(row, status_i).strip()
            if st:
                meta.append(f"status={st}")
        if ts_i is not None:
            ts = cell(row, ts_i).strip()
            if ts:
                meta.append(f"recorded={ts}")
        if sub_i is not None:
            sb = cell(row, sub_i).strip()
            if sb:
                meta.append(f"submitted_by={sb}")
        head = f"[{' | '.join(meta)}]\n" if meta else ""
        blocks.append(f"{head}{rem}".strip())

    if not blocks:
        return ""

    out = "\n\n---\n\n".join(blocks)
    if len(out) > max_chars:
        out = out[: max_chars - 1] + "…"
    return out


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


def is_missing_draft_http_error(e: HttpError) -> bool:
    """True when Gmail API indicates the draft no longer exists (deleted from UI, etc.)."""
    code = getattr(getattr(e, "resp", None), "status", None)
    if code in (404, 410):
        return True
    if code == 400 and getattr(e, "content", None):
        try:
            payload = json.loads(e.content.decode("utf-8"))
        except (ValueError, UnicodeError, AttributeError):
            return False
        err = payload.get("error") or {}
        for sub in err.get("errors") or []:
            reason = (sub.get("reason") or "").lower()
            if reason in ("notfound", "not_found", "invalid", "failedprecondition"):
                return True
        msg = str(err.get("message") or "").lower()
        if any(x in msg for x in ("not found", "invalid id", "invalid draft", "unknown draft")):
            return True
    return False


def _message_header_map(msg: dict) -> dict[str, str]:
    pl = msg.get("payload") or {}
    out: dict[str, str] = {}
    for h in pl.get("headers") or []:
        n = (h.get("name") or "").strip().lower()
        if n:
            out[n] = (h.get("value") or "").strip()
    return out


def _to_header_contains_email(to_header: str, want_lower: str) -> bool:
    if not want_lower or not to_header:
        return False
    t = to_header.lower()
    if want_lower in t:
        return True
    for raw in re.split(r"[,;]", to_header):
        part = raw.strip().lower()
        if "<" in part and ">" in part:
            part = part.split("<", 1)[1].split(">", 1)[0].strip()
        if part == want_lower:
            return True
    return False


def _draft_metadata_matches_recipient(hdrs: dict[str, str], want_lower: str) -> bool:
    if not want_lower:
        return False
    for key in ("to", "cc", "bcc"):
        if _to_header_contains_email(hdrs.get(key, ""), want_lower):
            return True
    return False


def gmail_has_open_draft_to_recipient(service, to_email: str, *, max_scan: int = 100) -> bool:
    """True if any Gmail draft To/Cc/Bcc includes this address (metadata scan, capped)."""
    want = normalize_email(to_email)
    if not want:
        return False
    scanned = 0
    page_token: str | None = None
    while scanned < max_scan:
        req = service.users().drafts().list(
            userId="me",
            maxResults=min(25, max_scan - scanned),
            pageToken=page_token,
        )
        resp = req.execute()
        for d in resp.get("drafts") or []:
            did = d.get("id")
            if not did:
                continue
            if scanned >= max_scan:
                return False
            try:
                dr = service.users().drafts().get(userId="me", id=did, format="metadata").execute()
            except HttpError as e:
                if is_missing_draft_http_error(e):
                    scanned += 1
                    continue
                raise
            msg = dr.get("message") or {}
            if _draft_resource_is_trashed(dr):
                scanned += 1
                continue
            hdrs = _message_header_map(msg)
            if _draft_metadata_matches_recipient(hdrs, want):
                return True
            scanned += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return False


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


def followup_sheet_logged_bodies_for_prompt(
    log_ws: gspread.Worksheet | None,
    partner_email: str,
    *,
    max_blocks: int = 2,
    max_chars_per_block: int = 12_000,
) -> str:
    """Non-empty `body_plain` from Email Agent Follow Up (synced outbound), newest last."""
    if log_ws is None:
        return ""
    want = normalize_email(partner_email)
    if not want:
        return ""
    values = log_ws.get_all_values()
    if len(values) < 2:
        return ""
    hdr = header_map(values[0])
    to_i = hdr.get("to_email")
    sent_i = hdr.get("sent_at")
    body_i = hdr.get("body_plain")
    subj_i = hdr.get("subject")
    if to_i is None or sent_i is None:
        return ""

    rows: list[tuple[datetime, str]] = []
    for row in values[1:]:
        to = normalize_email(cell(row, to_i))
        if to != want:
            continue
        dt = parse_sent_at_header(cell(row, sent_i))
        if dt is None:
            continue
        parts: list[str] = []
        if subj_i is not None:
            sj = cell(row, subj_i)
            if sj:
                parts.append(f"Subject: {sj}")
        if body_i is not None:
            bp = (cell(row, body_i) or "").strip()
            if bp:
                chunk = bp[:max_chars_per_block]
                if len(bp) > max_chars_per_block:
                    chunk += "…"
                parts.append(chunk)
        if not parts:
            continue
        rows.append((dt, "\n".join(parts)))
    rows.sort(key=lambda x: x[0])
    tail = rows[-max_blocks:]
    if not tail:
        return ""
    blocks = [f"[Logged send {dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC]\n{text}" for dt, text in tail]
    return "\n\n---\n\n".join(blocks)


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


# Reconcile appends notes like ``[2026-04-23T12:00:00Z] discarded: ...`` — used to bypass cadence
# when the user removed the Gmail draft (iterate before min-days since last *sent*).
_DISCARD_NOTE_TS_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]\s*discarded:",
    re.IGNORECASE,
)


def parse_latest_discard_utc_from_notes(notes: str) -> datetime | None:
    """Latest UTC timestamp from any ``[...Z] discarded:`` segment in *notes*."""
    best: datetime | None = None
    for m in _DISCARD_NOTE_TS_RE.finditer(notes or ""):
        ts = m.group(1)
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if best is None or dt > best:
            best = dt
    return best


def latest_discarded_utc_per_to_email(ws: gspread.Worksheet) -> dict[str, datetime]:
    """Per ``to_email``, max parsed discard time from ``discarded`` rows' ``notes``."""
    values = ws.get_all_values()
    if len(values) < 2:
        return {}
    hdr = header_map(values[0])
    em_i = hdr.get("to_email")
    st_i = hdr.get("status")
    notes_i = hdr.get("notes")
    if em_i is None or st_i is None:
        return {}
    best: dict[str, datetime] = {}
    for row in values[1:]:
        if cell(row, st_i).lower() != "discarded":
            continue
        em = normalize_email(cell(row, em_i))
        if not em:
            continue
        notes = cell(row, notes_i) if notes_i is not None else ""
        dt = parse_latest_discard_utc_from_notes(notes)
        if dt is None:
            continue
        prev = best.get(em)
        if prev is None or dt > prev:
            best[em] = dt
    return best


def cadence_bypass_after_discarded_draft(
    em: str,
    *,
    last_sent_dt: datetime | None,
    freshly_discarded_emails: set[str],
    latest_discard_utc_per_email: dict[str, datetime],
) -> bool:
    """True if min-days-since-sent should not block *em* (user discarded the pending Gmail draft)."""
    if em in freshly_discarded_emails:
        return True
    disc = latest_discard_utc_per_email.get(em)
    if disc is None or last_sent_dt is None:
        return False
    ls = last_sent_dt.astimezone(timezone.utc)
    return disc > ls


def _draft_resource_is_trashed(draft_resource: dict) -> bool:
    """True if the draft's message is in Gmail Trash (API still returns 200; we treat like deleted)."""
    msg = draft_resource.get("message") or {}
    for lid in msg.get("labelIds") or []:
        if str(lid).upper() == "TRASH":
            return True
    return False


def _scan_pending_review_rows(
    service,
    values: list[list[str]],
    *,
    verbose: bool,
    dry_run: bool,
) -> tuple[set[str], list[tuple[int, str, str]]]:
    """Return (blocking_emails, stale_rows) where each stale row is (sheet_row, email, draft_id_or_empty)."""
    if len(values) < 2:
        return set(), []
    hdr = header_map(values[0])
    em_i = hdr.get("to_email")
    st_i = hdr.get("status")
    draft_i = hdr.get("gmail_draft_id")
    if em_i is None or st_i is None:
        return set(), []

    pending_emails: set[str] = set()
    stale: list[tuple[int, str, str]] = []

    for sheet_row, row in enumerate(values[1:], start=2):
        if cell(row, st_i).lower() != "pending_review":
            continue
        em = normalize_email(cell(row, em_i))
        if not em:
            continue
        draft_id = (cell(row, draft_i) if draft_i is not None else "").strip()
        if not draft_id:
            if gmail_has_open_draft_to_recipient(service, em):
                pending_emails.add(em)
                if verbose:
                    print(
                        f"  reconcile: {em} row {sheet_row}: pending_review, no gmail_draft_id — "
                        f"open Gmail draft to this address exists; still blocking"
                    )
            else:
                stale.append((sheet_row, em, ""))
                if verbose:
                    print(
                        f"  reconcile: row {sheet_row} {em}: pending_review, no gmail_draft_id, "
                        f"no draft To/Cc/Bcc this address — {'would set discarded' if dry_run else 'setting discarded'}"
                    )
            continue
        try:
            dr = service.users().drafts().get(userId="me", id=draft_id, format="metadata").execute()
            if _draft_resource_is_trashed(dr):
                stale.append((sheet_row, em, draft_id))
                if verbose:
                    print(
                        f"  reconcile: row {sheet_row} {em}: Gmail draft {draft_id!r} is in Trash — "
                        f"{'would set discarded' if dry_run else 'setting discarded'}"
                    )
                continue
            pending_emails.add(em)
        except HttpError as e:
            if is_missing_draft_http_error(e):
                code = getattr(getattr(e, "resp", None), "status", None)
                stale.append((sheet_row, em, draft_id))
                if verbose:
                    print(
                        f"  reconcile: row {sheet_row} {em}: Gmail draft {draft_id!r} missing (HTTP {code}) — "
                        f"{'would set discarded' if dry_run else 'setting discarded'}"
                    )
            else:
                raise

    return pending_emails, stale


def pending_review_emails_after_gmail_reconcile(
    service,
    ws: gspread.Worksheet,
    *,
    dry_run: bool,
    verbose: bool,
) -> tuple[set[str], int, set[str]]:
    """Recipients still blocked by a real pending draft.

    Discards ``pending_review`` rows whose Gmail draft is gone, then **re-fetches** the sheet and
    re-scans so the same run does not keep blocking addresses that were only waiting on a stale row
    (e.g. iChakras after deleting the draft).

    Returns ``(pending_emails, n_rows_marked_discarded, freshly_discarded_emails)``. The third set
    is every ``to_email`` from a stale ``pending_review`` row in this invocation (including dry-run),
    so callers can bypass min-days cadence for those addresses in the same run.
    """
    values = ws.get_all_values()
    if len(values) < 2:
        return set(), 0, set()
    hdr = header_map(values[0])
    st_i = hdr.get("status")
    notes_i = hdr.get("notes")
    if st_i is None or hdr.get("to_email") is None:
        return set(), 0, set()

    status_col = st_i + 1
    notes_col = (notes_i + 1) if notes_i is not None else None

    total_updated = 0
    pending_emails: set[str] = set()
    stale: list[tuple[int, str, str]] = []
    freshly_discarded_emails: set[str] = set()

    for _ in range(4):
        pending_emails, stale = _scan_pending_review_rows(
            service, values, verbose=verbose, dry_run=dry_run
        )
        if not stale:
            return pending_emails, total_updated, freshly_discarded_emails
        for _, em_stale, _ in stale:
            ne = normalize_email(em_stale)
            if ne:
                freshly_discarded_emails.add(ne)
        if dry_run:
            return pending_emails, 0, freshly_discarded_emails

        now_tag = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for sheet_row, _em, draft_id in stale:
            ws.update_cell(sheet_row, status_col, "discarded")
            if notes_col is not None and notes_i is not None:
                prev = cell(values[sheet_row - 1], notes_i)
                if draft_id:
                    short_id = draft_id[:20] + "…" if len(draft_id) > 20 else draft_id
                    suffix = f"[{now_tag}] discarded: Gmail draft missing (was id {short_id})"
                else:
                    suffix = (
                        f"[{now_tag}] discarded: no open Gmail draft to this address "
                        f"(pending_review cleared — e.g. draft deleted; id was blank)"
                    )
                new_note = f"{prev}; {suffix}" if prev else suffix
                if len(new_note) > 2000:
                    new_note = new_note[:1997] + "…"
                ws.update_cell(sheet_row, notes_col, new_note)
            total_updated += 1

        values = ws.get_all_values()

    return pending_emails, total_updated, freshly_discarded_emails


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


def latest_thread_excerpts(service, partner_addr: str, max_messages: int = 3) -> list[str]:
    """Last N messages in the thread (full plain body when available), newest last — for templates."""
    ids = list_message_ids(service, partner_addr, max_list=60)
    metas: list[tuple[int, str]] = []
    for mid in ids:
        full = service.users().messages().get(userId="me", id=mid, format="full").execute()
        internal = full.get("internalDate")
        try:
            ms = int(internal) if internal is not None else 0
        except (TypeError, ValueError):
            ms = 0
        pl = full.get("payload") or {}
        body = extract_plain_body_from_payload(pl).strip()
        if not body:
            body = (full.get("snippet") or "").replace("\n", " ").strip()
        if body:
            metas.append((ms, body))
    metas.sort(key=lambda x: x[0])
    tail = metas[-max_messages:]
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
    body_text = extract_plain_body_from_payload(
        pl,
        per_part_cap=PER_MESSAGE_BODY_CAP,
        max_total=PER_MESSAGE_BODY_CAP,
    ).strip()
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
        "You draft polished, send-ready follow-up emails for Gary at Agroverse — ceremonial cacao, "
        "retail / consignment (friendly terms). The merchant should need only light editing.\n"
        "Rules:\n"
        '- Output **only** valid JSON: one object with keys "subject" and "body" (plain text, use \\n for newlines).\n'
        "- No markdown fences, no preamble, no placeholders like [Name] — use real details from context or a natural generic greeting (e.g. Hi —, or Hello —).\n"
        "- **In-person meetings / another store visit to meet:** Do **not** propose or invite an in-person meeting, a return visit to the shop to connect, "
        "\"stopping by\" again, or \"circling back\" in person. Gary often passes through and is **not** reliably available to come back for a sit-down. "
        "Prefer: **reply by email**, a **scheduled phone or video call**, or **delivery / logistics / paperwork** next steps — never frame the ask as meeting them on-site.\n"
        "- **Who to address:** If Hit List notes, DApp remarks, or the **email thread** show that **staff** provided the **owner**, **buyer**, **decision-maker**, "
        "or their **name** or **this email** as the right person to speak with, the message must speak **to that person** (salutation + body). "
        "Do **not** write as if the front-desk or staff contact is the primary reader when context clearly routes follow-up to **owner/buyer** (you may still "
        "thank staff briefly if natural).\n"
        "- **Body** structure: brief warm opening → 1–2 concrete sentences tying to **visit/DApp remarks** and/or **email thread** → "
        "one clear **call to action** (email reply with timing, **phone or video** call, samples, or paperwork — **never** in-person meetup) → "
        "short **signature block** on separate lines:\n"
        "  Gary\n"
        "  Agroverse | ceremonial cacao for retail\n"
        "  garyjob@agroverse.shop\n"
        "- Sound human and specific; weave in **DApp visit remarks** and thread facts when provided. Do not invent numbers, legal terms, or deals not in the context.\n"
        "- Subject: specific and scannable (shop name + short hook), not spammy. Under ~90 characters.\n"
        "- Length: about 120–220 words in body unless context demands shorter.\n"
    )


def grok_generate_followup(
    *,
    api_key: str,
    model: str,
    shop_name: str,
    store_key: str,
    to_email: str,
    hit_list_row: str,
    city_state: str,
    hit_list_notes: str,
    dapp_remarks_log: str,
    conversation_history: str,
) -> tuple[str, str]:
    crm_notes = (hit_list_notes or "").strip()
    locality = (city_state or "").strip()
    dapp_block = (dapp_remarks_log or "").strip()
    user = (
        f"Lead context (Hit List CRM):\n"
        f"- shop_name: {shop_name}\n"
        f"- store_key: {store_key}\n"
        f"- city/state (if known): {locality or '(not provided)'}\n"
        f"- hit_list_row(s): {hit_list_row}\n"
        f"- recipient_email: {to_email}\n"
        f"- hit_list_status: {HIT_STATUS_TARGET}\n"
    )
    if crm_notes:
        user += f"- internal_hit_list_notes (use for specificity; do not quote as if the merchant wrote this): {crm_notes}\n"
    user += (
        "- If notes or thread mention owner, buyer, decision-maker, or \"speak with X\", treat **X** as the addressee "
        "and **recipient_email** as the correct channel when it matches.\n"
    )
    user += "\n"
    if dapp_block:
        user += (
            "DApp field / visit remarks log (same shop or store key — chronological blocks separated by ---). "
            "Prioritize concrete details here for a complete, send-ready email:\n\n"
            f"{dapp_block}\n\n"
        )
    user += (
        "Email thread history with this address (chronological; may be truncated). "
        "Use only what is supported by this text:\n\n"
        f"{conversation_history or '(No prior messages in export — lean on DApp remarks and Hit List notes if present.)'}\n"
    )
    payload = {
        "model": model,
        "temperature": 0.42,
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


def build_message_raw(
    sender: str,
    to: str,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
    attachment_path: Path | None = None,
    attachment_filename: str | None = None,
) -> dict:
    """Build Gmail ``raw`` RFC822. Optional **html_body** for ``multipart/alternative``; optional PDF."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject

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


TEMPLATE_THREAD_EXCERPT_CHARS = 2000


def draft_body_template(shop_name: str, snippets: list[str]) -> str:
    shop = shop_name or "there"
    lines = [
        f"Hi —",
        "",
        f"Following up on Agroverse ceremonial cacao and next steps for {shop} (consignment-friendly terms). "
        f"I’m happy to answer questions by email or on a quick call — and to line up samples or simple paperwork — "
        f"without needing another in-person meeting on my side.",
        "",
    ]
    if snippets:
        lines.append("(Recent thread context for you — edit freely:)")
        cap = TEMPLATE_THREAD_EXCERPT_CHARS
        for s in snippets:
            lines.append(f"— {s[:cap]}{'…' if len(s) > cap else ''}")
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
    parser.add_argument(
        "--max-drafts",
        type=int,
        default=0,
        help="Cap new drafts per run; **0 = no limit** (draft every eligible recipient). Use a positive number to throttle.",
    )
    parser.add_argument(
        "--min-days-since-sent",
        type=float,
        default=DEFAULT_MIN_DAYS_SINCE_SENT,
        help=f"Min days since last logged send in {LOG_WS!r} before drafting again (default {DEFAULT_MIN_DAYS_SINCE_SENT}).",
    )
    parser.add_argument("--skip-label", action="store_true", help="Do not create/apply Gmail label.")
    parser.add_argument(
        "--track-opens",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Add an HTML alternative with a 1×1 open pixel (tid=suggestion_id). "
            "Default ON; pass --no-track-opens to disable for a one-off batch. "
            "Set EMAIL_AGENT_TRACKING_BASE_URL (default https://edgar.truesight.me); "
            "Edgar must implement GET /email_agent/open.gif — see email_agent_tracking.py."
        ),
    )
    parser.add_argument(
        "--track-clicks",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Rewrite http(s) URLs in the HTML alternative through Edgar "
            "GET /email_agent/click?tid=&r=&to= (recipient + destination are base64url); "
            "implies a multipart HTML part. Default ON; pass --no-track-clicks to disable. "
            "Combine with --track-opens as needed."
        ),
    )
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

    if args.max_drafts < 0:
        sys.stderr.write("--max-drafts must be >= 0 (use 0 for no limit).\n")
        sys.exit(2)

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
    log_tab_present = log_ws is not None
    if not log_tab_present:
        print(
            f"WARNING: worksheet {LOG_WS!r} not found — no sent history in sheet; "
            "every recipient is treated as having no logged send (cadence still enforces pending_review only)."
        )
    remarks_ws = open_dapp_remarks_worksheet(sh)
    if remarks_ws is None and args.use_grok:
        print(
            f"Note: worksheet {DAPP_REMARKS_WS!r} not found — Grok context will omit DApp visit remarks."
        )
    last_sent = last_sent_utctime_per_to_email(log_ws)
    pending_to, n_reconciled, freshly_discarded = pending_review_emails_after_gmail_reconcile(
        gsvc, sugg_ws, dry_run=args.dry_run, verbose=args.verbose
    )
    if n_reconciled:
        print(
            f"Reconciled {n_reconciled} row(s) in {SUGGESTIONS_WS!r}: "
            "pending_review → discarded (Gmail draft was deleted or missing)."
        )
    latest_discard_utc = latest_discarded_utc_per_to_email(sugg_ws)
    now = datetime.now(timezone.utc)

    targets = load_hit_list_targets(hit_ws)
    if not targets:
        print("No Hit List rows match Manager Follow-up with Email.")
        print(
            "EMAIL_AGENT_DRAFT_RESULT count=0 mode="
            + ("dry_run" if args.dry_run else "live")
            + " reason=no_manager_followup_targets"
            + f" reconciled_stale_rows={n_reconciled}"
        )
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
                print(
                    f"  skip {em}: active pending_review in {SUGGESTIONS_WS!r} "
                    f"(Gmail draft still exists for this address)"
                )
            continue
        prev = last_sent.get(em)
        if prev is not None:
            d = days_since_utc(prev, now)
            if d < args.min_days_since_sent:
                if not cadence_bypass_after_discarded_draft(
                    em,
                    last_sent_dt=prev,
                    freshly_discarded_emails=freshly_discarded,
                    latest_discard_utc_per_email=latest_discard_utc,
                ):
                    skipped_cadence += 1
                    if args.verbose:
                        print(
                            f"  skip {em}: last logged send {d:.1f}d ago "
                            f"(need >= {args.min_days_since_sent}d; sent_at={prev.date().isoformat()})"
                        )
                    continue
                if args.verbose:
                    print(
                        f"  allow {em}: cadence bypass (discarded draft after last logged send "
                        f"at {prev.date().isoformat()})"
                    )
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
    cap_note = "no cap (all eligible)" if args.max_drafts == 0 else f"cap={args.max_drafts}"
    print(f"Eligible: {len(candidates)} | will create drafts ({cap_note})")

    if not candidates:
        print(
            "EMAIL_AGENT_DRAFT_RESULT count=0 mode="
            + ("dry_run" if args.dry_run else "live")
            + " reason=no_eligible_recipients"
            + f" follow_up_tab_present={str(log_tab_present).lower()}"
            + f" distinct_recipients={len(by_email)}"
            + f" skipped_pending_review={skipped_pending}"
            + f" skipped_cadence_too_soon={skipped_cadence}"
            + f" min_days_since_sent={args.min_days_since_sent}"
            + f" reconciled_stale_rows={n_reconciled}"
        )
        return

    label_id: str | None = None
    audience_label_id: str | None = None
    if not args.dry_run and not args.skip_label:
        label_id = ensure_user_label_id(gsvc, DEFAULT_GMAIL_LABEL)
        # Top-level audience label parallel to AI/Follow-up. Every follow-up
        # draft from this script targets a retailer (Manager Follow-up /
        # Bulk Info Requested / AI: Prospect replied), so by definition B2B.
        # Applied as a SECOND label so existing AI/* filters keep working.
        audience_label_id = ensure_user_label_id(gsvc, "B2B")

    created_rows: list[list[str]] = []
    n_made = 0
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for to_addr in candidates:
        if args.max_drafts > 0 and n_made >= args.max_drafts:
            break
        sk, shop, rows_str, hit_notes, city_st = pick_primary_store(targets, to_addr)
        dapp_ctx = format_dapp_remarks_for_grok(remarks_ws, shop, sk)
        if args.verbose:
            if dapp_ctx:
                print(f"  DApp remarks for {to_addr}: {len(dapp_ctx)} chars (shop={shop!r})")
            elif remarks_ws is not None:
                print(f"  DApp remarks: no rows matched shop={shop!r} store_key={sk!r}")
        prev = last_sent.get(to_addr)
        prev_s = prev.strftime("%Y-%m-%d UTC") if prev else "none"

        snippets = latest_thread_excerpts(gsvc, to_addr, max_messages=3)
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
            sheet_ctx = followup_sheet_logged_bodies_for_prompt(log_ws, to_addr)
            if sheet_ctx:
                hist = (
                    "Outbound copies synced to the Hit List "
                    "(Email Agent Follow Up — may overlap Gmail export):\n\n"
                    + sheet_ctx
                    + "\n\n---\n\n"
                    + hist
                )
            try:
                subj, body = grok_generate_followup(
                    api_key=grok_key or "",
                    model=args.grok_model,
                    shop_name=shop,
                    store_key=sk,
                    to_email=to_addr,
                    hit_list_row=rows_str,
                    city_state=city_st,
                    hit_list_notes=hit_notes,
                    dapp_remarks_log=dapp_ctx,
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

        sug_id = str(uuid.uuid4())
        tracking_base = (os.environ.get("EMAIL_AGENT_TRACKING_BASE_URL") or "https://edgar.truesight.me").strip()
        html_body = None
        if args.track_opens or args.track_clicks:
            if not tracking_base:
                sys.stderr.write(
                    "EMAIL_AGENT_TRACKING_BASE_URL is empty; cannot use --track-opens/--track-clicks.\n"
                )
                sys.exit(2)
            html_body = plain_text_to_html_for_email_agent(
                body,
                tracking_base,
                sug_id,
                to_addr,
                track_opens=args.track_opens,
                track_clicks=args.track_clicks,
            )

        raw = build_message_raw(me, to_addr, subj, body, html_body=html_body)

        if args.dry_run:
            print(f"\n--- dry-run draft #{n_made + 1} → {to_addr} ({shop}) ---")
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

        ids_to_apply = [lid for lid in (label_id, audience_label_id) if lid]
        if ids_to_apply and msg_id:
            try:
                gsvc.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"addLabelIds": ids_to_apply},
                ).execute()
            except Exception as e:
                sys.stderr.write(f"Warning: could not apply label to draft message {msg_id}: {e}\n")

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
            "0",
            "0",
            msg_id,
        ]
        created_rows.append(row)
        n_made += 1
        print(f"Created draft #{n_made} id={draft_id!r} → {to_addr} ({shop})")

    if args.dry_run:
        print(
            "EMAIL_AGENT_DRAFT_RESULT count="
            + str(n_made)
            + " mode=dry_run (previews only; nothing written to Gmail or Sheets)"
            + f" follow_up_tab_present={str(log_tab_present).lower()}"
            + f" eligible_cap={len(candidates)}"
            + f" max_drafts_cap={'unlimited' if args.max_drafts == 0 else str(args.max_drafts)}"
            + f" skipped_pending_review={skipped_pending}"
            + f" skipped_cadence_too_soon={skipped_cadence}"
            + f" min_days_since_sent={args.min_days_since_sent}"
            + f" reconciled_stale_rows={n_reconciled}"
        )
        return

    if created_rows:
        sugg_ws.append_rows(created_rows, value_input_option="USER_ENTERED")
        print(f"Appended {len(created_rows)} row(s) to {SUGGESTIONS_WS!r}. Review Drafts in Gmail (label: {DEFAULT_GMAIL_LABEL!r}).")

    print(
        "EMAIL_AGENT_DRAFT_RESULT count="
        + str(len(created_rows))
        + " mode=live gmail_drafts_created="
        + str(len(created_rows))
        + " sheet_rows_appended="
        + str(len(created_rows))
        + f" follow_up_tab_present={str(log_tab_present).lower()}"
        + f" eligible_before_cap={len(candidates)}"
        + f" max_drafts_cap={'unlimited' if args.max_drafts == 0 else str(args.max_drafts)}"
        + f" skipped_pending_review={skipped_pending}"
        + f" skipped_cadence_too_soon={skipped_cadence}"
        + f" min_days_since_sent={args.min_days_since_sent}"
        + f" reconciled_stale_rows={n_reconciled}"
    )


if __name__ == "__main__":
    main()
