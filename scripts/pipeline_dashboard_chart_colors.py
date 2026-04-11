#!/usr/bin/env python3
"""
Re-apply bar colors on the holistic wellness Hit List "Pipeline Dashboard" chart.

Google Sheets PieChartSpec has no per-slice color fields in the API, so the dashboard
uses a horizontal bar chart with one color per category. Each bar is tinted by the
status row in the States tab (Research = lightest, Not Appropriate = darkest).

Requires: market_research/google_credentials.json with access to the spreadsheet.

Usage:
  cd market_research && python3 scripts/pipeline_dashboard_chart_colors.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
CHART_ID = 1799317612

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _rgb_for_states_index(idx: int | None, max_i: int) -> tuple[float, float, float]:
    if idx is None or idx < 0:
        return (0.65, 0.65, 0.65)
    t = idx / max_i
    r1, g1, b1 = 0.91, 0.97, 0.93
    r2, g2, b2 = 0.05, 0.38, 0.17
    return (_lerp(r1, r2, t), _lerp(g1, g2, t), _lerp(b1, b2, t))


def _style_entry(i: int, rgb: tuple[float, float, float]) -> dict:
    r, g, b = rgb
    return {
        "index": i,
        "color": {"red": r, "green": g, "blue": b},
        "colorStyle": {"rgbColor": {"red": r, "green": g, "blue": b}},
    }


def main() -> int:
    if not _SA_CREDS.is_file():
        print(f"Missing {_SA_CREDS}", file=sys.stderr)
        return 1

    creds = Credentials.from_service_account_file(str(_SA_CREDS), scopes=SCOPES)
    svc = build("sheets", "v4", credentials=creds)

    meta = svc.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields="sheets(properties(title),charts)",
    ).execute()

    spec = None
    for sh in meta.get("sheets", []):
        for c in sh.get("charts", []):
            if c.get("chartId") == CHART_ID:
                spec = c.get("spec")
                break
        if spec:
            break
    if not spec:
        print(f"Chart {CHART_ID} not found.", file=sys.stderr)
        return 1

    states_vals = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="States!A10:B35")
        .execute()
        .get("values", [])
    )
    status_order: list[str] = []
    for row in states_vals:
        if len(row) >= 2 and row[0] == "Status" and str(row[1]).strip():
            status_order.append(str(row[1]).strip())
    idx_map = {s: i for i, s in enumerate(status_order)}
    max_i = max(1, len(status_order) - 1)

    dash_vals = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="Pipeline Dashboard!D2:E200")
        .execute()
        .get("values", [])
    )
    labels: list[str] = []
    for row in dash_vals:
        if len(row) >= 2 and row[0]:
            labels.append(str(row[0]).strip())

    overrides = [
        _style_entry(i, _rgb_for_states_index(idx_map.get(lab), max_i))
        for i, lab in enumerate(labels)
    ]

    new_spec = copy.deepcopy(spec)
    new_spec["title"] = "Stores by status (color = States order: light → dark)"
    new_spec["subtitle"] = (
        "Each bar uses the States tab row for that status "
        "(Research = lightest; Not Appropriate = darkest)."
    )
    bc = new_spec.setdefault("basicChart", {})
    series_list = bc.get("series") or []
    if not series_list:
        print("Chart has no basicChart series.", file=sys.stderr)
        return 1
    series_list[0]["styleOverrides"] = overrides
    bc["series"] = series_list

    svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"updateChartSpec": {"chartId": CHART_ID, "spec": new_spec}}]},
    ).execute()
    print(f"Updated {len(overrides)} bar colors for {len(labels)} categories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
