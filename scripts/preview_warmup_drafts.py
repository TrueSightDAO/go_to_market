#!/usr/bin/env python3
"""
Batch-preview view for **AI/Warm-up** Gmail drafts pending operator review.

Reads ``Email Agent Drafts`` rows where ``status='pending_review'`` and
``gmail_label='AI/Warm-up'``, fetches the full subject/body from each Gmail
draft, cross-references the Hit List for high-leverage signals (Hosts
Circles=Yes, city/state, Notes), looks up DApp Remarks for prior CRM
history, runs a lint pass, and renders a single static HTML page sorted
**risk-tier first** so the operator's eye lands on the rows that need
real review.

Goal: replace uniform "open every draft, skim, send" with a tiered scan —
the linter pre-flags the cohort that genuinely needs reading, the rest
get a 3-line glance and a single click to Gmail.

Send action stays in Gmail (no automation here — the linter rules will
miss net-new failure modes until they're added, and an immediate-send
button removes the safety margin that justifies the linter).

Usage::

    cd market_research
    python3 scripts/preview_warmup_drafts.py
    python3 scripts/preview_warmup_drafts.py --no-browser
    python3 scripts/preview_warmup_drafts.py --limit 20
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf  # noqa: E402
from gmail_plain_body import extract_plain_body_from_payload  # noqa: E402

OUTPUT_DIR = _REPO / "scripts" / "output" / "warmup_batch_preview"
WARMUP_LABEL = "AI/Warm-up"
PENDING_STATUS = "pending_review"
HOSTS_CIRCLES_COL = "Hosts Circles"

GENERIC_INBOX_RE = re.compile(
    r"^(info|sales|hello|contact|admin|support|orders|hi|team|enquiry|enquiries|inquiry|inquiries)@",
    re.IGNORECASE,
)
GENERIC_SALUTATION_RE = re.compile(
    r"^\s*(hi|hello|hey|dear)\s+(there|team|folks|friends)\b", re.IGNORECASE
)
PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|\[[A-Z_]{3,}\]")
NON_LATIN_RE = re.compile(r"[Ѐ-ӿ一-鿿぀-ヿ؀-ۿ]")

SEV_RED = "red"
SEV_YELLOW = "yellow"
SEV_BLUE = "blue"
_SEV_RANK = {SEV_RED: 0, SEV_YELLOW: 1, SEV_BLUE: 2, "": 3}


def _yes(s: str) -> bool:
    """True for 'Yes', 'Yes (sound healing)', 'TRUE', '1', etc.
    Hit List Hosts Circles column stores descriptive variants like
    'Yes (sound bath)' — accept any value whose first token is 'yes'."""
    v = (s or "").strip().lower()
    if not v:
        return False
    if v in ("y", "true", "1"):
        return True
    return v.split()[0] == "yes" or v.split("(")[0].strip() == "yes"


def _gmail_service():
    creds = smf.get_gmail_creds()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _load_hit_list_index(ws) -> tuple[dict, dict, int | None]:
    """Returns (by_email, by_store_key, hosts_circles_idx). Both dicts map to
    a row payload {row, hosts_circles, notes, city_state, status}."""
    values = ws.get_all_values()
    if not values:
        return {}, {}, None
    hdr = smf.header_map(values[0])
    email_i = hdr.get("Email")
    store_i = hdr.get("Store Key")
    notes_i = hdr.get("Notes")
    city_i = hdr.get("City")
    state_i = hdr.get("State")
    status_i = hdr.get("Status")
    aw_i = hdr.get(HOSTS_CIRCLES_COL)

    by_email: dict[str, dict] = {}
    by_store: dict[str, dict] = {}
    for ri, row in enumerate(values[1:], start=2):
        em = smf.normalize_email(smf.cell(row, email_i)) if email_i is not None else None
        sk = smf.cell(row, store_i) if store_i is not None else ""
        city = smf.cell(row, city_i) if city_i is not None else ""
        state = smf.cell(row, state_i) if state_i is not None else ""
        payload = {
            "row": ri,
            "hosts_circles": _yes(smf.cell(row, aw_i)) if aw_i is not None else False,
            "notes": smf.cell(row, notes_i) if notes_i is not None else "",
            "city_state": ", ".join(x for x in [city, state] if x),
            "status": smf.cell(row, status_i) if status_i is not None else "",
        }
        if em and em not in by_email:
            by_email[em] = payload
        if sk and sk not in by_store:
            by_store[sk] = payload
    return by_email, by_store, aw_i


def _load_dapp_remarks_counts(ws) -> dict[str, int]:
    """Counts of DApp Remarks rows per Shop Name (case-insensitive). Used as a
    'has prior CRM history' signal; missing == cold first touch."""
    values = ws.get_all_values()
    if not values:
        return {}
    hdr = smf.header_map(values[0])
    shop_i = hdr.get("Shop Name")
    if shop_i is None:
        return {}
    counts: dict[str, int] = {}
    for row in values[1:]:
        sn = smf.cell(row, shop_i).lower()
        if sn:
            counts[sn] = counts.get(sn, 0) + 1
    return counts


def _load_pending_warmup_drafts(ws) -> list[dict]:
    values = ws.get_all_values()
    if not values:
        return []
    hdr = smf.header_map(values[0])
    need = ["status", "gmail_label", "gmail_draft_id", "to_email", "shop_name", "store_key", "subject", "body_preview", "created_at_utc", "notes", "hit_list_row"]
    for k in need:
        if k not in hdr:
            sys.stderr.write(f"Email Agent Drafts missing column: {k}\n")
            sys.exit(1)
    out: list[dict] = []
    for ri, row in enumerate(values[1:], start=2):
        if smf.cell(row, hdr["status"]) != PENDING_STATUS:
            continue
        if smf.cell(row, hdr["gmail_label"]) != WARMUP_LABEL:
            continue
        out.append({
            "sheet_row": ri,
            "to_email": smf.normalize_email(smf.cell(row, hdr["to_email"])) or "",
            "shop_name": smf.cell(row, hdr["shop_name"]),
            "store_key": smf.cell(row, hdr["store_key"]),
            "draft_id": smf.cell(row, hdr["gmail_draft_id"]),
            "subject_sheet": smf.cell(row, hdr["subject"]),
            "body_preview_sheet": smf.cell(row, hdr["body_preview"]),
            "created_at": smf.cell(row, hdr["created_at_utc"]),
            "notes": smf.cell(row, hdr["notes"]),
            "hit_list_row": smf.cell(row, hdr["hit_list_row"]),
        })
    return out


def _fetch_draft(service, draft_id: str) -> tuple[str, str, str, str]:
    """Returns (subject, body_plain, to_header, message_id). Empty strings on miss."""
    if not draft_id:
        return "", "", "", ""
    try:
        dr = service.users().drafts().get(userId="me", id=draft_id, format="full").execute()
    except HttpError as e:
        if smf.is_missing_draft_http_error(e):
            return "", "", "", ""
        raise
    msg = dr.get("message") or {}
    pl = msg.get("payload") or {}
    hdrs = smf._message_header_map(msg)
    body = extract_plain_body_from_payload(pl, max_total=20_000).strip()
    return hdrs.get("subject", ""), body, hdrs.get("to", ""), str(msg.get("id") or "")


def _lint(draft: dict, body: str, subject: str, hit: dict | None, dapp_count: int) -> list[tuple[str, str, str]]:
    """Returns list of (severity, code, human_message)."""
    out: list[tuple[str, str, str]] = []
    if not subject.strip():
        out.append((SEV_RED, "subject_empty", "Subject is empty"))
    if "your shop" in body.lower():
        out.append((SEV_RED, "fallback_shop_name", "Body uses fallback 'your shop' (shop name was missing at gen time)"))
    em = draft.get("to_email", "")
    if em and GENERIC_INBOX_RE.match(em):
        out.append((SEV_RED, "generic_inbox", f"Generic inbox ({em.split('@')[0]}@) — likely not read by decision maker"))
    first_3_lines = "\n".join(body.splitlines()[:3])
    if GENERIC_SALUTATION_RE.search(first_3_lines):
        out.append((SEV_RED, "no_first_name", "Salutation is generic ('Hi there' / 'Hello team') — no first-name parse"))
    if NON_LATIN_RE.search(subject) or NON_LATIN_RE.search(body[:500]):
        out.append((SEV_RED, "foreign_script", "Subject/body contains non-Latin script — venue may need a different template"))
    if PLACEHOLDER_RE.search(subject) or PLACEHOLDER_RE.search(body):
        out.append((SEV_RED, "unrendered_placeholder", "Unrendered template placeholder in subject or body"))
    if 0 < len(body) < 200:
        out.append((SEV_RED, "body_too_short", f"Body is only {len(body)} chars — generation likely truncated"))
    if not body.strip():
        out.append((SEV_RED, "body_empty", "Body is empty (Gmail draft missing or fetch failed)"))

    if hit is not None:
        if not hit.get("city_state"):
            out.append((SEV_YELLOW, "no_city_state", "Hit List has no City/State — Grok had less locale context"))
        if not (hit.get("notes") or "").strip():
            out.append((SEV_YELLOW, "no_hit_list_notes", "Hit List Notes is blank — no operator pre-context"))
    if dapp_count == 0:
        out.append((SEV_YELLOW, "no_dapp_history", "No prior DApp Remarks for this store_key — cold first touch"))

    if hit is not None and hit.get("hosts_circles"):
        out.append((SEV_BLUE, "hosts_circles", "Hit List Hosts Circles=Yes — high-leverage prospect, extra care"))
    return out


def _draft_sort_key(d: dict) -> tuple[int, int]:
    flags = d["flags"]
    top = min((_SEV_RANK[s] for s, *_ in flags), default=_SEV_RANK[""])
    aw = 0 if d.get("hosts_circles") else 1
    return (top, aw)


def _render_html(rows: list[dict], generated_at: str) -> str:
    sev_class = {SEV_RED: "f-red", SEV_YELLOW: "f-yel", SEV_BLUE: "f-blu"}
    n_total = len(rows)
    n_red = sum(1 for r in rows if any(s == SEV_RED for s, *_ in r["flags"]))
    n_yel = sum(1 for r in rows if any(s == SEV_YELLOW for s, *_ in r["flags"]) and not any(s == SEV_RED for s, *_ in r["flags"]))
    n_aw = sum(1 for r in rows if r.get("hosts_circles"))
    n_clean = sum(1 for r in rows if not any(s in (SEV_RED, SEV_YELLOW) for s, *_ in r["flags"]))

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append("<html lang='en'><head><meta charset='utf-8'>")
    parts.append("<title>Warm-up draft batch preview</title>")
    parts.append("<style>")
    parts.append("""
      body { font: 14px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1100px; margin: 24px auto; padding: 0 16px; color: #222; }
      h1 { font-size: 20px; margin: 0 0 4px; }
      .meta { color: #666; font-size: 12px; margin-bottom: 20px; }
      .summary { display: flex; gap: 16px; padding: 12px 16px; background: #f5f5f5; border-radius: 6px; margin-bottom: 20px; flex-wrap: wrap; }
      .summary div { font-size: 13px; }
      .summary b { font-size: 18px; display: block; }
      .draft { border: 1px solid #ddd; border-radius: 6px; padding: 12px 16px; margin-bottom: 12px; background: #fff; }
      .draft.red { border-left: 4px solid #d33; }
      .draft.yel { border-left: 4px solid #e90; }
      .draft.blu { border-left: 4px solid #28a; }
      .draft.clean { border-left: 4px solid #2a2; }
      .row1 { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
      .recipient { font-weight: 600; }
      .shop { color: #555; }
      .city { color: #888; font-size: 12px; }
      .aw { background: #28a; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }
      .subject { font-weight: 600; margin: 8px 0 6px; font-size: 15px; }
      .flags { margin: 6px 0; display: flex; gap: 6px; flex-wrap: wrap; }
      .flag { padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }
      .f-red { background: #fde; color: #a00; }
      .f-yel { background: #ffe9b3; color: #850; }
      .f-blu { background: #def; color: #036; }
      .actions { margin-top: 8px; font-size: 12px; }
      .actions a { color: #06c; text-decoration: none; margin-right: 14px; }
      .actions a:hover { text-decoration: underline; }
      details > summary { cursor: pointer; font-size: 12px; color: #555; margin-top: 8px; user-select: none; }
      details[open] > summary { color: #222; }
      pre.body { white-space: pre-wrap; word-wrap: break-word; background: #fafafa; padding: 12px; border-radius: 4px; margin-top: 8px; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; max-height: 500px; overflow-y: auto; }
      .empty { text-align: center; padding: 60px 0; color: #888; }
    """)
    parts.append("</style></head><body>")
    parts.append("<h1>Warm-up draft batch preview</h1>")
    parts.append(f"<div class='meta'>Generated {html.escape(generated_at)} · Status=<code>pending_review</code> · Label=<code>AI/Warm-up</code></div>")

    parts.append("<div class='summary'>")
    parts.append(f"<div><b>{n_total}</b>pending drafts</div>")
    parts.append(f"<div><b style='color:#d33'>{n_red}</b>flagged red (review)</div>")
    parts.append(f"<div><b style='color:#e90'>{n_yel}</b>flagged yellow only</div>")
    parts.append(f"<div><b style='color:#2a2'>{n_clean}</b>clean (glance + send)</div>")
    parts.append(f"<div><b style='color:#28a'>{n_aw}</b>Hosts Circles=Yes</div>")
    parts.append("</div>")

    if not rows:
        parts.append("<div class='empty'>No pending warm-up drafts.</div>")
        parts.append("</body></html>")
        return "".join(parts)

    for d in rows:
        flags = d["flags"]
        top_sev = min((_SEV_RANK[s] for s, *_ in flags), default=_SEV_RANK[""])
        cls = "clean"
        if top_sev == _SEV_RANK[SEV_RED]:
            cls = "red"
        elif top_sev == _SEV_RANK[SEV_YELLOW]:
            cls = "yel"
        elif top_sev == _SEV_RANK[SEV_BLUE]:
            cls = "blu"

        parts.append(f"<div class='draft {cls}'>")
        parts.append("<div class='row1'>")
        parts.append(f"<span class='recipient'>{html.escape(d['to_email'] or '(no email)')}</span>")
        if d['shop_name']:
            parts.append(f"<span class='shop'>{html.escape(d['shop_name'])}</span>")
        if d.get('city_state'):
            parts.append(f"<span class='city'>{html.escape(d['city_state'])}</span>")
        if d.get('hosts_circles'):
            parts.append("<span class='aw'>Hosts Circles</span>")
        parts.append("</div>")

        subj = d.get('subject') or d.get('subject_sheet') or '(no subject)'
        parts.append(f"<div class='subject'>{html.escape(subj)}</div>")

        if flags:
            parts.append("<div class='flags'>")
            for sev, code, msg in flags:
                parts.append(f"<span class='flag {sev_class[sev]}' title='{html.escape(msg)}'>{html.escape(code.replace('_', ' '))}</span>")
            parts.append("</div>")

        parts.append("<div class='actions'>")
        if d.get('message_id'):
            parts.append(f"<a href='https://mail.google.com/mail/u/0/#drafts/{html.escape(d['message_id'])}' target='_blank'>Open in Gmail</a>")
        else:
            parts.append("<a href='https://mail.google.com/mail/u/0/#drafts' target='_blank'>Open Drafts</a>")
        if d.get('hit_list_row'):
            parts.append(f"<span style='color:#999;font-size:12px'>Hit List row {html.escape(str(d['hit_list_row']))}</span>")
        parts.append("</div>")

        body = d.get('body') or d.get('body_preview_sheet') or ''
        if body:
            parts.append("<details><summary>Show body</summary>")
            parts.append(f"<pre class='body'>{html.escape(body)}</pre>")
            parts.append("</details>")
        parts.append("</div>")

    parts.append("</body></html>")
    return "".join(parts)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=None, help="Cap drafts processed (default: all pending).")
    p.add_argument("--no-browser", action="store_true", help="Don't auto-open the HTML in browser.")
    p.add_argument("--no-fetch", action="store_true",
                   help="Skip Gmail draft fetches; rely on body_preview from sheet (faster, lossy).")
    args = p.parse_args(argv)

    gc = smf.get_sheets_client()
    sh = gc.open_by_key(smf.SPREADSHEET_ID)
    drafts_ws = sh.worksheet(smf.SUGGESTIONS_WS)
    hit_ws = sh.worksheet(smf.HIT_LIST_WS)
    remarks_ws = sh.worksheet(smf.DAPP_REMARKS_WS)

    pending = _load_pending_warmup_drafts(drafts_ws)
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"Pending warm-up drafts: {len(pending)}")
    if not pending:
        out_path = _write_and_open([], args.no_browser)
        print(f"Wrote {out_path}")
        return 0

    by_email, by_store, _ = _load_hit_list_index(hit_ws)
    dapp_counts = _load_dapp_remarks_counts(remarks_ws)
    print(f"Hit List rows indexed: by_email={len(by_email)} by_store={len(by_store)}; DApp Remarks shops: {len(dapp_counts)}")

    service = None if args.no_fetch else _gmail_service()
    rows: list[dict] = []
    for d in pending:
        if service is not None:
            subject, body, to_hdr, msg_id = _fetch_draft(service, d["draft_id"])
            d["subject"] = subject or d["subject_sheet"]
            d["body"] = body
            d["to_header"] = to_hdr
            d["message_id"] = msg_id
        else:
            d["subject"] = d["subject_sheet"]
            d["body"] = d["body_preview_sheet"]
            d["to_header"] = ""
            d["message_id"] = ""

        hit = by_email.get(d["to_email"]) or by_store.get(d["store_key"])
        d["hosts_circles"] = bool(hit and hit.get("hosts_circles"))
        d["city_state"] = (hit or {}).get("city_state", "")
        dapp_count = dapp_counts.get(d["shop_name"].lower(), 0)
        d["flags"] = _lint(d, d["body"], d["subject"], hit, dapp_count)
        rows.append(d)

    rows.sort(key=_draft_sort_key)
    out_path = _write_and_open(rows, args.no_browser)

    n_red = sum(1 for r in rows if any(s == SEV_RED for s, *_ in r["flags"]))
    n_yel = sum(1 for r in rows if any(s == SEV_YELLOW for s, *_ in r["flags"]) and not any(s == SEV_RED for s, *_ in r["flags"]))
    n_clean = sum(1 for r in rows if not any(s in (SEV_RED, SEV_YELLOW) for s, *_ in r["flags"]))
    print(f"Flagged: red={n_red} yellow_only={n_yel} clean={n_clean}")
    print(f"Wrote {out_path}")
    return 0


def _write_and_open(rows: list[dict], no_browser: bool) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"warmup_preview_{stamp}.html"
    out_path.write_text(_render_html(rows, stamp), encoding="utf-8")
    if not no_browser:
        webbrowser.open(out_path.as_uri())
    return out_path


if __name__ == "__main__":
    sys.exit(main())
