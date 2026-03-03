#!/usr/bin/env python3
"""
Generate Expo West 2026 Agroverse contributor schedule PDF.
Run from market_research: python generate_expo_west_pdf.py
"""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUTPUT = Path(__file__).parent / "expo_west_2026_agroverse_schedule.pdf"

def main():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='AgendaTitle', fontSize=14, spaceAfter=6, textColor=colors.HexColor('#2c5f2d')))
    styles.add(ParagraphStyle(name='DayTitle', fontSize=12, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor('#1a472a')))
    styles.add(ParagraphStyle(name='Section', fontSize=10, spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name='Small', fontSize=9, spaceAfter=2))

    story = []

    # Title
    story.append(Paragraph(
        "<b>Natural Products Expo West 2026</b><br/>Agroverse.shop Contributor Schedule",
        ParagraphStyle(name='MainTitle', fontSize=18, spaceAfter=4, alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "<b>Focus:</b> Finding new buyers (retailers, distributors, food service) + Brand storytelling talking points",
        styles['Normal']
    ))
    story.append(Paragraph("<b>Dates:</b> March 3–6, 2026 | Anaheim, CA", styles['Normal']))
    story.append(Paragraph("<b>Venues:</b> Anaheim Convention Center (ACC), Anaheim Marriott, Hilton", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))

    # Day 1
    story.append(Paragraph("<b>Day 1 — Tuesday, March 3</b> (Education & CPG Innovation Summit)", styles['DayTitle']))
    day1_data = [
        ['Time', 'Session', 'Location', 'Agenda / Goals'],
        ['8:00–8:30 AM', 'Morning Wellness Wakeup Call', 'Marriott, Marquis Ballroom Center', 'Settle in, network. Agroverse wellness/ceremonial positioning.'],
        ['8:30–9:15 AM', 'Keynote: Reimagining Innovation — Buechel & Bittman', 'Marriott, Marquis Ballroom Center', 'Whole Foods trends; regenerative food framing.'],
        ['9:15–10:15 AM', 'Human-Centered Marketing in AI World', 'Marriott, Orange County Ballroom 1', 'Stand-out marketing; Agroverse story (DAO, farmer partnerships).'],
        ['9:30 AM–12:00 PM', 'The Deal Room — Investors & Brands', 'Marriott, Marquis Ballroom Center', 'Connect with investors; TrueSight DAO + regenerative supply chain pitch.'],
        ['10:00 AM–5:00 PM', 'Content Creation Studio', 'Marriott, Marquis Ballroom NE', 'Create branded content: regenerative cacao, farmer partnerships.'],
        ['10:30–11:30 AM', 'Acosta 2026 Consumer Predictions', 'Marriott, Orange County Ballroom 1', 'Buyer expectations; align Agroverse with consumer trends.'],
        ['11:45 AM–12:45 PM', 'Analytics & 3-Shelf Reality', 'Marriott, Orange County Ballroom 1', 'Retail shelf dynamics; Agroverse target segments.'],
        ['12:00–1:00 PM', 'Deal Room Tabletop Networking', 'Marriott, Marquis Ballroom NW', 'One-on-one with investors/brands; elevator pitch.'],
        ['12:00–5:00 PM', 'Fresh Ideas Organic Marketplace', 'TBD', 'Meet organic buyers; scout complementary brands.'],
        ['12:45–2:30 PM', 'Appetite for Innovation — Networking Lunch', 'Marriott, Marquis Ballroom Center', 'Build relationships; share Agroverse story; collect cards.'],
        ['1:00–4:00 PM', 'CPG Innovation Summit Networking Lounge', 'Marriott, Marquis Ballroom NW', 'Ongoing networking; ask "Who buys ceremonial cacao?"'],
        ['2:30–3:30 PM', 'From Labels to Leverage — AI & Ingredients', 'Marriott, Orange County Ballroom 1', 'Ingredient transparency; Agroverse traceability.'],
        ['2:45–3:05 PM', 'Keynote: Consumer Voices Shape CPG', 'Marriott, Marquis Ballroom Center', 'Consumer-driven innovation; DAO community angle.'],
        ['3:10–3:35 PM', 'Innovators at the Helm', 'Marriott, Marquis Ballroom Center', 'Blue Zones, Yerba Madre; wellness positioning.'],
        ['3:45–4:45 PM', 'The Future of Retail', 'Marriott, Orange County Ballroom 1', 'Target, UNFI, StartupCPG; retail channels.'],
        ['4:00–5:00 PM', 'NCN Investor Meetup', 'Marriott, Marquis Ballroom NW', 'Investor connections; DAO-backed supply chain.'],
        ['4:00–5:30 PM', 'Pitch Slam — Stories Rooted in Innovation', 'Marriott, Marquis Ballroom Center', 'Learn pitch formats; refine Agroverse pitch.'],
        ['5:00–6:00 PM', 'Buffer / Follow-ups', '—', 'Log contacts; schedule Wed meetings.'],
    ]
    t1 = Table(day1_data, colWidths=[1.1*inch, 2.2*inch, 1.8*inch, 2.4*inch])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(t1)
    story.append(Spacer(1, 0.2*inch))

    # Day 2
    story.append(Paragraph("<b>Day 2 — Wednesday, March 4</b> (Exhibit Hall Opens)", styles['DayTitle']))
    day2_data = [
        ['Time', 'Session', 'Location', 'Agenda / Goals'],
        ['8:00–9:00 AM', 'Pre-show prep', 'Hotel / ACC', 'Review buyer list; prepare one-pager and samples.'],
        ['9:00–10:00 AM', 'BUYER-ONLY HOURS', 'ACC Level 3 & North Halls', 'CRITICAL — Meet retail buyers, distributors before crowd.'],
        ['10:00 AM–12:00 PM', 'Exhibit Hall — North Halls & Level 3', 'ACC', 'Visit retailers, distributors, complementary brands.'],
        ['12:00–1:00 PM', 'Lunch / Networking', '—', 'Follow up with morning contacts.'],
        ['1:00–4:00 PM', 'Exhibit Hall — ACC Halls A–E & Arena', 'ACC', 'Broader exploration; chocolate, wellness, beverage buyers.'],
        ['4:00–6:00 PM', 'Exhibit Hall — Final sweep', 'ACC', 'Revisit high-priority booths; confirm follow-ups.'],
        ['6:00–7:30 PM', 'Buffer / Follow-ups', '—', 'Log contacts; send thank-you notes.'],
    ]
    t2 = Table(day2_data, colWidths=[1.1*inch, 2.2*inch, 1.8*inch, 2.4*inch])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.2*inch))

    # Day 3
    story.append(Paragraph("<b>Day 3 — Thursday, March 5</b>", styles['DayTitle']))
    day3_data = [
        ['Time', 'Session', 'Location', 'Agenda / Goals'],
        ['8:00–9:00 AM', 'Pre-show prep', 'Hotel / ACC', 'Review Wed contacts; prioritize Thu meetings.'],
        ['9:00–10:00 AM', 'BUYER-ONLY HOURS', 'ACC Halls A–E & Arena', 'CRITICAL — Second buyer-only window.'],
        ['9:00–10:00 AM', 'The Fiber Revolution', 'Marriott, Grand Ballroom E', 'Optional; functional food positioning.'],
        ['10:00 AM–12:00 PM', 'Exhibit Hall', 'ACC', 'Continue buyer outreach; pavilions.'],
        ['12:00–1:00 PM', 'Retail Media Playbook', 'Marriott, Grand Ballroom F', 'In-store marketing for future shelf placement.'],
        ['12:00–2:00 PM', 'Exhibit Hall + Lunch', 'ACC', 'Combine lunch with booth visits.'],
        ['2:00–4:00 PM', 'Exhibit Hall — Deep dives', 'ACC', 'Longer conversations; sample sharing.'],
        ['2:30–4:00 PM', 'Women in CPG Networking', 'Marriott, Platinum Ballroom 8', 'Diverse buyer/brand connections.'],
        ['4:00–6:00 PM', 'Exhibit Hall — Final sweep', 'ACC', 'Secure commitments; follow-up plan.'],
        ['6:00–7:30 PM', 'Buffer / Follow-ups', '—', 'Log contacts; send follow-ups.'],
    ]
    t3 = Table(day3_data, colWidths=[1.1*inch, 2.2*inch, 1.8*inch, 2.4*inch])
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(t3)
    story.append(Spacer(1, 0.2*inch))

    # Day 4
    story.append(Paragraph("<b>Day 4 — Friday, March 6</b> (Exhibits Close 2 PM)", styles['DayTitle']))
    day4_data = [
        ['Time', 'Session', 'Location', 'Agenda / Goals'],
        ['8:00–9:00 AM', 'Pre-show prep', 'Hotel / ACC', 'Final priority list.'],
        ['9:00–10:00 AM', 'From Discovery to Decision', 'Marriott, Grand Ballroom E', 'Consumer behavior; SPINS data.'],
        ['9:00–10:00 AM', 'Exhibit Hall — Early visit', 'ACC', 'Catch buyers before they leave.'],
        ['10:00 AM–2:00 PM', 'Exhibit Hall — Final hours', 'ACC', 'Last chance; confirm follow-up plan.'],
        ['2:00–3:00 PM', 'Wrap-up', '—', 'Final contact log; action plan.'],
    ]
    t4 = Table(day4_data, colWidths=[1.1*inch, 2.2*inch, 1.8*inch, 2.4*inch])
    t4.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(t4)
    story.append(Spacer(1, 0.3*inch))

    # Brand Storytelling
    story.append(Paragraph("<b>Brand Storytelling Talking Points — Agroverse.shop</b>", styles['DayTitle']))
    points = [
        "1. <b>Regenerative Ceremonial Cacao</b> — Sourced from regenerative farms; soil health, farmer livelihoods.",
        "2. <b>Direct Trade & Traceability</b> — Farmer-first; transparent supply chain.",
        "3. <b>TrueSight DAO / Agroverse Guild</b> — Community-owned; blockchain-backed; unique in CPG.",
        "4. <b>Ceremonial & Wellness</b> — Ceremonial use, wellness rituals, mindfulness.",
        "5. <b>Organic & Premium</b> — Organic certification; natural/specialty positioning.",
        "6. <b>Community & Impact</b> — Brazil partnerships (Cepotx, Coopercabruca).",
        "7. <b>Sustainable Packaging</b> — Align with retailer sustainability goals.",
    ]
    for p in points:
        story.append(Paragraph(p, styles['Small']))
    story.append(Spacer(1, 0.2*inch))

    # Checklist
    story.append(Paragraph("<b>Buyer Outreach Checklist</b>", styles['DayTitle']))
    checklist = [
        "☐ One-pager (brand story, products, wholesale terms)",
        "☐ Samples (if allowed)",
        "☐ Business cards",
        "☐ Wholesale deck / pricing (digital)",
        "☐ Follow-up template",
    ]
    for c in checklist:
        story.append(Paragraph(c, styles['Small']))
    story.append(Spacer(1, 0.2*inch))

    # Footer
    story.append(Paragraph(
        "<i>Source: attend.expowest.com, expowest.com. For Agroverse.shop contributors.</i>",
        styles['Small']
    ))

    doc.build(story)
    print(f"Generated: {OUTPUT}")

if __name__ == "__main__":
    main()
