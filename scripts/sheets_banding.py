"""Helpers to remove banded ranges before re-applying layout (avoids duplicate-banding API errors)."""

from __future__ import annotations

from typing import Any


def delete_banded_ranges_for_sheet(
    service: Any,
    spreadsheet_id: str,
    sheet_title: str,
) -> list[dict]:
    """Return batchUpdate requests that delete all banded ranges on the named sheet."""
    ss = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(title,sheetId),bandedRanges)",
        )
        .execute()
    )
    ids: list[int] = []
    for sheet in ss.get("sheets", []):
        props = sheet.get("properties") or {}
        if props.get("title") != sheet_title:
            continue
        for b in sheet.get("bandedRanges", []):
            bid = b.get("bandedRangeId")
            if bid is not None:
                ids.append(int(bid))
        break

    return [{"deleteBandedRange": {"bandedRangeId": bid}} for bid in ids]
