#!/usr/bin/env python3
"""Push the Content Marketing Schedule sheet into a dedicated Google Calendar.

Creates (once) a calendar named 'Agroverse Content Schedule' and keeps it in sync.

Rules:
  * Instagram tab  -> FUTURE posts only by default (--include-past to backfill)
  * Blog tabs      -> PUBLISHED rows only. An unpublished draft must never appear
                      on a public-facing content calendar.
  * LinkedIn / Email Newsletter tabs are headerless shells; skipped cleanly.

Idempotency: every event carries
    extendedProperties.private.cs_key = "<tab>:<primary_key>"
so a re-run PATCHES the existing event in place. It never creates duplicates.
Getting this wrong is the difference between a calendar and a mess -- a naive
re-run on a 130-event calendar would double it.

Usage:
    python3 scripts/sync_content_schedule_calendar.py            # forward view
    python3 scripts/sync_content_schedule_calendar.py --include-past
    python3 scripts/sync_content_schedule_calendar.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "1ghZXeMqFq97Vl6yLKrtDmMQdQkd-4EN5yQs34NA_sBQ"
SA_KEY_PATH = "/opt/truesight_autopilot/config/google/agroverse_ledger_manager_gdrive_key.json"
TOKEN_PATH = "/opt/truesight_autopilot/config/gmail/admin_token.json"

CAL_NAME = "Agroverse Content Schedule"
TZ = "America/Los_Angeles"
SHARE_WITH = ["garyjob@agroverse.shop"]

# tab -> (date column, title column, extra description columns, published-only?)
TABS = {
    "Instagram Content Schedule": {
        "date": "Post Day",
        "title": "Description",
        "extra": ["Post Type", "Theme", "Theme Focus", "status", "CTA"],
        "prefix": "[POST]",
        "published_only": False,
    },
    "Agroverse Blog Content Schedule": {
        "date": "Publish Date",
        "title": "Blog Title",
        "extra": ["Theme", "status", "SEO Keywords", "Live URL"],
        "prefix": "[AGROVERSE]",
        "published_only": True,
    },
    "TrueSight Blog Content Schedule": {
        "date": "Publish Date",
        "title": "Blog Title",
        "extra": ["Theme", "status", "SEO Keywords", "Live URL"],
        "prefix": "[TRUESIGHT]",
        "published_only": True,
    },
}


def calendar_service():
    raw = json.load(open(TOKEN_PATH))
    cred = Credentials(
        token=raw.get("token"),
        refresh_token=raw.get("refresh_token"),
        token_uri=raw.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=raw.get("client_id"),
        client_secret=raw.get("client_secret"),
        scopes=raw.get("scopes"),
    )
    return build("calendar", "v3", credentials=cred, cache_discovery=False)


def sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY_PATH, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_or_create_calendar(svc, apply: bool) -> str:
    for c in svc.calendarList().list().execute().get("items", []):
        if c.get("summary") == CAL_NAME:
            print(f"calendar exists: {c['id']}")
            return c["id"]
    if not apply:
        print(f"[DRY] would create calendar '{CAL_NAME}'")
        return "DRY-RUN-CALENDAR"
    body = {
        "summary": CAL_NAME,
        "description": (
            "Forward content calendar for Agroverse / TrueSight DAO. Auto-synced from "
            "the '20250924 - Instagram Content Marketing Schedule' sheet. "
            "Edit the sheet, not the calendar."
        ),
        "timeZone": TZ,
    }
    cal = svc.calendars().insert(body=body).execute()
    print(f"calendar CREATED: {cal['id']}")
    for addr in SHARE_WITH:
        try:
            svc.acl().insert(
                calendarId=cal["id"],
                body={"role": "writer", "scope": {"type": "user", "value": addr}},
            ).execute()
            print(f"  shared writer -> {addr}")
        except Exception as e:  # noqa: BLE001 - sharing is best-effort
            print(f"  share failed -> {addr}: {type(e).__name__}: {e}")
    return cal["id"]


def parse_day(s: str) -> date | None:
    s = (s or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def existing_by_key(svc, cal_id: str) -> dict[str, str]:
    out, tok = {}, None
    while True:
        r = (
            svc.events()
            .list(calendarId=cal_id, maxResults=2500, singleEvents=True, pageToken=tok)
            .execute()
        )
        for e in r.get("items", []):
            k = (e.get("extendedProperties", {}).get("private", {}) or {}).get("cs_key")
            if k:
                out[k] = e["id"]
        tok = r.get("nextPageToken")
        if not tok:
            return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-past", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply = not args.dry_run

    svc = calendar_service()
    cal_id = get_or_create_calendar(svc, apply)
    sh = sheets_service()
    today = date.today()

    existing = existing_by_key(svc, cal_id) if apply else {}
    print(f"existing synced events: {len(existing)}")

    totals = {"create": 0, "update": 0, "skip_past": 0, "skip_unpub": 0, "skip_baddate": 0}
    seen: set[str] = set()

    for tab, cfg in TABS.items():
        v = (
            sh.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!A1:R600")
            .execute()
            .get("values", [])
        )
        if not v:
            print(f"  {tab}: EMPTY (headerless shell) -- nothing to sync")
            continue
        hdr = [h.strip() for h in v[0]]
        ix = {h: i for i, h in enumerate(hdr)}
        if cfg["date"] not in ix or cfg["title"] not in ix:
            print(f"  {tab}: missing {cfg['date']!r}/{cfg['title']!r} -- SKIPPED")
            continue

        n_c = n_u = 0
        for row in [r + [""] * (len(hdr) - len(r)) for r in v[1:]]:
            d = parse_day(row[ix[cfg["date"]]])
            if not d:
                totals["skip_baddate"] += 1
                continue
            if d < today and not args.include_past:
                totals["skip_past"] += 1
                continue
            if cfg["published_only"] and row[ix.get("status", 0)].strip().upper() != "PUBLISHED":
                totals["skip_unpub"] += 1
                continue

            primary = row[ix["primary_key"]].strip() if "primary_key" in ix else str(d)
            key = f"{tab}:{primary}"
            if key in seen:
                continue
            seen.add(key)

            bits = [
                f"{c}: {row[ix[c]].strip()[:400]}"
                for c in cfg["extra"]
                if c in ix and row[ix[c]].strip()
            ]
            bits.append(f"sheet: {tab} - primary_key: {primary}")
            body = {
                "summary": f"{cfg['prefix']} {row[ix[cfg['title']]].strip()[:120]}",
                "description": "\n".join(bits),
                "start": {"date": d.isoformat()},
                "end": {"date": (d + timedelta(days=1)).isoformat()},
                "extendedProperties": {
                    "private": {"cs_key": key, "sheet_tab": tab, "primary_key": primary}
                },
            }
            if not apply:
                totals["create"] += 1
                continue
            if key in existing:
                svc.events().patch(calendarId=cal_id, eventId=existing[key], body=body).execute()
                totals["update"] += 1
                n_u += 1
            else:
                svc.events().insert(calendarId=cal_id, body=body).execute()
                totals["create"] += 1
                n_c += 1
        print(f"  {tab}: {n_c} created, {n_u} updated")

    print(
        "\nTOTALS "
        + " ".join(f"{k}={v}" for k, v in totals.items())
    )
    print(f"cal_id={cal_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
