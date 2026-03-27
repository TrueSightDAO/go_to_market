#!/usr/bin/env python3
"""
Populate the 81% chocolate bar Google Doc with tabulated checklists (Docs API).

Requires:
  - Google Docs API enabled for the service account's GCP project
  - Document shared with Editor to the service account in google-service-account.json
  - Scope: https://www.googleapis.com/auth/documents

Run from repo root or any cwd (uses paths relative to this file).
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

DOC_ID = "1cP5vq7o6QM3Sgkeklixvw4DmJW1kGD4O-qDUPDT_fC4"
# agroverse_shop key — shared with agroverse-qr-code-manager@...
KEY_PATH = Path(__file__).resolve().parents[2] / "agroverse_shop" / "google-service-account.json"
SCOPES = ["https://www.googleapis.com/auth/documents"]


def _append_index(doc: dict) -> int:
    """Index to insert before the document's trailing newline."""
    content = doc.get("body", {}).get("content", [])
    if not content:
        return 1
    return content[-1]["endIndex"] - 1


def _batch(docs, doc_id: str, requests: list) -> None:
    if not requests:
        return
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def _insert_text(docs, doc_id: str, text: str) -> None:
    doc = docs.documents().get(documentId=doc_id).execute()
    idx = _append_index(doc)
    _batch(docs, doc_id, [{"insertText": {"location": {"index": idx}, "text": text}}])


def _style_range(docs, doc_id: str, start: int, end: int, named_style: str) -> None:
    _batch(
        docs,
        doc_id,
        [
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": named_style},
                    "fields": "namedStyleType",
                }
            }
        ],
    )


def _insert_heading(docs, doc_id: str, text: str, style: str = "HEADING_1") -> None:
    doc = docs.documents().get(documentId=doc_id).execute()
    idx = _append_index(doc)
    line = text if text.endswith("\n") else text + "\n"
    _batch(docs, doc_id, [{"insertText": {"location": {"index": idx}, "text": line}}])
    doc2 = docs.documents().get(documentId=doc_id).execute()
    end = _append_index(doc2) + 1
    start = end - len(line)
    _style_range(docs, doc_id, start, end, style)


def _table_cells_in_order(table: dict) -> list[int]:
    """Insert indices for each cell (row-major): paragraph startIndex inside the cell."""
    indices: list[int] = []
    for row in table.get("tableRows", []):
        for cell in row.get("tableCells", []):
            inner = cell.get("content") or []
            for se in inner:
                if "paragraph" not in se:
                    continue
                para = se["paragraph"]
                elems = para.get("elements") or []
                if elems:
                    idx = elems[0].get("startIndex")
                else:
                    idx = se.get("startIndex")
                if idx is not None:
                    indices.append(idx)
                break
    return indices


def _insert_table_filled(docs, doc_id: str, headers: list[str], rows: list[list[str]]) -> None:
    doc = docs.documents().get(documentId=doc_id).execute()
    idx = _append_index(doc)
    nrows = len(rows) + 1
    ncols = len(headers)
    _batch(
        docs,
        doc_id,
        [{"insertTable": {"rows": nrows, "columns": ncols, "location": {"index": idx}}}],
    )
    doc = docs.documents().get(documentId=doc_id).execute()
    tables = []
    for el in doc["body"]["content"]:
        if "table" in el:
            tables.append(el["table"])
    if not tables:
        raise RuntimeError("Table not found after insertTable")
    table = tables[-1]
    cell_indices = _table_cells_in_order(table)
    expected = nrows * ncols
    if len(cell_indices) != expected:
        raise RuntimeError(f"Cell count mismatch: want {expected}, got {len(cell_indices)}")

    all_rows = [headers] + rows
    flat: list[str] = []
    for r in all_rows:
        flat.extend(_pad_row(r, ncols))

    pairs = list(zip(cell_indices, flat))
    # Insert from highest index first so earlier cell indices stay valid within one batch.
    pairs.sort(key=lambda x: x[0], reverse=True)
    requests = [{"insertText": {"location": {"index": i}, "text": v}} for i, v in pairs]
    _batch(docs, doc_id, requests)
    _insert_text(docs, doc_id, "\n")


def _pad_row(row: list[str], ncols: int) -> list[str]:
    out = list(row[:ncols])
    while len(out) < ncols:
        out.append("")
    return out


def main() -> int:
    if not KEY_PATH.is_file():
        print("Missing key file:", KEY_PATH, file=sys.stderr)
        return 1

    creds = service_account.Credentials.from_service_account_file(str(KEY_PATH), scopes=SCOPES)
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)

    # Replace body: delete everything except structural shell (clear to one empty paragraph)
    doc = docs.documents().get(documentId=DOC_ID).execute()
    content = doc["body"]["content"]
    # Delete from first editable index to end-1 (exclude document trailing newline)
    last_end = content[-1]["endIndex"]
    if last_end > 2:
        _batch(
            docs,
            DOC_ID,
            [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": last_end - 1}}}],
        )

    _insert_heading(docs, DOC_ID, "81% single-estate premium bar — packaging & compliance checklist", "TITLE")
    _insert_text(
        docs,
        DOC_ID,
        "Agroverse Premium 50g dark chocolate bar · Product development & retail assembly\n"
        "81% cacao (per Kirsten) · Brand: Agroverse — regenerative Amazon narrative · Manufacturer: TrueTech Inc.\n\n",
    )

    _insert_heading(docs, DOC_ID, "A. Document meta", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Field", "Value / owner"],
        [
            ["Product working name", "Amazonian Regenerative 81% Dark Chocolate (TBD legal)"],
            ["Unit format", "50 g bar · compostable kraft pouch (high-barrier bio-film)"],
            ["Retail case", "10 × 50 g display box (RDB)"],
            ["Primary manufacturing", "TrueTech Inc. / Santos line constraints TBD"],
            ["US distributor on label", "Agroverse, San Francisco, CA"],
            ["Revision date", "[Date]"],
        ],
    )

    _insert_heading(docs, DOC_ID, "B. Primary pack — front of pack (marketing)", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Line item", "Requirement / notes"],
        [
            ["Brand logo", "Primary placement (top / center); master artwork version"],
            ["Product name", "Final legal name + sub-brand if any"],
            ["Cacao callout", "81% dark cacao — high visibility; legal review vs formula"],
            ["Net quantity", "50 g (1.76 oz) — bottom ~30% principal display (US habit)"],
            ["Callout: regenerative", "Only with substantiation / legal approval"],
            ["Callout: single origin / estate", "Named farm or region — align with trace QR"],
            ["Callout: vegan / plant-based", "Only if true for formula & facility"],
            ["Color / PMS", "CMYK + Pantone; match RDB and web"],
        ],
    )

    _insert_heading(docs, DOC_ID, "C. Primary pack — back of pack (legal, trace, ops)", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Line item", "Requirement / notes"],
        [
            ["Statement of identity", "e.g. dark chocolate — legal wording"],
            ["Nutrition Facts", "FDA vertical format; NLEA type sizes; serving = bar if applicable"],
            ["Ingredients", "Descending by weight; sub-ingredients as required"],
            ["Allergens", "Contains / facility advisory — copacker sign-off"],
            ["Manufacturer block", "Manufactured by: TrueTech Inc."],
            ["Distributor block", "Distributed by: Agroverse, San Francisco, CA"],
            ["Country of origin", "If imported — required where applicable"],
            ["Traceability QR", "agroverse.shop — farm / shipment / impact; batch URL schema"],
            ["Unit barcode", "UPC-A / GTIN; quiet zones; contrast on kraft"],
            ["Compost / disposal", "Industrial vs home compost; cert marks only if certified"],
            ["Certification icons", "Organic, Fair Trade, FSC, etc. — only if valid"],
            ["Variable print area", "~30 × 15 mm white box — batch + best-before (inkjet)"],
            ["Optional: Prop 65 / bilingual", "CA + export markets if needed"],
        ],
    )

    _insert_heading(docs, DOC_ID, "D. Primary pack — technical & quality (often missed)", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Topic", "Considerations"],
        [
            ["Barrier & shelf life", "WVTR/OTR or supplier spec; sensory at 0/3/6 mo; bloom risk"],
            ["Compostable claims", "No greenwashing; PFAS / barrier chemistry review"],
            ["Print & adhesion", "Inkjet vs thermal; rub resistance on film/kraft"],
            ["Dimensions / break", "Bar mold, thickness, headspace vs pouch and RDB crush"],
            ["MOQ / lead time", "Film, print, copacker; wet proof / press proof"],
        ],
    )

    _insert_heading(docs, DOC_ID, "E. Secondary pack — RDB exterior (10 × 50 g)", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Line item", "Requirement / notes"],
        [
            ["Display title", "e.g. Agroverse Regenerative Cacao 10-Pack"],
            ["Mission blurb", "Exact approved brand sentence"],
            ["Unit count", "Contains 10 × 50 g bars"],
            ["Imagery", "On-brand; shelf visibility; contrast vs competitors"],
            ["PMS / CMYK", "Match pouch; note corrugated vs board delta"],
        ],
    )

    _insert_heading(docs, DOC_ID, "F. RDB — bottom, sides, logistics", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Line item", "Requirement / notes"],
        [
            ["Case GTIN", "GTIN-14 / ITF-14 — distinct from unit UPC"],
            ["Human-readable GTIN", "Below barcode per GS1"],
            ["Lot / best-before", "On shipper — many distributors require"],
            ["Temp / humidity", "15–18 °C (60–65 °F) guidance; keep dry"],
            ["Handling", "Fragile; max stack height — art + spec sheet"],
            ["Producer statement", "Produced for Agroverse by TrueTech Inc."],
            ["Recycling / disposal", "Markings only if valid for material & market"],
        ],
    )

    _insert_heading(docs, DOC_ID, "G. RDB — structure & automation (Santos-ready)", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Line item", "Requirement / notes"],
        [
            ["Material", "350 gsm C1S vs kraft corrugated — ECT/burst targets"],
            ["Tear / perf", "SRP tear strip; retail open vs Brazil→US shipping strength"],
            ["Internal dims", "+2 mm tolerance vs filled pouch; divider vs stack"],
            ["Closure", "Tuck-top vs glue-flap — confirm with Santos line"],
            ["Automation", "Minimize hand fold / stickers; line speed compatibility"],
            ["Testing", "Drop / crush; ISTA if e-comm or club"],
        ],
    )

    _insert_heading(docs, DOC_ID, "H. Hierarchy & supply chain (case → pallet)", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Topic", "Considerations"],
        [
            ["Pack hierarchy", "Unit → inner bundle? → RDB → master shipper → pallet"],
            ["Each level GTIN", "What is sellable vs ship-only; data in GS1"],
            ["Dims & weight", "L × W × H and kg per RDB and per master case"],
            ["Pallet pattern", "Ti × Hi; SSCC label if required by 3PL/retailer"],
            ["Incoterms / FOB", "Who owns damage in transit; insurance"],
        ],
    )

    _insert_heading(docs, DOC_ID, "I. Artwork & compliance process", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Line item", "Requirement / notes"],
        [
            ["Files", "Vector .AI / .PDF; fonts outlined; CMYK + PMS"],
            ["Dielines", "Version control; bleed / safe / trim; barcode quiet zones"],
            ["FDA review", "NLEA minimum sizes; claims review (81%, regenerative, etc.)"],
            ["Color proof", "China box vs Brazil pouch — match protocol"],
            ["Approvals", "Agroverse · TrueTech · legal · retailer routing if any"],
        ],
    )

    _insert_heading(docs, DOC_ID, "J. Next steps (discussion)", "HEADING_2")
    _insert_table_filled(
        docs,
        DOC_ID,
        ["Topic", "Notes"],
        [
            ["Product legal name", "Lock before print"],
            ["81% formula & ingredients", "Final list + allergen"],
            ["Farm / estate story", "QR destination + front-pack claims"],
            ["Mission wording", "Exact phrase sign-off"],
            ["Pantone deck", "Share with pouch + box printers"],
            ["Santos closure choice", "Tuck vs glue + sample run"],
            ["Design handoff", "Timeline + milestone dates"],
        ],
    )

    _insert_text(
        docs,
        DOC_ID,
        "\n— End of checklist (auto-generated). Edit rows as decisions are made.\n",
    )

    print("Updated document:", DOC_ID)
    print("Open: https://docs.google.com/document/d/" + DOC_ID + "/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
