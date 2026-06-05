#!/usr/bin/env python3
"""
Classify genuine prospect replies and auto-park the unambiguous negatives.

Why (see ``agentic_ai_context/WARMUP_AUTOSEND_PLAN.md`` §3 PR3): the 60-day
audit showed soft-nos like "reach out again around September" and hard-nos
like "we are not interested" each consumed an operator triage pass just to
set a status the reply already dictated. This script does that bookkeeping:

  category            → automatic Hit List action
  ------------------    -----------------------------------------------
  soft_no_with_date   → Status ``Deferred / Revisit later`` + Follow Up Date
  soft_no             → Status ``On Hold``
  hard_no             → Status ``Rejected``
  referral            → status unchanged; referred shop names appended to
                        Sales Process Notes for discovery triage
  interested /        → no status change — these ride the reply-acceleration
  question / other      path (draft_prospect_reply_responses.py + notify)

Every classification (including no-action ones) writes a ``DApp Remarks``
audit row with the model rationale and the classified ``message_id=…``
marker (the idempotency key — re-runs skip already-classified messages).
Parking actions go through the shared ``hit_list_dapp_remarks_sheet``
apply-semantics (Status, Sales Process Notes, Status Updated By/Date,
remark marked Processed) — same convention as photo review / contact
enrichment.

Parking is **gated on the row's current Status** — only rows still in the
automated-outreach states (``AI: Prospect replied``, ``AI: Warm up prospect``,
``Manager Follow-up``, ``Followed Up``) are parked; operator-managed states
are never clobbered.

Usage::

    cd market_research
    python3 scripts/classify_warmup_replies.py             # dry-run
    python3 scripts/classify_warmup_replies.py --execute
    python3 scripts/classify_warmup_replies.py --execute --limit 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf  # noqa: E402
from gmail_plain_body import extract_plain_body_from_payload  # noqa: E402
from hit_list_dapp_remarks_sheet import (  # noqa: E402
    append_dapp_remark_and_apply,
    gspread_retry,
)

PROSPECT_REPLIED_LABEL = "AI/Prospect Replied"
SUBMITTED_BY = "classify_warmup_replies"
NOISE_SENDER_SUBSTRINGS = (
    "mailer-daemon", "mailsuite.com", "noreply", "no-reply", "postmaster",
)
CATEGORIES = (
    "interested", "question", "soft_no_with_date", "soft_no",
    "hard_no", "wrong_contact", "referral", "other",
)
PARKABLE_STATUSES = {
    "AI: Prospect replied", "AI: Warm up prospect", "Manager Follow-up", "Followed Up",
}
PARK_STATUS = {
    "soft_no_with_date": "Deferred / Revisit later",
    "soft_no": "On Hold",
    "hard_no": "Rejected",
}

CLASSIFY_SYSTEM = (
    "You classify a retail prospect's email reply to a ceremonial-cacao wholesale "
    "outreach. Output ONLY valid JSON: {\"category\": one of "
    f"{list(CATEGORIES)}, "
    '"revisit_date": "YYYY-MM-DD" or "" (when they name a time to reconnect — '
    "resolve relative mentions like 'September' to the NEXT occurrence after the "
    'reply date), "referrals": [shop names they suggested instead, if any], '
    '"rationale": one sentence}. '
    "Rules: 'we already have a supplier' with no invitation = soft_no. "
    "'not interested' / 'going to pass' = hard_no. A named month/season to retry "
    "= soft_no_with_date. Asking anything about product/terms/logistics = question. "
    "Wanting samples or to proceed = interested. 'I'm not the right person, try X' "
    "where X is an email/department = wrong_contact; suggesting OTHER SHOPS = referral. "
    "When mixed, prefer interested > question > referral > wrong_contact > "
    "soft_no_with_date > soft_no > hard_no. Uncertain = other."
)


def _addr_of(from_hdr: str) -> str:
    s = (from_hdr or "").strip()
    if "<" in s and ">" in s:
        s = s.split("<", 1)[1].split(">", 1)[0]
    return s.strip().lower()


def _is_noise(from_hdr: str) -> bool:
    low = (from_hdr or "").lower()
    return any(t in low for t in NOISE_SENDER_SUBSTRINGS)


def _classified_message_ids(remarks_ws) -> set[str]:
    vals = gspread_retry(lambda: remarks_ws.get_all_values())
    if len(vals) < 2:
        return set()
    hdr = {h: i for i, h in enumerate(vals[0])}
    i_by = hdr.get("Submitted By")
    i_rem = hdr.get("Remarks")
    out: set[str] = set()
    for row in vals[1:]:
        if i_by is None or i_rem is None:
            break
        if (row[i_by] if len(row) > i_by else "") != SUBMITTED_BY:
            continue
        rem = row[i_rem] if len(row) > i_rem else ""
        if "message_id=" in rem:
            out.add(rem.split("message_id=", 1)[1].split(";", 1)[0].strip())
    return out


def _grok_classify(api_key: str, model: str, reply_text: str, reply_date: str, shop: str) -> dict:
    user = (
        f"Reply date: {reply_date}\nShop: {shop}\n\n"
        f"Prospect's reply:\n\n{reply_text[:4000]}"
    )
    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    r = requests.post(
        smf.GROK_ENDPOINT,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json=payload, timeout=120,
    )
    if not r.ok:
        raise RuntimeError(f"Grok HTTP {r.status_code}: {r.text[:300]}")
    content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    content = content.strip()
    if "```" in content:
        a = content.find("```")
        a = content.find("\n", a) + 1
        b = content.find("```", a)
        content = content[a:b].strip()
    parsed = json.loads(content)
    cat = str(parsed.get("category", "other")).strip()
    if cat not in CATEGORIES:
        cat = "other"
    return {
        "category": cat,
        "revisit_date": str(parsed.get("revisit_date", "") or "").strip(),
        "referrals": [str(x).strip() for x in (parsed.get("referrals") or []) if str(x).strip()],
        "rationale": str(parsed.get("rationale", "") or "").strip(),
    }


def _hit_lookup(hit_ws) -> tuple[dict[str, dict], list[str]]:
    vals = gspread_retry(lambda: hit_ws.get_all_values())
    headers = vals[0]
    hdr = {h: i for i, h in enumerate(headers)}
    out: dict[str, dict] = {}
    for ri, row in enumerate(vals[1:], start=2):
        em = smf.normalize_email(row[hdr["Email"]] if len(row) > hdr["Email"] else "")
        if not em or em in out:
            continue
        out[em] = {
            "row": ri,
            "shop": row[hdr["Shop Name"]] if len(row) > hdr["Shop Name"] else "",
            "status": row[hdr["Status"]] if len(row) > hdr["Status"] else "",
        }
    return out, headers


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--execute", action="store_true",
                    help="Write classifications + park rows. Default is dry-run.")
    ap.add_argument("--limit", type=int, default=15,
                    help="Cap replies classified per run (default 15).")
    ap.add_argument("--grok-model", default=smf.DEFAULT_GROK_MODEL)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args(argv)

    grok_key = smf.get_grok_api_key()
    if not grok_key:
        sys.stderr.write("GROK_API_KEY unavailable — classification requires it.\n")
        return 1

    service = build("gmail", "v1", credentials=smf.get_gmail_creds(), cache_discovery=False)
    my_email = smf.gmail_profile_email(service)
    sa = smf.get_sheets_client()
    sh = sa.open_by_key(smf.SPREADSHEET_ID)
    hit_ws = sh.worksheet(smf.HIT_LIST_WS)
    remarks_ws = smf.open_dapp_remarks_worksheet(sh)
    if remarks_ws is None:
        sys.stderr.write("DApp Remarks worksheet not found.\n")
        return 1

    label_id = smf.ensure_user_label_id(service, PROSPECT_REPLIED_LABEL)
    hit_index, hit_headers = _hit_lookup(hit_ws)
    done_ids = _classified_message_ids(remarks_ws)

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

    handled = 0
    for t in threads:
        if handled >= args.limit:
            break
        tid = t.get("id") or ""
        try:
            thread = service.users().threads().get(userId="me", id=tid, format="full").execute()
        except HttpError:
            continue
        # Latest genuine inbound message on the thread (skip drafts + noise + mine).
        latest = None
        for m in thread.get("messages") or []:
            if "DRAFT" in (m.get("labelIds") or []):
                continue
            hdrs = {h.get("name", "").lower(): h.get("value", "")
                    for h in (m.get("payload") or {}).get("headers") or []}
            frm = hdrs.get("from", "")
            if _is_noise(frm) or my_email in frm.lower():
                continue
            latest = {"id": str(m.get("id") or ""), "from": frm,
                      "date": hdrs.get("date", ""), "payload": m.get("payload") or {}}
        if latest is None or latest["id"] in done_ids:
            continue

        prospect_addr = _addr_of(latest["from"])
        hit = hit_index.get(prospect_addr)
        shop = (hit or {}).get("shop") or prospect_addr
        reply_text = extract_plain_body_from_payload(latest["payload"], max_total=20_000).strip()
        if not reply_text:
            continue

        try:
            cls = _grok_classify(grok_key, args.grok_model, reply_text, latest["date"], shop)
        except Exception as e:
            sys.stderr.write(f"  classify failed for {shop}: {e}\n")
            continue
        handled += 1

        park_to = PARK_STATUS.get(cls["category"])
        current_status = (hit or {}).get("status", "")
        will_park = bool(park_to and hit and current_status in PARKABLE_STATUSES)
        action = f"park → {park_to}" if will_park else (
            f"would park → {park_to} BUT status {current_status!r} is operator-managed"
            if park_to and hit else "remark only"
        )
        print(f"{shop[:40]:40} {cls['category']:18} {action}")
        if cls["rationale"]:
            print(f"    {cls['rationale'][:120]}")
        if not args.execute:
            continue

        now_iso = datetime.now(timezone.utc).isoformat()
        sid = f"classify-{uuid.uuid4()}"
        marker = f"message_id={latest['id']}; thread_id={tid}"
        referral_note = (
            f" Referrals: {', '.join(cls['referrals'])}." if cls["referrals"] else ""
        )
        remark_text = (
            f"[classify-reply {now_iso}] outcome={cls['category']}; {marker}. "
            f"{cls['rationale']}{referral_note}"
        )

        if will_park:
            applied_status = park_to
            append_dapp_remark_and_apply(
                hit_ws, remarks_ws, hit["row"], shop, applied_status,
                remark_text, SUBMITTED_BY, now_iso, sid,
                hit_headers=hit_headers,
            )
            if cls["category"] == "soft_no_with_date" and cls["revisit_date"]:
                c_fud = hit_headers.index("Follow Up Date") + 1
                gspread_retry(lambda: hit_ws.update_cell(hit["row"], c_fud, cls["revisit_date"]))
                print(f"    Follow Up Date ← {cls['revisit_date']}")
        elif cls["category"] == "referral" and hit:
            # Status unchanged; remark + Sales Process Notes via apply with same status.
            append_dapp_remark_and_apply(
                hit_ws, remarks_ws, hit["row"], shop, current_status,
                remark_text, SUBMITTED_BY, now_iso, sid,
                hit_headers=hit_headers,
            )
        else:
            # Audit-only remark, pre-marked Processed so no other consumer re-triages it.
            r_headers = gspread_retry(lambda: remarks_ws.row_values(1))
            row_out = []
            for h in r_headers:
                row_out.append({
                    "Submission ID": sid, "Shop Name": shop, "Status": current_status,
                    "Remarks": remark_text, "Submitted By": SUBMITTED_BY,
                    "Submitted At": now_iso, "Processed": "Yes", "Processed At": now_iso,
                }.get(h, ""))
            gspread_retry(lambda: remarks_ws.append_row(row_out, value_input_option="USER_ENTERED"))

        done_ids.add(latest["id"])
        time.sleep(max(0.0, args.sleep))

    print(f"\nthreads scanned: {len(threads)}; replies classified this run: {handled}")
    if not args.execute:
        print("dry-run (default) — pass --execute to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
