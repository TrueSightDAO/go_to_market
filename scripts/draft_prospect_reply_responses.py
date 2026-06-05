#!/usr/bin/env python3
"""
Reply acceleration: when a prospect replies, stage a context-aware response
draft **in-thread** and notify the operator — so the median human response
drops from ~29 hours to same-session.

Why (see ``agentic_ai_context/WARMUP_AUTOSEND_PLAN.md`` §1, PR2): genuine
replies are where partners come from — the thread that converted to
``Partnered`` got sub-hour responses; the slowest soft-no sat 10 days. The
hourly ``email-agent-sync-followup.yml`` already *detects* replies (labels the
inbound message ``AI/Prospect Replied`` and promotes the Hit List row). This
script closes the gap between detection and response:

  1. Finds ``AI/Prospect Replied`` threads where the **prospect spoke last**
     (no operator message after the inbound, no draft staged on the thread,
     no ``pending_review`` sheet row for the thread).
  2. Generates a Grok reply grounded in the full thread history + Hit List
     notes + DApp field remarks (same context plumbing as
     ``suggest_manager_followup_drafts.py --use-grok``).
  3. Creates the Gmail draft **on the thread** (proper ``In-Reply-To`` /
     ``References``), labels it ``AI/Prospect Replied``, and appends an
     ``Email Agent Drafts`` row (``status=pending_review``) so the DApp
     Outbound Review Prospects tab surfaces it.
  4. Emails the operator a notification: the prospect's message, the staged
     draft, and a Gmail deep-link.

**The draft is never sent by automation.** The operator edits/sends in Gmail —
replies are human territory (WARMUP_AUTOSEND_PLAN.md guardrail #2).

Falls back to a plain template draft when ``GROK_API_KEY`` is unavailable —
a same-hour mediocre draft beats a 29-hour-later perfect one.

Usage::

    cd market_research
    python3 scripts/draft_prospect_reply_responses.py            # dry-run
    python3 scripts/draft_prospect_reply_responses.py --execute
    python3 scripts/draft_prospect_reply_responses.py --execute --limit 5 --no-notify
"""
from __future__ import annotations

import argparse
import base64
import sys
import time
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf  # noqa: E402
from gmail_plain_body import extract_plain_body_from_payload  # noqa: E402

PROSPECT_REPLIED_LABEL = "AI/Prospect Replied"
PENDING_STATUS = "pending_review"
REPLY_PROTOCOL = "PARTNER_OUTREACH_PROTOCOL v0.1 warmup_reply"
BODY_PREVIEW_MAX = 500
# Automated senders whose messages must never count as "the prospect spoke".
NOISE_SENDER_SUBSTRINGS = (
    "mailer-daemon", "mailsuite.com", "noreply", "no-reply", "postmaster",
)


def _now_sheet_ts() -> str:
    return datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")


def _addr_of(from_hdr: str) -> str:
    s = (from_hdr or "").strip()
    if "<" in s and ">" in s:
        s = s.split("<", 1)[1].split(">", 1)[0]
    return s.strip().lower()


def _is_noise(from_hdr: str) -> bool:
    low = (from_hdr or "").lower()
    return any(t in low for t in NOISE_SENDER_SUBSTRINGS)


def _load_hit_index(hit_ws) -> dict[str, dict]:
    """email -> {row, shop, store_key, notes, city_state}."""
    values = hit_ws.get_all_values()
    hdr = smf.header_map(values[0])
    out: dict[str, dict] = {}
    for ri, row in enumerate(values[1:], start=2):
        em = smf.normalize_email(smf.cell(row, hdr.get("Email")))
        if not em or em in out:
            continue
        city = smf.cell(row, hdr.get("City"))
        state = smf.cell(row, hdr.get("State"))
        out[em] = {
            "row": ri,
            "shop": smf.cell(row, hdr.get("Shop Name")),
            "store_key": smf.cell(row, hdr.get("Store Key")),
            "notes": smf.cell(row, hdr.get("Notes")),
            "city_state": ", ".join(x for x in [city, state] if x),
        }
    return out


def _pending_thread_ids(drafts_ws) -> set[str]:
    """thread_ids that already have a pending_review Email Agent Drafts row."""
    values = drafts_ws.get_all_values()
    if len(values) < 2:
        return set()
    hdr = smf.header_map(values[0])
    i_status = hdr.get("status")
    i_thread = hdr.get("thread_id")
    i_notes = hdr.get("notes")
    out: set[str] = set()
    for row in values[1:]:
        if smf.cell(row, i_status) != PENDING_STATUS:
            continue
        tid = smf.cell(row, i_thread)
        if tid:
            out.add(tid)
            continue
        # Older rows carry the thread id inside notes ("thread_id=…").
        notes = smf.cell(row, i_notes)
        if "thread_id=" in notes:
            out.add(notes.split("thread_id=", 1)[1].split(";", 1)[0].strip())
    return out


def _grok_generate_reply(
    *, api_key: str, model: str, hit: dict, prospect_addr: str,
    inbound_text: str, conversation_history: str, dapp_remarks_log: str,
) -> tuple[str, str]:
    """Reply-specific user prompt over the shared Agroverse system prompt."""
    import json

    import requests

    user = (
        "A retail prospect has just REPLIED to our outreach. Draft Gary's response "
        "to their message — answer what they actually asked or said; do not restart "
        "the pitch from scratch.\n\n"
        f"Lead context (Hit List CRM):\n"
        f"- shop_name: {hit.get('shop') or '(unknown)'}\n"
        f"- city/state: {hit.get('city_state') or '(not provided)'}\n"
        f"- recipient_email: {prospect_addr}\n"
    )
    notes = (hit.get("notes") or "").strip()
    if notes:
        user += f"- internal_hit_list_notes (context only, never quote): {notes}\n"
    user += (
        "\nTHE PROSPECT'S LATEST MESSAGE (respond to this directly):\n\n"
        f"{inbound_text[:4000]}\n\n"
    )
    if dapp_remarks_log:
        user += f"DApp field / visit remarks (chronological):\n\n{dapp_remarks_log}\n\n"
    user += (
        "Full email thread history (chronological; may be truncated):\n\n"
        f"{conversation_history or '(none)'}\n\n"
        "Rules for this reply: acknowledge their specific points; if they asked a "
        "question you cannot answer from the context, say Gary will confirm rather "
        "than inventing facts; if they declined, thank them warmly and leave the "
        "door open (no hard sell); if they showed interest, propose the concrete "
        "next step (samples, address confirmation, or a scheduled call)."
    )
    payload = {
        "model": model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": smf.grok_system_prompt()},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    r = requests.post(smf.GROK_ENDPOINT, headers=headers, json=payload, timeout=120)
    if not r.ok:
        raise RuntimeError(f"Grok HTTP {r.status_code}: {r.text[:500]}")
    content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    content = content.strip()
    if "```" in content:
        a = content.find("```")
        a = content.find("\n", a) + 1
        b = content.find("```", a)
        content = content[a:b].strip()
    parsed = json.loads(content)
    subj = str(parsed.get("subject", "")).strip()
    body = str(parsed.get("body", "")).strip()
    if not body:
        raise RuntimeError("Grok JSON missing body")
    return subj, body


def _template_reply(hit: dict, inbound_text: str) -> tuple[str, str]:
    shop = hit.get("shop") or "your shop"
    body = (
        "Hi —\n\n"
        f"Thank you for getting back to me about Agroverse ceremonial cacao for {shop}. "
        "I read your note and will respond properly very shortly — happy to answer "
        "anything by email, line up samples, or schedule a quick call, whichever suits.\n\n"
        "Thanks,\nGary\nAgroverse | ceremonial cacao for retail\ngaryjob@agroverse.shop"
    )
    return f"Re: Agroverse cacao — {shop}", body


def _reply_raw(*, sender: str, to: str, subject: str, body: str,
               in_reply_to: str, references: str) -> str:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (f"{references} {in_reply_to}".strip() if references else in_reply_to)
    msg.set_content(body, charset="utf-8")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--execute", action="store_true",
                    help="Create drafts + send notifications. Default is dry-run.")
    ap.add_argument("--limit", type=int, default=10,
                    help="Cap threads processed per run (default 10).")
    ap.add_argument("--no-notify", action="store_true",
                    help="Skip the operator notification email.")
    ap.add_argument("--no-grok", action="store_true",
                    help="Force the plain template instead of Grok.")
    ap.add_argument("--grok-model", default=smf.DEFAULT_GROK_MODEL)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args(argv)

    creds = smf.get_gmail_creds()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    my_email = smf.gmail_profile_email(service)
    sa = smf.get_sheets_client()
    sh = sa.open_by_key(smf.SPREADSHEET_ID)
    hit_ws = sh.worksheet(smf.HIT_LIST_WS)
    drafts_ws = sh.worksheet(smf.SUGGESTIONS_WS)
    remarks_ws = smf.open_dapp_remarks_worksheet(sh)

    label_id = smf.ensure_user_label_id(service, PROSPECT_REPLIED_LABEL)
    hit_index = _load_hit_index(hit_ws)
    pending_threads = _pending_thread_ids(drafts_ws)
    grok_key = None if args.no_grok else smf.get_grok_api_key()

    threads: list[dict] = []
    page_token = None
    while True:
        resp = service.users().threads().list(
            userId="me", labelIds=[label_id], maxResults=100, pageToken=page_token
        ).execute()
        threads.extend(resp.get("threads") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    staged = 0
    examined = 0
    for t in threads:
        if staged >= args.limit:
            break
        tid = t.get("id") or ""
        if not tid or tid in pending_threads:
            continue
        try:
            thread = service.users().threads().get(userId="me", id=tid, format="full").execute()
        except HttpError:
            continue
        msgs = thread.get("messages") or []
        if any("DRAFT" in (m.get("labelIds") or []) for m in msgs):
            continue  # a reply is already staged on this thread
        examined += 1

        # Build the genuine-sender timeline; find who spoke last.
        timeline: list[dict] = []
        for m in msgs:
            hdrs = {h.get("name", "").lower(): h.get("value", "")
                    for h in (m.get("payload") or {}).get("headers") or []}
            frm = hdrs.get("from", "")
            if _is_noise(frm):
                continue
            timeline.append({
                "mine": my_email in frm.lower(),
                "from": frm,
                "addr": _addr_of(frm),
                "subject": hdrs.get("subject", ""),
                "message_id_hdr": hdrs.get("message-id", ""),
                "references": hdrs.get("references", ""),
                "payload": m.get("payload") or {},
            })
        if not timeline or timeline[-1]["mine"]:
            continue  # operator already responded (or nothing genuine)
        last = timeline[-1]
        prospect_addr = last["addr"]
        inbound_text = extract_plain_body_from_payload(last["payload"], max_total=20_000).strip()
        hit = hit_index.get(prospect_addr) or {}
        shop = hit.get("shop") or prospect_addr

        print(f"{'STAGE' if args.execute else 'WOULD STAGE':12} {shop[:40]:40} <{prospect_addr}> thread={tid}")
        if not args.execute:
            staged += 1
            continue

        # --- generate ---
        subject, body = "", ""
        if grok_key:
            try:
                conv = smf.fetch_conversation_history(
                    service, prospect_addr, my_email,
                    max_messages=12, max_total_chars=18_000,
                )
                dapp_log = ""
                if remarks_ws is not None and hit:
                    dapp_log = smf.format_dapp_remarks_for_grok(
                        remarks_ws, hit.get("shop", ""), hit.get("store_key", "")
                    )
                subject, body = _grok_generate_reply(
                    api_key=grok_key, model=args.grok_model, hit=hit,
                    prospect_addr=prospect_addr, inbound_text=inbound_text,
                    conversation_history=conv, dapp_remarks_log=dapp_log,
                )
            except Exception as e:
                sys.stderr.write(f"  grok failed ({e}); falling back to template\n")
        if not body:
            subject, body = _template_reply(hit, inbound_text)
        # Reply subject threads better as Re: of the inbound.
        inbound_subj = last["subject"] or subject
        reply_subject = inbound_subj if inbound_subj.lower().startswith("re:") else f"Re: {inbound_subj}"

        raw = _reply_raw(
            sender=my_email, to=prospect_addr, subject=reply_subject, body=body,
            in_reply_to=last["message_id_hdr"], references=last["references"],
        )
        draft = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw, "threadId": tid}}
        ).execute()
        draft_id = str(draft.get("id") or "")
        dmsg_id = str((draft.get("message") or {}).get("id") or "")
        try:
            service.users().messages().modify(
                userId="me", id=dmsg_id, body={"addLabelIds": [label_id]}
            ).execute()
        except Exception as e:
            sys.stderr.write(f"  WARNING: label apply failed: {e}\n")

        drafts_ws.append_row([
            str(uuid.uuid4()), _now_sheet_ts(),
            hit.get("store_key", ""), hit.get("shop", ""), prospect_addr,
            str(hit.get("row", "")), draft_id, reply_subject,
            body.replace("\n", " ")[:BODY_PREVIEW_MAX],
            PENDING_STATUS, PROSPECT_REPLIED_LABEL, REPLY_PROTOCOL,
            f"kind=warmup_reply; source=draft_prospect_reply_responses; thread_id={tid}",
            "0", "0", dmsg_id, tid,
        ], value_input_option="USER_ENTERED")

        if not args.no_notify:
            note = EmailMessage()
            note["From"] = my_email
            note["To"] = my_email
            note["Subject"] = f"[Prospect reply] {shop} — response drafted, needs your eyes"
            note.set_content(
                f"{shop} <{prospect_addr}> replied. A response draft is staged on the "
                f"thread (label {PROSPECT_REPLIED_LABEL}).\n\n"
                f"Open thread: https://mail.google.com/mail/u/0/#all/{tid}\n\n"
                f"--- Their message ---\n{inbound_text[:1500]}\n\n"
                f"--- Staged draft ---\n{body}\n",
                charset="utf-8",
            )
            service.users().messages().send(
                userId="me",
                body={"raw": base64.urlsafe_b64encode(note.as_bytes()).decode("ascii")},
            ).execute()

        staged += 1
        print(f"  staged draft {draft_id} + notification")
        time.sleep(max(0.0, args.sleep))

    print(f"\nthreads with label: {len(threads)}; examined (no draft, not pending): {examined}; "
          f"{'staged' if args.execute else 'would stage'}: {staged}")
    if not args.execute:
        print("dry-run (default) — pass --execute to stage drafts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
