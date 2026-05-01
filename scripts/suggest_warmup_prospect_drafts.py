#!/usr/bin/env python3
"""
Gmail **drafts** for Hit List rows with Status = **AI: Warm up prospect** and Email set.

- Cadence: same as manager follow-up — at most one **pending_review** suggestion per recipient
  while the Gmail draft exists; next draft after **Email Agent Follow Up** shows a prior **sent** at least
  ``--min-days-since-sent`` ago (default **7**), **unless** a pending draft was **discarded** (Gmail draft
  deleted / reconcile), in which case the next draft is allowed immediately. Run **sync_email_agent_followup.py** first.
- **Attachments (3 by default):**
    - ``retail_price_list/agroverse_wholesale_price_list_2026.pdf`` (wholesale tiers)
    - ``retail_price_list/agroverse_packaging_front.jpeg`` (bag front, on shelf)
    - ``retail_price_list/agroverse_packaging_back.jpeg`` (bag back, on shelf)
  Override individually with ``--pdf-path`` / ``--packaging-front`` / ``--packaging-back``.
- **Grok** (optional ``--use-grok``): first-touch intro; no in-person visit assumption; flexible consignment or bulk;
  lead with Amazon rainforest restoration (tree per bag, QR traceability); style reference in
  ``templates/warmup_outreach_reference.md``.
- **Reply promotion:** By default, before drafting, promotes rows to **AI: Prospect replied** when Gmail shows
  an **inbound** message **from** the prospect **after** the latest logged **sent_at** for that address in
  **Email Agent Follow Up**.

Usage:
  cd market_research
  python3 scripts/sync_email_agent_followup.py
  python3 scripts/suggest_warmup_prospect_drafts.py --dry-run
  python3 scripts/suggest_warmup_prospect_drafts.py --use-grok
  python3 scripts/suggest_warmup_prospect_drafts.py --reply-promotion-only
  python3 scripts/suggest_warmup_prospect_drafts.py --skip-reply-promotion
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
from pathlib import Path
from typing import Any

import gspread
import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf

from email_agent_tracking import plain_text_to_html_for_email_agent
from gmail_plain_body import extract_plain_body_from_payload
from hit_list_dapp_remarks_sheet import append_dapp_remark_and_apply
_WARMUP_REF = _REPO / "templates" / "warmup_outreach_reference.md"
_DEFAULT_PDF = _REPO / "retail_price_list" / "agroverse_wholesale_price_list_2026.pdf"
_DEFAULT_PACKAGING_FRONT = _REPO / "retail_price_list" / "agroverse_packaging_front.jpeg"
_DEFAULT_PACKAGING_BACK = _REPO / "retail_price_list" / "agroverse_packaging_back.jpeg"

SPREADSHEET_ID = smf.SPREADSHEET_ID
HIT_LIST_WS = smf.HIT_LIST_WS
SUGGESTIONS_WS = smf.SUGGESTIONS_WS
LOG_WS = smf.LOG_WS
DAPP_REMARKS_WS = smf.DAPP_REMARKS_WS

HIT_STATUS_WARMUP = "AI: Warm up prospect"
HIT_STATUS_REPLIED = "AI: Prospect replied"
PROTOCOL_VERSION = "PARTNER_OUTREACH_PROTOCOL v0.1 warmup_intro"
DEFAULT_MIN_DAYS = smf.DEFAULT_MIN_DAYS_SINCE_SENT
BODY_PREVIEW_MAX = smf.BODY_PREVIEW_MAX
GROK_ENDPOINT = smf.GROK_ENDPOINT
DEFAULT_GROK_MODEL = smf.DEFAULT_GROK_MODEL
DEFAULT_GMAIL_LABEL = "AI/Warm-up"
PER_MESSAGE_BODY_CAP = smf.PER_MESSAGE_BODY_CAP


def load_warmup_targets(ws: gspread.Worksheet) -> list[dict]:
    values = ws.get_all_values()
    if not values:
        return []
    hdr = smf.header_map(values[0])
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
        if smf.cell(row, status_i) != HIT_STATUS_WARMUP:
            continue
        em = smf.normalize_email(smf.cell(row, email_i))
        if not em:
            continue
        city = smf.cell(row, city_i) if city_i is not None else ""
        state = smf.cell(row, state_i) if state_i is not None else ""
        locale = ", ".join(x for x in [city, state] if x)
        out.append(
            {
                "hit_list_row": r,
                "store_key": smf.cell(row, store_i) if store_i is not None else "",
                "shop_name": smf.cell(row, shop_i) if shop_i is not None else "",
                "to_email": em,
                "notes": smf.cell(row, notes_i) if notes_i is not None else "",
                "city_state": locale,
            }
        )
    return out


def _email_from_from_header(from_hdr: str) -> str:
    if not from_hdr:
        return ""
    s = from_hdr.strip()
    m = re.search(r"<([^>]+)>", s)
    addr = (m.group(1) if m else s).strip().lower()
    if addr.startswith("mailto:"):
        addr = addr[7:].split("?")[0].strip().lower()
    return addr


def _message_internal_ms(full: dict) -> int:
    try:
        return int(full.get("internalDate", 0) or 0)
    except (TypeError, ValueError):
        return 0


def inbound_reply_details(
    service,
    *,
    partner_email: str,
    after_ms: int,
    max_scan: int = 30,
) -> dict | None:
    """Return reply details dict if partner sent a message after after_ms, else None."""
    want = smf.normalize_email(partner_email)
    if not want:
        return None
    q = f"from:{want}"
    page_token = None
    scanned = 0
    while scanned < max_scan:
        req = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=min(15, max_scan - scanned), pageToken=page_token)
        )
        resp = req.execute()
        for m in resp.get("messages") or []:
            mid = m.get("id")
            if not mid:
                continue
            try:
                full = service.users().messages().get(userId="me", id=mid, format="full").execute()
            except HttpError:
                continue
            ms = _message_internal_ms(full)
            if ms <= after_ms:
                continue
            pl = full.get("payload") or {}
            frm = ""
            subject = ""
            for h in pl.get("headers") or []:
                hn = (h.get("name") or "").lower()
                if hn == "from":
                    frm = h.get("value") or ""
                elif hn == "subject":
                    subject = h.get("value") or ""
            from_addr = _email_from_from_header(frm)
            if from_addr != want:
                continue
            body = extract_plain_body_from_payload(pl, max_total=5_000)
            if not body:
                body = (full.get("snippet") or "").replace("\n", " ").strip()
            date_iso = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
            return {
                "message_id": mid,
                "subject": subject,
                "date": date_iso,
                "body": body,
            }
        scanned += len(resp.get("messages") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return None


# Backward-compatible alias
inbound_from_partner_after = inbound_reply_details


def promote_warmup_replies(
    hit_ws: gspread.Worksheet,
    log_ws: gspread.Worksheet | None,
    gsvc: Any,
    remarks_ws: gspread.Worksheet | None,
    *,
    dry_run: bool,
    verbose: bool,
) -> int:
    """Set Hit List Status to AI: Prospect replied when inbound after last logged sent.
    Also appends a DApp Remarks row with the reply content for audit + template refinement."""
    if log_ws is None:
        print("WARNING: Email Agent Follow Up missing — skip reply promotion.")
        return 0

    last_sent = smf.last_sent_utctime_per_to_email(log_ws)
    values = hit_ws.get_all_values()
    if len(values) < 2:
        return 0
    hdr = smf.header_map(values[0])
    status_i = hdr.get("Status")
    email_i = hdr.get("Email")
    shop_i = hdr.get("Shop Name")
    if status_i is None or email_i is None:
        return 0
    status_col = status_i + 1
    n = 0

    for r, row in enumerate(values[1:], start=2):
        if smf.cell(row, status_i) != HIT_STATUS_WARMUP:
            continue
        em = smf.normalize_email(smf.cell(row, email_i))
        if not em:
            continue
        prev = last_sent.get(em)
        if prev is None:
            if verbose:
                print(f"  promote-skip row {r} {em}: no logged sent in {LOG_WS!r}")
            continue
        after_ms = int(prev.timestamp() * 1000)
        reply = inbound_reply_details(gsvc, partner_email=em, after_ms=after_ms)
        if reply:
            if verbose:
                print(f"  promote row {r} {em}: inbound after last send → {HIT_STATUS_REPLIED!r}")
            if not dry_run:
                # Append DApp Remarks with reply content before flipping status
                if remarks_ws is not None:
                    shop_name = smf.cell(row, shop_i) if shop_i is not None else ""
                    remarks_text = (
                        f"Prospect replied to warm-up email.\n\n"
                        f"Reply subject: {reply['subject']}\n"
                        f"Reply date: {reply['date']}\n"
                        f"Reply body:\n{reply['body']}"
                    )
                    try:
                        append_dapp_remark_and_apply(
                            hit_ws=hit_ws,
                            remark_ws=remarks_ws,
                            sheet_row=r,
                            name=shop_name,
                            ai_status=HIT_STATUS_REPLIED,
                            remarks=remarks_text,
                            submitted_by="warmup_reply_promotion",
                            submitted_at=reply['date'],
                            submission_id=str(uuid.uuid4()),
                        )
                    except Exception as e:
                        print(f"  WARNING: DApp Remarks append failed for row {r}: {e}")
                hit_ws.update_cell(r, status_col, HIT_STATUS_REPLIED)
            n += 1
    return n


def load_warmup_reference_text() -> str:
    if not _WARMUP_REF.is_file():
        return ""
    try:
        t = _WARMUP_REF.read_text(encoding="utf-8").strip()
        if len(t) > 8000:
            t = t[:7999] + "…"
        return t
    except OSError:
        return ""


def grok_warmup_system_prompt() -> str:
    ref = load_warmup_reference_text()
    ref_block = (
        f"Style reference (paraphrase only; do not copy; synthesize tone and structure):\n\n{ref}\n\n"
        if ref
        else ""
    )
    return (
        "You draft a **first-touch** outreach email for Gary at Agroverse — ceremonial cacao for "
        "independent retailers. The merchant should need only light editing.\n"
        "Rules:\n"
        '- Output **only** valid JSON: one object with keys "subject" and "body" (plain text, use \\n for newlines).\n'
        "- No markdown fences, no preamble.\n"
        "- **Do not** assume Gary is **in their city** or will **visit their shop**. No “stopping by,” "
        "**in-person meetings**, or return-visit framing. Prefer **email reply** or a **short call** they schedule.\n"
        "- **Lead with mission impact:** purchases support **restoration of the Amazon rainforest**; **each bag "
        "plants a new tree**, **directly traceable** via the **unique QR code on that bag** (keep this accurate "
        "and prominent — at least one clear sentence early in the body).\n"
        "- **Commercial fit:** say Agroverse is **flexible** and happy with **either** a **consignment-friendly** "
        "retail path **or** **wholesale / bulk** — present them as **parallel options**, not as a contrast "
        "(avoid lines like “while others choose wholesale for margins” or any implication that bulk is mainly "
        "about beating other retailers’ choices).\n"
        "- **Do not** assume, imply, or acknowledge that the shop **already carries cacao**, has their **own "
        "cacao supplier**, or needs an “alongside what you stock” angle. Do not invite them to compare against "
        "an existing cacao line you do not know they have.\n"
        "- State clearly that the email has **three attachments**: a **wholesale price list PDF** plus "
        "**two photos of the packaging** (front and back of the bar) for shelf-fit reference. Do not paste "
        "prices in the body unless already in context notes.\n"
        "- **Visual reference link:** include exactly one short mention of **https://agroverse.shop/wholesale** as a "
        "*visual* companion to the attachments — partner-shop shelf gallery and current U.S. stockist list. "
        "Frame the page and the attachments as **complementary**, not redundant: the page is for shelf-proof and "
        "social validation, the PDF is for SKU and pricing detail. **Do not** make the link the primary call to "
        "action — the primary CTA stays “reply by email with consignment vs bulk.”\n"
        "- **Amazon-restoration proof reel:** include exactly one short mention of "
        "**https://www.instagram.com/p/DJqW8TRtJK3/** as a 30-second visual that shows end-to-end how the "
        "tree-per-bag program is actively restoring the Amazon rainforest. Frame as a *short proof* — "
        "30 seconds, watch on phone — not a CTA. Pair it with the Amazon-restoration line earlier in the body "
        "so a recipient who is moved by the mission can see it in motion before they decide whether to reply.\n"
        "- Salutation: use a natural greeting for the **shop** or a generic “Hi —” if no contact name is known.\n"
        "- **Body** ~140–240 words unless shorter fits. End with a short signature block:\n"
        "  Gary\n"
        "  Agroverse | ceremonial cacao for retail\n"
        "  garyjob@agroverse.shop\n"
        "- Subject: specific, warm, not spammy; include shop name if known. Under ~90 characters.\n"
        + ref_block
    )


def grok_generate_warmup(
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
        f"- hit_list_status: {HIT_STATUS_WARMUP} (first-touch intro; PDF wholesale list + two packaging photos will be attached)\n"
    )
    if crm_notes:
        user += (
            "- internal_hit_list_notes (use for specificity; do not quote as if the merchant wrote this): "
            f"{crm_notes}\n"
        )
    user += "\n"
    if dapp_block:
        user += (
            "DApp / field remarks (same shop or store key):\n\n"
            f"{dapp_block}\n\n"
        )
    user += (
        "Optional Gmail thread snippets or related mail (may be empty for unknown addresses):\n\n"
        f"{conversation_history or '(none)'}\n"
    )
    payload = {
        "model": model,
        "temperature": 0.42,
        "messages": [
            {"role": "system", "content": grok_warmup_system_prompt()},
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


def build_message_raw_with_attachments(
    sender: str,
    to: str,
    subject: str,
    body: str,
    pdf_path: Path,
    *,
    html_body: str | None = None,
    image_paths: list[Path] | None = None,
) -> dict[str, str]:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Wholesale PDF not found: {pdf_path}")
    pdf_data = pdf_path.read_bytes()

    image_blobs: list[tuple[bytes, str, str]] = []
    for ip in image_paths or []:
        if not ip.is_file():
            raise FileNotFoundError(f"Image attachment not found: {ip}")
        suffix = ip.suffix.lower().lstrip(".")
        subtype = "jpeg" if suffix in ("jpg", "jpeg") else (suffix or "octet-stream")
        image_blobs.append((ip.read_bytes(), subtype, ip.name))

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject

    if html_body:
        inner = EmailMessage()
        inner.set_content(body, charset="utf-8")
        inner.add_alternative(html_body, subtype="html")
        msg.make_mixed()
        msg.attach(inner)
    else:
        msg.set_content(body, charset="utf-8")

    msg.add_attachment(pdf_data, maintype="application", subtype="pdf", filename=pdf_path.name)
    for data, subtype, filename in image_blobs:
        msg.add_attachment(data, maintype="image", subtype=subtype, filename=filename)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def warmup_subject_template(shop_name: str) -> str:
    s = (shop_name or "Intro").strip()
    return f"Ceremonial cacao for {s} — each bag plants a tree (PDF attached)"


def warmup_body_template(shop_name: str) -> str:
    shop = shop_name or "your shop"
    return (
        f"Hi —\n\n"
        f"I’m Gary with Agroverse (farm-linked ceremonial cacao). I’m reaching out to {shop} because our model ties "
        f"every sale to **Amazon rainforest restoration**: **each bag plants a new tree**, and the **unique QR code "
        f"on that bag** links to **direct traceability** for that planting.\n\n"
        f"30-second proof of the restoration in motion: https://www.instagram.com/p/DJqW8TRtJK3/ — watch on "
        f"your phone, see the actual tree planting and the satellite imagery the QR code unlocks for customers.\n\n"
        f"We’re **flexible on structure** — **either** **consignment-friendly** retail **or** **wholesale / bulk** "
        f"works on our side; I’ve attached our **wholesale price list PDF** so you can skim SKUs and tiers, "
        f"plus **two photos of the packaging** (front and back) so you can picture how it sits on shelf. "
        f"For partner-shop shelf photos and the current U.S. stockist list, see "
        f"https://agroverse.shop/wholesale — that's the visual companion to the PDF.\n\n"
        f"No need to meet in person on my side; happy to answer by email or on a quick call if that’s easier. "
        f"If you tell me which path you’d rather explore first (consignment vs bulk), I can point you to the "
        f"lightest next step.\n\n"
        f"Thanks,\n"
        f"Gary\n"
        f"Agroverse | ceremonial cacao for retail\n"
        f"garyjob@agroverse.shop\n"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Warm up prospect: Gmail drafts + wholesale PDF + optional Grok.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-drafts", type=int, default=0, help="Cap new drafts; 0 = unlimited.")
    p.add_argument("--min-days-since-sent", type=float, default=DEFAULT_MIN_DAYS)
    p.add_argument("--skip-label", action="store_true")
    p.add_argument("--expected-mailbox", default=smf.EXPECTED_MAILBOX)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--use-grok", action="store_true")
    p.add_argument("--grok-model", default=DEFAULT_GROK_MODEL)
    p.add_argument(
        "--pdf-path",
        type=Path,
        default=_DEFAULT_PDF,
        help="Wholesale list PDF to attach.",
    )
    p.add_argument(
        "--packaging-front",
        type=Path,
        default=_DEFAULT_PACKAGING_FRONT,
        help="On-shelf packaging photo (front of bag) to attach. Pass empty string to skip.",
    )
    p.add_argument(
        "--packaging-back",
        type=Path,
        default=_DEFAULT_PACKAGING_BACK,
        help="On-shelf packaging photo (back of bag) to attach. Pass empty string to skip.",
    )
    p.add_argument("--reply-promotion-only", action="store_true", help="Only promote Warm up → Prospect replied.")
    p.add_argument("--skip-reply-promotion", action="store_true")
    p.add_argument(
        "--track-opens",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Multipart HTML + 1×1 open pixel (tid=suggestion_id). Default ON; "
            "pass --no-track-opens to disable for a one-off batch."
        ),
    )
    p.add_argument(
        "--track-clicks",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Rewrite http(s) URLs in the HTML part via Edgar /email_agent/click. "
            "Default ON; pass --no-track-clicks to disable for a one-off batch."
        ),
    )
    args = p.parse_args()

    if args.max_drafts < 0:
        sys.stderr.write("--max-drafts must be >= 0\n")
        sys.exit(2)

    if args.use_grok and not args.dry_run:
        if not smf.get_grok_api_key():
            sys.stderr.write("GROK_API_KEY not set. Export or add to .env\n")
            sys.exit(1)

    gcreds = smf.get_gmail_creds()
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
    me = smf.gmail_profile_email(gsvc)
    exp = args.expected_mailbox.strip().lower()
    if me != exp:
        sys.stderr.write(f"Gmail profile is {me!r}, expected {exp!r}.\n")
        sys.exit(1)

    sa = smf.get_sheets_client()
    sh = sa.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)
    sugg_ws = smf.ensure_suggestions_worksheet(sh)
    log_ws = smf.open_follow_up_worksheet(sh)
    remarks_ws = smf.open_dapp_remarks_worksheet(sh)

    promoted = 0
    if not args.skip_reply_promotion:
        promoted = promote_warmup_replies(
            hit_ws,
            log_ws,
            gsvc,
            remarks_ws,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        if promoted:
            print(f"Promoted {promoted} row(s) {HIT_STATUS_WARMUP!r} → {HIT_STATUS_REPLIED!r}.")
        if args.reply_promotion_only:
            print(f"WARMUP_REPLY_PROMOTION count={promoted} dry_run={args.dry_run}")
            return

    log_tab_present = log_ws is not None
    last_sent = smf.last_sent_utctime_per_to_email(log_ws)
    pending_to, n_reconciled, freshly_discarded = smf.pending_review_emails_after_gmail_reconcile(
        gsvc, sugg_ws, dry_run=args.dry_run, verbose=args.verbose
    )
    if n_reconciled:
        print(
            f"Reconciled {n_reconciled} row(s) in {SUGGESTIONS_WS!r}: pending_review → discarded."
        )
    latest_discard_utc = smf.latest_discarded_utc_per_to_email(sugg_ws)
    now = datetime.now(timezone.utc)

    targets = load_warmup_targets(hit_ws)
    if not targets:
        print(f"No Hit List rows match {HIT_STATUS_WARMUP!r} with Email.")
        print(
            "WARMUP_DRAFT_RESULT count=0 reason=no_targets "
            f"promoted={promoted} dry_run={args.dry_run}"
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
                print(f"  skip {em}: pending_review active")
            continue
        prev = last_sent.get(em)
        if prev is not None:
            d = smf.days_since_utc(prev, now)
            if d < args.min_days_since_sent:
                if not smf.cadence_bypass_after_discarded_draft(
                    em,
                    last_sent_dt=prev,
                    freshly_discarded_emails=freshly_discarded,
                    latest_discard_utc_per_email=latest_discard_utc,
                ):
                    skipped_cadence += 1
                    if args.verbose:
                        print(f"  skip {em}: last send {d:.1f}d ago (need {args.min_days_since_sent})")
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
    print(
        f"{HIT_STATUS_WARMUP} rows: {len(targets)} | distinct recipients: {len(by_email)} | "
        f"eligible: {len(candidates)} | promoted_replies: {promoted}"
    )

    if not candidates:
        print(
            "WARMUP_DRAFT_RESULT count=0 reason=no_eligible "
            f"skipped_pending={skipped_pending} skipped_cadence={skipped_cadence} "
            f"promoted={promoted} dry_run={args.dry_run}"
        )
        return

    label_id: str | None = None
    audience_label_id: str | None = None
    if not args.dry_run and not args.skip_label:
        label_id = smf.ensure_user_label_id(gsvc, DEFAULT_GMAIL_LABEL)
        # Top-level audience label parallel to AI/Warm-up. Every warm-up draft
        # produced by this script targets a retailer (Hit List status =
        # AI: Warm up prospect), so it's by definition B2B. Applied as a
        # SECOND label — Gmail keeps both, and the AI/* lifecycle swap
        # downstream (sync_email_agent_followup.py: AI/Warm-up →
        # AI/Sent Warm-up) leaves this label alone.
        audience_label_id = smf.ensure_user_label_id(gsvc, "B2B")

    created_rows: list[list[str]] = []
    n_made = 0
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for to_addr in candidates:
        if args.max_drafts > 0 and n_made >= args.max_drafts:
            break
        sk, shop, rows_str, hit_notes, city_st = smf.pick_primary_store(targets, to_addr)
        if remarks_ws is not None:
            dapp_ctx = smf.format_dapp_remarks_for_grok(remarks_ws, shop, sk)
        else:
            dapp_ctx = ""
        prev = last_sent.get(to_addr)
        prev_s = prev.strftime("%Y-%m-%d UTC") if prev else "none"

        snippets = smf.latest_thread_excerpts(gsvc, to_addr, max_messages=2)
        source = "template"
        subj: str
        body: str

        if args.use_grok and not args.dry_run:
            grok_key = smf.get_grok_api_key()
            hist = smf.fetch_conversation_history(
                gsvc,
                to_addr,
                me.lower(),
                max_messages=min(30, smf.DEFAULT_GROK_MAX_MESSAGES),
                max_total_chars=min(80_000, smf.DEFAULT_GROK_MAX_CONTEXT_CHARS),
            )
            sheet_ctx = smf.followup_sheet_logged_bodies_for_prompt(log_ws, to_addr, max_blocks=1)
            if sheet_ctx:
                hist = (
                    "Outbound copies (Email Agent Follow Up):\n\n"
                    + sheet_ctx
                    + "\n\n---\n\n"
                    + hist
                )
            try:
                subj, body = grok_generate_warmup(
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
                subj = warmup_subject_template(shop)
                body = warmup_body_template(shop)
                source = "template_fallback"
        else:
            subj = warmup_subject_template(shop)
            body = warmup_body_template(shop)

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

        image_paths = [
            ip for ip in (args.packaging_front, args.packaging_back)
            if ip and str(ip).strip()
        ]
        try:
            raw = build_message_raw_with_attachments(
                me, to_addr, subj, body, args.pdf_path,
                html_body=html_body, image_paths=image_paths,
            )
        except FileNotFoundError as e:
            sys.stderr.write(f"{e}\n")
            sys.exit(1)

        if args.dry_run:
            print(f"\n--- dry-run draft → {to_addr} ({shop}) ---")
            if args.use_grok:
                print("(Note: --dry-run skips Grok; preview is template.)")
            print(f"Subject: {subj}")
            print(body[:700] + ("…" if len(body) > 700 else ""))
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
                sys.stderr.write(f"Warning: label on draft message {msg_id}: {e}\n")

        preview = body.replace("\n", " ")[:BODY_PREVIEW_MAX]
        attachment_names = ",".join(
            [args.pdf_path.name] + [p.name for p in image_paths]
        )
        notes = (
            f"kind=warmup_intro; attachments={attachment_names}; source={source}; "
            f"cadence min_days={args.min_days_since_sent}; last_logged_send={prev_s}; "
            f"grok_model={args.grok_model if args.use_grok else 'n/a'}. Edit before Send."
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
        ]
        created_rows.append(row)
        n_made += 1
        print(f"Created warmup draft #{n_made} id={draft_id!r} → {to_addr} ({shop})")

    if args.dry_run:
        print(
            f"WARMUP_DRAFT_RESULT count={n_made} mode=dry_run promoted={promoted} "
            f"skipped_pending={skipped_pending} skipped_cadence={skipped_cadence}"
        )
        return

    if created_rows:
        sugg_ws.append_rows(created_rows, value_input_option="USER_ENTERED")
        print(f"Appended {len(created_rows)} row(s) to {SUGGESTIONS_WS!r}.")

    print(
        "WARMUP_DRAFT_RESULT count="
        + str(len(created_rows))
        + f" mode=live promoted_replies={promoted} "
        f"skipped_pending={skipped_pending} skipped_cadence={skipped_cadence} "
        f"follow_up_tab={str(log_tab_present).lower()}"
    )


if __name__ == "__main__":
    main()