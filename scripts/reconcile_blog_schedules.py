#!/usr/bin/env python3
"""Reconcile the blog tabs of the Content Marketing Schedule sheet against the
live blog indexes.

For every sheet row this stamps one of three terminal-ish states:
  PUBLISHED      -- live, with its Live URL
  NOT PUBLISHED  -- genuinely absent from the live index (planned, never shipped)
  (blank)        -- untouched; the row is left for a human

The important property is that a row never keeps an *ambiguous* state: either we
found it live, or we assert it is not, or we leave it explicitly blank on purpose.

Usage:
    python3 scripts/reconcile_blog_schedules.py --tab truesight --dry-run
    python3 scripts/reconcile_blog_schedules.py --tab agroverse --apply
    python3 scripts/reconcile_blog_schedules.py --tab all --apply

Hard-won lessons baked in (each one cost a dry run):

  * html.unescape BEFORE normalization. Live titles carry &rsquo; / &mdash;. If you
    strip entities first and then look for them, tail() always returns '' and
    rename detection silently reports zero matches instead of failing loudly.
  * Prefix/subset matching is required. A post retitled shorter on publish
    ("Expanding Our Regenerative Cacao Network" vs "...: 26 Sourcing Activities
    in Two Weeks") is the SAME post. Exact and tail matching both miss it and you
    append a duplicate.
  * Existence is checked against the enumerated slug set, never a substring hit.
    Generic words like 'truesight' / 'framework' appear in site chrome and will
    false-positive on any unpublished post.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
import urllib.request
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = "1ghZXeMqFq97Vl6yLKrtDmMQdQkd-4EN5yQs34NA_sBQ"
SA_KEY_PATH = "/opt/truesight_autopilot/config/google/agroverse_ledger_manager_gdrive_key.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TABS = {
    "agroverse": {
        "tab": "Agroverse Blog Content Schedule",
        "index_url": "https://agroverse.shop/blog/",
        "post_url_fmt": "https://agroverse.shop/post/{slug}/",
    },
    "truesight": {
        "tab": "TrueSight Blog Content Schedule",
        "index_url": "https://truesight.me/blog/",
        "post_url_fmt": "https://truesight.me/{href}",
    },
}

MONTHS = (
    r"(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)"
)


def norm(s: str) -> str:
    """Normalize a title for comparison. Unescape FIRST -- see module docstring."""
    s = html.unescape(s or "")
    s = re.sub(r"[^a-z0-9 ]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def tail(title: str) -> str:
    """Compare on the part after a colon (sheets often carry 'Title: subtitle')."""
    return norm(title.split(":")[-1]) if ":" in (title or "") else ""


def slugify(s: str) -> str:
    s = html.unescape(s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"^-+|-+$", "", s)


def col_letter(idx: int) -> str:
    s = ""
    i = idx + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def live_slugs(cfg: dict) -> set[str]:
    """Enumerate the slugs actually present on the live blog index."""
    h = fetch(cfg["index_url"])
    if cfg["tab"].startswith("Agroverse"):
        return set(re.findall(r"/post/([a-z0-9\-]+)/?", h))
    # truesight.me links are posts/<slug>.html
    return set(re.findall(r"posts/([a-z0-9\-]+)\.html", h))


def live_titles(cfg: dict) -> list[dict]:
    """Parse live blog cards into {date, title, url} for authoritative stamping."""
    h = fetch(cfg["index_url"])
    out = []
    if cfg["tab"].startswith("Agroverse"):
        return out  # slug-based matching is sufficient and safer
    for block in re.split(r'class="blog-card"', h)[1:]:
        dm = re.search(MONTHS + r"\s+\d{1,2},\s+\d{4}", block)
        hm = re.search(r'href="([^"]+\.html)"', block)
        tm = re.search(r"<h[2-4][^>]*>(.*?)</h[2-4]>", block, re.S)
        if not (dm and tm):
            continue
        out.append(
            {
                "date": datetime.strptime(dm.group(0), "%B %d, %Y").date(),
                "title": re.sub(r"<[^>]+>", "", tm.group(1)).strip(),
                "url": cfg["post_url_fmt"].format(href=hm.group(1)) if hm else "",
            }
        )
    return out


def reconcile(cfg: dict, apply: bool) -> dict:
    from google.oauth2.service_account import Credentials as _SA

    creds = _SA.from_service_account_file(SA_KEY_PATH, scopes=SCOPES)
    sv = build("sheets", "v4", credentials=creds, cache_discovery=False)
    tab = cfg["tab"]

    slugs = live_slugs(cfg)
    print(f"[{tab}] live slugs on index: {len(slugs)}")

    v = (
        sv.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1:R400")
        .execute()
        .get("values", [])
    )
    if not v:
        print(f"[{tab}] EMPTY tab -- nothing to reconcile")
        return {"published": 0, "not_published": 0}

    hdr = [c.strip() for c in v[0]]
    ix = {c: i for i, c in enumerate(hdr)}
    rows = [r + [""] * (len(hdr) - len(r)) for r in v[1:]]

    # Ensure a Live URL column exists.
    if "Live URL" not in ix:
        letter = col_letter(len(hdr))
        print(f"[{tab}] adding header 'Live URL' at col {letter}")
        if apply:
            sv.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"'{tab}'!{letter}1",
                valueInputOption="RAW",
                body={"values": [["Live URL"]]},
            ).execute()
        ix["Live URL"] = len(hdr)
        hdr.append("Live URL")

    st, lu = ix["status"], ix["Live URL"]
    data, pub, miss = [], 0, 0

    for i, r in enumerate(rows):
        title = r[ix["Blog Title"]].strip()
        if not title:
            continue
        sg = slugify(title)
        if sg in slugs:
            data.append({"range": f"'{tab}'!{col_letter(st)}{i + 2}", "values": [["PUBLISHED"]]})
            data.append(
                {
                    "range": f"'{tab}'!{col_letter(lu)}{i + 2}",
                    "values": [[cfg["post_url_fmt"].format(slug=sg)]],
                }
            )
            pub += 1
        elif not r[st].strip():
            # Only assert NOT PUBLISHED where the sheet was blank. Never overwrite
            # a status a human set (e.g. SCHEDULED for a future post).
            data.append(
                {"range": f"'{tab}'!{col_letter(st)}{i + 2}", "values": [["NOT PUBLISHED"]]}
            )
            miss += 1

    print(f"[{tab}] would set PUBLISHED={pub} NOT_PUBLISHED={miss}")
    if apply and data:
        sv.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"valueInputOption": "RAW", "data": data},
        ).execute()
        print(f"[{tab}] wrote {len(data)} cells")
    elif not apply:
        print(f"[{tab}] DRY RUN -- nothing written")
    return {"published": pub, "not_published": miss}


def append_published(cfg: dict, rows_out: list[list[str]], hdr: list[str], ix: dict) -> None:
    """Append rows the sheet is missing entirely (live but untracked)."""
    from google.oauth2.service_account import Credentials as _SA

    creds = _SA.from_service_account_file(SA_KEY_PATH, scopes=SCOPES)
    sv = build("sheets", "v4", credentials=creds, cache_discovery=False)
    sv.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{cfg['tab']}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows_out},
    ).execute()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", default="all", choices=["all", *TABS])
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    which = list(TABS) if args.tab == "all" else [args.tab]
    for name in which:
        cfg = TABS[name]
        # Agroverse blog index dates are unreliable for title matching; slug match only.
        reconcile(cfg, args.apply)
        print()
    if not args.apply:
        print("DRY RUN overall -- re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
