#!/usr/bin/env python3
"""
Rewrite the spreadsheet tab "States" with canonical allowed values for the Hit List
and the Stores Nearby dapp (https://dapp.truesight.me/stores_nearby.html).

Use this so automation and manual edits use the same strings as `option value=` and
URL query params (`status=`, `shop_type=`).

Requires: market_research/google_credentials.json + sheet shared with service account.
See HIT_LIST_CREDENTIALS.md.

Usage:
  cd market_research && python3 scripts/populate_states_reference_sheet.py
  python3 scripts/populate_states_reference_sheet.py --dry-run   # print rows only
  python3 scripts/format_states_reference_sheet.py                 # layout / filters / banding
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
WS_TITLE = "States"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Mirrors dapp/stores_nearby.html <select id="newStoreStatus"> and status filter values.
# Notes column: plain language for operators; keep column B (exact_value) copy-paste identical to dapp.
STATUSES: list[tuple[str, str]] = [
    (
        "Research",
        "Early stage: gathering store info, photos, fit. Automated photo review may move this to an “AI: …” status.",
    ),
    (
        "AI: Shortlisted",
        "Machine thought storefront photos look on‑brand. You review; promote to Shortlisted or choose AI: Enrich with contact / reject paths.",
    ),
    (
        "AI: No fit signal",
        "Site was crawled, no qualifying keywords (cacao ceremony / women's "
        "circle / sound bath / etc.) found. Replaces the legacy "
        "'AI: Photo rejected' state from 2026-05-03 onward. Recoverable: a "
        "future re-crawl that finds keywords promotes this row back to "
        "AI: Enrich with contact via the rescue path.",
    ),
    (
        "AI: Photo rejected",
        "LEGACY (pre-2026-05-03): the old photo+Grok rubric flagged this row "
        "as a weak fit from imagery. The rubric is retired; rows still in this "
        "state get re-evaluated by the site-crawl rescue path (or migrate to "
        "AI: No fit signal once crawled).",
    ),
    (
        "AI: Photo needs review",
        "LEGACY (pre-2026-05-03): the photo rubric couldn't decide. No "
        "automation reaches this state any more; manual triage only.",
    ),
    (
        "AI: Enrich with contact",
        "You (or a script) will try to find how to reach them: website → email or contact form. "
        "When enrichment runs, the row should move to AI: Email found, AI: Contact Form found, or AI: Enrich — manual.",
    ),
    (
        "AI: Email found",
        "A public email was found and should be in Hit List column K (Email). "
        "Next: draft / send intro (e.g. via Gmail or GAS); when that path is started, move to AI: Warm up prospect.",
    ),
    (
        "AI: Contact Form found",
        "No trustworthy email; the main path is a web form. Put the form/page URL in column AE (Contact Form URL). "
        "You submit the form manually; when they reply, advance status (e.g. Contacted).",
    ),
    (
        "AI: Enrich — manual",
        "Automation could not get a clear email or one contact URL. You handle outreach manually (site, phone, DM, visit).",
    ),
    (
        "AI: Warm up prospect",
        "First touch is underway (draft in inbox, email sent, or logged). Watch your inbox for replies and follow up.",
    ),
    (
        "AI: Prospect replied",
        "They sent an inbound reply (automation may set this after your last logged send). **You** draft the next email; then move to Contacted, Manager Follow-up, Bulk Info Requested, etc.",
    ),
    (
        "Shortlisted",
        "Human‑confirmed lead: promising fit; queued for outreach or an in‑person visit.",
    ),
    (
        "Instagram Followed",
        "You are following their Instagram; use for light touch / research before or alongside email.",
    ),
    (
        "Contacted",
        "You have made initial contact (email, form, call, or visit). Conversation started.",
    ),
    (
        "Manager Follow-up",
        "After a visit: staff asked you to follow up with the manager or buyer—use the contact fields and your email templates.",
    ),
    (
        "Bulk Info Requested",
        "They asked for wholesale or bulk pricing. Use the bulk‑info / PDF overview flow (separate from a short intro).",
    ),
    (
        "Meeting Scheduled",
        "A meeting or call is on the calendar with owner or buyer.",
    ),
    (
        "Followed Up",
        "You completed the promised follow‑up with the decision‑maker; waiting on their answer or next step.",
    ),
    (
        "Partnered",
        "Active retail or wholesale partner; ongoing relationship.",
    ),
    (
        "On Hold",
        "Paused on purpose (timing, inventory, their request)—not rejected.",
    ),
    (
        "Rejected",
        "They said no or are not interested in carrying / listing you.",
    ),
    (
        "Not Appropriate",
        "Not a strategic fit (category, values, channel)—close the loop politely.",
    ),
]

# Mirrors <select id="newStoreShopType"> — stored value uses slash, not " / ".
SHOP_TYPES: list[tuple[str, str]] = [
    (
        "Metaphysical/Spiritual",
        "Crystals, tarot, spiritual books, ritual supplies. "
        'On the dapp the label shows “Metaphysical / Spiritual”. URL must use a slash: shop_type=Metaphysical%2FSpiritual',
    ),
    ("Wellness Center", "Spa, holistic health, services + retail hybrid."),
    ("Health Food Store", "Grocery / supplements / natural foods focus."),
    ("Natural Goods", "Eco or natural lifestyle products (broader than only food)."),
    ("Conscious Cafe", "Café with intentional sourcing or wellness positioning."),
    ("Boutique Chocolate", "Fine or craft chocolate retail (strong fit for sampling)."),
    ("Antique Store", "Vintage / antiques; use only if they also move consumable retail."),
    ("Gift Shop", "General gifts; note if they stock specialty food."),
    ("Candy Store", "Confection-focused retail."),
    ("Yoga Studio", "Movement / mindfulness venue; small retail adjacency."),
    ("Apothecary", "Herb, botanical, or old‑school apothecary positioning."),
    ("Other", "Does not match a label above; explain in Notes if useful."),
]

# Mirrors <select id="newStoreState"> — two-letter codes only in Hit List col F.
US_STATES: list[tuple[str, str]] = [
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("DC", "District of Columbia"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
]

# Hit List column C — not exposed on stores_nearby suggest form; keep aligned for bulk edits.
PRIORITIES: list[tuple[str, str]] = [
    ("High", "Act on soon: strategic city, strong visual fit, or warm intro."),
    ("Medium", "Normal queue: good fit, standard timing."),
    ("Low", "Nice‑to‑have or long‑tail; revisit when capacity allows."),
    ("Existing Partner", "Already a partner; sheet‑only tag for renewals or upsell (not on dapp suggest form)."),
]


def row(field: str, exact: str, notes: str, col: str) -> list[str]:
    return [field, exact, notes, col]


def build_table() -> list[list[str]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[list[str]] = [
        [
            "About this tab",
            "Canonical list of allowed values for the Hit List and the Stores Nearby dapp.",
            "Use column B (exact_value) verbatim when typing in Sheets or filtering URLs — "
            "no extra spaces, no “pretty” labels unless they match exactly. "
            "Column C explains what each value means for humans.",
            "",
        ],
        [
            "How to read this sheet",
            "Column A = field (Status, Shop Type, …). Column B = exact_value — copy verbatim into the Hit List or dapp. "
            "Column C = notes for people (meanings and next steps; not used by code). Column D = which Hit List column.",
            "",
            "",
        ],
        ["", "Live dapp", "https://dapp.truesight.me/stores_nearby.html", ""],
        ["", "Repo source", "dapp/stores_nearby.html + market_research/scripts/populate_states_reference_sheet.py", ""],
        ["refreshed_utc", now, "Last time this tab was regenerated from code.", ""],
        [],
        row("field", "exact_value", "notes for people (what it means)", "hit_list_column"),
        [],
        row(
            "— Status —",
            "",
            "Hit List column B. Flow tip: Research → AI photo outcomes → optional AI: Enrich with contact → "
            "AI: Email found / AI: Contact Form found / AI: Enrich — manual → AI: Warm up prospect → "
            "(optional AI: Prospect replied after they write back) → partnership stages. "
            "Dapp map filters: repeat &status=<exact_value> in the URL.",
            "B (Status)",
        ),
    ]
    for val, note in STATUSES:
        out.append(row("Status", val, note, "B"))
    out.append([])
    out.append(
        row(
            "— Shop Type —",
            "",
            "Hit List column G. Describes what kind of retail they are. "
            "URL filters: &shop_type=<exact_value> — for Metaphysical/Spiritual encode the slash as %2F.",
            "G (Shop Type)",
        )
    )
    for val, note in SHOP_TYPES:
        out.append(row("Shop Type", val, note, "G"))
    out.append([])
    out.append(
        row(
            "— US State (two-letter) —",
            "",
            "Hit List column F: two‑letter USPS codes only (including DC). Must match the dapp dropdown.",
            "F (State)",
        )
    )
    for code, name in US_STATES:
        out.append(row("State", code, name, "F"))
    out.append([])
    out.append(
        row(
            "— Priority —",
            "",
            "Hit List column C only (not on the dapp “suggest a store” form). "
            "Use to rank who gets attention first inside the sheet.",
            "C (Priority)",
        )
    )
    for val, note in PRIORITIES:
        out.append(row("Priority", val, note, "C"))
    return out


def get_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing service account {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def main() -> None:
    parser = argparse.ArgumentParser(description='Populate "States" reference tab from dapp enums.')
    parser.add_argument("--dry-run", action="store_true", help="Print table; do not write Sheets.")
    args = parser.parse_args()

    table = build_table()
    if args.dry_run:
        for r in table:
            print("\t".join(r))
        print(f"\nRows: {len(table)}", file=sys.stderr)
        return

    gc = get_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(WS_TITLE)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WS_TITLE, rows=len(table) + 50, cols=6)

    ws.clear()
    # Expand if needed
    need_rows = max(ws.row_count, len(table) + 10)
    if ws.row_count < need_rows:
        ws.resize(rows=need_rows, cols=max(ws.col_count, 5))

    ws.update(
        values=table,
        range_name="A1",
        value_input_option="USER_ENTERED",
    )
    print(f"Wrote {len(table)} rows to tab {WS_TITLE!r} in spreadsheet {SPREADSHEET_ID}.")


if __name__ == "__main__":
    main()
