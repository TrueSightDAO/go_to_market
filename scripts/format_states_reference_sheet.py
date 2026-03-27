#!/usr/bin/env python3
"""
Readable layout for the "States" reference tab:
- Freeze rows through the column header (row 6): title block + header stay visible
- Green header row on the field / exact_value / notes / hit_list_column line
- Column widths, wrap on notes, filter on the header row, banded data rows

Requires: market_research/google_credentials.json service account.

Usage:
  cd market_research && python3 scripts/format_states_reference_sheet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from sheets_banding import delete_banded_ranges_for_sheet

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
WS_TITLE = "States"
NUM_COLS = 4
# Intro rows 1–5, header on row 6 → freeze 6 rows (1-based)
FROZEN_ROW_COUNT = 6
HEADER_ROW_0 = 5  # 0-based index of "field | exact_value | ..."

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_HEADER_BG = {"red": 0.176, "green": 0.353, "blue": 0.153}
_HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}

_COL_WIDTHS = [140, 260, 520, 160]


def get_sheet_id(service, title: str) -> int:
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID, fields="sheets(properties)").execute()
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == title:
            return int(props["sheetId"])
    sys.stderr.write(f"Worksheet not found: {title!r}\n")
    sys.exit(1)


def main() -> None:
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing {_SA_CREDS}\n")
        sys.exit(1)

    creds = Credentials.from_service_account_file(str(_SA_CREDS), scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    sid = get_sheet_id(service, WS_TITLE)

    col_width_reqs = []
    for i, px in enumerate(_COL_WIDTHS):
        col_width_reqs.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sid,
                        "dimension": "COLUMNS",
                        "startIndex": i,
                        "endIndex": i + 1,
                    },
                    "properties": {"pixelSize": px},
                    "fields": "pixelSize",
                }
            }
        )

    delete_reqs = delete_banded_ranges_for_sheet(service, SPREADSHEET_ID, WS_TITLE)

    requests: list[dict] = [
        *delete_reqs,
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sid,
                    "gridProperties": {"frozenRowCount": FROZEN_ROW_COUNT},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": HEADER_ROW_0,
                    "endRowIndex": HEADER_ROW_0 + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": NUM_COLS,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": _HEADER_BG,
                        "textFormat": {
                            "foregroundColor": _HEADER_FG,
                            "bold": True,
                            "fontSize": 11,
                            "fontFamily": "Calibri",
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
            }
        },
        *col_width_reqs,
        {
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": FROZEN_ROW_COUNT,
                    "startColumnIndex": 0,
                    "endColumnIndex": NUM_COLS,
                },
                "cell": {
                    "userEnteredFormat": {
                        "verticalAlignment": "TOP",
                        "textFormat": {"fontSize": 10, "fontFamily": "Calibri"},
                    }
                },
                "fields": "userEnteredFormat(verticalAlignment,textFormat)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": FROZEN_ROW_COUNT,
                    "startColumnIndex": 2,
                    "endColumnIndex": 3,
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "verticalAlignment": "TOP",
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": HEADER_ROW_0,
                        "endRowIndex": 5000,
                        "startColumnIndex": 0,
                        "endColumnIndex": NUM_COLS,
                    }
                }
            }
        },
        {
            "addBanding": {
                "bandedRange": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": HEADER_ROW_0 + 1,
                        "endRowIndex": 5000,
                        "startColumnIndex": 0,
                        "endColumnIndex": NUM_COLS,
                    },
                    "rowProperties": {
                        "firstBandColor": {"red": 0.97, "green": 0.97, "blue": 0.97},
                        "secondBandColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                    },
                }
            }
        },
    ]

    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": requests}).execute()
    print(f"Formatted worksheet {WS_TITLE!r} (sheetId={sid}).")


if __name__ == "__main__":
    main()
