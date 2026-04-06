#!/usr/bin/env python3
"""
Wholesale + retail-pack PDF for attaching to follow-ups (page 1: pricing; page 2: farm profiles; independent retail,
no large committed quantities). Based on generate_earth_commons_price_list.py;
adds traceability / lab-note line inspired by purchase-agreement collateral, without
logistics tables or order-size numbers.

Usage:
  python3 retail_price_list/generate_retailer_wholesale_attachment_pdf.py

Output:
  agroverse_wholesale_retail_overview_2026.pdf (same directory as this script)
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(SCRIPT_DIR, "20230711 - Agroverse logo for trademark filing.jpeg")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "agroverse_wholesale_retail_overview_2026.pdf")


def main() -> None:
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    story: list = []

    if os.path.exists(LOGO_PATH):
        from PIL import Image as PILImage

        pil_img = PILImage.open(LOGO_PATH)
        w, h = pil_img.size
        max_w = 0.625 * inch
        scale = max_w / w
        img = Image(LOGO_PATH, width=max_w, height=h * scale)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 0.2 * inch))

    title_style = ParagraphStyle(
        name="Title",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    story.append(Paragraph("Wholesale &amp; retail-pack overview", title_style))
    story.append(
        Paragraph(
            "<i>Effective 2026 — independent retail</i>",
            ParagraphStyle(name="Year", parent=styles["Normal"], alignment=TA_CENTER, fontSize=11),
        )
    )
    story.append(Spacer(1, 0.22 * inch))

    story.append(
        Paragraph(
            "<b>Bulk &amp; mixed orders</b> — We work with shops that buy wholesale by the pound "
            "(paste, nibs, tea, beans) and/or carry our 200g retail bags. "
            "<b>Order sizes are flexible</b>—tell us what you need and we’ll align on what is in stock "
            "and shipping from our San Francisco warehouse or Brazil, depending on the line and season.",
            ParagraphStyle(name="Intro", parent=styles["Normal"], fontSize=10, alignment=TA_LEFT),
        )
    )
    story.append(Spacer(1, 0.12 * inch))
    story.append(
        Paragraph(
            "<b>Quality &amp; traceability</b> — Product is ceremonial-grade; farm taste profiles and links are on the "
            "<b>following page</b>. <b>Heavy-metal / lab summaries and import paperwork</b> are available on request "
            "for buyer due diligence (we provide these routinely for wholesale accounts).",
            ParagraphStyle(name="Trace", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#333333")),
        )
    )
    story.append(Spacer(1, 0.28 * inch))

    story.append(Paragraph("Bulk purchase (per pound, USD)", styles["Heading2"]))
    bulk_data = [
        ["Product", "Price (USD)"],
        ["Ceremonial cacao paste", "$20.00 per pound"],
        ["Cacao nibs", "$20.00 per pound"],
        ["Cacao tea", "$20.00 per pound"],
        ["Cacao beans", "$20.00 per pound"],
    ]
    bulk_table = Table(bulk_data, colWidths=[3.5 * inch, 2.5 * inch])
    bulk_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a27")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5f5f5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
            ]
        )
    )
    story.append(bulk_table)
    story.append(Spacer(1, 0.15 * inch))
    story.append(
        Paragraph(
            "<b>Note:</b> Prices do not include shipping. Availability follows the most recent harvest and current stock.",
            ParagraphStyle(name="Note", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555")),
        )
    )
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("Retail packs (200g) — resale", styles["Heading2"]))
    consign_data = [
        ["Option", "Details"],
        ["Ceremonial cacao (200g)", "Wholesale cost: $17.00 per bag (includes shipping to you)"],
        ["Suggested retail", "$25–35 per bag"],
        ["Starter depth", "Often 5 bags to start; we replenish as you sell"],
    ]
    consign_table = Table(consign_data, colWidths=[2.2 * inch, 3.8 * inch])
    consign_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a27")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5f5f5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(consign_table)
    story.append(Spacer(1, 0.15 * inch))
    story.append(
        Paragraph(
            "Retail packs: https://agroverse.shop/category/retail-packs/",
            ParagraphStyle(name="Link", parent=styles["Normal"], fontSize=9),
        )
    )
    story.append(Spacer(1, 0.32 * inch))

    # Farms section starts on page 2 (pricing + retail packs stay on page 1).
    story.append(PageBreak())
    story.append(Paragraph("Our farms — taste profiles", styles["Heading2"]))
    story.append(
        Paragraph(
            "Each farm has a distinct sensory fingerprint. For <b>Oscar (reference lot AGL4)</b> and "
            "<b>Paulo (AGL8)</b>, the 0–10 scores below match the same axes used on the interactive taste wheels "
            "on the Agroverse product pages (ceremonial SKUs). <b>Vivi</b> summarizes the <b>AGL13</b> cabruca hybrid "
            "lot in qualitative terms—cup together or request formal cupping notes as needed.",
            ParagraphStyle(name="FarmIntro", parent=styles["Normal"], fontSize=10),
        )
    )
    story.append(Spacer(1, 0.18 * inch))

    tbl_head_style = ParagraphStyle(
        name="tblHead",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )
    tbl_cell_style = ParagraphStyle(
        name="tblCell",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=10,
    )

    def taste_table(data_rows: list[list[str]], col_widths: list[float]) -> Table:
        hdr = [
            Paragraph("<b>Axis / phase</b>", tbl_head_style),
            Paragraph("<b>Score</b>", tbl_head_style),
            Paragraph("<b>Notes</b>", tbl_head_style),
        ]
        body = []
        for row in data_rows:
            body.append([Paragraph(row[0], tbl_cell_style), Paragraph(row[1], tbl_cell_style), Paragraph(row[2], tbl_cell_style)])
        t = Table([hdr] + body, colWidths=col_widths)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a27")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
                ]
            )
        )
        return t

    farms = [
        {
            "title": "Oscar's Farm — Bahia (reference AGL4)",
            "urls": [
                "Farm: https://agroverse.shop/farms/oscar-bahia/index.html",
                "Shipment / story: https://agroverse.shop/shipments/agl4/index.html",
            ],
            "narrative": (
                "Three generations on a century-old farm; venerable fine-flavored Criollo genetics. The cup reads as "
                "<b>deep, dark European chocolate</b> with an almost dessert-like <b>buttery fat</b> that coats the palate. "
                "Older-tree depth shows as subtle <b>earth and wood</b>; the finish stays <b>round and low in acidity</b>—a "
                "classic choice for drinking chocolate, paste, and premium tablets."
            ),
            "table": taste_table(
                [
                    ["Chocolate", "9 / 10", "Deep dark European; intense cocoa core"],
                    ["Buttery / mouthfeel", "10 / 10", "Velvety; rich fat wraps the tongue"],
                    ["Earth / wood", "5 / 10", "Mature-tree bass note; not smoky-dominant"],
                    ["Smooth finish", "9 / 10", "Low perceived acidity; lingering close"],
                    ["Overall intensity", "8 / 10", "Full-bodied without harsh edges"],
                ],
                [2.0 * inch, 0.85 * inch, 3.5 * inch],
            ),
        },
        {
            "title": "Paulo's La do Sitio — Pará, Amazon (reference AGL8)",
            "urls": [
                "Farm: https://agroverse.shop/farms/paulo-la-do-sitio-para/index.html",
                "Shipment / story: https://agroverse.shop/shipments/agl8/index.html",
            ],
            "narrative": (
                "Amazon terroir with a dramatic arc in the cup: the first impression is <b>bold smoke and tobacco</b>, then "
                "the same lot opens into <b>green herb and lush florals</b> as it develops—think Amazon forest after rain, "
                "not barbeque. The <b>transformation note</b> is intentionally high; it is what makes this lot memorable "
                "in ceremony and high-cocoa recipes."
            ),
            "table": taste_table(
                [
                    ["Smoky (initial)", "8 / 10", "Bold, rich; Amazon fire-kiln / post-harvest bass"],
                    ["Tobacco (initial)", "7 / 10", "Earthy, deep; pairs with the smoke entry"],
                    ["Green / herbal (developed)", "6 / 10", "Fresh, vibrant; lifts the mid-palate"],
                    ["Floral (developed)", "7 / 10", "Lush, delicate; counters the opening smoke"],
                    ["Transformation (whole cup)", "9 / 10", "Evolving arc from smoke → florals—signature of AGL8"],
                ],
                [2.0 * inch, 0.85 * inch, 3.5 * inch],
            ),
        },
        {
            "title": "Vivi's Jesus Do Deus — Itacaré, Bahia (reference AGL13)",
            "urls": [
                "Farm: https://agroverse.shop/farms/vivi-jesus-do-deus-itacare/index.html",
                "Shipment / story: https://agroverse.shop/shipments/agl13/index.html",
            ],
            "narrative": (
                "A cabruca agroforestry system grown out of a former cattle ranch near Itacaré—hand-tended pods, "
                "heavy biodiversity shade, top-grade organic hybrid material in commercial lots. The public D3 taste wheel "
                "for Vivi is still rolling out with retail SKUs; for now use this qualitative map and the AGL13 shipment "
                "page when you pitch buyers."
            ),
            "table": taste_table(
                [
                    ["Forest fruit / brightness", "—", "Mild tropical lift typical of coastal Bahia cabruca lots"],
                    ["Floral / herbal", "—", "High canopy; clean aromatics rather than heavy smoke"],
                    ["Nutty / brown", "—", "Supports chocolate building blocks without rough tannin"],
                    ["Acidity", "—", "Bright but controlled—friendly in drinking chocolate"],
                    ["Body & finish", "—", "Medium body; clean, slightly creamy finish when well-prepared"],
                ],
                [2.0 * inch, 0.55 * inch, 4.0 * inch],
            ),
        },
    ]

    for farm in farms:
        story.append(Paragraph(f"<b>{farm['title']}</b>", styles["Normal"]))
        story.append(
            Paragraph(
                farm["narrative"],
                ParagraphStyle(
                    name="TasteNarr",
                    parent=styles["Normal"],
                    fontSize=9,
                    leftIndent=10,
                    textColor=colors.HexColor("#333333"),
                ),
            )
        )
        story.append(Spacer(1, 0.1 * inch))
        story.append(farm["table"])
        story.append(Spacer(1, 0.08 * inch))
        for u in farm["urls"]:
            story.append(Paragraph(u, ParagraphStyle(name="FarmLink", parent=styles["Normal"], fontSize=8, leftIndent=10)))
        story.append(Spacer(1, 0.22 * inch))

    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(
            "Each bag sold supports our mission to restore Amazon rainforest—tree planting tied to sales.",
            ParagraphStyle(name="Mission", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER),
        )
    )
    story.append(Spacer(1, 0.28 * inch))
    story.append(
        Paragraph(
            "<b>Contact</b><br/>Agroverse | Phone: 415-300-0019 | agroverse.shop",
            ParagraphStyle(name="Contact", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER),
        )
    )

    doc.build(story)
    print(f"Generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
