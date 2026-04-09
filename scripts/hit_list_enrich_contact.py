#!/usr/bin/env python3
"""
Hit List: process rows with Status **AI: Enrich with contact**.

For each row (default max 10 per run):
  - Resolve **Website** from the sheet or Google Places **website** (Notes must contain place_id if missing).
  - Fetch homepage + common /contact paths; extract emails (regex) and contact-form heuristics.
  - Optional **Grok** (text-only): pick one email from candidates, or pick best contact-page URL from a provided list.
  - Update the row and set **one** outcome status:
      **AI: Email found** + column Email (K),
      **AI: Contact Form found** + column Contact Form URL (AE),
      **AI: Enrich — manual** if neither works.

Does not send email or submit forms — enrichment only.

Environment:
  - google_credentials.json (Sheets editor)
  - GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY (Places Details for website)
  - GROK_API_KEY (optional with --no-grok; Grok skips when only one clear email)

Usage:
  cd market_research
  python3 scripts/hit_list_enrich_contact.py --dry-run --limit 2
  python3 scripts/hit_list_enrich_contact.py --limit 10
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials

REPO = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
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


def place_details_website(key: str, place_id: str) -> str:
    r = requests.get(
        DETAILS_URL,
        params={"place_id": place_id, "fields": "website", "key": key},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        return ""
    return ((data.get("result") or {}).get("website") or "").strip()


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
    p.add_argument("--limit", type=int, default=10, help="Max rows to process (default 10).")
    p.add_argument("--dry-run", action="store_true", help="Print plan only; do not write sheet.")
    p.add_argument("--sleep-fetch", type=float, default=0.4, help="Delay between HTTP fetches.")
    p.add_argument(
        "--no-grok",
        action="store_true",
        help="Do not call Grok (first email / first form URL heuristics only).",
    )
    args = p.parse_args()

    gc = gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
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
    try:
        i_upd_by = header.index("Status Updated By")
        i_upd_at = header.index("Status Updated Date")
    except ValueError:
        i_upd_by = -1
        i_upd_at = -1

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
        return

    print(f"Processing {len(queued)} row(s). dry_run={args.dry_run} grok={use_grok}", flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for rn, cells in queued:
        shop = cells[i_shop].strip()
        notes = cells[i_notes].strip()
        website = cells[i_website].strip()
        pm = PLACE_ID_IN_NOTES.search(notes)
        pid = pm.group(1).strip() if pm else ""

        if not website and pid:
            website = place_details_website(mkey, pid)
            time.sleep(0.15)

        note_add = f"[enrich-contact {stamp}]"
        if not website:
            print(f"  row {rn} {shop!r}: no website — {STATUS_MANUAL}", flush=True)
            new_notes = (notes + "\n" + note_add + " outcome=no_website").strip()
            if not args.dry_run:
                ws.update_cell(rn, i_status + 1, STATUS_MANUAL)
                ws.update_cell(rn, i_notes + 1, new_notes)
                if i_upd_by >= 0:
                    ws.update_cell(rn, i_upd_by + 1, "hit_list_enrich_contact")
                if i_upd_at >= 0:
                    ws.update_cell(rn, i_upd_at + 1, stamp[:10])
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
            new_notes = (
                notes + "\n" + note_add + f" outcome=email website={website[:80]}"
            ).strip()
            if not args.dry_run:
                ws.update_cell(rn, i_status + 1, STATUS_EMAIL)
                ws.update_cell(rn, i_email + 1, chosen_email)
                ws.update_cell(rn, i_notes + 1, new_notes)
                if i_upd_by >= 0:
                    ws.update_cell(rn, i_upd_by + 1, "hit_list_enrich_contact")
                if i_upd_at >= 0:
                    ws.update_cell(rn, i_upd_at + 1, stamp[:10])
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
            new_notes = (
                notes + "\n" + note_add + f" outcome=contact_form website={website[:80]}"
            ).strip()
            if not args.dry_run:
                ws.update_cell(rn, i_status + 1, STATUS_FORM)
                ws.update_cell(rn, i_form + 1, form_url_final or "")
                ws.update_cell(rn, i_notes + 1, new_notes)
                if i_upd_by >= 0:
                    ws.update_cell(rn, i_upd_by + 1, "hit_list_enrich_contact")
                if i_upd_at >= 0:
                    ws.update_cell(rn, i_upd_at + 1, stamp[:10])
        else:
            print(
                f"  row {rn} {shop!r}: {STATUS_MANUAL} (no email / no form heuristic)",
                flush=True,
            )
            new_notes = (
                notes + "\n" + note_add + f" outcome=manual website={website[:80]}"
            ).strip()
            if not args.dry_run:
                ws.update_cell(rn, i_status + 1, STATUS_MANUAL)
                ws.update_cell(rn, i_notes + 1, new_notes)
                if i_upd_by >= 0:
                    ws.update_cell(rn, i_upd_by + 1, "hit_list_enrich_contact")
                if i_upd_at >= 0:
                    ws.update_cell(rn, i_upd_at + 1, stamp[:10])

        time.sleep(0.35)

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
