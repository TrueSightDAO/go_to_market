"""
Shared Hit List ↔ DApp Remarks sheet writes (append remark + apply to Hit List).

Mirrors the workflow used by the DApp / process_dapp_remarks: one row on **DApp Remarks**,
then sync **Status**, **Sales Process Notes**, **Status Updated By**, **Status Updated Date**,
and mark the remark **Processed** (same pattern as hit_list_research_photo_review.py).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import gspread
from gspread.utils import rowcol_to_a1


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
) -> None:
    hit_vals = hit_ws.get_all_values()
    headers = hit_vals[0]
    hidx = {h: i for i, h in enumerate(headers)}
    for col in ("Status", "Sales Process Notes", "Status Updated By", "Status Updated Date"):
        if col not in hidx:
            raise ValueError(f'Hit List missing column "{col}"')

    now_iso = datetime.now(timezone.utc).isoformat()
    note_prefix = f"[{submitted_at} | {submitted_by}]" if submitted_at else f"[{now_iso} | {submitted_by}]"
    note_line = f"{note_prefix} {remarks}"
    existing_notes = hit_ws.cell(hit_row, hidx["Sales Process Notes"] + 1).value or ""
    new_notes = append_sales_note(str(existing_notes), note_line)

    c_status = hidx["Status"] + 1
    c_notes = hidx["Sales Process Notes"] + 1
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

    ridx_row = find_remark_row_by_submission(remark_ws, submission_id)
    if not ridx_row:
        raise RuntimeError(f"Could not find DApp Remarks row for submission {submission_id}")
    r_headers = remark_ws.row_values(1)
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
) -> None:
    """Append one DApp Remarks row and sync Status / Sales Process Notes on Hit List."""
    r_headers = remark_ws.row_values(1)
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
    remark_ws.append_row(row_out, value_input_option="USER_ENTERED")
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
    )
