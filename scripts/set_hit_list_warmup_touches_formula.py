#!/usr/bin/env python3
"""
Write Hit List formulas for outbound touch counts from **Email Agent Follow Up**:

- **Column AU** — warm-up **sent** count: ``status`` = ``warmup``.
- **Column AV** — follow-up **sent** count: ``status`` = ``follow_up``.

Each uses the same join keys as the sheet (**Store Key** in AD, else **Email** in K vs Follow Up
``store_key`` / ``to_email``). Counts are Gmail **Sent** rows classified by
``sync_email_agent_followup.py``, not draft rows on Email Agent Drafts.

Requires market_research/google_credentials.json with Editor access to the Hit List spreadsheet.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
# Column AU = warm-up sent count; AV = follow-up sent count (1-based A=1 …)
AU_COL_INDEX = 47
AV_COL_INDEX = 48
CRED_PATH = _REPO / "google_credentials.json"
SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
)


def _touch_count_formula(row: int, status: str) -> str:
    """Row is 2-based Hit List data row (matches Google row number)."""
    # Follow Up: C = store_key, E = to_email, J = status (after body_plain migration + status column).
    return (
        f'=IF($AD{row}<>"", '
        f'COUNTIFS(\'Email Agent Follow Up\'!$C:$C, $AD{row}, '
        f'\'Email Agent Follow Up\'!$J:$J, "{status}"), '
        f'IF($K{row}<>"", '
        f'COUNTIFS(\'Email Agent Follow Up\'!$E:$E, LOWER($K{row}), '
        f'\'Email Agent Follow Up\'!$J:$J, "{status}"), '
        f"0))"
    )


def _au_formula(row: int) -> str:
    return _touch_count_formula(row, "warmup")


def _av_formula(row: int) -> str:
    return _touch_count_formula(row, "follow_up")


def _sheet_range_a1(tab_title: str, a1_suffix: str) -> str:
    """Quote sheet tab for A1 notation (handles spaces and embedded quotes)."""
    t = tab_title or ""
    if "'" in t:
        return "'" + t.replace("'", "''") + "'!" + a1_suffix
    if any(ch in t for ch in (" ", ".")):
        return "'" + t + "'!" + a1_suffix
    return t + "!" + a1_suffix


def write_au_av_for_hit_list_rows(ws: gspread.Worksheet, rows: list[int]) -> int:
    """Write AU/AV COUNTIFS formulas for each 1-based Hit List row (typically new appends).

    Uses one ``values_batch_update`` call for all rows. Raises if the worksheet has fewer than
    **AV** columns in row 1.
    """
    uniq = sorted({int(r) for r in rows if r is not None and int(r) >= 2})
    if not uniq:
        return 0

    header = ws.row_values(1)
    if len(header) < AV_COL_INDEX:
        raise ValueError(
            f"Hit List row 1 has only {len(header)} columns; need at least {AV_COL_INDEX} (AV)."
        )

    tab = ws.title
    data: list[dict] = []
    for r in uniq:
        rng = _sheet_range_a1(tab, f"AU{r}:AV{r}")
        data.append({"range": rng, "values": [[_au_formula(r), _av_formula(r)]]})

    ws.spreadsheet.values_batch_update({"valueInputOption": "USER_ENTERED", "data": data})
    return len(uniq)


def main() -> None:
    if not CRED_PATH.is_file():
        raise SystemExit(f"Missing {CRED_PATH}")

    creds = Credentials.from_service_account_file(str(CRED_PATH), scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(HIT_LIST_WS)

    values = ws.get_all_values()
    if len(values) < 2:
        raise SystemExit("Hit List has no data rows.")

    header = values[0]
    if len(header) < AV_COL_INDEX:
        raise SystemExit(
            f"Hit List header has only {len(header)} columns; need at least {AV_COL_INDEX} (AV)."
        )
    au_header = header[AU_COL_INDEX - 1].strip()
    if au_header and "warm" not in au_header.lower():
        print(
            f"Warning: AU1 is {au_header!r} — expected something like 'Warm-up email sent'. Proceeding.",
            file=sys.stderr,
        )
    av_header = header[AV_COL_INDEX - 1].strip()
    if av_header and "follow" not in av_header.lower():
        print(
            f"Warning: AV1 is {av_header!r} — expected something like 'Follow-up emails sent'. Proceeding.",
            file=sys.stderr,
        )

    last_row = len(values)
    au_rng = f"AU2:AU{last_row}"
    av_rng = f"AV2:AV{last_row}"
    au_formulas = [[_au_formula(r)] for r in range(2, last_row + 1)]
    av_formulas = [[_av_formula(r)] for r in range(2, last_row + 1)]

    print(f"Updating {au_rng} ({len(au_formulas)} rows) …", file=sys.stderr)
    ws.update(range_name=au_rng, values=au_formulas, value_input_option="USER_ENTERED")
    print(f"Updating {av_rng} ({len(av_formulas)} rows) …", file=sys.stderr)
    ws.update(range_name=av_rng, values=av_formulas, value_input_option="USER_ENTERED")
    print(f"OK: wrote AU warm-up + AV follow-up COUNTIFS into {au_rng} and {av_rng}.", file=sys.stderr)


if __name__ == "__main__":
    main()
