#!/usr/bin/env python3
"""
Shared helpers to append rows to the Agroverse SEO monitoring Google Sheet.

Convention: **Change_log** — one row per shipped HTML URL (or other discrete resource), not one
concatenated row per release. See agentic_ai_context/SEO_MONITORING_SHEET_WORKFLOW.md.

Production workbook:
  https://docs.google.com/spreadsheets/d/1qRlufSUQusQbJc3AwonIvHtfiAQjwhnMtl79FFkGBt8/edit
"""

from __future__ import annotations

from pathlib import Path

from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SPREADSHEET_ID = "1qRlufSUQusQbJc3AwonIvHtfiAQjwhnMtl79FFkGBt8"
_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Order matches bootstrap_seo_monitoring_sheet.CHANGELOG_HEADERS
def change_log_row(
    changed_date: str,
    author: str,
    site_area: str,
    change_type: str,
    url_or_path: str,
    summary: str,
    link_pr_or_commit: str = "",
    expected_impact: str = "",
    follow_up_date: str = "",
    target_keyword: str = "",
) -> list[str]:
    return [
        changed_date,
        author,
        site_area,
        change_type,
        url_or_path,
        summary,
        link_pr_or_commit,
        expected_impact,
        follow_up_date,
        target_keyword,
    ]


def sheets_values(creds_path: Path | None = None):
    p = creds_path or _SA_CREDS
    if not p.is_file():
        raise FileNotFoundError(p)
    creds = SACredentials.from_service_account_file(str(p), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds).spreadsheets().values()


def append_rows(
    *,
    spreadsheet_id: str,
    sheet_title: str,
    rows: list[list[str]],
    creds_path: Path | None = None,
) -> None:
    if not rows:
        return
    sh = sheets_values(creds_path)
    try:
        sh.append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_title}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"Sheets append failed: {e}") from e
