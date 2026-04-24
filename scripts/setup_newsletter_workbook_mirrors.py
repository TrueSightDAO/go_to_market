#!/usr/bin/env python3
"""
Create **live mirrors** of Main Ledger tabs into the dedicated newsletter workbook
using `IMPORTRANGE`, and add an **Email 360** sheet to cross-reference one email
against newsletters, subscribers, QR rows, SKUs (via QR SKU codes), and Currencies.

Source (Main Ledger):
  https://docs.google.com/spreadsheets/d/1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU

Destination (newsletter + analytics workbook):
  https://docs.google.com/spreadsheets/d/1ed3q3SJ8ztGwfWit6Wxz_S72Cn5jKQFkNrHpeOVXP8s

Uses **market_research/google_credentials.json**
(`agroverse-market-research@get-data-io.iam.gserviceaccount.com`). That identity
needs **read** access on the source file and **Editor** on the destination.

**IMPORTRANGE authorization:** The first **human** who opens the destination
workbook after formulas are written may need to approve access to the source
for each `IMPORTRANGE` (Google shows a prompt under the cell). The service
account itself cannot complete that click-through; use an owner account once.

Does **not** modify **Agroverse News Letter Emails** (Edgar + send log stay as-is).

Examples:
  cd market_research
  python3 scripts/setup_newsletter_workbook_mirrors.py --dry-run
  python3 scripts/setup_newsletter_workbook_mirrors.py --yes
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"

SOURCE_SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
DEST_SPREADSHEET_ID = "1ed3q3SJ8ztGwfWit6Wxz_S72Cn5jKQFkNrHpeOVXP8s"

# Tabs on the destination that receive IMPORTRANGE from the Main Ledger (exact names).
MIRROR_SHEET_TITLES = [
    "Agroverse News Letter Subscribers",
    "Agroverse QR codes",
    "Agroverse SKUs",
    "Currencies",
]

LOOKUP_SHEET_TITLE = "Email 360"
WORKBOOK_CONTEXT_SHEET = "Workbook context"

# Do not touch this tab on the destination workbook.
PROTECTED_DEST_TABS = frozenset({"Agroverse News Letter Emails"})

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EMAIL_HEADER_CANDIDATES = (
    "email",
    "e-mail",
    "e_mail",
    "recipient_email",
    "customer email",
    "customer_email",
    "buyer email",
    "owner email",
    "onboarding email",
)

SKU_HEADER_CANDIDATES = (
    "sku",
    "agroverse sku",
    "product sku",
    "shopify sku",
    "sku code",
    "variant sku",
    "barcode sku",
    "product id",
    "gtin",
)

SHIPMENT_HEADER_CANDIDATES = ("shipment", "ship code", "agl code")

LEDGER_HEADER_CANDIDATES = ("ledger", "ledger url", "shop path")


def get_sheets_client():
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def _col_letter(idx_1based: int) -> str:
    s = ""
    n = idx_1based
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def find_column_index(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    normed = [_norm_header(h) for h in headers]
    for i, h in enumerate(normed):
        if h in candidates:
            return i + 1
    for cand in candidates:
        for i, h in enumerate(normed):
            if cand in h or h in cand:
                return i + 1
    return None


def imporange_formula(source_id: str, sheet_title: str) -> str:
    """Single-cell formula that spills the mirrored grid."""
    url = f"https://docs.google.com/spreadsheets/d/{source_id}/edit"
    safe_title = sheet_title.replace("'", "''")
    return f'=IMPORTRANGE("{url}","{safe_title}!A:ZZ")'


def ensure_worksheet(sh: gspread.Spreadsheet, title: str, rows: int = 3000, cols: int = 52) -> gspread.Worksheet:
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)


def read_header_row(gc: gspread.Client, spreadsheet_id: str, sheet_title: str) -> list[str]:
    sh = gc.open_by_key(spreadsheet_id)
    ws = sh.worksheet(sheet_title)
    row = ws.row_values(1)
    return row


def build_email360_sheet(
    *,
    qr_email_col: int,
    qr_sku_col: int | None,
    skus_sku_col: int | None,
    sub_email_col: int | None,
    qr_ledger_col: int | None,
    skus_shipment_col: int | None,
) -> list[list[str]]:
    """
    Return a grid of static labels + formulas for the Email 360 tab.
    Layout: newsletter block column A; QR block column R; SKUs via QR column AG;
            subscribers narrow block column BD; notes / campaigns row 3.
    """
    # Newsletter log: recipient_email is column E (5) per send_newsletter.py / Edgar model.
    news_recipient_col = 5
    nl = f"'Agroverse News Letter Emails'!A:P"
    nl_email_idx = news_recipient_col
    news_filter = (
        f'=IF(LEN(TRIM($B$2))=0,"",FILTER({nl}, '
        f'LOWER(TRIM(INDEX({nl},0,{nl_email_idx})))=LOWER(TRIM($B$2))))'
    )

    qr_rng = "'Agroverse QR codes'!A:ZZ"
    qr_filter = (
        f'=IF(LEN(TRIM($B$2))=0,"",FILTER({qr_rng}, '
        f'LOWER(TRIM(INDEX({qr_rng},0,{qr_email_col})))=LOWER(TRIM($B$2))))'
    )

    sub_block = ""
    if sub_email_col:
        sr = "'Agroverse News Letter Subscribers'!A:ZZ"
        sub_block = (
            f'=IF(LEN(TRIM($B$2))=0,"",FILTER({sr}, '
            f'LOWER(TRIM(INDEX({sr},0,{sub_email_col})))=LOWER(TRIM($B$2))))'
        )

    sku_block = ""
    sk = "'Agroverse SKUs'!A:ZZ"
    ec = qr_email_col
    if qr_sku_col and skus_sku_col:
        qc = qr_sku_col
        sc = skus_sku_col
        # COUNTIF(unique_qr_skus, sku_column) pattern: one row kept per SKU row whose
        # SKU code appears in the email's QR-derived unique list.
        sku_block = (
            f'=IF(LEN(TRIM($B$2))=0,"",FILTER({sk}, '
            f'COUNTIF(UNIQUE(FILTER(INDEX({qr_rng},0,{qc}), '
            f'(LEN(TRIM(INDEX({qr_rng},0,{qc})))>0)*'
            f'(LOWER(TRIM(INDEX({qr_rng},0,{ec})))=LOWER(TRIM($B$2))))), '
            f'TRIM(INDEX({sk},0,{sc})))>0))'
        )
    elif qr_ledger_col and skus_shipment_col:
        # QR `ledger` URLs like https://agroverse.shop/agl4 → slug agl4; match SKUs Shipment (AGL4).
        lc = qr_ledger_col
        sc = skus_shipment_col
        slug_expr = (
            f'IFERROR(REGEXEXTRACT(LOWER(INDEX({qr_rng},0,{lc})), '
            f'"agroverse\\.shop/([a-z0-9-]+)$"), "")'
        )
        sku_block = (
            f'=IF(LEN(TRIM($B$2))=0,"",FILTER({sk}, '
            f'COUNTIF(UNIQUE(FILTER({slug_expr}, '
            f'LEN(TRIM({slug_expr}))>0, '
            f'LOWER(TRIM(INDEX({qr_rng},0,{ec})))=LOWER(TRIM($B$2)))), '
            f'LOWER(TRIM(INDEX({sk},0,{sc}))))>0))'
        )

    campaigns_digest = (
        '=IF(LEN(TRIM($B$2))=0,"",TEXTJOIN(", ", TRUE, UNIQUE(FILTER('
        "'Agroverse News Letter Emails'!C:C, "
        "LOWER(TRIM('Agroverse News Letter Emails'!E:E))=LOWER(TRIM($B$2))))))"
    )

    grid: list[list[str]] = [[""] * 130 for _ in range(60)]
    # Row indices 1-based in sheet -> 0-based in grid
    def put(r: int, c: int, val: str) -> None:
        grid[r - 1][c - 1] = val

    put(1, 1, "Email 360 — enter an email in B2 to cross-reference.")
    put(2, 1, "Lookup email")
    put(2, 2, "")  # user types here
    put(3, 1, "Distinct newsletter campaigns for this email:")
    put(3, 3, campaigns_digest)

    put(4, 1, "Newsletter sends (rows from Agroverse News Letter Emails)")
    put(5, 1, news_filter)

    put(4, 18, "QR code rows (Agroverse QR codes)")
    put(5, 18, qr_filter)

    put(
        4,
        33,
        "SKUs linked via QR (same SKU column on both tabs, or ledger URL slug ↔ Shipment)",
    )
    put(5, 33, sku_block or "SKU linkage skipped: could not detect matching SKU columns.")

    put(4, 56, "Subscriber row (Agroverse News Letter Subscribers)")
    put(5, 56, sub_block or "Subscriber filter skipped: no Email column detected in row 1.")

    put(4, 80, "Currencies (full mirror — reference for pricing columns in SKUs)")
    put(5, 80, "='Currencies'!A:ZZ")

    put(35, 1, "Notes")
    put(
        36,
        1,
        "• Newsletter→SKU: there is no separate join column in the send log; use campaigns/subjects "
        "next to QR-derived SKUs to infer what they were told about.",
    )
    put(
        37,
        1,
        "• QR→SKU: either matching SKU columns on both tabs, or ledger URL slug ↔ SKUs Shipment (see Workbook context).",
    )
    put(38, 1, "• Currencies is mirrored wholesale for manual lookup against SKU price fields.")

    return grid


def write_workbook_context_sheet(dst: gspread.Spreadsheet, source_id: str, dest_id: str) -> None:
    """Human-readable tab describing mirrors, Email 360, and operator steps."""
    src_url = f"https://docs.google.com/spreadsheets/d/{source_id}/edit"
    dest_url = f"https://docs.google.com/spreadsheets/d/{dest_id}/edit"
    lines: list[list[str]] = [
        ["Newsletter + analytics workbook (context)"],
        [""],
        ["Destination (this file):"],
        [dest_url],
        ["Source (Main Ledger, mirrored tabs):"],
        [src_url],
        [""],
        ["What lives here"],
        [
            "- Agroverse News Letter Emails — canonical send + open/click log "
            "(Edgar + send_newsletter.py). Not overwritten by this script."
        ],
        [
            "- Agroverse News Letter Subscribers / Agroverse QR codes / Agroverse SKUs / Currencies — "
            "live IMPORTRANGE mirrors from Main Ledger (formula in A1 on each tab)."
        ],
        [
            "- Email 360 — enter lookup email in B2; spills newsletter sends, QR rows, "
            "SKUs (ledger URL slug matched to SKUs Shipment), subscriber row, campaigns digest, "
            "and a Currencies reference block."
        ],
        [""],
        ["Operator setup"],
        [
            "1. Share this workbook with agroverse-market-research@get-data-io.iam.gserviceaccount.com "
            "(Editor) and edgar-dapp-listener@get-data-io.iam.gserviceaccount.com (Editor)."
        ],
        [
            "2. Open this spreadsheet once as a human and click Allow access on each IMPORTRANGE "
            "if Google prompts (service accounts cannot complete that click-through)."
        ],
        [
            "3. Re-run: cd market_research && python3 scripts/setup_newsletter_workbook_mirrors.py --yes"
        ],
        [""],
        ["Email ↔ SKU reasoning"],
        [
            "- Primary link: Owner Email on QR rows + ledger URL slug (e.g. …/agl4) matched to "
            "Agroverse SKUs → Shipment column (case-insensitive)."
        ],
        [
            "- Newsletter → product: infer from campaign + subject next to those SKUs; "
            "the send log does not store SKU IDs."
        ],
        [""],
        ["Scripts"],
        ["- market_research/scripts/send_newsletter.py"],
        ["- market_research/scripts/setup_newsletter_workbook_mirrors.py"],
        ["- sentiment_importer app/models/gdrive/newsletter_emails.rb (same destination spreadsheet ID)."],
    ]
    ws = ensure_worksheet(dst, WORKBOOK_CONTEXT_SHEET, rows=max(200, len(lines) + 10), cols=2)
    ws.clear()
    ws.update(
        values=lines,
        range_name=f"A1:A{len(lines)}",
        value_input_option="USER_ENTERED",
    )


def trim_grid(grid: list[list[str]]) -> list[list[str]]:
    max_r = 0
    max_c = 0
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell:
                max_r = max(max_r, r + 1)
                max_c = max(max_c, c + 1)
    return [row[:max_c] for row in grid[:max_r]]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source-id", default=SOURCE_SPREADSHEET_ID)
    p.add_argument("--dest-id", default=DEST_SPREADSHEET_ID)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="Perform writes (mirrors + Email 360)")
    args = p.parse_args(argv)

    if not _SA_CREDS.is_file():
        print(f"Missing service account file: {_SA_CREDS}", file=sys.stderr)
        return 1

    gc = get_sheets_client()
    gc.open_by_key(args.source_id)  # validate source is readable
    dst = gc.open_by_key(args.dest_id)

    # Introspect headers on SOURCE for formula construction
    qr_headers = read_header_row(gc, args.source_id, "Agroverse QR codes")
    sku_headers = read_header_row(gc, args.source_id, "Agroverse SKUs")
    sub_headers = read_header_row(gc, args.source_id, "Agroverse News Letter Subscribers")

    qr_email_col = find_column_index(qr_headers, EMAIL_HEADER_CANDIDATES)
    qr_sku_col = find_column_index(qr_headers, SKU_HEADER_CANDIDATES)
    skus_sku_col = find_column_index(sku_headers, SKU_HEADER_CANDIDATES)
    sub_email_col = find_column_index(sub_headers, EMAIL_HEADER_CANDIDATES)
    qr_ledger_col = find_column_index(qr_headers, LEDGER_HEADER_CANDIDATES)
    skus_shipment_col = find_column_index(sku_headers, SHIPMENT_HEADER_CANDIDATES)

    print("Detected columns (1-based) on Main Ledger:")
    print(f"  Agroverse QR codes — email: {qr_email_col}, sku-ish: {qr_sku_col}, ledger: {qr_ledger_col}")
    print(f"  Agroverse SKUs — sku-ish: {skus_sku_col}, shipment: {skus_shipment_col}")
    print(f"  Agroverse News Letter Subscribers — email: {sub_email_col}")
    if not qr_email_col:
        print("ERROR: Could not find an email column on 'Agroverse QR codes' row 1.", file=sys.stderr)
        return 1

    print("\nMirror tabs to (re)bind with IMPORTRANGE:")
    for t in MIRROR_SHEET_TITLES:
        print(f"  - {t!r}")

    if args.dry_run:
        print("\nDry run: no changes made.")
        return 0

    if not args.yes:
        print("\nRefusing to write without --yes (try --dry-run first).", file=sys.stderr)
        return 1

    for title in MIRROR_SHEET_TITLES:
        if title in PROTECTED_DEST_TABS:
            print(f"Skip protected tab: {title!r}", file=sys.stderr)
            continue
        ws = ensure_worksheet(dst, title)
        ws.clear()
        formula = imporange_formula(args.source_id, title)
        ws.update(
            range_name="A1",
            values=[[formula]],
            value_input_option="USER_ENTERED",
        )

    # Email 360 sheet
    ws360 = ensure_worksheet(dst, LOOKUP_SHEET_TITLE, rows=4000, cols=130)
    ws360.clear()
    grid = trim_grid(
        build_email360_sheet(
            qr_email_col=qr_email_col,
            qr_sku_col=qr_sku_col,
            skus_sku_col=skus_sku_col,
            sub_email_col=sub_email_col,
            qr_ledger_col=qr_ledger_col,
            skus_shipment_col=skus_shipment_col,
        )
    )
    if grid:
        end_col = _col_letter(len(grid[0]))
        end_row = len(grid)
        rng = f"A1:{end_col}{end_row}"
        ws360.update(values=grid, range_name=rng, value_input_option="USER_ENTERED")

    write_workbook_context_sheet(dst, args.source_id, args.dest_id)

    print(
        f"\nWrote IMPORTRANGE into A1 for {len(MIRROR_SHEET_TITLES)} tab(s); "
        f"built {LOOKUP_SHEET_TITLE!r} and {WORKBOOK_CONTEXT_SHEET!r}. "
        "Open the destination spreadsheet as a human once to authorize IMPORTRANGE if prompted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
