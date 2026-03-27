#!/usr/bin/env python3
"""
Generate PDF schedule for Agroverse.shop contributor at Natural Products Expo West 2026.
Run: python generate_expo_west_schedule_pdf.py
Output: expo_west_2026_agroverse_schedule.pdf
"""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUTPUT = Path(__file__).parent / "expo_west_2026_agroverse_schedule.pdf"


def _cell_style():
    return ParagraphStyle(
        "TableCell",
        fontSize=8,
        leading=10,
        leftIndent=2,
        rightIndent=2,
        spaceAfter=2,
    )


def _wrap_table(data, cell_style):
    """Convert table data to Paragraphs for proper text wrapping."""
    return [[Paragraph(cell, cell_style) for cell in row] for row in data]


def main():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=12,
        alignment=TA_CENTER,
    )
    h2_style = ParagraphStyle(
        "CustomH2",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
    )
    h3_style = ParagraphStyle(
        "CustomH3",
        parent=styles["Heading3"],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = styles["Normal"]
    body_style.fontSize = 9
    body_style.spaceAfter = 6
    cell_style = _cell_style()

    story = []

    # Title
    story.append(Paragraph("Natural Products Expo West 2026", title_style))
    story.append(Paragraph("Agroverse.shop Contributor Schedule", title_style))
    story.append(Spacer(1, 0.2 * inch))

    # Goals
    story.append(Paragraph("Goals", h2_style))
    story.append(Paragraph(
        "1. Find retailers to join our ceremonial cacao distribution network",
        body_style,
    ))
    story.append(Paragraph(
        "2. Gather talking points for Agroverse.shop brand storytelling",
        body_style,
    ))
    story.append(Paragraph(
        "Constraints: Single contributor, cannot be in two places at once. Maximum impact prioritized.",
        body_style,
    ))
    story.append(Paragraph(
        "Event: March 3–6, 2026 | Anaheim Convention Center & Marriott",
        body_style,
    ))
    story.append(Spacer(1, 0.2 * inch))

    # Tuesday
    story.append(Paragraph("Tuesday, March 3 — Education & Pre-Show", h2_style))
    tue_data = [
        ["Time", "Activity", "Location", "Agenda / What to Achieve"],
        ["8:00–8:30 AM", "CPG Summit: Morning Wellness Wakeup Call", "Marriott, Marquis Ballroom Center", "Networking. Connect with brand founders and investors. Exchange cards."],
        ["8:30–9:15 AM", "Keynote: Jason Buechel & Mark Bittman", "Marriott, Marquis Ballroom Center", "Brand story. Whole Foods + food systems. Capture quotes on retail, regenerative food."],
        ["9:15–10:15 AM", "Human-Centered Marketing in AI World", "Marriott, Orange County Ballroom 1", "Storytelling. Learn how brands stand out. Notes for ceremonial cacao positioning."],
        ["10:30–11:30 AM", "Acosta 2026 Consumer Predictions", "Marriott, Orange County Ballroom 1", "Retail intel. Buyer priorities, category trends. Use for pitch angles."],
        ["11:45 AM–12:45 PM", "Analytics & 3-Shelf Reality", "Marriott, Orange County Ballroom 1", "Retail strategy. How brands win shelf space. Apply to Agroverse pitch."],
        ["12:45–2:30 PM", "Appetite for Innovation — Networking Lunch", "Marriott, Marquis Ballroom Center", "High-impact networking. Retailers, distributors, organic buyers. Exchange contacts."],
        ["2:30–3:30 PM", "From Labels to Leverage — Ingredient Data", "Marriott, Orange County Ballroom 1", "Brand story. Ingredient transparency. Align with regenerative, farm-direct story."],
        ["3:45–4:45 PM", "Future of Retail — Innovating for Success", "Marriott, Orange County Ballroom 1", "Retail relationships. UNFI, Target panel. Identify distribution partners."],
        ["4:00–5:30 PM", "Pitch Slam — Stories Rooted in Innovation", "Marriott, Marquis Ballroom Center", "Storytelling + investors. Refine Agroverse pitch and brand story."],
    ]
    t1 = Table(_wrap_table(tue_data, cell_style), colWidths=[1.1 * inch, 1.8 * inch, 1.5 * inch, 2.1 * inch])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A7C59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    story.append(t1)
    story.append(Spacer(1, 0.15 * inch))

    # Wednesday
    story.append(PageBreak())
    story.append(Paragraph("Wednesday, March 4 — Exhibit Hall Opens + Buyer-Only", h2_style))
    wed_data = [
        ["Time", "Activity", "Location", "Agenda / What to Achieve"],
        ["9:00–10:00 AM", "BUYER-ONLY HOURS (Critical)", "ACC Level 3 & North Halls", "Only buyers in hall. Natural/specialty grocery, wellness retailers. Collect contacts."],
        ["10:00 AM–12:00 PM", "Exhibit hall — Cacao, chocolate, organic", "ACC Halls A–E, North Halls", "Retailer discovery. Map competitors. Identify retailers. Note booth numbers."],
        ["12:00–1:00 PM", "Lunch / Retail Media session (optional)", "Marriott Grand Ballroom F", "Quick lunch or session on retail media ROI."],
        ["1:00–4:00 PM", "Exhibit hall — Distributor & retailer meetings", "ACC Halls A–E", "Distribution. UNFI, KeHE, regional. Pitch Agroverse. Visit Lindt (1135), organic pavilion."],
        ["5:00–7:00 PM", "Gender Equity in Nutraceuticals (optional)", "Hilton, California A", "Networking. WIN event. Potential retail partners."],
        ["6:00–9:00 PM", "An Organic Night Out (Ticketed)", "Marriott, Marquis Ballroom", "Brand story + organic network. Organic leaders, retailers. Capture messaging."],
    ]
    t2 = Table(_wrap_table(wed_data, cell_style), colWidths=[1.1 * inch, 1.8 * inch, 1.5 * inch, 2.1 * inch])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A7C59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.15 * inch))

    # Thursday
    story.append(PageBreak())
    story.append(Paragraph("Thursday, March 5 — Exhibit Hall Day 2", h2_style))
    thu_data = [
        ["Time", "Activity", "Location", "Agenda / What to Achieve"],
        ["9:00–10:00 AM", "BUYER-ONLY HOURS (Repeat)", "ACC Halls A–E & Arena", "Second buyer window. Cover new halls. Follow up Wed contacts."],
        ["10:00 AM–12:00 PM", "Exhibit hall — Follow-ups and new prospects", "ACC Halls A–E, Arena", "Revisit contacts. Daabon Organic (1941), organic pavilion, Fresh Ideas."],
        ["12:00–1:00 PM", "Retail Media Playbook", "Marriott Grand Ballroom F", "Retail strategy. How brands drive in-store sales."],
        ["1:00–4:00 PM", "Exhibit hall — Deep conversations", "ACC Halls A–E", "Close deals. Longer conversations. Exchange samples, pricing. Regional chains."],
        ["4:00–6:00 PM", "J.E.D.I. Community Happy Hour", "Arena Plaza", "Inclusive networking. Diverse industry connections."],
        ["6:00–7:45 PM", "NEXTY Awards Ceremony", "Marriott, Marquis Ballroom Center", "Brand inspiration. See what wins. Apply to Agroverse positioning."],
    ]
    t3 = Table(_wrap_table(thu_data, cell_style), colWidths=[1.1 * inch, 1.8 * inch, 1.5 * inch, 2.1 * inch])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A7C59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    story.append(t3)
    story.append(Spacer(1, 0.15 * inch))

    # Friday
    story.append(PageBreak())
    story.append(Paragraph("Friday, March 6 — Final Day (Exhibits close 2pm)", h2_style))
    fri_data = [
        ["Time", "Activity", "Location", "Agenda / What to Achieve"],
        ["8:00–9:00 AM", "Keynote: Dr. Jessica Knurick", "Marriott, Marquis Ballroom Center", "Brand story. Nutrition, food systems. Messaging for Agroverse."],
        ["9:00–10:00 AM", "From Discovery to Decision — Health & Wellness CPG", "Marriott, Grand Ballroom E", "Consumer insights. SPINS + New Hope. Final talking points."],
        ["10:00 AM–2:00 PM", "Exhibit hall — Last chance", "ACC Halls A–E", "Final push. Secure commitments. Collect contacts. Prioritize high-potential retailers."],
    ]
    t4 = Table(_wrap_table(fri_data, cell_style), colWidths=[1.1 * inch, 1.8 * inch, 1.5 * inch, 2.1 * inch])
    t4.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A7C59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    story.append(t4)
    story.append(Spacer(1, 0.2 * inch))

    # Summary
    story.append(Paragraph("Priority Tiers", h2_style))
    story.append(Paragraph("Tier 1 — Must Do:", h3_style))
    story.append(Paragraph("• Buyer-only hours (Wed & Thu 9–10am) • CPG Innovation Summit (Tue) • An Organic Night Out (Wed) • Exhibit hall Wed–Fri", body_style))
    story.append(Paragraph("Tier 2 — High Value:", h3_style))
    story.append(Paragraph("• Acosta Consumer Predictions • Human-Centered Marketing • From Labels to Leverage • NEXTY Awards • Dr. Knurick keynote", body_style))
    story.append(Paragraph("Post-Expo: Email contacts within 48hrs. Schedule calls. Document talking points. Add retailers to Hit List.", body_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Generated for Agroverse.shop | Natural Products Expo West 2026 | Anaheim, CA", body_style))

    doc.build(story)
    print(f"PDF saved: {OUTPUT}")

if __name__ == "__main__":
    main()
