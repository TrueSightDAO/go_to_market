#!/usr/bin/env python3
"""
Populate the 81% chocolate bar spec Google Sheet: one tab per section, lean rows,
with a “Suggested (site / repo)” column filled from agroverse.shop + this monorepo.

Spreadsheet:
  https://docs.google.com/spreadsheets/d/13WbBbbC2dgPo8itltfNvMIx2qFCgDI1aS5Ald3JDCBc/

Requires:
  - Google Sheets API enabled for the service account GCP project
  - Sheet shared (Editor) with agroverse-qr-code-manager@get-data-io.iam.gserviceaccount.com
  - agroverse_shop/google-service-account.json
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = "13WbBbbC2dgPo8itltfNvMIx2qFCgDI1aS5Ald3JDCBc"
KEY_PATH = Path(__file__).resolve().parents[2] / "agroverse_shop" / "google-service-account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEAD = ["Topic", "What to decide / check", "Suggested (Agroverse.shop + repo)", "Owner", "Status"]

# Tabs that use HEAD row + Owner/Status columns (readable table layout)
DATA_SHEET_TITLES = frozenset(
    {
        "Meta",
        "Primary_front",
        "Primary_back",
        "Primary_technical",
        "RDB_design",
        "RDB_logistics",
        "RDB_structure",
        "Artwork_compliance",
        "Next_steps",
    }
)

# Column widths (px) — A:E
COLUMN_PIXELS = [(0, 1, 170), (1, 2, 270), (2, 3, 480), (3, 4, 130), (4, 5, 110)]


def apply_readability_formatting(sh, spreadsheet_id: str) -> None:
    """Freeze header row, wrap text, column widths, light header fill."""
    meta = sh.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))",
    ).execute()

    requests: list[dict] = []
    for s in meta.get("sheets", []):
        sid = s["properties"]["sheetId"]
        title = s["properties"]["title"]

        for c0, c1, px in COLUMN_PIXELS:
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sid,
                            "dimension": "COLUMNS",
                            "startIndex": c0,
                            "endIndex": c1,
                        },
                        "properties": {"pixelSize": px},
                        "fields": "pixelSize",
                    }
                }
            )

        if title in DATA_SHEET_TITLES:
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sid,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                }
            )
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sid,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 5,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.86,
                                    "green": 0.89,
                                    "blue": 0.94,
                                },
                                "textFormat": {"bold": True, "fontSize": 11},
                                "horizontalAlignment": "LEFT",
                                "verticalAlignment": "MIDDLE",
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": (
                            "userEnteredFormat(backgroundColor,textFormat,"
                            "horizontalAlignment,verticalAlignment,wrapStrategy)"
                        ),
                    }
                }
            )
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sid,
                            "startRowIndex": 1,
                            "endRowIndex": 2000,
                            "startColumnIndex": 0,
                            "endColumnIndex": 5,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "wrapStrategy": "WRAP",
                                "verticalAlignment": "TOP",
                                "horizontalAlignment": "LEFT",
                                "textFormat": {"fontSize": 10},
                            }
                        },
                        "fields": (
                            "userEnteredFormat(wrapStrategy,verticalAlignment,"
                            "horizontalAlignment,textFormat)"
                        ),
                    }
                }
            )
        else:
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sid,
                            "startRowIndex": 0,
                            "endRowIndex": 500,
                            "startColumnIndex": 0,
                            "endColumnIndex": 5,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "wrapStrategy": "WRAP",
                                "verticalAlignment": "TOP",
                                "horizontalAlignment": "LEFT",
                                "textFormat": {"fontSize": 10},
                            }
                        },
                        "fields": (
                            "userEnteredFormat(wrapStrategy,verticalAlignment,"
                            "horizontalAlignment,textFormat)"
                        ),
                    }
                }
            )

    chunk = 450
    for i in range(0, len(requests), chunk):
        sh.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests[i : i + chunk]},
        ).execute()


def main() -> int:
    if not KEY_PATH.is_file():
        print("Missing:", KEY_PATH, file=sys.stderr)
        return 1

    creds = service_account.Credentials.from_service_account_file(str(KEY_PATH), scopes=SCOPES)
    sh = build("sheets", "v4", credentials=creds, cache_discovery=False)

    new_titles = [
        "Meta",
        "Primary_front",
        "Primary_back",
        "Primary_technical",
        "RDB_design",
        "RDB_logistics",
        "RDB_structure",
        "Artwork_compliance",
        "Next_steps",
    ]

    meta = sh.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID, fields="sheets(properties(sheetId,title))"
    ).execute()
    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}

    requests = []
    if "Sheet1" in existing and "Start_here" not in existing:
        for s in meta.get("sheets", []):
            if s["properties"]["title"] == "Sheet1":
                requests.append(
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": s["properties"]["sheetId"],
                                "title": "Start_here",
                            },
                            "fields": "title",
                        }
                    }
                )
                break
        existing.discard("Sheet1")
        existing.add("Start_here")

    for title in new_titles:
        if title not in existing:
            requests.append({"addSheet": {"properties": {"title": title}}})

    if requests:
        sh.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
        ).execute()

    blocks: list[tuple[str, list[list[str]]]] = []

    blocks.append(
        (
            "Start_here",
            [
                [
                    "Lean packaging spec for the 81% / 50g bar + 10-count RDB.",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "Each tab is one section. Fill Owner/Status as you go.",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "Site tagline (homepage <title>): Regenerating our Amazon rainforest, One Cacao at a time",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "Canonical domain in HTML: https://www.agroverse.shop — product feeds use https://agroverse.shop; keep redirects consistent for QR.",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "Related Google Doc (long form): https://docs.google.com/document/d/1cP5vq7o6QM3Sgkeklixvw4DmJW1kGD4O-qDUPDT_fC4/edit",
                    "",
                    "",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "Meta",
            [
                HEAD,
                [
                    "Brand voice / hero line",
                    "Short line for RDB or ads",
                    "Regenerating our Amazon rainforest, One Cacao at a time (matches index.html <title> / footer)",
                    "",
                    "",
                ],
                [
                    "Impact stat (marketing)",
                    "Optional front/RDB copy",
                    "Homepage uses “Regenerating 10,000 hectares of the Amazon Rainforest” + dynamic hectares widget",
                    "",
                    "",
                ],
                [
                    "Public phone",
                    "If shown on pack or site",
                    "415-300-0019 (footer + JSON-LD on index.html)",
                    "",
                    "",
                ],
                [
                    "Public email",
                    "Contact / community",
                    "community@agroverse.shop (homepage mailto)",
                    "",
                    "",
                ],
                [
                    "Web / QR base URL",
                    "QR landing must resolve",
                    "Use same host strategy as ceremonial SKUs: www canonical on pages; apex ok in feeds if 301/302 consistent",
                    "",
                    "",
                ],
                [
                    "Trace pattern",
                    "What QR opens",
                    "Match existing product pages: link to shipments (e.g. AGL4) + farm slugs under /shipments/, /farms/ in agroverse_shop",
                    "",
                    "",
                ],
                [
                    "Distributor block (US)",
                    "FDA-style address",
                    "Use legal entity address (site JSON-LD is US-only today—confirm full street for labels)",
                    "",
                    "",
                ],
                [
                    "Manufacturer",
                    "Copacker on label",
                    "TrueTech Inc. (per your brief); add full address when finalized",
                    "",
                    "",
                ],
                [
                    "Digital brand colors (print = define PMS)",
                    "Pouch + box",
                    "CSS on site: primary ~#3b3333, accent ~#fefc8f — translate to Pantone for print",
                    "",
                    "",
                ],
                [
                    "Typography reference",
                    "Inspiration only for print",
                    "Playfair Display + Open Sans on shop — print fonts may differ",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "Primary_front",
            [
                HEAD,
                [
                    "Legal product name",
                    "Before art lock",
                    "Working: Amazonian Regenerative 81% Dark Chocolate — align with chosen single estate / farm name",
                    "",
                    "",
                ],
                [
                    "Cacao intensity",
                    "Large callout",
                    "81% (per Kirsten); legal review vs formula wording",
                    "",
                    "",
                ],
                [
                    "Net contents",
                    "FDA placement habit",
                    "50 g (1.76 oz); bottom ~30% principal display panel",
                    "",
                    "",
                ],
                [
                    "Origin wording",
                    "Single estate vs region",
                    "Site copy spans Bahia ↔ Pará; pick one farm story for this SKU or stay regional until decided",
                    "",
                    "",
                ],
                [
                    "Claims: regenerative / vegan / plant-based",
                    "Only if true",
                    "Site stresses regenerative + single-estate cacao; vegan only if formula + facility support it",
                    "",
                    "",
                ],
                [
                    "Logo & color",
                    "Shelf pop",
                    "Align with web palette above; provide vector logo lockup",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "Primary_back",
            [
                HEAD,
                [
                    "Statement of identity",
                    "e.g. dark chocolate",
                    "Lawyer + copacker wording for US",
                    "",
                    "",
                ],
                [
                    "Nutrition & ingredients",
                    "NLEA",
                    "Vertical Facts; ingredients descending by weight; serving likely = 1 bar (50 g)",
                    "",
                    "",
                ],
                [
                    "Allergens",
                    "Contains / may contain",
                    "Must match TrueTech facility & formula",
                    "",
                    "",
                ],
                [
                    "Manufacturer / distributor",
                    "Required lines",
                    "Manufactured by TrueTech Inc.; Distributed by Agroverse (full address TBD)",
                    "",
                    "",
                ],
                [
                    "Country of origin",
                    "If imported",
                    "Brazil — confirm exact phrasing with counsel",
                    "",
                    "",
                ],
                [
                    "QR → traceability",
                    "Same ecosystem as cacao bags",
                    "Point to agroverse.shop paths used today: /shipments/AGLx, /farms/... (see repo product-page copy)",
                    "",
                    "",
                ],
                [
                    "Unit barcode",
                    "UPC",
                    "Assign GTIN; quiet zones; test scan on kraft",
                    "",
                    "",
                ],
                [
                    "Compost / disposal",
                    "Cert-level accuracy",
                    "Industrial vs home compost; only use cert logos you hold",
                    "",
                    "",
                ],
                [
                    "Batch + best-before",
                    "Inkjet area",
                    "~30×15 mm white knock-out (per your brief)",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "Primary_technical",
            [
                HEAD,
                [
                    "Barrier & shelf life",
                    "WVTR/OTR targets",
                    "Set with film supplier + sensory milestones (0/3/6 mo); plan for bloom in warm/humid lanes",
                    "",
                    "",
                ],
                [
                    "Film / ink compatibility",
                    "Compostable stack",
                    "Confirm adhesives & PFAS stance with supplier",
                    "",
                    "",
                ],
                [
                    "Bar geometry",
                    "Fits pouch + RDB",
                    "Define thickness + break pattern; +2 mm RDB clearance (your note)",
                    "",
                    "",
                ],
                [
                    "MOQ & proofs",
                    "Film + print",
                    "Wet proof / press proof before mass run",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "RDB_design",
            [
                HEAD,
                [
                    "Display title",
                    "10-pack face",
                    "e.g. Agroverse Regenerative Cacao 10-Pack",
                    "",
                    "",
                ],
                [
                    "Mission blurb",
                    "One sentence",
                    "Regenerating 10,000 hectares… or shorter tagline from homepage — pick one approved string",
                    "",
                    "",
                ],
                [
                    "Unit count",
                    "Clear on face",
                    "Contains 10 × 50 g bars",
                    "",
                    "",
                ],
                [
                    "Imagery",
                    "Shelf blocking",
                    "Hero cacao / farm story consistent with site photography style",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "RDB_logistics",
            [
                HEAD,
                [
                    "Case GTIN",
                    "Distinct from unit UPC",
                    "GTIN-14 / ITF-14 for the 10-pack sellable unit",
                    "",
                    "",
                ],
                [
                    "Human-readable barcode",
                    "GS1",
                    "Under barcode; verify quiet zones",
                    "",
                    "",
                ],
                [
                    "Lot / best-before on shipper",
                    "3PL / retail",
                    "Many buyers require on outer; mirror batch logic from unit",
                    "",
                    "",
                ],
                [
                    "Handling marks",
                    "Temp / humidity / stack",
                    "15–18 °C guidance; keep dry; fragile / max stack (align with chocolate norms)",
                    "",
                    "",
                ],
                [
                    "Producer line",
                    "Outer copy",
                    "Produced for Agroverse by TrueTech Inc.",
                    "",
                    "",
                ],
                [
                    "Pallet / case data",
                    "Ops",
                    "L×W×H, weight, Ti×Hi, SSCC if 3PL needs",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "RDB_structure",
            [
                HEAD,
                [
                    "Material",
                    "Board vs corrugated",
                    "350 gsm C1S vs kraft corrugated — pick with Santos + weight drop test",
                    "",
                    "",
                ],
                [
                    "SRP / tear feature",
                    "Retail open",
                    "Tear strip that survives Brazil→US shipping",
                    "",
                    "",
                ],
                [
                    "Closure",
                    "Automation",
                    "Tuck-top vs glue-flap — confirm with Santos line speed",
                    "",
                    "",
                ],
                [
                    "Internal fit",
                    "Crush protection",
                    "+2 mm tolerance; consider divider vs nested stack",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "Artwork_compliance",
            [
                HEAD,
                [
                    "Art files",
                    "Handoff",
                    "Vector PDF/AI; CMYK + PMS; fonts outlined; dieline version control",
                    "",
                    "",
                ],
                [
                    "Claims review",
                    "81% / regenerative / organic",
                    "Align every front claim with formula, certs, and counsel",
                    "",
                    "",
                ],
                [
                    "Color proof",
                    "Cross-border",
                    "China box vs Brazil pouch — define proofing protocol",
                    "",
                    "",
                ],
                [
                    "Approvals",
                    "Sign-offs",
                    "Agroverse · TrueTech · legal · retailer routing if any",
                    "",
                    "",
                ],
            ],
        )
    )

    blocks.append(
        (
            "Next_steps",
            [
                HEAD,
                [
                    "Lock legal product name",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "Finalize 81% formula & ingredient deck",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "Choose farm / estate story for this SKU",
                    "",
                    "Oscar (Bahia) vs Pará farms already featured on site — pick one narrative",
                    "",
                    "",
                ],
                [
                    "Approve mission one-liner for RDB",
                    "",
                    "Match homepage / footer phrasing",
                    "",
                    "",
                ],
                [
                    "Pantone chips to printers",
                    "",
                    "Derive from #3b3333 / #fefc8f or updated brand deck",
                    "",
                    "",
                ],
                [
                    "Santos: tuck vs glue + sample run",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "Issue GTINs (unit + case)",
                    "",
                    "Register in GS1; add to internal SKU sheet / products.js when PDP goes live",
                    "",
                    "",
                ],
            ],
        )
    )

    data_body = []
    for sheet_title, rows in blocks:
        # Prefix range with sheet name; escape single quotes in title
        safe = "'" + sheet_title.replace("'", "''") + "'"
        data_body.append({"range": f"{safe}!A1", "values": rows})

    sh.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data_body},
    ).execute()

    apply_readability_formatting(sh, SPREADSHEET_ID)

    print("Populated:", SPREADSHEET_ID)
    print(
        "Open: https://docs.google.com/spreadsheets/d/"
        + SPREADSHEET_ID
        + "/edit"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
