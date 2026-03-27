#!/usr/bin/env python3
"""
Readable layout for "Email Agent Suggestions":
- Freeze header, green header row, column widths, wrap on body_preview / notes
- Filter + banded rows (removes old banding first)

Usage:
  cd market_research && python3 scripts/format_email_agent_suggestions_sheet.py
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
WS_TITLE = "Email Agent Suggestions"
NUM_COLS = 13

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_HEADER_BG = {"red": 0.176, "green": 0.353, "blue": 0.153}
_HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}

_COL_WIDTHS = [
    210,
    150,
    200,
    180,
    220,
    90,
    210,
    260,
    380,
    120,
    160,
    110,
    200,
]


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

    body = {
        "requests": [
            *delete_reqs,
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sid,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
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
                        "startRowIndex": 1,
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
                        "startRowIndex": 1,
                        "startColumnIndex": 8,
                        "endColumnIndex": 13,
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
                            "startRowIndex": 0,
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
                            "startRowIndex": 1,
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
    }

    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()
    print(f"Formatted worksheet {WS_TITLE!r} (sheetId={sid}).")


if __name__ == "__main__":
    main()
