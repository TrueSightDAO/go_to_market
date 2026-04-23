#!/usr/bin/env python3
"""
Apply readable formatting to the "Email Agent Follow Up" worksheet:
- Freeze header row
- Header: bold, white on green (Agroverse palette)
- Column widths tuned for scanning
- Snippet and body_plain columns: wrap text, top-align
- Auto filter on header row
- Banded rows on data (alternating light gray / white)

Requires: spreadsheet shared with market_research/google_credentials.json service account.

Usage:
  cd market_research && python3 scripts/format_email_agent_followup_sheet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
LOG_WS = "Email Agent Follow Up"
NUM_COLS = 13  # matches LOG_HEADERS in sync_email_agent_followup.py (incl. Open, Click through)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Header fill ≈ #2d5a27
_HEADER_BG = {"red": 0.176, "green": 0.353, "blue": 0.153}
_HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}

# Column widths (pixels) — A..M (snippet + body_plain + status + engagement)
_COL_WIDTHS = [220, 150, 200, 160, 240, 280, 170, 320, 420, 120, 130, 72, 110]


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
    sid = get_sheet_id(service, LOG_WS)

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

    body = {
        "requests": [
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
                        "startColumnIndex": 7,
                        "endColumnIndex": 9,
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
                            "startColumnIndex": 0,
                            "endRowIndex": 5000,
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
                            "firstBandColor": {
                                "red": 0.97,
                                "green": 0.97,
                                "blue": 0.97,
                            },
                            "secondBandColor": {
                                "red": 1.0,
                                "green": 1.0,
                                "blue": 1.0,
                            },
                        },
                    }
                }
            },
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body=body
    ).execute()
    print(f"Formatted worksheet {LOG_WS!r} (sheetId={sid}).")


if __name__ == "__main__":
    main()
