#!/usr/bin/env python3
"""
Hit List: process rows with Status **AI: Enrich with contact**, AND opportunistically
fill empty location/hours/listing columns on any row whose Notes has a ``place_id``.

Two queues per run:

1. **Contact enrichment queue** (Status = ``AI: Enrich with contact``, default cap 10):
   - Resolve **Website** from the sheet or Google Places **website** (Notes must contain place_id if missing).
   - Fetch homepage + common /contact paths; extract emails (regex) and contact-form heuristics.
   - Optional **Grok** (text-only): pick one email from candidates, or pick best contact-page URL from a provided list.
   - Update the row and set **one** outcome status:
       **AI: Email found** + column Email (K),
       **AI: Contact Form found** + column Contact Form URL (AE),
       **AI: Enrich — manual** if neither works.
   - Log each run on tab **DApp Remarks** (same columns as human DApp submits), then apply to
     **Hit List** (Status, **Sales Process Notes**, Status Updated By/Date) and mark the remark
     **Processed** — same pipeline as ``hit_list_research_photo_review`` / ``process_dapp_remarks``.
     Audit text is ``[enrich-contact ISO8601] outcome=…`` in the remark **Remarks** cell; **Notes**
     is left unchanged (still used for place_id / discovery context).

2. **Fill-gap queue** (default cap 20, disable with ``--no-fill-gaps``):
   - Any row whose Notes has ``place_id: …`` AND at least one of {Address, City, State,
     Latitude, Longitude, Monday Open, Google listing} is empty. (The contact-enrichment queue
     above also applies this fill on its own rows in the same Places Details call — single
     API call, both responsibilities discharged.)
   - Subsumes the standalone ``backfill_hit_list_opening_hours.py`` and
     ``backfill_hit_list_google_listing.py`` for the routine cron path; those remain available
     as manual one-shots.

Both queues share one Places Details call per row (fields:
``website,formatted_address,address_components,geometry,opening_hours,business_status``).

Does not send email or submit forms — enrichment only.

Environment:
  - google_credentials.json (Sheets editor)
  - GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY (Places Details)
  - GROK_API_KEY (optional with --no-grok; Grok skips when only one clear email)

Usage:
  cd market_research
  python3 scripts/hit_list_enrich_contact.py --dry-run --limit 2
  python3 scripts/hit_list_enrich_contact.py --limit 10
  python3 scripts/hit_list_enrich_contact.py --fill-gaps-limit 50
  python3 scripts/hit_list_enrich_contact.py --no-fill-gaps              # contact queue only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

from hit_list_dapp_remarks_sheet import append_dapp_remark_and_apply

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import discover_apothecaries_la_hit_list as dl  # noqa: E402
import backfill_hit_list_opening_hours as bl  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
DAPP_REMARKS_WS = "DApp Remarks"
SUBMITTED_BY_ENRICH = "hit_list_enrich_contact"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

QUEUE_STATUS = "AI: Enrich with contact"
STATUS_EMAIL = "AI: Email found"
STATUS_FORM = "AI: Contact Form found"
STATUS_MANUAL = "AI: Enrich — manual"

GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = os.environ.get("GROK_CONTACT_MODEL", "grok-4-1-fast-non-reasoning")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (compatible; TrueSight HitListEnrich/1.0; +https://truesight.me)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)

PLACE_ID_IN_NOTES = re.compile(
    r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})",
)
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

SKIP_EMAIL_SUBSTRINGS = (
    "@example.",
    "@domain.",
    "wix.com",
    "sentry.io",
    "schema.org",
    ".png",
    ".jpg",
    "noreply@",
    "no-reply@",
    "donotreply@",
    "privacy@",
)

CONTACT_PATHS = (
    "/",
    "/contact",
    "/contact-us",
    "/contacts",
    "/about",
    "/about-us",
    "/pages/contact",
)


def load_dotenv_repo() -> None:
    env_path = REPO / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass


def maps_api_key() -> str:
    load_dotenv_repo()
    k = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not k:
        raise SystemExit(
            "Set GOOGLE_MAPS_API_KEY (or GOOGLE_PLACES_API_KEY) in .env or environment."
        )
    return k


def grok_api_key() -> str | None:
    load_dotenv_repo()
    k = os.environ.get("GROK_API_KEY")
    return k.strip() if k else None


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def place_details_full(key: str, place_id: str) -> dict[str, Any]:
    """Return the Places Details ``result`` dict for fields shared by this script and the
    discovery / opening-hours / Google-listing helpers, or ``{}`` on non-OK status.
    Reuses ``dl.place_details`` so the requested field set stays canonical."""
    data = dl.place_details(key, place_id)
    if data.get("status") != "OK":
        return {}
    return data.get("result") or {}


GAP_HEADERS_PRIMARY = ("Address", "City", "State", "Latitude", "Longitude")
GAP_HEADER_HOURS_FIRST = "Monday Open"
GAP_HEADER_LISTING = dl.GOOGLE_LISTING_COL


def _row_cell(row: list[str], header: list[str], name: str) -> tuple[str, int]:
    """Return (current_value_stripped, 0-based-col-index) or ("", -1) if header missing."""
    if name not in header:
        return "", -1
    ci = header.index(name)
    cur = (row[ci] if ci < len(row) else "").strip()
    return cur, ci


def has_any_gap(row: list[str], header: list[str]) -> bool:
    """True if any of {Address, City, State, Lat, Lng, Monday Open, Google listing} is empty."""
    for name in (*GAP_HEADERS_PRIMARY, GAP_HEADER_HOURS_FIRST, GAP_HEADER_LISTING):
        cur, ci = _row_cell(row, header, name)
        if ci < 0:
            continue
        if not cur:
            return True
    return False


def apply_place_result_to_row_gaps(
    ws: gspread.Worksheet,
    header: list[str],
    rn: int,
    row: list[str],
    res: dict[str, Any],
    *,
    dry_run: bool,
    force: bool = False,
    log_prefix: str = "",
) -> list[str]:
    """Fill empty {Address, City, State, Latitude, Longitude, weekday hours, Google listing} cells
    on row ``rn`` from a Places Details ``result`` dict.

    Idempotent: skips columns whose current value is non-empty unless ``force=True``.
    Opening hours are written only when ALL 14 weekday cells are currently empty (atomic block).

    Returns the list of header names whose cells were updated (or would be, in dry-run)."""
    parsed = dl.parse_address_components(res.get("address_components") or [])
    loc = (res.get("geometry") or {}).get("location") or {}
    p_lat = loc.get("lat")
    p_lng = loc.get("lng")

    updates: list[tuple[int, str, str]] = []  # (col_idx_0based, header_name, value)

    cur_addr, ci_addr = _row_cell(row, header, "Address")
    if ci_addr >= 0 and (force or not cur_addr):
        street = parsed.get("street_line") or ""
        if street:
            updates.append((ci_addr, "Address", street))

    cur_city, ci_city = _row_cell(row, header, "City")
    if ci_city >= 0 and (force or not cur_city):
        city = parsed.get("city") or parsed.get("_neighborhood") or ""
        if city:
            updates.append((ci_city, "City", city))

    cur_state, ci_state = _row_cell(row, header, "State")
    if ci_state >= 0 and (force or not cur_state):
        state = parsed.get("state") or ""
        if state:
            updates.append((ci_state, "State", state))

    cur_lat, ci_lat = _row_cell(row, header, "Latitude")
    if ci_lat >= 0 and (force or not cur_lat) and p_lat is not None:
        updates.append((ci_lat, "Latitude", str(p_lat)))

    cur_lng, ci_lng = _row_cell(row, header, "Longitude")
    if ci_lng >= 0 and (force or not cur_lng) and p_lng is not None:
        updates.append((ci_lng, "Longitude", str(p_lng)))

    hour_cells: list[tuple[str, int, str]] = []
    has_any_hours = False
    for h in dl.HIT_LIST_OPENING_HOUR_COLS:
        cur_h, ci_h = _row_cell(row, header, h)
        hour_cells.append((h, ci_h, cur_h))
        if cur_h:
            has_any_hours = True
    if (force or not has_any_hours) and all(ci >= 0 for _, ci, _ in hour_cells):
        grid = dl.opening_hours_week_grid_from_place_result(res)
        if any((grid.get(h) or "").strip() for h in dl.HIT_LIST_OPENING_HOUR_COLS):
            for h, ci_h, _ in hour_cells:
                v = (grid.get(h) or "").strip()
                updates.append((ci_h, h, v))

    cur_gl, ci_gl = _row_cell(row, header, dl.GOOGLE_LISTING_COL)
    if ci_gl >= 0 and (force or not cur_gl):
        label = dl.google_listing_from_business_status(res.get("business_status"))
        if label:
            updates.append((ci_gl, dl.GOOGLE_LISTING_COL, label))

    if not updates:
        return []

    updated_names = [h for _, h, _ in updates]
    if dry_run:
        print(
            f"  {log_prefix}row {rn}: dry-run would fill {len(updates)} cell(s): {updated_names}",
            flush=True,
        )
        return updated_names

    batch: list[dict[str, Any]] = []
    for ci, _h, val in updates:
        batch.append(
            {
                "range": rowcol_to_a1(rn, ci + 1),
                "values": [[val]],
            }
        )
    ws.batch_update(batch, value_input_option="USER_ENTERED")
    print(
        f"  {log_prefix}row {rn}: filled {len(updates)} cell(s): {updated_names}",
        flush=True,
    )
    return updated_names


def fetch_html(url: str, timeout: float = 20.0) -> str | None:
    u = (url or "").strip()
    if not u:
        return None
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    try:
        r = SESSION.get(u, timeout=timeout, allow_redirects=True)
        if r.status_code != 200 or not r.text:
            return None
        ct = (r.headers.get("Content-Type") or "").lower()
        if "html" not in ct and "text" not in ct and "xml" not in ct:
            return None
        return r.text
    except requests.RequestException:
        return None


def strip_tags_to_text(html: str, max_chars: int) -> str:
    s = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    s = re.sub(r"(?is)<style.*?>.*?</style>", " ", s)
    s = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_chars:
        s = s[: max_chars // 2] + "\n…\n" + s[-max_chars // 2 :]
    return s


def regex_emails(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in EMAIL_RE.finditer(text):
        e = m.group(0).strip().rstrip(".,);:]\"'")
        el = e.lower()
        if any(bad in el for bad in SKIP_EMAIL_SUBSTRINGS):
            continue
        if el not in seen:
            seen.add(el)
            out.append(e)
    return out


def collect_fetched_pages(
    base_url: str, sleep_s: float, max_chars: int
) -> tuple[list[tuple[str, str, str]], str]:
    """Returns [(url, html, plain_text), ...] and combined plain text for email regex."""
    root = base_url.strip()
    if not root.lower().startswith(("http://", "https://")):
        root = "https://" + root
    parts: list[tuple[str, str, str]] = []
    for path in CONTACT_PATHS:
        if path == "/":
            u = root.rstrip("/") + "/" if not root.endswith("/") else root
        else:
            u = urllib.parse.urljoin(
                root if root.endswith("/") else root + "/", path.lstrip("/")
            )
        html = fetch_html(u)
        time.sleep(max(0.0, sleep_s))
        if not html:
            continue
        txt = strip_tags_to_text(html, max_chars)
        if txt:
            parts.append((u, html, txt))
    combined = "\n\n".join(f"=== {u} ===\n{t}" for u, _, t in parts)
    return parts, combined


def heuristic_contact_form_url(url: str, html: str) -> bool:
    h = html.lower()
    if "<form" not in h:
        return False
    markers = (
        "type=\"email\"",
        "type='email'",
        'name="email"',
        "name='email'",
        "contact",
        "message",
        "your message",
        "get in touch",
    )
    return any(m in h for m in markers)


def pick_form_url(
    pages: list[tuple[str, str, str]]
) -> str | None:
    """
    pages: (url, raw_html, plain_text) for pages that have forms.
    Prefer URL path containing contact.
    """
    if not pages:
        return None
    scored: list[tuple[int, str]] = []
    for u, raw, _ in pages:
        low = u.lower()
        score = 0
        if "contact" in low:
            score += 10
        if low.rstrip("/").endswith("contact") or "contact-us" in low:
            score += 5
        scored.append((score, u))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def grok_chat_json(system: str, user: str) -> dict[str, Any]:
    key = grok_api_key()
    if not key:
        return {}
    r = requests.post(
        GROK_ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": GROK_MODEL,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return {}


def grok_pick_email(shop: str, website: str, candidates: list[str]) -> str | None:
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    user = json.dumps(
        {
            "shop_name": shop,
            "website": website,
            "candidate_emails": candidates,
        },
        indent=2,
    )
    sys = (
        "You choose ONE business contact email for a B2B retail intro. "
        "Return JSON only: {\"chosen\": \"email@domain.com\" | null}. "
        "chosen MUST be exactly one of candidate_emails. Prefer info@, hello@, contact@, shop@ over personal. "
        "If none fit, chosen null."
    )
    out = grok_chat_json(sys, user)
    ch = (out.get("chosen") or "").strip()
    if ch and ch.lower() in {c.lower() for c in candidates}:
        for c in candidates:
            if c.lower() == ch.lower():
                return c
    return candidates[0]


def grok_pick_contact_url(shop: str, website: str, urls: list[str]) -> str | None:
    if not urls:
        return None
    if len(urls) == 1:
        return urls[0]
    user = json.dumps(
        {"shop_name": shop, "website": website, "candidate_urls": urls},
        indent=2,
    )
    sys = (
        "You pick the single best URL where a human would submit a **contact** or **inquiry** form. "
        "Return JSON only: {\"chosen\": \"https://...\" | null}. "
        "chosen MUST be exactly one of candidate_urls, or null."
    )
    out = grok_chat_json(sys, user)
    ch = (out.get("chosen") or "").strip()
    if ch in urls:
        return ch
    for u in urls:
        if u.rstrip("/") == ch.rstrip("/"):
            return u
    return urls[0]


def main() -> None:
    p = argparse.ArgumentParser(description="Enrich Hit List contact from websites (AI: Enrich with contact queue).")
    p.add_argument("--limit", type=int, default=10, help="Max contact-enrich rows to process (default 10).")
    p.add_argument("--dry-run", action="store_true", help="Print plan only; do not write sheet.")
    p.add_argument("--sleep-fetch", type=float, default=0.4, help="Delay between HTTP fetches.")
    p.add_argument(
        "--no-grok",
        action="store_true",
        help="Do not call Grok (first email / first form URL heuristics only).",
    )
    p.add_argument(
        "--fill-gaps-limit",
        type=int,
        default=20,
        help="Max rows to fill empty Address/City/State/Lat/Lng/hours/Google listing cells from a "
        "place_id in Notes (default 20). Independent from --limit. Set 0 to disable.",
    )
    p.add_argument(
        "--no-fill-gaps",
        action="store_true",
        help="Disable the location/hours/listing fill-gap sweep entirely.",
    )
    p.add_argument(
        "--resolve-missing-place-id",
        action="store_true",
        help="In the fill-gap sweep, fall back to Find Place from Text when Notes has no place_id "
        "(needs Shop Name + some location text). Off by default to avoid extra Places billing.",
    )
    p.add_argument(
        "--find-radius-m",
        type=float,
        default=50000.0,
        help="Find Place locationbias radius in meters when --resolve-missing-place-id is set.",
    )
    args = p.parse_args()

    gc = gspread_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(HIT_LIST_WS)
    remark_ws = sh.worksheet(DAPP_REMARKS_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No data rows.")
        return
    header = rows[0]

    def idx(name: str) -> int:
        try:
            return header.index(name)
        except ValueError:
            raise SystemExit(f"Hit List missing required column {name!r}. Add it to row 1.")

    i_status = idx("Status")
    i_shop = idx("Shop Name")
    i_email = idx("Email")
    i_notes = idx("Notes")
    i_website = idx("Website")
    try:
        i_form = header.index("Contact Form URL")
    except ValueError:
        raise SystemExit(
            "Hit List missing column Contact Form URL (expected after Store Key, column AE). "
            "Add header Contact Form URL."
        )
    mkey = maps_api_key()
    use_grok = not args.no_grok and bool(grok_api_key())
    if not use_grok and not args.no_grok:
        print("Warning: GROK_API_KEY not set; running without Grok disambiguation.", flush=True)

    queued: list[tuple[int, list[str]]] = []
    for ri, row in enumerate(rows[1:], start=2):
        cells = row + [""] * (len(header) - len(row))
        if cells[i_status].strip() != QUEUE_STATUS:
            continue
        queued.append((ri, cells))
        if len(queued) >= max(1, args.limit):
            break

    if not queued:
        print(f"No rows with Status={QUEUE_STATUS!r} (limit {args.limit}).")
    else:
        print(f"Processing {len(queued)} row(s). dry_run={args.dry_run} grok={use_grok}", flush=True)

    contact_processed_rows: set[int] = set()

    for rn, cells in queued:
        shop = cells[i_shop].strip()
        notes = cells[i_notes].strip()
        website = cells[i_website].strip()
        pm = PLACE_ID_IN_NOTES.search(notes)
        pid = pm.group(1).strip() if pm else ""

        place_res: dict[str, Any] = {}
        if pid:
            place_res = place_details_full(mkey, pid)
            time.sleep(0.15)
        if not website:
            website = (place_res.get("website") or "").strip()

        if place_res:
            apply_place_result_to_row_gaps(
                ws, header, rn, cells, place_res,
                dry_run=args.dry_run, log_prefix="[fill] ",
            )
        contact_processed_rows.add(rn)

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")

        if not website:
            print(f"  row {rn} {shop!r}: no website — {STATUS_MANUAL}", flush=True)
            remark = f"[enrich-contact {stamp}] outcome=no_website"
            if not args.dry_run:
                append_dapp_remark_and_apply(
                    ws,
                    remark_ws,
                    rn,
                    shop,
                    STATUS_MANUAL,
                    remark,
                    SUBMITTED_BY_ENRICH,
                    submitted_at,
                    str(uuid.uuid4()),
                )
            continue

        page_triples, combined = collect_fetched_pages(website, args.sleep_fetch, 12000)
        emails = regex_emails(combined)

        form_pages: list[tuple[str, str, str]] = []
        for u, html, plain in page_triples:
            if heuristic_contact_form_url(u, html):
                form_pages.append((u, html, plain))

        chosen_email: str | None = None
        if emails:
            if use_grok and len(emails) > 1:
                chosen_email = grok_pick_email(shop, website, emails)
                time.sleep(0.5)
            else:
                chosen_email = emails[0]
            # prefer obvious business prefixes when Grok off
            if chosen_email is None and emails:
                chosen_email = emails[0]

        outcome_status = STATUS_MANUAL
        form_url_final: str | None = None

        if chosen_email:
            outcome_status = STATUS_EMAIL
            print(
                f"  row {rn} {shop!r}: {STATUS_EMAIL} email={chosen_email!r}",
                flush=True,
            )
            remark = f"[enrich-contact {stamp}] outcome=email website={website[:80]}"
            if not args.dry_run:
                ws.update_cell(rn, i_email + 1, chosen_email)
                append_dapp_remark_and_apply(
                    ws,
                    remark_ws,
                    rn,
                    shop,
                    outcome_status,
                    remark,
                    SUBMITTED_BY_ENRICH,
                    submitted_at,
                    str(uuid.uuid4()),
                )
        elif form_pages:
            candidates_urls = list({u for u, _, _ in form_pages})
            form_url_final = pick_form_url(form_pages)
            if use_grok and len(candidates_urls) > 1:
                g = grok_pick_contact_url(shop, website, candidates_urls)
                if g:
                    form_url_final = g
                time.sleep(0.5)
            outcome_status = STATUS_FORM
            print(
                f"  row {rn} {shop!r}: {STATUS_FORM} url={form_url_final!r}",
                flush=True,
            )
            remark = f"[enrich-contact {stamp}] outcome=contact_form website={website[:80]}"
            if not args.dry_run:
                ws.update_cell(rn, i_form + 1, form_url_final or "")
                append_dapp_remark_and_apply(
                    ws,
                    remark_ws,
                    rn,
                    shop,
                    outcome_status,
                    remark,
                    SUBMITTED_BY_ENRICH,
                    submitted_at,
                    str(uuid.uuid4()),
                )
        else:
            print(
                f"  row {rn} {shop!r}: {STATUS_MANUAL} (no email / no form heuristic)",
                flush=True,
            )
            remark = f"[enrich-contact {stamp}] outcome=manual website={website[:80]}"
            if not args.dry_run:
                append_dapp_remark_and_apply(
                    ws,
                    remark_ws,
                    rn,
                    shop,
                    STATUS_MANUAL,
                    remark,
                    SUBMITTED_BY_ENRICH,
                    submitted_at,
                    str(uuid.uuid4()),
                )

        time.sleep(0.35)

    fill_done = 0
    fill_skipped = 0
    fill_resolved_notes = 0
    fill_cap = 0 if args.no_fill_gaps else max(0, args.fill_gaps_limit)
    if fill_cap > 0:
        idx_notes = i_notes  # 0-based Notes column
        print(
            f"Fill-gap sweep: cap={fill_cap} resolve_missing_pid={bool(args.resolve_missing_place_id)}",
            flush=True,
        )
        for ri, raw_row in enumerate(rows[1:], start=2):
            if fill_done >= fill_cap:
                break
            if ri in contact_processed_rows:
                continue
            row = raw_row + [""] * (len(header) - len(raw_row))
            notes = row[idx_notes] if idx_notes < len(row) else ""
            if not has_any_gap(row, header):
                continue

            pm = PLACE_ID_IN_NOTES.search(notes or "")
            pid: str | None = pm.group(1).strip() if pm else None

            if not pid and args.resolve_missing_place_id:
                pid, reason = bl.resolve_place_id(
                    mkey, row, header, radius_m=args.find_radius_m
                )
                time.sleep(0.15)
                if not pid:
                    fill_skipped += 1
                    continue
                new_notes = bl.append_place_id_to_notes(notes, pid)
                if new_notes != (notes or ""):
                    if not args.dry_run:
                        ncell = rowcol_to_a1(ri, idx_notes + 1)
                        ws.update(
                            range_name=ncell,
                            values=[[new_notes]],
                            value_input_option="USER_ENTERED",
                        )
                        notes = new_notes
                        row[idx_notes] = new_notes
                        fill_resolved_notes += 1
                        print(
                            f"  [fill] row {ri}: appended place_id to Notes ({pid})",
                            flush=True,
                        )
                        time.sleep(0.5)
                    else:
                        print(
                            f"  [fill] row {ri}: dry-run would append place_id to Notes ({pid})",
                            flush=True,
                        )
            elif not pid:
                fill_skipped += 1
                continue

            assert pid is not None
            place_res = place_details_full(mkey, pid)
            time.sleep(0.15)
            if not place_res:
                fill_skipped += 1
                continue

            updated = apply_place_result_to_row_gaps(
                ws, header, ri, row, place_res,
                dry_run=args.dry_run, log_prefix="[fill] ",
            )
            if updated:
                fill_done += 1
                time.sleep(0.5)
            else:
                fill_skipped += 1

        print(
            f"Fill-gap sweep done. filled={fill_done} skipped={fill_skipped} "
            f"notes_place_id_appended={fill_resolved_notes} dry_run={args.dry_run}",
            flush=True,
        )

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
