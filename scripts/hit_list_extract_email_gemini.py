#!/usr/bin/env python3
"""
Given a Hit List row, fetch public website HTML (and a few guessed /contact URLs), collapse
to plain text, then ask **Gemini** to list **only** email addresses that appear **verbatim**
in that text (no guessing). A regex pass runs first so you often see candidates even if the
model refuses.

Env (market_research/.env, never commit):
  GEMINI_API_KEY — from https://aistudio.google.com/app/apikey
  (aliases: GOOGLE_API_KEY, or GEMINI_API if you renamed it)

Optional for website discovery when the sheet has no URL:
  GOOGLE_MAPS_API_KEY / GOOGLE_PLACES_API_KEY + place_id in Notes → Place Details website

Examples:
  cd market_research
  pip install -r requirements.txt

  python3 scripts/hit_list_extract_email_gemini.py --shop "Seagrape" --dry-run
  python3 scripts/hit_list_extract_email_gemini.py --row 492 --write-sheet

Expect many small shops to have **no** published email; output may be empty — that is normal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
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

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)

PLACE_ID_IN_NOTES = re.compile(
    r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})",
)
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Loose email harvest from raw HTML/text (pre-filter; Gemini still asked to confirm verbatim).
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


def gemini_api_key() -> str:
    load_dotenv_repo()
    k = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API")
    )
    if not k or not k.strip():
        raise SystemExit(
            "Set GEMINI_API_KEY (or GOOGLE_API_KEY) in market_research/.env — see .env.example"
        )
    return k.strip()


def maps_api_key() -> str | None:
    load_dotenv_repo()
    return os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")


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


def fetch_html(url: str, timeout: float = 18.0) -> str | None:
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
    """Cheap HTML → text; good enough for contact blurb."""
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


def collect_sources(base_url: str, sleep_s: float, max_chars_each: int) -> tuple[str, list[str]]:
    """Fetch base + contact paths; return concatenated plain text + list of URLs tried."""
    root = base_url.strip()
    if not root.lower().startswith(("http://", "https://")):
        root = "https://" + root
    parts: list[str] = []
    tried: list[str] = []
    for path in CONTACT_PATHS:
        u = urllib.parse.urljoin(root if root.endswith("/") else root + "/", path.lstrip("/"))
        if path == "/":
            u = root.rstrip("/") + "/" if not root.endswith("/") else root
        tried.append(u)
        html = fetch_html(u)
        time.sleep(max(0.0, sleep_s))
        if not html:
            continue
        txt = strip_tags_to_text(html, max_chars_each)
        if txt:
            parts.append(f"=== FETCHED URL: {u} ===\n{txt}")
    combined = "\n\n".join(parts)
    return combined, tried


def hit_list_row_by_number(ws: gspread.Worksheet, row_1based: int) -> tuple[int, list[str], list[str]]:
    """Return (row_1based, header, row_values) as list cells."""
    rows = ws.get_all_values()
    if row_1based < 2 or row_1based > len(rows):
        raise SystemExit(f"Row {row_1based} out of range (sheet has {len(rows)} rows)")
    header = rows[0]
    row = rows[row_1based - 1]
    return row_1based, header, row


def hit_list_find_shop(ws: gspread.Worksheet, needle: str) -> tuple[int, list[str], list[str]]:
    rows = ws.get_all_values()
    if len(rows) < 2:
        raise SystemExit("Hit List empty")
    header = rows[0]
    try:
        ni = header.index("Shop Name")
    except ValueError:
        raise SystemExit("Hit List missing Shop Name column")
    nlow = needle.strip().lower()
    for i, row in enumerate(rows[1:], start=2):
        if ni < len(row) and nlow in row[ni].strip().lower():
            return i, header, row
    raise SystemExit(f"No row with Shop Name matching {needle!r}")


def cell(row: list[str], header: list[str], name: str) -> str:
    try:
        i = header.index(name)
    except ValueError:
        return ""
    return row[i].strip() if i < len(row) else ""


def run_gemini(
    model_name: str,
    shop_name: str,
    city: str,
    source_text: str,
) -> dict[str, Any]:
    import google.generativeai as genai

    genai.configure(api_key=gemini_api_key())
    model = genai.GenerativeModel(model_name)

    prompt = f"""You extract **business contact emails** for outreach.

Store name (context only, may not appear in source): {shop_name}
City (context): {city}

Below is **SOURCE_TEXT** copied from the store's public website HTML (and maybe /contact pages).
**Rules:**
1. List **only** email addresses that appear **verbatim** in SOURCE_TEXT (exact substring match).
2. Do **not** infer, guess, or complete partial addresses. Do not use the store name alone.
3. Prefer emails that look like the business (info@, hello@, shop@, contact@) over random newsletter widgets; still only if verbatim in SOURCE_TEXT.
4. Ignore obvious placeholders (example.com, @sentry.wixpress.com, image filenames).

Return **only** valid JSON with this shape:
{{"emails": ["a@b.com"], "notes": "short reason or empty"}}

If there are no verbatim emails, return {{"emails": [], "notes": "none in source"}}.

SOURCE_TEXT:
---
{source_text}
---
"""
    cfg = {"temperature": 0.1, "max_output_tokens": 512}
    try:
        resp = model.generate_content(
            prompt,
            generation_config={**cfg, "response_mime_type": "application/json"},
        )
    except Exception:
        resp = model.generate_content(prompt, generation_config=cfg)

    raw = (resp.text or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"emails": [], "notes": "parse_error", "raw": raw[:500]}


def main() -> None:
    p = argparse.ArgumentParser(
        description="Extract contact emails for one Hit List row via website + Gemini (verbatim only)."
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--row", type=int, metavar="N", help="1-based sheet row (header is row 1)")
    g.add_argument("--shop", metavar="SUBSTRING", help="Match Shop Name (first hit, case-insensitive)")
    p.add_argument("--dry-run", action="store_true", help="Do not write Email column")
    p.add_argument("--write-sheet", action="store_true", help="Write first new email to Hit List Email column")
    p.add_argument(
        "--allow-questionable",
        action="store_true",
        help="If no regex-backed email, still write Gemini's first email (hallucination risk).",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        help='Gemini model id (default gemini-2.0-flash or $GEMINI_MODEL)',
    )
    p.add_argument("--sleep-fetch", type=float, default=0.35, help="Delay between HTTP fetches")
    p.add_argument("--max-chars-per-page", type=int, default=24000, help="Plain-text cap per fetched URL")
    args = p.parse_args()

    gc = gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
    if args.row:
        rn, header, row = hit_list_row_by_number(ws, args.row)
    else:
        rn, header, row = hit_list_find_shop(ws, args.shop)

    shop = cell(row, header, "Shop Name")
    city = cell(row, header, "City")
    website = cell(row, header, "Website")
    notes = cell(row, header, "Notes")
    existing_email = cell(row, header, "Email")

    if existing_email and not args.write_sheet:
        print(f"Row {rn} already has Email={existing_email!r}; use --write-sheet to overwrite.")

    mkey = maps_api_key()
    if not website.strip():
        pm = PLACE_ID_IN_NOTES.search(notes)
        pid = pm.group(1).strip() if pm else ""
        if pid and mkey:
            website = place_details_website(mkey, pid)
            time.sleep(0.2)
            print(f"Resolved website from Places: {website or '(none)'}")
        else:
            print("No Website on row and no place_id / Maps key to resolve.")

    if not website.strip():
        raise SystemExit("No website URL to fetch; add Website or ensure Notes has place_id + GOOGLE_MAPS_API_KEY")

    print(f"Row {rn}: {shop!r} | {city!r}")
    print(f"Fetching: {website}")

    source_text, tried = collect_sources(website, args.sleep_fetch, args.max_chars_per_page)
    if not source_text.strip():
        raise SystemExit(f"No HTML text fetched from URLs tried: {tried[:5]}…")

    reg = regex_emails(source_text)
    print(f"Regex candidates (verbatim in fetched text): {reg or '(none)'}")

    print(f"Calling Gemini ({args.model})…", flush=True)
    parsed = run_gemini(args.model, shop, city, source_text)
    emails = [str(x).strip() for x in (parsed.get("emails") or []) if str(x).strip()]
    # Intersection with regex adds safety against hallucination
    reg_set = {e.lower() for e in reg}
    safe = [e for e in emails if e.lower() in reg_set]
    questionable = [e for e in emails if e.lower() not in reg_set]

    print(json.dumps({"gemini_parsed": parsed, "safe_verbatim": safe, "model_not_in_regex": questionable}, indent=2))

    if args.write_sheet and not args.dry_run:
        pick = safe[0] if safe else ""
        if not pick and args.allow_questionable and emails:
            pick = emails[0]
            print(f"Using questionable model-only email (no regex hit): {pick!r}")
        if not pick:
            print("Nothing to write (no verbatim email in fetched HTML).")
            return
        try:
            ci = header.index("Email")
        except ValueError:
            raise SystemExit("Hit List missing Email column")
        ws.update_cell(rn, ci + 1, pick)
        print(f"Wrote Email={pick!r} to row {rn}.")
    elif args.write_sheet and args.dry_run:
        print("Dry-run: would write first safe email if any.")
    else:
        print("Done (no --write-sheet).")


if __name__ == "__main__":
    main()
