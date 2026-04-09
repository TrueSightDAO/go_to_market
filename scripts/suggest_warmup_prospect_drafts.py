#!/usr/bin/env python3
"""
Gmail **drafts** for Hit List rows with Status = **AI: Warm up prospect** and Email set.

- Cadence: same as manager follow-up — at most one **pending_review** suggestion per recipient
  while the Gmail draft exists; next draft only after **Email Agent Follow Up** shows a prior
  **sent** at least ``--min-days-since-sent`` ago (default **7**). Run **sync_email_agent_followup.py** first.
- **Attachment:** ``retail_price_list/agroverse_wholesale_price_list_2026.pdf`` on each draft.
- **Grok** (optional ``--use-grok``): first-touch intro; no in-person visit assumption; consignment + bulk paths;
  style reference in ``templates/warmup_outreach_reference.md``.
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

import suggest_manager_followup_drafts as smf

_REPO = Path(__file__).resolve().parent.parent
_WARMUP_REF = _REPO / "templates" / "warmup_outreach_reference.md"
_DEFAULT_PDF = _REPO / "retail_price_list" / "agroverse_wholesale_price_list_2026.pdf"

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
DEFAULT_GMAIL_LABEL = smf.DEFAULT_GMAIL_LABEL
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


def inbound_from_partner_after(
    service,
    *,
    partner_email: str,
    after_ms: int,
    max_scan: int = 30,
) -> bool:
    """True if any message From partner with internalDate > after_ms."""
    want = smf.normalize_email(partner_email)
    if not want:
        return False
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
            for h in pl.get("headers") or []:
                if (h.get("name") or "").lower() == "from":
                    frm = h.get("value") or ""
                    break
            from_addr = _email_from_from_header(frm)
            if from_addr != want:
                continue
            # Exclude obvious auto-reply if From is partner but we want real human - still count as reply
            return True
        scanned += len(resp.get("messages") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return False


def promote_warmup_replies(
    hit_ws: gspread.Worksheet,
    log_ws: gspread.Worksheet | None,
    gsvc: Any,
    *,
    dry_run: bool,
    verbose: bool,
) -> int:
    """Set Hit List Status to AI: Prospect replied when inbound after last logged sent."""
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
        if inbound_from_partner_after(gsvc, partner_email=em, after_ms=after_ms):
            if verbose:
                print(f"  promote row {r} {em}: inbound after last send → {HIT_STATUS_REPLIED!r}")
            if not dry_run:
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
        "- Acknowledge retailers differ: some prefer **consignment**, others prefer **bulk / wholesale purchase**. "
        "Offer both paths briefly and neutrally.\n"
        "- State clearly that a **wholesale price list PDF is attached** (do not paste prices in the body unless "
        "already in context notes).\n"
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
        f"- hit_list_status: {HIT_STATUS_WARMUP} (first-touch intro; PDF wholesale list will be attached)\n"
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


def build_message_raw_with_pdf(
    sender: str,
    to: str,
    subject: str,
    body: str,
    pdf_path: Path,
) -> dict[str, str]:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Wholesale PDF not found: {pdf_path}")
    data = pdf_path.read_bytes()
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")
    msg.add_attachment(
        data,
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def warmup_subject_template(shop_name: str) -> str:
    s = (shop_name or "Intro").strip()
    return f"Ceremonial cacao for {s} — wholesale options (PDF attached)"


def warmup_body_template(shop_name: str) -> str:
    shop = shop_name or "your shop"
    return (
        f"Hi —\n\n"
        f"I’m Gary with Agroverse (farm-linked ceremonial cacao). I’m reaching out to {shop} because "
        f"I think your customers may appreciate a transparent, craft cacao option alongside what you already carry.\n\n"
        f"Some retailers start with **consignment-friendly** terms; others prefer a **straight bulk order** when they "
        f"know their velocity. I’ve attached our **wholesale price list PDF** so you can skim SKUs and tiers — "
        f"no need to meet in person on my side; happy to answer by email or on a quick call if that’s easier.\n\n"
        f"If you tell me which path fits you better (consignment vs bulk), I can point you to the lightest next step.\n\n"
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
    p.add_argument("--reply-promotion-only", action="store_true", help="Only promote Warm up → Prospect replied.")
    p.add_argument("--skip-reply-promotion", action="store_true")
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
    pending_to, n_reconciled = smf.pending_review_emails_after_gmail_reconcile(
        gsvc, sugg_ws, dry_run=args.dry_run, verbose=args.verbose
    )
    if n_reconciled:
        print(
            f"Reconciled {n_reconciled} row(s) in {SUGGESTIONS_WS!r}: pending_review → discarded."
        )
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
                skipped_cadence += 1
                if args.verbose:
                    print(f"  skip {em}: last send {d:.1f}d ago (need {args.min_days_since_sent})")
                continue
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
    if not args.dry_run and not args.skip_label:
        label_id = smf.ensure_user_label_id(gsvc, DEFAULT_GMAIL_LABEL)

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

        try:
            raw = build_message_raw_with_pdf(me, to_addr, subj, body, args.pdf_path)
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

        if label_id and msg_id:
            try:
                gsvc.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"addLabelIds": [label_id]},
                ).execute()
            except Exception as e:
                sys.stderr.write(f"Warning: label on draft message {msg_id}: {e}\n")

        sug_id = str(uuid.uuid4())
        preview = body.replace("\n", " ")[:BODY_PREVIEW_MAX]
        notes = (
            f"kind=warmup_intro; attachment={args.pdf_path.name}; source={source}; "
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