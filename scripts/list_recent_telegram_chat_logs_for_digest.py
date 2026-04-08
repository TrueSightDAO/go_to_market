#!/usr/bin/env python3
"""
Print recent rows from tab **Telegram Chat Logs** on the TrueSight DAO Telegram compilation
sheet — for drafting **Beer Hall** digests (community contributions / Telegram activity not
visible from Git alone).

Uses **Status date** (or similar) when parseable; otherwise **Created**-style columns if
present. Filters to the last **--hours** (default 24), then prints plain-language bullets for
copy-paste. **Human/agent** still dedupes against the Git poll and the draft TLDR (this script
does not read WhatsApp).

Spreadsheet: https://docs.google.com/spreadsheets/d/1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ/edit
Tab: **Telegram Chat Logs** (often `gid=0`)

Usage (from market_research/):
  python3 scripts/list_recent_telegram_chat_logs_for_digest.py
  python3 scripts/list_recent_telegram_chat_logs_for_digest.py --hours 48
  python3 scripts/list_recent_telegram_chat_logs_for_digest.py --max-rows 800

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
SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
TELEGRAM_LOG_WS = "Telegram Chat Logs"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER_ALIASES_DATE = (
    "status date",
    "status_date",
    "date",
    "posted",
    "created",
    "timestamp",
)
HEADER_ALIASES_CONTRIBUTION = (
    "contribution made",
    "contribution_made",
    "message",
    "telegram message",
)
HEADER_ALIASES_CONTRIBUTOR = (
    "contributor name",
    "contributor_name",
    "contributor",
    "from",
)
HEADER_ALIASES_PROJECT = (
    "project name",
    "project_name",
    "project",
)
HEADER_ALIASES_STATUS = (
    "status",
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


def _header_row_index(rows: list[list[str]]) -> int:
    for i, row in enumerate(rows[:15]):
        joined = " ".join(_norm(c) for c in row[:6])
        if "telegram update" in joined and ("contribution" in joined or "chatroom" in joined):
            return i
        if row and _norm(row[0]) in ("telegram update id", "update id"):
            return i
    return 0


def _col_map(header: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for j, cell in enumerate(header):
        key = _norm(cell)
        if not key:
            continue
        out[key] = j
    return out


def _find_col(m: dict[str, int], aliases: tuple[str, ...]) -> int | None:
    for a in aliases:
        for k, j in m.items():
            if k == a or k.replace(" ", "_") == a or a in k:
                return j
    return None


def _meaningful(contribution: str, status: str) -> bool:
    c = (contribution or "").strip()
    if len(c) < 12:
        return False
    if _norm(c) in ("unknown", "invalid", "n/a", "-"):
        return False
    st = _norm(status)
    if st == "invalid" and len(c) < 40:
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
    p.add_argument("--hours", type=float, default=24.0, help="Look-back window (default 24)")
    p.add_argument(
        "--max-rows",
        type=int,
        default=600,
        help="Max data rows to scan from the bottom of the sheet (default 600)",
    )
    p.add_argument("--sheet", default=TELEGRAM_LOG_WS, help="Worksheet title")
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

    hdr_idx = _header_row_index(all_vals)
    header = all_vals[hdr_idx]
    cmap = _col_map(header)
    i_date = _find_col(cmap, HEADER_ALIASES_DATE)
    i_contrib = _find_col(cmap, HEADER_ALIASES_CONTRIBUTION)
    i_name = _find_col(cmap, HEADER_ALIASES_CONTRIBUTOR)
    i_proj = _find_col(cmap, HEADER_ALIASES_PROJECT)
    i_status = _find_col(cmap, HEADER_ALIASES_STATUS)

    if i_contrib is None:
        # Fall back: "Telegram Message ID" column sometimes holds long text in broken layouts;
        # prefer column containing "contribution" in header label
        for k, j in cmap.items():
            if "contribution" in k:
                i_contrib = j
                break

    if i_contrib is None:
        sys.stderr.write(
            "Could not find a Contribution / message column. Headers: "
            + ", ".join(h for h in header if h)[:500]
            + "\n"
        )
        sys.exit(1)

    data_rows = all_vals[hdr_idx + 1 :]
    if args.max_rows > 0 and len(data_rows) > args.max_rows:
        data_rows = data_rows[-args.max_rows :]

    candidates: list[tuple[datetime | None, str]] = []
    idxs = [x for x in (i_date, i_contrib, i_name, i_proj, i_status) if x is not None]
    max_i = max(idxs) if idxs else i_contrib

    for row in data_rows:
        while len(row) <= max_i:
            row.append("")
        dt = None
        if i_date is not None and i_date < len(row):
            dt = _parse_sheet_date(row[i_date])
        contrib = row[i_contrib] if i_contrib < len(row) else ""
        status = row[i_status] if i_status is not None and i_status < len(row) else ""
        name = row[i_name] if i_name is not None and i_name < len(row) else ""
        proj = row[i_proj] if i_proj is not None and i_proj < len(row) else ""

        if not _meaningful(contrib, status):
            continue
        if dt is not None and dt < cutoff:
            continue
        # If no parseable date, include row only when scanning recent tail (heuristic: last 30 rows)
        if dt is None:
            continue

        snippet = contrib.replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = snippet[:217] + "…"
        who = (name or "").strip() or "Contributor"
        proj_bit = f" ({proj.strip()})" if proj and proj.strip() and _norm(proj) != "unknown" else ""
        line = f"- {who}{proj_bit}: {snippet}"
        if status and _norm(status) not in ("unknown",):
            line += f" [status: {status.strip()[:80]}]"
        candidates.append((dt, line))

    candidates.sort(key=lambda x: (x[0] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    print(
        f"# Telegram Chat Logs — rows with parseable date on/after "
        f"{cutoff.isoformat()} UTC (~{args.hours}h look-back)\n"
        f"# Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0\n"
        f"# Tab: {args.sheet!r}\n"
        f"# Dedup: skip any line already covered by the Git poll or today's draft TLDR.\n"
    )
    if not candidates:
        print("(no qualifying rows in this window — widen --hours or check Status date column)")
        return
    for _, line in candidates:
        print(line)


if __name__ == "__main__":
    main()
