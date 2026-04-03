#!/usr/bin/env python3
"""
Create (or update) the Agroverse SEO monitoring spreadsheet in a Drive folder.

Tabs: Instructions, Keywords_targets, Change_log, Weekly_GSC, DataForSEO_monthly_discovery — formatted for human reading.
Seeds Keywords_targets from a DataForSEO non-brand CSV if present (see paths below).

Requires:
  - market_research/google_credentials.json (service account)
  - Drive folder shared with the service account email (Editor):
        agroverse-market-research@get-data-io.iam.gserviceaccount.com
  - Sheets API + Drive API enabled for the GCP project

Usage (from market_research/):
  python3 scripts/bootstrap_seo_monitoring_sheet.py
  python3 scripts/bootstrap_seo_monitoring_sheet.py --folder-id 1esYnlwChRmv9-M3ymWYhWMPHRowhOluw

Optional:
  --share garyjob@agroverse.shop   (writer on the new file)
  --keywords-csv path/to/nonbrand.csv
  --title "Custom title"

After create: open the Sheet → Extensions → Apps Script → paste or clasp-push
from google_app_scripts/seo_monitoring_gsc/. See agentic_ai_context/SEO_MONITORING_SHEET_WORKFLOW.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"

DEFAULT_FOLDER_ID = "1esYnlwChRmv9-M3ymWYhWMPHRowhOluw"
DEFAULT_TITLE = "Agroverse Shop — SEO monitoring (GSC weekly)"
DEFAULT_SHARE = "garyjob@agroverse.shop"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

INSTRUCTIONS_LINES = [
    "SEO monitoring workbook — how to use",
    "",
    "1) Keywords_targets — curated queries we care about; edit intent_cluster, priority (P1/P2/P3), target_url.",
    "2) Change_log — record every shipped SEO/content change (date, URL, summary, link).",
    "3) Weekly_GSC — filled by Apps Script (Search Console). Uses Monday–Sunday week with ~3-day GSC lag.",
    "",
    "Search Console property (for Apps Script Config.gs): use EXACTLY how it appears in GSC, e.g.",
    "   sc-domain:agroverse.shop   OR   https://www.agroverse.shop/",
    "",
    "4) DataForSEO_monthly_discovery — filled by Apps Script (1st of month). Ideas not already on Keywords_targets.",
    "   Set Script properties DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD; run installMonthlyDataForSeoTrigger() once.",
    "",
    "Sheet + folder: share this file with anyone who needs edit access.",
    "Service account (for this bootstrap script): must have Editor on the Drive folder.",
    "",
    "Apps Script: bind the script from market_research/google_app_scripts/seo_monitoring_gsc/",
    "Enable: Extensions → Apps Script → Services → Google Search Console API.",
    "Run installWeeklyTrigger() once (from Triggers.gs) after authorizing.",
]

KEYWORDS_HEADERS = [
    "keyword",
    "intent_cluster",
    "priority",
    "target_url",
    "notes",
    "dfs_search_volume",
    "dfs_competition",
    "dfs_cpc",
    "baseline_week",
    "last_reviewed",
]

CHANGELOG_HEADERS = [
    "changed_date",
    "author",
    "site_area",
    "change_type",
    "url_or_path",
    "summary",
    "link_pr_or_commit",
    "expected_impact",
    "follow_up_date",
]

WEEKLY_HEADERS = [
    "week_start",
    "week_end",
    "query",
    "page",
    "clicks",
    "impressions",
    "ctr",
    "position",
]

DATAFORSEO_MONTHLY_HEADERS = [
    "pull_date",
    "keyword",
    "search_volume",
    "competition",
    "competition_index",
    "cpc",
    "low_top_of_page_bid",
    "high_top_of_page_bid",
    "note",
]


def _creds():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing service account JSON: {_SA_CREDS}\n")
        sys.exit(1)
    return SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)


def _find_default_keywords_csv() -> Path | None:
    out_dir = _REPO / "output" / "dataforseo"
    if not out_dir.is_dir():
        return None
    candidates = sorted(out_dir.glob("*_nonbrand.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_keyword_rows(csv_path: Path, limit: int) -> list[list]:
    rows: list[list] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if not kw:
                continue
            vol = (row.get("search_volume") or "").strip()
            comp = (row.get("competition") or "").strip()
            cpc = (row.get("cpc") or "").strip()
            rows.append(
                [
                    kw,
                    "",
                    "",
                    "",
                    "",
                    vol,
                    comp,
                    cpc,
                    "",
                    "",
                ]
            )
    rows.sort(key=lambda r: int(r[5]) if r[5].isdigit() else 0, reverse=True)
    return rows[:limit]


def _ensure_worksheets(sheets_svc, spreadsheet_id: str) -> dict[str, int]:
    meta = sheets_svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles_to_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    requests = []
    if "Sheet1" in titles_to_ids and "Instructions" not in titles_to_ids:
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": titles_to_ids["Sheet1"], "title": "Instructions"},
                    "fields": "title",
                }
            }
        )
        titles_to_ids["Instructions"] = titles_to_ids.pop("Sheet1")

    for name in ("Keywords_targets", "Change_log", "Weekly_GSC", "DataForSEO_monthly_discovery"):
        if name not in titles_to_ids:
            requests.append({"addSheet": {"properties": {"title": name}}})

    if requests:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()

    meta = sheets_svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}


def _set_instructions(sheets_svc, spreadsheet_id: str, sheet_id: int) -> None:
    rows = [[line] for line in INSTRUCTIONS_LINES]
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Instructions!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()
    _format_instructions_column(sheets_svc, spreadsheet_id, sheet_id, len(rows))


def _format_instructions_column(sheets_svc, spreadsheet_id: str, sheet_id: int, num_rows: int) -> None:
    body = {
        "requests": [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 720},
                    "fields": "pixelSize",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": num_rows,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "wrapStrategy": "WRAP",
                            "verticalAlignment": "TOP",
                        }
                    },
                    "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment",
                }
            },
        ]
    }
    sheets_svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()


def _write_table_with_header(
    sheets_svc,
    spreadsheet_id: str,
    sheet_title: str,
    sheet_id: int,
    headers: list[str],
    data_rows: list[list],
) -> None:
    values = [headers] + data_rows
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()
    _format_header_row(sheets_svc, spreadsheet_id, sheet_id, len(headers), len(values))


def _format_header_row(
    sheets_svc, spreadsheet_id: str, sheet_id: int, num_cols: int, last_row: int
) -> None:
    body = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.94, "green": 0.94, "blue": 0.92},
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor",
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": num_cols,
                    }
                }
            },
        ]
    }
    if last_row > 1:
        body["requests"].append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": min(last_row, 5000),
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "verticalAlignment": "TOP",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
                }
            }
        )
    sheets_svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()


def _changelog_seed() -> list[list]:
    return [
        [
            "YYYY-MM-DD",
            "you@example.com",
            "homepage / category / product",
            "title_meta | new_page | content | internal_links | technical",
            "https://www.agroverse.shop/...",
            "Short description of what changed",
            "commit URL or PR",
            "e.g. strengthen ceremonial cacao head terms",
            "",
        ]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create SEO monitoring spreadsheet in Drive")
    parser.add_argument("--folder-id", default=DEFAULT_FOLDER_ID, help="Drive folder ID (parents)")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Spreadsheet title")
    parser.add_argument("--share", default=DEFAULT_SHARE, help="Share with this user (writer); empty to skip")
    parser.add_argument("--keywords-csv", default=None, help="Non-brand keyword CSV (default: latest *_nonbrand.csv)")
    parser.add_argument("--keyword-limit", type=int, default=45, help="Max keyword rows to seed")
    parser.add_argument("--spreadsheet-id", default=None, help="If set, only populate tabs on existing file")
    args = parser.parse_args()

    creds = _creds()
    drive = build("drive", "v3", credentials=creds)
    sheets_svc = build("sheets", "v4", credentials=creds)

    spreadsheet_id = args.spreadsheet_id
    if not spreadsheet_id:
        try:
            created = (
                drive.files()
                .create(
                    body={
                        "name": args.title,
                        "mimeType": "application/vnd.google-apps.spreadsheet",
                        "parents": [args.folder_id],
                    },
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except HttpError as e:
            sys.stderr.write(
                f"Drive API error creating spreadsheet: {e}\n"
                "Ensure the folder is shared with the service account (Editor).\n"
            )
            sys.exit(1)
        spreadsheet_id = created["id"]
        print(f"Created spreadsheet id={spreadsheet_id}")
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        print(url)
        if args.share:
            try:
                drive.permissions().create(
                    fileId=spreadsheet_id,
                    body={"type": "user", "role": "writer", "emailAddress": args.share},
                    sendNotificationEmail=False,
                    supportsAllDrives=True,
                ).execute()
                print(f"Shared (writer) with {args.share!r}")
            except HttpError as e:
                sys.stderr.write(f"Warning: could not share with {args.share}: {e}\n")
    else:
        print(f"Using existing spreadsheet id={spreadsheet_id}")

    title_to_id = _ensure_worksheets(sheets_svc, spreadsheet_id)

    _set_instructions(sheets_svc, spreadsheet_id, title_to_id["Instructions"])

    kw_csv = Path(args.keywords_csv) if args.keywords_csv else _find_default_keywords_csv()
    kw_rows: list[list] = []
    if kw_csv and kw_csv.is_file():
        kw_rows = _load_keyword_rows(kw_csv, args.keyword_limit)
        print(f"Seeded {len(kw_rows)} keywords from {kw_csv}")
    else:
        print("No keywords CSV found; Keywords_targets left with header + empty rows.")

    _write_table_with_header(
        sheets_svc,
        spreadsheet_id,
        "Keywords_targets",
        title_to_id["Keywords_targets"],
        KEYWORDS_HEADERS,
        kw_rows,
    )

    _write_table_with_header(
        sheets_svc,
        spreadsheet_id,
        "Change_log",
        title_to_id["Change_log"],
        CHANGELOG_HEADERS,
        _changelog_seed(),
    )

    _write_table_with_header(
        sheets_svc,
        spreadsheet_id,
        "Weekly_GSC",
        title_to_id["Weekly_GSC"],
        WEEKLY_HEADERS,
        [],
    )

    _write_table_with_header(
        sheets_svc,
        spreadsheet_id,
        "DataForSEO_monthly_discovery",
        title_to_id["DataForSEO_monthly_discovery"],
        DATAFORSEO_MONTHLY_HEADERS,
        [],
    )

    print(
        "\nNext: bind Apps Script (see SEO_MONITORING_SHEET_WORKFLOW.md); "
        "run installWeeklyTrigger() and installMonthlyDataForSeoTrigger() once after Script properties are set."
    )


if __name__ == "__main__":
    main()
