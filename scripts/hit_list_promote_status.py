#!/usr/bin/env python3
"""
Hit List: automated status promotions with DApp Remarks (same apply path as photo review / enrich).

Modes:
  shortlisted-to-enrich — Status **AI: Shortlisted** → **AI: Enrich with contact**
    Guardrails: cap per run (--limit), and by default require **Website** OR **place_id** in **Notes**
    (so enrich-contact has something to work with). Optional --require-website for stricter checks.
    Does **not** change **AI: Contact Form found** (manual follow-up only).

  email-to-warmup — Status **AI: Email found** → **AI: Warm up prospect**
    Guardrails: cap per run (lower default), **Email** must be non-empty.
    **Never** targets Contact Form rows (they are not AI: Email found).

Each promotion: append **DApp Remarks** + apply to **Hit List** via **hit_list_dapp_remarks_sheet.append_dapp_remark_and_apply**.

Environment:
  - market_research/google_credentials.json

Usage:
  cd market_research
  python3 scripts/hit_list_promote_status.py shortlisted-to-enrich --dry-run --limit 5
  python3 scripts/hit_list_promote_status.py email-to-warmup --limit 3
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from hit_list_dapp_remarks_sheet import append_dapp_remark_and_apply

REPO = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
DAPP_REMARKS_WS = "DApp Remarks"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SUBMITTED_BY = "hit_list_status_promote"

STATUS_SHORTLISTED = "AI: Shortlisted"
STATUS_ENRICH = "AI: Enrich with contact"
STATUS_EMAIL_FOUND = "AI: Email found"
STATUS_WARMUP = "AI: Warm up prospect"
STATUS_CONTACT_FORM = "AI: Contact Form found"

PLACE_ID_IN_NOTES = re.compile(
    r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})",
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


def gspread_client() -> gspread.Client:
    load_dotenv_repo()
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def col_idx(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        raise SystemExit(f"Hit List missing required column {name!r}.")


def row_cells(row: list[str], width: int) -> list[str]:
    return row + [""] * (width - len(row))


def has_place_id(notes: str) -> bool:
    return bool(PLACE_ID_IN_NOTES.search((notes or "").strip()))


def enrich_predicate(cells: list[str], i_notes: int, i_website: int, require_website: bool) -> bool:
    website = (cells[i_website] or "").strip()
    notes = (cells[i_notes] or "").strip()
    if require_website:
        return bool(website)
    return bool(website) or has_place_id(notes)


def current_status(ws: gspread.Worksheet, row: int, col_1based: int) -> str:
    v = ws.cell(row, col_1based).value
    return (v or "").strip()


def run_shortlisted_to_enrich(
    ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    header: list[str],
    limit: int,
    dry_run: bool,
    require_website: bool,
    shop_filter: str | None,
) -> None:
    i_status = col_idx(header, "Status")
    i_shop = col_idx(header, "Shop Name")
    i_notes = col_idx(header, "Notes")
    i_website = col_idx(header, "Website")
    width = len(header)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No data rows.")
        return

    candidates: list[tuple[int, list[str]]] = []
    for ri, row in enumerate(rows[1:], start=2):
        cells = row_cells(row, width)
        if cells[i_status].strip() != STATUS_SHORTLISTED:
            continue
        if shop_filter and shop_filter.strip().lower() not in cells[i_shop].lower():
            continue
        if not enrich_predicate(cells, i_notes, i_website, require_website):
            continue
        candidates.append((ri, cells))
        if len(candidates) >= max(1, limit):
            break

    if not candidates:
        print(
            f"No rows with Status={STATUS_SHORTLISTED!r} passing guardrails "
            f"(limit={limit}, require_website={require_website}).",
            flush=True,
        )
        return

    pred = "Website or place_id in Notes" if not require_website else "Website only"
    print(
        f"Promoting {len(candidates)} row(s) → {STATUS_ENRICH!r} "
        f"(guardrail: {pred}). dry_run={dry_run}",
        flush=True,
    )

    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")

    for ri, cells in candidates:
        shop = cells[i_shop].strip()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        remarks = (
            f"Automated promotion {stamp}: {STATUS_SHORTLISTED} → {STATUS_ENRICH}. "
            f"Guardrails: cap/limit run, {pred}. "
            f"AI: Contact Form found rows are never auto-promoted (manual follow-up). "
            f"Next: hit_list_enrich_contact queue."
        )
        live = current_status(ws, ri, i_status + 1)
        if live != STATUS_SHORTLISTED:
            print(f"  skip row {ri} {shop!r}: status now {live!r}", flush=True)
            continue
        print(f"  row {ri} {shop!r}", flush=True)
        if dry_run:
            continue
        append_dapp_remark_and_apply(
            ws,
            remark_ws,
            ri,
            shop,
            STATUS_ENRICH,
            remarks,
            SUBMITTED_BY,
            submitted_at,
            str(uuid.uuid4()),
        )
        time.sleep(1.0)

    print("Done (shortlisted-to-enrich).", flush=True)


def run_email_to_warmup(
    ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    header: list[str],
    limit: int,
    dry_run: bool,
    shop_filter: str | None,
) -> None:
    i_status = col_idx(header, "Status")
    i_shop = col_idx(header, "Shop Name")
    i_email = col_idx(header, "Email")
    width = len(header)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No data rows.")
        return

    candidates: list[tuple[int, list[str]]] = []
    for ri, row in enumerate(rows[1:], start=2):
        cells = row_cells(row, width)
        st = cells[i_status].strip()
        if st != STATUS_EMAIL_FOUND:
            continue
        email = (cells[i_email] or "").strip()
        if not email:
            continue
        if shop_filter and shop_filter.strip().lower() not in cells[i_shop].lower():
            continue
        candidates.append((ri, cells))
        if len(candidates) >= max(1, limit):
            break

    if not candidates:
        print(
            f"No rows with Status={STATUS_EMAIL_FOUND!r} and non-empty Email "
            f"(limit={limit}).",
            flush=True,
        )
        return

    print(
        f"Promoting {len(candidates)} row(s) → {STATUS_WARMUP!r} "
        f"(enables warmup draft script). dry_run={dry_run}",
        flush=True,
    )

    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")

    for ri, cells in candidates:
        shop = cells[i_shop].strip()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        remarks = (
            f"Automated promotion {stamp}: {STATUS_EMAIL_FOUND} → {STATUS_WARMUP}. "
            f"Email present; capped batch. Implies readiness for Gmail warmup draft pipeline "
            f"(suggest_warmup_prospect_drafts). "
            f"Does not apply to {STATUS_CONTACT_FORM} (manual)."
        )
        live = current_status(ws, ri, i_status + 1)
        if live != STATUS_EMAIL_FOUND:
            print(f"  skip row {ri} {shop!r}: status now {live!r}", flush=True)
            continue
        live_email = (ws.cell(ri, i_email + 1).value or "").strip()
        if not live_email:
            print(f"  skip row {ri} {shop!r}: Email now empty", flush=True)
            continue
        print(f"  row {ri} {shop!r} email={live_email!r}", flush=True)
        if dry_run:
            continue
        append_dapp_remark_and_apply(
            ws,
            remark_ws,
            ri,
            shop,
            STATUS_WARMUP,
            remarks,
            SUBMITTED_BY,
            submitted_at,
            str(uuid.uuid4()),
        )
        time.sleep(1.0)

    print("Done (email-to-warmup).", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Hit List status promotions with DApp Remarks (guardrailed)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_s = sub.add_parser(
        "shortlisted-to-enrich",
        help=f"{STATUS_SHORTLISTED} → {STATUS_ENRICH}",
    )
    p_s.add_argument("--limit", type=int, default=15, help="Max rows per run (default 15).")
    p_s.add_argument(
        "--require-website",
        action="store_true",
        help="Require Website non-empty (ignore place_id-only Notes).",
    )
    p_s.add_argument("--dry-run", action="store_true", help="Print plan only; no sheet writes.")
    p_s.add_argument(
        "--shop",
        type=str,
        default="",
        help="Only rows whose Shop Name contains this substring (case-insensitive).",
    )

    p_e = sub.add_parser(
        "email-to-warmup",
        help=f"{STATUS_EMAIL_FOUND} → {STATUS_WARMUP}",
    )
    p_e.add_argument("--limit", type=int, default=5, help="Max rows per run (default 5).")
    p_e.add_argument("--dry-run", action="store_true", help="Print plan only; no sheet writes.")
    p_e.add_argument(
        "--shop",
        type=str,
        default="",
        help="Only rows whose Shop Name contains this substring (case-insensitive).",
    )

    args = p.parse_args()
    gc = gspread_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(HIT_LIST_WS)
    remark_ws = sh.worksheet(DAPP_REMARKS_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No Hit List header/data.")
        sys.exit(0)
    header = rows[0]

    shop_filter = (args.shop or "").strip() or None

    if args.cmd == "shortlisted-to-enrich":
        run_shortlisted_to_enrich(
            ws,
            remark_ws,
            header,
            args.limit,
            args.dry_run,
            args.require_website,
            shop_filter,
        )
    elif args.cmd == "email-to-warmup":
        run_email_to_warmup(
            ws,
            remark_ws,
            header,
            args.limit,
            args.dry_run,
            shop_filter,
        )
    else:
        p.error("Unknown command")


if __name__ == "__main__":
    main()
