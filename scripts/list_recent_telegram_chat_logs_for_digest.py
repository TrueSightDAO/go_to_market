#!/usr/bin/env python3
"""
Print recent rows from tab **Telegram Chat Logs** on the TrueSight DAO Telegram compilation
sheet — for drafting **Beer Hall** digests (community contributions / Telegram activity not
visible from Git alone).

Uses **Status date** (or similar) when parseable; otherwise **Created**-style columns if
present. Filters to the last **--hours** (default 24), then prints plain-language bullets for
copy-paste. **Human/agent** still dedupes against the Git poll and the draft TLDR (this script
does not read WhatsApp).

Spreadsheet: https://docs.google.com/spreadsheets/d/1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ/edit
Tab: **Telegram Chat Logs** (often `gid=0`)

Usage (from market_research/):
  python3 scripts/list_recent_telegram_chat_logs_for_digest.py
  python3 scripts/list_recent_telegram_chat_logs_for_digest.py --hours 48
  python3 scripts/list_recent_telegram_chat_logs_for_digest.py --max-rows 800

Requires: google_credentials.json; spreadsheet shared with the service account (Editor).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
TELEGRAM_LOG_WS = "Telegram Chat Logs"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER_ALIASES_DATE = (
    "status date",
    "status_date",
    "date",
    "posted",
    "created",
    "timestamp",
)
HEADER_ALIASES_CONTRIBUTION = (
    "contribution made",
    "contribution_made",
    "message",
    "telegram message",
)
HEADER_ALIASES_CONTRIBUTOR = (
    "contributor name",
    "contributor_name",
    "contributor",
    "from",
)
HEADER_ALIASES_PROJECT = (
    "project name",
    "project_name",
    "project",
)
HEADER_ALIASES_STATUS = (
    "status",
)

# Edgar event types that carry zero Beer Hall signal — filter entirely
_EDGAR_NOISE_TYPES = {
    "email registered event",
    "email verification event",
}

# Edgar event types that ARE signal — parse structured fields from them
_EDGAR_SIGNAL_TYPES = {
    "contribution event",
    "sales event",
    "dao inventory expense event",
}


def _parse_edgar_event(raw: str) -> dict[str, str] | None:
    """Parse Edgar's structured event text into a clean dict.

    Edgar embeds structured key-value pairs in the Telegram message like:
      [CONTRIBUTION EVENT] - Type: USD - Amount: 25 - Description: Grok api - Contributor(s): Gary Teh
    Returns None if the text is not a recognised Edgar event.
    """
    m = re.match(r"\[([A-Z][A-Z\s]+EVENT)\]", raw.strip(), re.IGNORECASE)
    if not m:
        return None
    event_type = m.group(1).strip().lower()

    # Noise events: skip entirely
    if event_type in _EDGAR_NOISE_TYPES:
        return {"_noise": "1"}

    # Parse key: value pairs separated by " - "
    body = raw[m.end():].strip().lstrip("-").strip()
    fields: dict[str, str] = {"_type": event_type}
    for part in re.split(r"\s+-\s+", body):
        kv = part.split(":", 1)
        if len(kv) == 2:
            k = kv[0].strip().lower()
            v = kv[1].strip()
            fields[k] = v
    return fields


def _edgar_to_bullet(fields: dict[str, str], contributor_col: str) -> str:
    """Convert parsed Edgar fields into a clean Beer Hall bullet line."""
    etype = fields.get("_type", "")
    desc = fields.get("description", "").strip()
    contrib = (fields.get("contributor(s)") or fields.get("contributors") or contributor_col or "").strip()
    amount = fields.get("amount", "").strip()
    unit = fields.get("type", "").strip()

    if "sales event" in etype:
        item = fields.get("item", "").strip()
        price = fields.get("sales price", "").strip()
        sold_by = fields.get("sold by", "").strip()
        collector = fields.get("cash proceeds collected by", "").strip()
        parts = []
        if price:
            parts.append(f"sold for {price}")
        if sold_by:
            parts.append(f"by {sold_by}")
        if collector and collector != sold_by:
            parts.append(f"(cash: {collector})")
        detail = " ".join(parts) or item
        return f"_Sale:_ {item} — {detail}" if item else f"_Sale:_ {detail}"

    if "dao inventory expense" in etype:
        member = fields.get("dao member name", contrib).strip()
        ledger = fields.get("target ledger", "").strip()
        inv = fields.get("inventory type", desc).strip()
        return f"_Inventory:_ {inv} logged under {ledger} (by {member})"

    # Contribution event
    if not desc:
        return ""
    # Truncate description sensibly at sentence boundary
    if len(desc) > 300:
        cut = desc[:300]
        last_stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        desc = (cut[: last_stop + 1] if last_stop > 80 else cut[:297] + "…")
    who = contrib or "Contributor"
    if unit.lower() == "usd" and amount:
        return f"_Contribution:_ {desc} — ${amount} USD by {who}"
    if unit.lower() in ("time (minutes)", "time") and amount:
        hrs = int(amount) // 60
        mins = int(amount) % 60
        time_str = (f"{hrs}h {mins}m" if hrs else f"{mins}m") if amount.isdigit() else f"{amount}min"
        return f"_Contribution:_ {desc} — {time_str} by {who}"
    return f"_Contribution:_ {desc} (by {who})"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _parse_sheet_date(raw: str) -> datetime | None:
    t = (raw or "").strip()
    if not t:
        return None
    if re.fullmatch(r"\d{8}", t):
        try:
            return datetime.strptime(t, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(t[:19] if len(t) > 10 else t, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        if "T" in t:
            return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        pass
    return None


def _header_row_index(rows: list[list[str]]) -> int:
    for i, row in enumerate(rows[:15]):
        joined = " ".join(_norm(c) for c in row[:6])
        if "telegram update" in joined and ("contribution" in joined or "chatroom" in joined):
            return i
        if row and _norm(row[0]) in ("telegram update id", "update id"):
            return i
    return 0


def _col_map(header: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for j, cell in enumerate(header):
        key = _norm(cell)
        if not key:
            continue
        out[key] = j
    return out


def _find_col(m: dict[str, int], aliases: tuple[str, ...]) -> int | None:
    for a in aliases:
        for k, j in m.items():
            if k == a or k.replace(" ", "_") == a or a in k:
                return j
    return None


def _meaningful(contribution: str, status: str) -> bool:
    c = (contribution or "").strip()
    if len(c) < 12:
        return False
    if _norm(c) in ("unknown", "invalid", "n/a", "-"):
        return False
    st = _norm(status)
    if st == "invalid" and len(c) < 40:
        return False
    return True


def get_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours", type=float, default=24.0, help="Look-back window (default 24)")
    p.add_argument(
        "--max-rows",
        type=int,
        default=600,
        help="Max data rows to scan from the bottom of the sheet (default 600)",
    )
    p.add_argument("--sheet", default=TELEGRAM_LOG_WS, help="Worksheet title")
    args = p.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    gc = get_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(args.sheet)
    except gspread.WorksheetNotFound:
        sys.stderr.write(
            f"Worksheet {args.sheet!r} not found. Check tab name matches exactly.\n"
        )
        sys.exit(1)

    all_vals = ws.get_all_values()
    if not all_vals:
        print("(empty worksheet)")
        return

    hdr_idx = _header_row_index(all_vals)
    header = all_vals[hdr_idx]
    cmap = _col_map(header)
    i_date = _find_col(cmap, HEADER_ALIASES_DATE)
    i_contrib = _find_col(cmap, HEADER_ALIASES_CONTRIBUTION)
    i_name = _find_col(cmap, HEADER_ALIASES_CONTRIBUTOR)
    i_proj = _find_col(cmap, HEADER_ALIASES_PROJECT)
    i_status = _find_col(cmap, HEADER_ALIASES_STATUS)

    if i_contrib is None:
        # Fall back: "Telegram Message ID" column sometimes holds long text in broken layouts;
        # prefer column containing "contribution" in header label
        for k, j in cmap.items():
            if "contribution" in k:
                i_contrib = j
                break

    if i_contrib is None:
        sys.stderr.write(
            "Could not find a Contribution / message column. Headers: "
            + ", ".join(h for h in header if h)[:500]
            + "\n"
        )
        sys.exit(1)

    data_rows = all_vals[hdr_idx + 1 :]
    if args.max_rows > 0 and len(data_rows) > args.max_rows:
        data_rows = data_rows[-args.max_rows :]

    candidates: list[tuple[datetime | None, str]] = []
    idxs = [x for x in (i_date, i_contrib, i_name, i_proj, i_status) if x is not None]
    max_i = max(idxs) if idxs else i_contrib

    for row in data_rows:
        while len(row) <= max_i:
            row.append("")
        dt = None
        if i_date is not None and i_date < len(row):
            dt = _parse_sheet_date(row[i_date])
        contrib = row[i_contrib] if i_contrib < len(row) else ""
        status = row[i_status] if i_status is not None and i_status < len(row) else ""
        name = row[i_name] if i_name is not None and i_name < len(row) else ""
        proj = row[i_proj] if i_proj is not None and i_proj < len(row) else ""

        if not _meaningful(contrib, status):
            continue
        if dt is not None and dt < cutoff:
            continue
        # If no parseable date, include row only when scanning recent tail (heuristic: last 30 rows)
        if dt is None:
            continue

        # Try to parse as Edgar structured event first
        edgar = _parse_edgar_event(contrib)
        if edgar is not None:
            if edgar.get("_noise"):
                continue  # Email register/verify — skip entirely
            bullet = _edgar_to_bullet(edgar, name)
            if not bullet:
                continue
            line = f"- {bullet}"
        else:
            # Non-Edgar freeform text — use raw snippet
            snippet = contrib.replace("\n", " ").strip()
            if len(snippet) > 300:
                snippet = snippet[:297] + "…"
            who = (name or "").strip() or "Contributor"
            proj_bit = f" ({proj.strip()})" if proj and proj.strip() and _norm(proj) != "unknown" else ""
            line = f"- {who}{proj_bit}: {snippet}"

        if status and _norm(status) not in ("unknown",):
            line += f" [{status.strip()[:40]}]"
        candidates.append((dt, line))

    candidates.sort(key=lambda x: (x[0] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    print(
        f"# Telegram Chat Logs — rows with parseable date on/after "
        f"{cutoff.isoformat()} UTC (~{args.hours}h look-back)\n"
        f"# Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0\n"
        f"# Tab: {args.sheet!r}\n"
        f"# Dedup: skip any line already covered by the Git poll or today's draft TLDR.\n"
    )
    if not candidates:
        print("(no qualifying rows in this window — widen --hours or check Status date column)")
        return
    for _, line in candidates:
        print(line)


if __name__ == "__main__":
    main()
