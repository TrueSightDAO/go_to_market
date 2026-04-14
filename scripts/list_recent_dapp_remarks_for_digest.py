#!/usr/bin/env python3
"""
Print recent rows from tab **DApp Remarks** on the Hit List workbook — for drafting **Beer Hall**
digests (field / partner **offline** turn-by-turn notes that do not appear in Git or Telegram logs).

Uses **Submitted At** when parseable. Filters to the last **--hours** (default 48). By default
**--humans-only** drops rows whose **Submitted By** looks like known automation (Hit List scripts,
batch jobs); pass **--include-automation** to show everything for auditing.

Spreadsheet: https://docs.google.com/spreadsheets/d/1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc/edit
Tab: **DApp Remarks** (often first tab / `gid=0`)

Usage (from market_research/):
  python3 scripts/list_recent_dapp_remarks_for_digest.py
  python3 scripts/list_recent_dapp_remarks_for_digest.py --hours 72
  python3 scripts/list_recent_dapp_remarks_for_digest.py --include-automation

Requires: google_credentials.json; spreadsheet shared with the service account (Editor).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
DAPP_REMARKS_WS = "DApp Remarks"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Substrings (normalized) in Submitted By → treat as automation unless --include-automation
_AUTOMATION_MARKERS = (
    "hit_list_",
    "field_agent",
    "enrich_contact",
    "photo_review",
    "suggest_manager",
    "places_pull",
    "process_dapp",
    "append_",
    "google_apps_script",
    "gmail_oauth",
    "workflow_dispatch",
    "github actions",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _parse_sheet_date(raw: str) -> datetime | None:
    t = (raw or "").strip()
    if not t:
        return None
    if re.fullmatch(r"\d{8}", t):
        try:
            return datetime.strptime(t, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(t[:19] if len(t) > 10 else t, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        if "T" in t:
            return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        pass
    return None


def _col_map(header: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for j, cell in enumerate(header):
        key = _norm(cell)
        if not key:
            continue
        out[key] = j
    return out


def _find_col(m: dict[str, int], *names: str) -> int | None:
    for want in names:
        w = _norm(want)
        for k, j in m.items():
            if k == w or k.replace(" ", "_") == w or w in k:
                return j
    return None


def _is_automation_submitter(submitted_by: str) -> bool:
    s = _norm(submitted_by)
    if not s:
        return True
    return any(m in s for m in _AUTOMATION_MARKERS)


def _meaningful_remark(remarks: str) -> bool:
    r = (remarks or "").strip()
    if len(r) < 8:
        return False
    if _norm(r) in ("n/a", "-", "none"):
        return False
    return True


def get_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours", type=float, default=48.0, help="Look-back window from Submitted At (default 48)")
    p.add_argument(
        "--max-rows",
        type=int,
        default=800,
        help="Max data rows to scan from the bottom of the sheet (default 800)",
    )
    p.add_argument("--sheet", default=DAPP_REMARKS_WS, help="Worksheet title")
    p.add_argument(
        "--include-automation",
        action="store_true",
        help="Include script/system Submitted By rows (default: humans-oriented filter on)",
    )
    args = p.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    gc = get_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(args.sheet)
    except gspread.WorksheetNotFound:
        sys.stderr.write(
            f"Worksheet {args.sheet!r} not found. Check tab name matches exactly.\n"
        )
        sys.exit(1)

    all_vals = ws.get_all_values()
    if not all_vals:
        print("(empty worksheet)")
        return

    header = all_vals[0]
    cmap = _col_map(header)
    i_sub_at = _find_col(cmap, "Submitted At", "submitted_at")
    i_remarks = _find_col(cmap, "Remarks", "remark")
    i_shop = _find_col(cmap, "Shop Name", "shop name")
    i_status = _find_col(cmap, "Status")
    i_by = _find_col(cmap, "Submitted By", "submitted_by")
    i_proc = _find_col(cmap, "Processed")

    if i_remarks is None:
        sys.stderr.write(
            "Could not find Remarks column. Headers: " + ", ".join(h for h in header if h)[:500] + "\n"
        )
        sys.exit(1)
    if i_sub_at is None:
        sys.stderr.write(
            "Could not find Submitted At column. Headers: " + ", ".join(h for h in header if h)[:500] + "\n"
        )
        sys.exit(1)

    data_rows = all_vals[1:]
    if args.max_rows > 0 and len(data_rows) > args.max_rows:
        data_rows = data_rows[-args.max_rows :]

    max_i = max(i for i in (i_sub_at, i_remarks, i_shop, i_status, i_by, i_proc) if i is not None)

    candidates: list[tuple[datetime | None, str]] = []
    for row in data_rows:
        while len(row) <= max_i:
            row.append("")
        raw_at = row[i_sub_at] if i_sub_at < len(row) else ""
        dt = _parse_sheet_date(raw_at)
        remarks = row[i_remarks] if i_remarks < len(row) else ""
        shop = row[i_shop] if i_shop is not None and i_shop < len(row) else ""
        status = row[i_status] if i_status is not None and i_status < len(row) else ""
        by = row[i_by] if i_by is not None and i_by < len(row) else ""
        proc = row[i_proc] if i_proc is not None and i_proc < len(row) else ""

        if not _meaningful_remark(remarks):
            continue
        if not args.include_automation and _is_automation_submitter(by):
            continue
        if dt is not None and dt < cutoff:
            continue
        if dt is None:
            continue

        snippet = re.sub(r"\s+", " ", remarks).strip()
        if len(snippet) > 260:
            snippet = snippet[:257] + "…"
        shop_bit = f"{shop.strip()} — " if shop and shop.strip() else ""
        who = (by or "").strip() or "Unknown"
        st = (status or "").strip()
        st_bit = f" [status: {st[:72]}]" if st else ""
        proc_bit = ""
        if proc and _norm(proc) not in ("", "no", "n"):
            proc_bit = " _(processed)_"
        line = f"- {shop_bit}{snippet} _(by {who})_{st_bit}{proc_bit}"
        candidates.append((dt, line))

    candidates.sort(key=lambda x: (x[0] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    filter_note = "all submitters" if args.include_automation else "human-oriented (automation Submitted By filtered out)"
    print(
        f"# DApp Remarks — rows with Submitted At on/after {cutoff.isoformat()} UTC "
        f"(~{args.hours}h look-back; {filter_note})\n"
        f"# Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0\n"
        f"# Tab: {args.sheet!r}\n"
        "# Use under Community in Beer Hall Message 2 (offline / field narrative). "
        "Dedup vs Git bullets and Telegram log lines.\n"
    )
    if not candidates:
        print(
            "(no qualifying rows — widen --hours, try --include-automation, "
            "or confirm Submitted At parses as ISO / YYYY-MM-DD)"
        )
        return
    for _, line in candidates:
        print(line)


if __name__ == "__main__":
    main()
