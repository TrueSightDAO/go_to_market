#!/usr/bin/env python3
"""
Generate bulk inventory availability PDF for wholesale (e.g. Third Eye order prep).
Uses Agroverse logo header. Data sourced from shipping planner API / warehouse (Matheus Reis).
Usage: python3 generate_bulk_availability_pdf.py
Output: agroverse_bulk_availability.pdf
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import os

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RETAIL_DIR = os.path.join(SCRIPT_DIR, "..", "retail_price_list")
LOGO_PATH = os.path.join(RETAIL_DIR, "20230711 - Agroverse logo for trademark filing.jpeg")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "agroverse_bulk_availability.pdf")

# Conversion note for cacao almonds (beans)
ALMONDS_CONVERSION_NOTE = "Cacao almonds (beans): 100 kg converts to ~77.77 kg cacao paste."


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

    # Logo - 0.625" x 0.88" per AGROVERSE_PRICE_LIST_AND_ASSETS.md
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

    # Title
    title_style = ParagraphStyle(
        name="Title",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    story.append(Paragraph("Bulk Inventory Availability", title_style))
    story.append(Paragraph(
        "<i>Warehouse: Matheus Reis — Ilhéus, Brazil</i>",
        ParagraphStyle(name="Sub", parent=styles["Normal"], alignment=TA_CENTER, fontSize=10)
    ))
    story.append(Spacer(1, 0.3 * inch))

    # Inventory data: Product Type, Description, Quantity, Unit Weight (kg), Total Weight (kg)
    # Grouped by farm
    inventory = [
        # Oscar's Farm
        ("Cacao Mass", "Cacao Mass Bar (500g) - Ilheus, Brazil 2024", "38", "0.500", "19.000", "Oscar's Farm"),
        ("Cacao Nibs", "Cacao Nibs (KG) - Ilheus, Brazil 2024", "80", "1.000", "80.000", "Oscar's Farm"),
        ("Cacao Almonds", "Cacao Almonds KG from Oscar's farm - AGL14", "40", "1.000", "40.000", "Oscar's Farm"),
        # Paulo's Farm
        ("Cacao Almonds", "Cacao Almonds (KG)", "274", "1.000", "274.000", "Paulo's Farm"),
        # Vivi's Farm
        ("Cacao Almonds", "Cacao Almonds KG from Vivi's farm - AGL13", "15", "1.000", "15.000", "Vivi's Farm"),
        ("Cacao Nibs", "Cacao Nibs (Kilograms) Santos 20260213 - AGL13", "100", "1.000", "100.000", "Vivi's Farm"),
    ]

    # Build table data
    table_data = [["Product Type", "Description", "Qty", "Unit (kg)", "Total (kg)", "Farm"]]
    for row in inventory:
        table_data.append(list(row))

    col_widths = [1.1 * inch, 2.8 * inch, 0.5 * inch, 0.7 * inch, 0.9 * inch, 1.0 * inch]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a27")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (2, 0), (4, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.25 * inch))

    # Conversion note for cacao almonds
    story.append(Paragraph(
        f"<b>Note:</b> {ALMONDS_CONVERSION_NOTE}",
        ParagraphStyle(name="Note", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    ))
    story.append(Spacer(1, 0.2 * inch))

    # Summary by product type
    story.append(Paragraph("Summary by Product Type", styles["Heading2"]))
    summary_data = [
        ["Product Type", "Total Available (kg)", "Notes"],
        ["Cacao Mass", "19.000", "Ready to use (blocks)"],
        ["Cacao Nibs", "180.000", "Needs conversion to paste"],
        ["Cacao Almonds (beans)", "329.000", "100 kg → ~77.77 kg paste"],
    ]
    sum_table = Table(summary_data, colWidths=[1.8 * inch, 1.8 * inch, 2.4 * inch])
    sum_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a27")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(sum_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph(
        "Contact: Agroverse | Phone: 415-300-0019 | agroverse.shop",
        ParagraphStyle(name="Contact", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER)
    ))

    doc.build(story)
    print(f"Generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
