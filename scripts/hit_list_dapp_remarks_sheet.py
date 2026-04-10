"""
Shared Hit List ↔ DApp Remarks sheet writes (append remark + apply to Hit List).

Mirrors the workflow used by the DApp / process_dapp_remarks: one row on **DApp Remarks**,
then sync **Status**, **Sales Process Notes**, **Status Updated By**, **Status Updated Date**,
and mark the remark **Processed** (same pattern as hit_list_research_photo_review.py).
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Mapping
from datetime import datetime, timezone

import gspread
from gspread.exceptions import APIError
from gspread.utils import rowcol_to_a1

_APPEND_RANGE_ROW = re.compile(r"!A(\d+)(?::[A-Z]+(\d+))?", re.IGNORECASE)


def _parse_row_from_append_response(res: dict) -> int | None:
    """Parse Google Sheets values.append response for the first row of the appended range."""
    if not res:
        return None
    upd = res.get("updates") or {}
    r = upd.get("updatedRange") or res.get("updatedRange")
    if not r:
        return None
    m = _APPEND_RANGE_ROW.search(str(r))
    if m:
        return int(m.group(1))
    return None


def _gspread_call_with_retry(fn, *, max_attempts: int = 5) -> object:
    """Retry on Sheets 429 read/write quota (Read requests per minute per user)."""
    delay = 2.0
    # jitter so concurrent CI jobs don't stampede the same retry instant
    for attempt in range(max_attempts):
        try:
            return fn()
        except APIError as e:
            err = getattr(e, "response", None)
            http = getattr(err, "status_code", None) if err is not None else None
            # Google Sheets returns HTTP 429; error body may also include code 429.
            if (http == 429 or getattr(e, "code", None) == 429) and attempt < max_attempts - 1:
                time.sleep(delay + random.uniform(0, 1.5))
                delay = min(delay * 1.8, 75.0)
                continue
            raise
    raise RuntimeError("unreachable _gspread_call_with_retry")


# Public alias for scripts that batch-read sheets (same backoff as DApp remark apply path).
gspread_retry = _gspread_call_with_retry


def append_sales_note(existing: str, note_line: str) -> str:
    if not existing or not str(existing).strip():
        return note_line
    return f"{str(existing).strip()}\n\n{note_line}"


def find_remark_row_by_submission(ws: gspread.Worksheet, submission_id: str) -> int | None:
    vals = ws.get_all_values()
    headers = vals[0]
    try:
        sid_idx = headers.index("Submission ID")
    except ValueError:
        return None
    for rn, row in enumerate(vals[1:], start=2):
        if len(row) > sid_idx and row[sid_idx].strip() == submission_id:
            return rn
    return None


def apply_remark_to_hit_list(
    hit_ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    hit_row: int,
    submission_id: str,
    _shop_name: str,
    status: str,
    remarks: str,
    submitted_by: str,
    submitted_at: str,
    *,
    hit_headers: list[str] | None = None,
    remark_row: int | None = None,
    remark_headers: list[str] | None = None,
) -> None:
    # Prefer caller-supplied headers (one row read) or a single header row — never full-sheet
    # get_all_values() here; batch promote runs hit the 60 reads/min quota otherwise.
    if hit_headers is not None:
        headers = hit_headers
    else:
        headers = _gspread_call_with_retry(lambda: hit_ws.row_values(1))
    hidx = {h: i for i, h in enumerate(headers)}
    for col in ("Status", "Sales Process Notes", "Status Updated By", "Status Updated Date"):
        if col not in hidx:
            raise ValueError(f'Hit List missing column "{col}"')

    now_iso = datetime.now(timezone.utc).isoformat()
    note_prefix = f"[{submitted_at} | {submitted_by}]" if submitted_at else f"[{now_iso} | {submitted_by}]"
    note_line = f"{note_prefix} {remarks}"
    c_notes = hidx["Sales Process Notes"] + 1
    existing_notes = _gspread_call_with_retry(
        lambda: hit_ws.cell(hit_row, c_notes).value
    ) or ""
    new_notes = append_sales_note(str(existing_notes), note_line)

    c_status = hidx["Status"] + 1
    c_by = hidx["Status Updated By"] + 1
    c_dt = hidx["Status Updated Date"] + 1

    hit_ws.batch_update(
        [
            {"range": rowcol_to_a1(hit_row, c_status), "values": [[status]]},
            {"range": rowcol_to_a1(hit_row, c_notes), "values": [[new_notes]]},
            {"range": rowcol_to_a1(hit_row, c_by), "values": [[submitted_by]]},
            {"range": rowcol_to_a1(hit_row, c_dt), "values": [[now_iso]]},
        ],
        value_input_option="USER_ENTERED",
    )

    ridx_row = remark_row
    if not ridx_row:
        ridx_row = find_remark_row_by_submission(remark_ws, submission_id)
    if not ridx_row:
        raise RuntimeError(f"Could not find DApp Remarks row for submission {submission_id}")
    if remark_headers is not None:
        r_headers = remark_headers
    else:
        r_headers = _gspread_call_with_retry(lambda: remark_ws.row_values(1))
    ridx = {h: i for i, h in enumerate(r_headers)}
    remark_ws.batch_update(
        [
            {"range": rowcol_to_a1(ridx_row, ridx["Processed"] + 1), "values": [["Yes"]]},
            {"range": rowcol_to_a1(ridx_row, ridx["Processed At"] + 1), "values": [[now_iso]]},
        ],
        value_input_option="USER_ENTERED",
    )


def append_dapp_remark_and_apply(
    hit_ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    sheet_row: int,
    name: str,
    ai_status: str,
    remarks: str,
    submitted_by: str,
    submitted_at: str,
    submission_id: str,
    *,
    hit_headers: list[str] | None = None,
    remark_headers: list[str] | None = None,
) -> None:
    """Append one DApp Remarks row and sync Status / Sales Process Notes on Hit List."""
    r_headers = remark_headers if remark_headers is not None else _gspread_call_with_retry(
        lambda: remark_ws.row_values(1)
    )
    row_out: list[str] = []
    for h in r_headers:
        if h == "Submission ID":
            row_out.append(submission_id)
        elif h == "Shop Name":
            row_out.append(name)
        elif h == "Status":
            row_out.append(ai_status)
        elif h == "Remarks":
            row_out.append(remarks)
        elif h == "Submitted By":
            row_out.append(submitted_by)
        elif h == "Submitted At":
            row_out.append(submitted_at)
        elif h == "Processed":
            row_out.append("")
        elif h == "Processed At":
            row_out.append("")
        else:
            row_out.append("")
    append_res = _gspread_call_with_retry(
        lambda: remark_ws.append_row(row_out, value_input_option="USER_ENTERED")
    )
    ar_dict: dict = dict(append_res) if isinstance(append_res, Mapping) else {}
    remark_row = _parse_row_from_append_response(ar_dict)
    time.sleep(1.5)
    apply_remark_to_hit_list(
        hit_ws,
        remark_ws,
        sheet_row,
        submission_id,
        name,
        ai_status,
        remarks,
        submitted_by,
        submitted_at,
        hit_headers=hit_headers,
        remark_row=remark_row,
        remark_headers=r_headers,
    )
