#!/usr/bin/env python3
"""
Generate Earth Commons wholesale & consignment price list PDF for 2026.
Usage: python3 generate_earth_commons_price_list.py
Output: agroverse_wholesale_price_list_2026.pdf (overwrites existing)
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import os

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(SCRIPT_DIR, "20230711 - Agroverse logo for trademark filing.jpeg")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "agroverse_wholesale_price_list_2026.pdf")


def main():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    # Logo - maintain aspect ratio (logo is 668x944, portrait), scaled smaller
    if os.path.exists(LOGO_PATH):
        from PIL import Image as PILImage
        pil_img = PILImage.open(LOGO_PATH)
        w, h = pil_img.size
        max_w = 0.625 * inch  # 50% of previous height, proportion maintained
        scale = max_w / w
        img = Image(LOGO_PATH, width=max_w, height=h * scale)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 0.2 * inch))

    # Title
    title_style = ParagraphStyle(
        name="Title",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    story.append(Paragraph("Wholesale & Consignment Price List", title_style))
    story.append(Paragraph("<i>Effective 2026</i>", ParagraphStyle(name="Year", parent=styles["Normal"], alignment=TA_CENTER, fontSize=11)))
    story.append(Spacer(1, 0.3 * inch))

    # Bulk Purchase Table
    story.append(Paragraph("Bulk Purchase", styles["Heading2"]))
    bulk_data = [
        ["Product", "Price (USD)"],
        ["Ceremonial cacao paste", "$20.00 per pound"],
        ["Cacao nibs", "$20.00 per pound"],
        ["Cacao tea", "$20.00 per pound"],
        ["Cacao beans", "$20.00 per pound"],
    ]
    bulk_table = Table(bulk_data, colWidths=[3.5 * inch, 2.5 * inch])
    bulk_table.setStyle(TableStyle([
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
    ]))
    story.append(bulk_table)
    story.append(Spacer(1, 0.15 * inch))

    # Shipping notes
    story.append(Paragraph(
        "<b>Note:</b> Prices do not include shipping costs. "
        "Depending on order amount, shipments originate from either our warehouse in San Francisco or Brazil. "
        "Availability depends on current stock from the most recent harvesting season.",
        ParagraphStyle(name="Note", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    ))
    story.append(Spacer(1, 0.35 * inch))

    # Consignment
    story.append(Paragraph("Consignment — Retail Packs", styles["Heading2"]))
    consign_data = [
        ["Option", "Details"],
        ["Ceremonial cacao (200g)", "Cost price: $17.00 per bag (includes shipping)"],
        ["Recommended retail", "$25–35 per bag"],
        ["Initial order", "5 bags to start; we ship more as sales volume increases"],
    ]
    consign_table = Table(consign_data, colWidths=[2.2 * inch, 3.8 * inch])
    consign_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a27")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5f5f5")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(consign_table)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "Retail packs: https://agroverse.shop/category/retail-packs/",
        ParagraphStyle(name="Link", parent=styles["Normal"], fontSize=9)
    ))
    story.append(Spacer(1, 0.35 * inch))

    # Farm Profiles with Taste Profiles
    story.append(Paragraph("Our Farms — Taste Profiles", styles["Heading2"]))
    story.append(Paragraph(
        "Each farm's cacao has a unique taste profile. We support multiple farms across the Brazilian Amazon.",
        ParagraphStyle(name="Intro", parent=styles["Normal"], fontSize=10)
    ))
    story.append(Spacer(1, 0.2 * inch))

    farms = [
        {
            "name": "Oscar's Farm",
            "location": "Bahia, Brazil",
            "url": "https://agroverse.shop/farms/oscar-bahia/index.html",
            "taste": "Deep, dark European chocolate profile with exceptionally buttery, velvety mouthfeel. Intense chocolate notes with subtle undertones of earth and wood. Smooth, low-acidity finish—ideal for ceremonial use and premium chocolate.",
        },
        {
            "name": "Paulo's La do Sitio Farm",
            "location": "Pará, Amazon Rainforest",
            "url": "https://agroverse.shop/farms/paulo-la-do-sitio-para/index.html",
            "taste": "Bold smoky and tobaccoy notes that unfold into a lush green floral profile. Rich and earthy, transforming from bold earthiness to delicate floral notes. Award-winning regenerative cacao from the heart of the Amazon.",
        },
        {
            "name": "Vivi's Jesus Do Deus Farm",
            "location": "Itacaré, Bahia",
            "url": "https://agroverse.shop/farms/vivi-jesus-do-deus-itacare/index.html",
            "taste": "Top-grade organic cacao from cabruca agroforestry. Former cattle ranch transformed into regenerative cacao forest. Ideal for chocolate makers seeking traceable, sustainable cacao.",
        },
    ]

    for farm in farms:
        story.append(Paragraph(f"<b>{farm['name']}</b> — {farm['location']}", styles["Normal"]))
        story.append(Paragraph(farm["taste"], ParagraphStyle(name="Taste", parent=styles["Normal"], fontSize=9, leftIndent=12, textColor=colors.HexColor("#444444"))))
        story.append(Paragraph(farm["url"], ParagraphStyle(name="FarmLink", parent=styles["Normal"], fontSize=8, leftIndent=12)))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(
        "Each bag sold helps plant a tree as part of our mission to restore 10,000 hectares of Amazon rainforest.",
        ParagraphStyle(name="Mission", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 0.3 * inch))

    # Contact
    story.append(Paragraph(
        "<b>Contact</b><br/>Agroverse | Phone: 415-300-0019 | agroverse.shop",
        ParagraphStyle(name="Contact", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER)
    ))

    doc.build(story)
    print(f"Generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
