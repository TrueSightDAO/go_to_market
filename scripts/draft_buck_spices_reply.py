#!/usr/bin/env python3
"""
One-off: draft an in-thread reply to Beau at Buck's Spices.

Beau replied to a warm-up email on 2026-04-30 with two questions:
  1. How would you propose we use the paste, for example?
  2. We are licensed to mix dry ingredients. We have thought about upgrading
     this to include wet ingredients. I assume the paste is wet?

This script finds the most recent inbound message from a buckspices.com
sender (or a fallback search), composes a reply that:
  - Pivots from paste (wet, license-wrong) to the dry-friendly SKUs
    (ceremonial cacao blocks, 81% bars, beans/nibs).
  - Maps his customer profile (tradition / food / drink / history) to
    ceremonial cacao's 5,000-year Mesoamerican lineage.
  - Offers an in-person sample drop-off as the next step.
  - Embeds the Agroverse open-tracking pixel via Edgar's `email_agent/open.gif`,
    using the same helper as suggest_manager_followup_drafts.py.

Creates a Gmail DRAFT only — never sends. The threadId, In-Reply-To, and
References headers are wired correctly so it lands in the same thread when
viewed in Gmail.

Run from market_research repo root:
    python3 scripts/draft_buck_spices_reply.py --dry-run
    python3 scripts/draft_buck_spices_reply.py
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import uuid
from email.message import EmailMessage
from pathlib import Path

# Allow importing siblings when run as a script.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from email_agent_tracking import build_open_pixel_html  # noqa: E402
from gmail_user_credentials import load_gmail_user_credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = Path(__file__).resolve().parents[1] / "credentials" / "gmail" / "token.json"
TRACKING_BASE_URL = os.environ.get("EMAIL_AGENT_TRACKING_BASE_URL", "https://edgar.truesight.me")
GMAIL_PROFILE_EXPECTED = "garyjob@agroverse.shop"

# Sender domains / addresses to try, in order.
SENDER_QUERIES = [
    "from:@buckspices.com",
    "from:bucks-spices.com",
    "from:beau",
    "Buck's Spices",
]


def find_thread_and_latest_message(service, query: str, *, my_addr: str):
    """Return (thread_id, latest_inbound_message_dict). 'Inbound' means From != my_addr,
    so we skip Gary's own prior drafts/sent messages and reply to Beau's actual email.
    """
    # Force inbound by adding -from:me to the query.
    qry = f"({query}) -from:me"
    resp = service.users().messages().list(userId="me", q=qry, maxResults=10).execute()
    messages = resp.get("messages", []) or []
    if not messages:
        return None, None
    thread_id = messages[0].get("threadId")
    # Re-fetch the entire thread and pick the latest message whose From != my_addr.
    thread = service.users().threads().get(
        userId="me", id=thread_id, format="metadata",
        metadataHeaders=["Message-ID", "From", "To", "Subject", "References", "In-Reply-To"],
    ).execute()
    msgs = thread.get("messages", []) or []
    for m in reversed(msgs):
        from_hdr = header_value(m, "From").lower()
        if my_addr.lower() not in from_hdr:
            return thread_id, m
    # Fall back: no inbound message found in thread.
    return thread_id, msgs[-1] if msgs else None


def header_value(msg: dict, name: str) -> str:
    for h in (msg.get("payload", {}) or {}).get("headers", []) or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "") or ""
    return ""


REPLY_PLAIN = """\
Hi Beau,

Thanks for the thoughtful response — and for the operational details. They're useful.

Quick correction on the paste, before anything else. Cacao paste is actually solid at room temperature — cocoa butter holds it together until it hits roughly 93°F. For retail packaging and shelf purposes it behaves like baker's chocolate, cocoa butter, or coconut oil — all of which sit on dry retail shelves under standard licensing, not wet-ingredient licensing. Worth a 5-minute call to your county health department to confirm in your jurisdiction, but in most places sealed paste in its packaged form fits a dry-ingredients license the same way a chocolate bar does. Where the wet-ingredients license actually becomes the gate is what you might want to *do* with the paste at the store — making ganache to sell, dispensing hot drinks, running bonbon workshops on premises. Selling it sealed = same risk surface as a sealed bar.

So paste doesn't have to wait on the license upgrade.

Here's what we have ready to ship this week, both shelf-friendly and lined up with your "tradition / food / drink / history" customer profile:

- Oscar Bahia ceremonial cacao, 200g (pre-grated, ready to scoop). Single-origin from Oscar's 100-year-old family farm in Bahia ( https://agroverse.shop/farms/oscar-bahia/ ). We've already grated the blocks down, so the customer just scoops into hot water or milk and stirs — no grater, no special tools, no learning curve. Lower barrier for the curious-but-cautious customer.
- Fazenda Santa Ana 2023 ceremonial cacao, 200g (also pre-grated). A second Bahia farm, different micro-climate, different flavor profile ( https://agroverse.shop/farms/fazenda-santa-ana-bahia/ ). Same scoop-and-stir format.
- Organic cacao nibs, 8-oz. Roasted and chopped — pure cacao, no sugar, slightly bitter, distinctly nutty. From the same Bahia farms.

For your shelf-level use-case question, the through-line for these is "the customer who likes the story":

- Mesoamerican xocolatl. The original 5,000-year-old preparation — ceremonial cacao, chili, vanilla, frothed in hot water. The Maya and Aztec drank it daily. With the pre-grated form, it's a 2-minute drink at home, which means even a customer who's only history-curious (not ceremony-curious) can actually try it.
- Side-by-side single-origin tasting. A spoon of the Oscar grind in one cup of warm milk, a spoon of the Santa Ana grind in another. Same story arc as a single-origin coffee flight, with deeper roots — and two farms gives you a built-in "compare and contrast" pitch at the counter.
- Cacao nibs as a savory ingredient. Drop them on a cheese board, fold into a steak rub, sprinkle on roasted vegetables. Bitter-nutty crunch that surprises people who only know cacao as a sweet ingredient.

Now to your paste question directly. Five honest use cases:

- Drinking chocolate / xocolatl, the smoother cousin. Same Mesoamerican drink as the block, but paste melts faster and gives a silkier mouthfeel. A pre-made sweetened "drinking chocolate concentrate" lets customers scoop and stir at home.
- Mole and slow-braised savory. A spoon of paste deepens chili, mole, short ribs. Spanish convent kitchens in the 1500s leaned on this; the food-history customer eats it up.
- Bonbons / custom chocolate. Melt with cocoa butter and sweetener, temper, mold. Good shape for a customer-facing or workshop activity from single-farm Bahia cacao.
- Baking — brownies, ganache, truffles. Direct replacement for unsweetened "baker's chocolate" at a noticeably higher quality bar.
- Pre-made ceremonial cacao for circle hosts. Some practitioners prefer paste over a block because it's portion-ready — saves grating when serving twenty people at a cacao circle.

The wet-license upgrade earns its keep if you want to *make things* with the paste at the store (in-store workshops, ganache for the case, hot drinks dispensed on site). For just shelving sealed paste, you most likely don't need the upgrade.

Let me know if any of this raises follow-up questions, or if there's a particular angle you want to dig into further.

Best,
Gary

Gary Teh
Agroverse
agroverse.shop
"""


def build_html_body(plain: str, tracking_html: str) -> str:
    # Convert the plain text into a tame HTML body, preserving paragraph/list shape.
    blocks = []
    current = []
    for line in plain.splitlines():
        if not line.strip():
            if current:
                blocks.append(("para" if not current[0].startswith("- ") else "list", current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(("para" if not current[0].startswith("- ") else "list", current))

    parts = []
    for kind, lines in blocks:
        if kind == "list":
            items = "".join(f"<li>{_escape_html(l[2:].strip())}</li>" for l in lines if l.startswith("- "))
            parts.append(f"<ul>{items}</ul>")
        else:
            joined = "<br>".join(_escape_html(l) for l in lines)
            parts.append(f"<p>{joined}</p>")
    body_html = "".join(parts)

    return f"""<!doctype html>
<html><body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-size:14px;color:#222;line-height:1.5;">
{body_html}
{tracking_html}
</body></html>"""


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the composed reply and exit without creating the draft.")
    parser.add_argument("--query", default=None,
                        help="Override the Gmail search query (default: try buckspices.com, beau, Buck's Spices).")
    parser.add_argument("--thread-id", default=None,
                        help="Optionally pass the Gmail API threadId directly (bypasses search).")
    parser.add_argument("--send-as", default=GMAIL_PROFILE_EXPECTED,
                        help=f"Verify Gmail profile matches this address (default: {GMAIL_PROFILE_EXPECTED}).")
    args = parser.parse_args(argv)

    creds = load_gmail_user_credentials(TOKEN_PATH, GMAIL_SCOPES)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    profile = service.users().getProfile(userId="me").execute()
    actual = (profile.get("emailAddress") or "").strip().lower()
    if args.send_as and actual != args.send_as.lower():
        sys.stderr.write(f"Refusing to draft: authenticated as {actual!r}, expected {args.send_as!r}.\n")
        return 1
    print(f"Authenticated as {actual}")

    thread_id = args.thread_id
    latest = None
    if not thread_id:
        queries = [args.query] if args.query else SENDER_QUERIES
        for q in queries:
            tid, msg = find_thread_and_latest_message(service, q, my_addr=actual)
            if tid:
                thread_id, latest = tid, msg
                print(f"Found thread via query {q!r}: thread_id={thread_id}")
                break
        if not thread_id:
            sys.stderr.write("No matching thread found. Try --query or --thread-id.\n")
            return 1
    else:
        # Pull latest message in the thread to get headers.
        thread = service.users().threads().get(userId="me", id=thread_id, format="metadata",
                                               metadataHeaders=["Message-ID", "From", "To", "Subject", "References", "In-Reply-To"]).execute()
        msgs = thread.get("messages", []) or []
        if not msgs:
            sys.stderr.write(f"Thread {thread_id} has no messages.\n")
            return 1
        latest = msgs[-1]

    msg_id_hdr = header_value(latest, "Message-ID")
    refs_hdr = header_value(latest, "References")
    from_hdr = header_value(latest, "From")
    subj_hdr = header_value(latest, "Subject") or "Re: Agroverse cacao"

    # Reply subject: prepend Re: if not already.
    reply_subject = subj_hdr if subj_hdr.lower().startswith("re:") else f"Re: {subj_hdr}"

    print(f"Replying to: {from_hdr}")
    print(f"Subject:     {reply_subject}")
    print(f"In-Reply-To: {msg_id_hdr}")

    suggestion_id = str(uuid.uuid4())
    tracking_html = build_open_pixel_html(TRACKING_BASE_URL, suggestion_id)
    html_body = build_html_body(REPLY_PLAIN, tracking_html)

    msg = EmailMessage()
    msg["From"] = actual
    msg["To"] = from_hdr
    msg["Subject"] = reply_subject
    if msg_id_hdr:
        msg["In-Reply-To"] = msg_id_hdr
        msg["References"] = (refs_hdr + " " + msg_id_hdr).strip() if refs_hdr else msg_id_hdr
    msg.set_content(REPLY_PLAIN, charset="utf-8")
    msg.add_alternative(html_body, subtype="html")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    body = {"message": {"raw": raw, "threadId": thread_id}}

    if args.dry_run:
        print("\n--- DRY RUN: composed reply (plain) ---\n")
        print(REPLY_PLAIN)
        print(f"\nTracking suggestion_id = {suggestion_id}")
        print(f"Tracking pixel = {TRACKING_BASE_URL}/email_agent/open.gif?tid={suggestion_id}")
        return 0

    # Iteration UX: nuke any prior draft on this same thread so re-running
    # replaces in place instead of stacking duplicates in the Drafts folder.
    deleted = 0
    page_token = None
    while True:
        resp = service.users().drafts().list(userId="me", maxResults=100,
                                              pageToken=page_token).execute()
        for d in resp.get("drafts", []) or []:
            d_msg = d.get("message", {}) or {}
            if d_msg.get("threadId") == thread_id:
                try:
                    service.users().drafts().delete(userId="me", id=d["id"]).execute()
                    deleted += 1
                except Exception as e:
                    sys.stderr.write(f"Could not delete prior draft {d.get('id')!r}: {e}\n")
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    if deleted:
        print(f"Replaced {deleted} prior draft(s) on this thread.")

    draft = service.users().drafts().create(userId="me", body=body).execute()
    print(f"\nDraft created: id={draft.get('id')} message.threadId={(draft.get('message') or {}).get('threadId')}")
    print(f"Tracking suggestion_id = {suggestion_id}")
    print("Open Gmail → Drafts to review and send.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
