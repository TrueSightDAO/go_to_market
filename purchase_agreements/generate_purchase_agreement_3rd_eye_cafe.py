#!/usr/bin/env python3
"""
Purchase agreement PDF — 3rd Eye Cafe / Neil Dumra.

Style reference (same repo): ../generate_expo_west_schedule_pdf.py,
../retail_price_list/generate_earth_commons_price_list.py — ReportLab,
letter, green table headers (#2d5a27), readable body text.

Run from repo root or this directory:
  python3 purchase_agreements/generate_purchase_agreement_3rd_eye_cafe.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_PATH = SCRIPT_DIR / "purchase_agreement_3rd_eye_cafe_20260325.pdf"
LOGO_PATH = REPO_ROOT / "retail_price_list" / "20230711 - Agroverse logo for trademark filing.jpeg"

# Farm profile (canonical page on agroverse.shop)
FARM_CANONICAL_URL = "https://agroverse.shop/farms/oscar-bahia/index.html"

# Calculations (cargo value = product line for ad valorem / bond context)
LB_CACAO = 276
PRICE_PER_LB = 20.00
PRODUCT_TOTAL = LB_CACAO * PRICE_PER_LB
CARGO_VALUE_USD = PRODUCT_TOTAL
AD_VAL_RATE = 0.0015  # 0.15%
INLAND_BASE = 695.00
INLAND_AD_VAL = round(CARGO_VALUE_USD * AD_VAL_RATE, 2)
INLAND_TOTAL = INLAND_BASE + INLAND_AD_VAL
AIRPORT_BR = 250.00  # 0.30/kg on 210 kg chargeable = $63; minimum $250 applies
AIR_FREIGHT = 735.00
TERMINAL_TAP = 200.00
IMPORT_HANDLING = 125.00
DELIVERY_DOOR = 355.00
US_CUSTOMS_CLEARANCE = 150.00
FDA_PROCESSING = 100.00
# Assume invoice has 3 or fewer lines (first 3 free per broker quote)
INVOICE_LINE_FEES = 0.00
QUOTED_LOGISTICS_SUBTOTAL = (
    INLAND_TOTAL
    + AIRPORT_BR
    + AIR_FREIGHT
    + TERMINAL_TAP
    + IMPORT_HANDLING
    + DELIVERY_DOOR
    + US_CUSTOMS_CLEARANCE
    + FDA_PROCESSING
    + INVOICE_LINE_FEES
)
MPF_MIN = 33.58
BOND_MIN_EST = 100.00  # broker: $6/$1k + duty, $100 min — not part of 50% deposit base per Section 5
# Deposit = 50% × (cacao + quoted forwarder subtotal); duties/MPF/bond reconciled on final invoices.
DEPOSIT_BASE_LOGISTICS = QUOTED_LOGISTICS_SUBTOTAL
DEPOSIT_50_PCT = round(0.5 * (PRODUCT_TOTAL + DEPOSIT_BASE_LOGISTICS), 2)
DEPOSIT_BASE_TOTAL = round(PRODUCT_TOTAL + DEPOSIT_BASE_LOGISTICS, 2)
BALANCE_50_ON_ARRIVAL = DEPOSIT_50_PCT  # same half of deposit base
EST_EXTRAS_AFTER_DEPOSIT_BASE = round(MPF_MIN + BOND_MIN_EST, 2)
EST_TOTAL_EXCL_DUTIES = round(DEPOSIT_BASE_TOTAL + EST_EXTRAS_AFTER_DEPOSIT_BASE, 2)

# Footer on every page: space for buyer initials + page number (dispute hygiene)
BUYER_INITIALS_LABEL = "Buyer (3rd Eye Cafe) initials:"
SIGNATORY_BUYER_LINE = "3rd Eye Cafe"


def _purchase_agreement_page_footer(canvas, doc):
    """Draw initials line + page number in bottom margin (all pages)."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#333333"))
    pw, _ph = doc.pagesize
    y = 0.42 * inch
    canvas.drawString(doc.leftMargin, y, f"{BUYER_INITIALS_LABEL} __________")
    page_num = canvas.getPageNumber()
    canvas.drawRightString(pw - doc.rightMargin, y, f"Page {page_num}")
    canvas.restoreState()


def _bullets(paragraph_markup_list, style, left_indent=22, bullet_indent=8):
    """Bullet list for readability; each item is mini-HTML for Paragraph."""
    return ListFlowable(
        [ListItem(Paragraph(text, style)) for text in paragraph_markup_list],
        bulletType="bullet",
        leftIndent=left_indent,
        bulletIndent=bullet_indent,
        spaceBefore=2,
        spaceAfter=6,
    )


def _wrap_table_rows(rows, header_style, body_style):
    """
    Convert table string data to Paragraphs so <br/>, <b>, entities, and
    wrapping work. Plain Table cells do not interpret ReportLab markup.
    """
    out = []
    for i, row in enumerate(rows):
        style = header_style if i == 0 else body_style
        out.append([Paragraph(cell, style) for cell in row])
    return out


def _money_table_matrix(data_rows, hdr_l, hdr_r, desc_style, amt_style):
    """Build matrix for a two-column money table (header + data rows)."""
    m = [
        [Paragraph("Line item", hdr_l), Paragraph("Amount (USD)", hdr_r)],
    ]
    for desc, amt in data_rows:
        m.append([Paragraph(desc, desc_style), Paragraph(amt, amt_style)])
    return m


def main():
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    if LOGO_PATH.is_file():
        try:
            from PIL import Image as PILImage

            pil_img = PILImage.open(LOGO_PATH)
            w, h = pil_img.size
            max_w = 0.625 * inch
            scale = max_w / w
            img = Image(str(LOGO_PATH), width=max_w, height=h * scale)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 0.15 * inch))
        except Exception:
            pass

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    subtitle = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=10,
        spaceAfter=14,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=8,
        textColor=colors.HexColor("#1a3d16"),
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    small = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#444444"),
    )
    body_li = ParagraphStyle(
        "BodyLi",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
        spaceAfter=0,
        spaceBefore=0,
    )
    small_li = ParagraphStyle(
        "SmallLi",
        parent=small,
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        spaceAfter=0,
        spaceBefore=0,
    )
    green_header = colors.HexColor("#2d5a27")
    light_row = colors.HexColor("#f5f5f5")

    # Table cell styles (must use Paragraph in cells — not plain strings)
    tbl_head = ParagraphStyle(
        "TblHead",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        leading=11,
        alignment=TA_LEFT,
        spaceAfter=0,
        spaceBefore=0,
    )
    tbl_body_9 = ParagraphStyle(
        "TblBody9",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        alignment=TA_LEFT,
        spaceAfter=2,
        spaceBefore=0,
    )
    tbl_body_8 = ParagraphStyle(
        "TblBody8",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        spaceAfter=2,
        spaceBefore=0,
    )
    tbl_head_amt = ParagraphStyle(
        "TblHeadAmt",
        parent=tbl_head,
        alignment=TA_RIGHT,
    )
    tbl_money_desc = ParagraphStyle(
        "TblMoneyDesc",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        alignment=TA_LEFT,
        spaceAfter=0,
        spaceBefore=0,
    )
    tbl_money_amt = ParagraphStyle(
        "TblMoneyAmt",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        alignment=TA_RIGHT,
        fontName="Helvetica",
        spaceAfter=0,
        spaceBefore=0,
    )
    tbl_money_section = ParagraphStyle(
        "TblMoneySection",
        parent=tbl_money_desc,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1a3d16"),
        leading=12,
    )

    story.append(Paragraph("Purchase Agreement", title_style))
    story.append(
        Paragraph(
            f"Ceremonial cacao paste &mdash; "
            f'<a href="{FARM_CANONICAL_URL}" color="blue">Oscar&rsquo;s farm</a> '
            f"(Bahia, Brazil)",
            subtitle,
        )
    )
    story.append(
        Paragraph(
            f'<font size="8">Farm profile: <a href="{FARM_CANONICAL_URL}" color="blue">{FARM_CANONICAL_URL}</a></font>',
            subtitle,
        )
    )
    story.append(
        Paragraph(
            "<b>Agreement date:</b> March 25, 2026 &nbsp;|&nbsp; "
            "<b>Quote / logistics reference:</b> Sea Coast Logistics (e-mail March 24, 2026)",
            subtitle,
        )
    )

    parties_data = [
        ["Buyer (Customer)", "Seller (Agroverse supply network)"],
        [
            "3rd Eye Cafe<br/>"
            "Attention: Neil Dumra, Owner<br/>"
            "1701 Toomey Rd<br/>"
            "Austin, TX 78704<br/>"
            "United States",
            "U.S. import coordination / FDA Importer of Record (where applicable):<br/>"
            "<b>TrueTech Inc.</b><br/>"
            "EIN: 88-3411514<br/>"
            "CBP Importer Number: 88-341151400<br/>"
            "<br/>"
            "Origin processing &amp; export warehouse (Brazil):<br/>"
            "R. Cel. Paiva, 46 - Centro<br/>"
            "Ilh&eacute;us - BA, 45653-310, Brazil",
        ],
    ]
    pt = Table(
        _wrap_table_rows(parties_data, tbl_head, tbl_body_9),
        colWidths=[3.0 * inch, 3.25 * inch],
    )
    pt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), green_header),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
                ("TOPPADDING", (0, 1), (-1, -1), 10),
                ("BACKGROUND", (0, 1), (-1, -1), light_row),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]
        )
    )
    story.append(pt)
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("1. Product, price, and allocation hold", h2))
    story.append(
        Paragraph(
            f"Buyer agrees to purchase and Seller agrees to supply <b>two hundred seventy-six ({LB_CACAO}) pounds</b> "
            "of <b>ceremonial cacao paste</b>, sourced from "
            f'<a href="{FARM_CANONICAL_URL}" color="blue">Oscar&rsquo;s farm</a> (Bahia, Brazil), at '
            f"<b>USD ${PRICE_PER_LB:.2f} per pound</b>, for a <b>product subtotal of USD ${PRODUCT_TOTAL:,.2f}</b> "
            "(exclusive of logistics, duties, bonds, and customs assessments described below). "
            f'Farm profile: <a href="{FARM_CANONICAL_URL}" color="blue">{FARM_CANONICAL_URL}</a>.',
            body,
        )
    )
    story.append(
        _bullets(
            [
                "<b>Allocation hold.</b> Quoted pricing and availability are held for "
                "<b>ten (10) calendar days</b> from issuance, <b>through and including April 5, 2026</b>. "
                "After that, pricing and availability may change until a signed agreement and deposit are received.",
                "<b>Destination address.</b> Delivery is quoted to the Buyer address in the table above. "
                "If the receiving location differs, Buyer must provide the "
                "<b>correct destination address in writing before freight is booked</b>; quotes and transit may change.",
            ],
            body_li,
        )
    )

    story.append(Paragraph("2. Processing and transit timeline", h2))
    story.append(
        Paragraph(
            "After a signed agreement and the deposit in Section 5, Seller targets the following (estimates only):",
            body,
        )
    )
    story.append(
        _bullets(
            [
                "<b>Processing (~2 weeks):</b> convert <b>approximately eighty (80) kg</b> of cacao nibs and "
                "<b>approximately forty (40) kg</b> of cacao beans into cacao paste at the Brazil facility.",
                "<b>International freight (~2 additional weeks):</b> ship finished paste from "
                "<i>R. Cel. Paiva, 46 - Centro, Ilh&eacute;us - BA, 45653-310, Brazil</i> "
                "to <i>3rd Eye Cafe, 1701 Toomey Rd, Austin, TX 78704</i>.",
                "<b>Dependencies:</b> actual dates depend on production slots, carrier space, and customs clearance.",
                "<b>Updates:</b> Seller will provide reasonable progress updates during processing and shipping.",
            ],
            body_li,
        )
    )

    story.append(
        Paragraph(
            "3. Line items, totals, and payment schedule (Sea Coast Logistics)",
            h2,
        )
    )
    story.append(
        Paragraph(
            "The following table tabulates each quoted charge and how much is due now versus on arrival. "
            "Figures are from the Sea Coast Logistics e-mail dated March 24, 2026, except product price from Section 1.",
            body,
        )
    )
    story.append(
        _bullets(
            [
                "<b>Forwarder:</b> Sea Coast Logistics.",
                "<b>Routing:</b> pickup Ilh&eacute;us-area warehouse (address in Buyer/Seller table); "
                "delivery <b>Austin, TX 78704</b>.",
                "<b>Shipment assumptions:</b> <b>one (1) pallet</b>, 122 &times; 100 &times; 100 cm; "
                "<b>180 kg</b> actual weight; <b>210 kg</b> chargeable weight for air pricing.",
            ],
            body_li,
        )
    )

    def _usd(x):
        return f"{x:,.2f}"

    money_rows = [
        (
            f"Ceremonial cacao paste &mdash; {LB_CACAO} lb @ USD {_usd(PRICE_PER_LB)}/lb "
            f'(<a href="{FARM_CANONICAL_URL}" color="blue">Oscar&rsquo;s farm</a>, Bahia)',
            _usd(PRODUCT_TOTAL),
        ),
        (
            "Inland transport (Brazil): USD 695.00 + 0.15% ad valorem on cargo value "
            f"(USD {_usd(CARGO_VALUE_USD)} &rarr; USD {_usd(INLAND_AD_VAL)})",
            _usd(INLAND_TOTAL),
        ),
        (
            "Airport charges (Brazil): USD 0.30/kg, minimum 250.00 (210 kg chargeable; minimum applies)",
            _usd(AIRPORT_BR),
        ),
        (
            "Air freight SSA&ndash;IAH (210 kg chargeable weight)",
            _usd(AIR_FREIGHT),
        ),
        ("Airline terminal fee (TAP)", _usd(TERMINAL_TAP)),
        ("Import handling fee (per shipment)", _usd(IMPORT_HANDLING)),
        ("Delivery to door (airport collection; dock-to-door)", _usd(DELIVERY_DOOR)),
        ("U.S. customs clearance (broker)", _usd(US_CUSTOMS_CLEARANCE)),
        (
            "Commercial invoice line-item fees (broker; first 3 lines free)",
            _usd(INVOICE_LINE_FEES),
        ),
        ("FDA processing (broker)", _usd(FDA_PROCESSING)),
        (
            "<b>Subtotal &mdash; quoted freight, brokerage, and clearance (Section 3)</b>",
            f"<b>{_usd(QUOTED_LOGISTICS_SUBTOTAL)}</b>",
        ),
        (
            "<b>Subtotal &mdash; product + quoted logistics "
            "<i>(base for 50% / 50% payment installments)</i></b>",
            f"<b>{_usd(DEPOSIT_BASE_TOTAL)}</b>",
        ),
        (
            "<b>Due upon signed agreement &mdash; 50% immediate payment "
            "<i>(processing starts after this amount is received)</i></b>",
            f"<b>{_usd(DEPOSIT_50_PCT)}</b>",
        ),
        (
            "<b>Due upon arrival at Buyer&rsquo;s premises &mdash; remaining 50% of the subtotal above</b>",
            f"<b>{_usd(BALANCE_50_ON_ARRIVAL)}</b>",
        ),
        (
            "Estimated MPF (U.S. customs; <b>minimum</b> per broker notice; reconciled on entry)&mdash; "
            "<i>not included in the 50% deposit base</i>",
            _usd(MPF_MIN),
        ),
        (
            "Estimated single-entry surety bond (<b>minimum</b> per broker; actual bond varies)&mdash; "
            "<i>not included in the 50% deposit base</i>",
            _usd(BOND_MIN_EST),
        ),
        (
            "Import duties (if any)",
            "At cost (TBD)",
        ),
        (
            "<b>Estimated order total, excluding duties &amp; customs exams</b>",
            f"<b>{_usd(EST_TOTAL_EXCL_DUTIES)}</b>",
        ),
    ]
    money_matrix = _money_table_matrix(
        money_rows,
        tbl_head,
        tbl_head_amt,
        tbl_money_desc,
        tbl_money_amt,
    )
    # Demarcate product (cacao) from Sea Coast line items: thick rule + section header row
    money_matrix.insert(
        2,
        [
            Paragraph(
                "<b>Sea Coast Logistics</b> &mdash; quoted freight, brokerage, and U.S. customs clearance",
                tbl_money_section,
            ),
            Paragraph("", tbl_money_amt),
        ],
    )
    money_table = Table(money_matrix, colWidths=[4.95 * inch, 1.3 * inch])
    sea_coast_header_row = 2
    first_subtotal_row = 12  # quoted logistics subtotal (after header + product + sea coast banner + 10 charge rows)
    pay_block_row = 14  # LINEABOVE before 50% / 50% block
    pay_row_a, pay_row_b = 14, 15
    est_total_row = 19
    money_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), green_header),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light_row]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("LINEBELOW", (0, 1), (-1, 1), 1.25, colors.black),
                ("LINEABOVE", (0, sea_coast_header_row), (-1, sea_coast_header_row), 0.5, colors.grey),
                ("SPAN", (0, sea_coast_header_row), (1, sea_coast_header_row)),
                ("BACKGROUND", (0, sea_coast_header_row), (-1, sea_coast_header_row), colors.HexColor("#dde8dd")),
                ("LINEABOVE", (0, first_subtotal_row), (-1, first_subtotal_row), 0.75, colors.black),
                ("LINEABOVE", (0, pay_block_row), (-1, pay_block_row), 0.75, green_header),
                ("BACKGROUND", (0, pay_row_a), (-1, pay_row_b), colors.HexColor("#d4e8d4")),
                ("TEXTCOLOR", (0, pay_row_a), (-1, pay_row_b), colors.HexColor("#0d260d")),
                ("LINEABOVE", (0, est_total_row), (-1, est_total_row), 0.75, colors.black),
                ("BACKGROUND", (0, est_total_row), (-1, est_total_row), colors.HexColor("#eef5ee")),
            ]
        )
    )
    story.append(Spacer(1, 0.06 * inch))
    story.append(money_table)
    story.append(Spacer(1, 0.08 * inch))
    story.append(
        Paragraph(
            "<b>Excluded from the quoted-logistics subtotal above:</b> import duties; variable surety bond beyond the "
            "minimum shown; MPF above the broker&rsquo;s stated min/max; commercial-invoice line items beyond the "
            "first three (USD 5.00/line); customs examinations if assessed. "
            "<b>Bond &amp; duties (broker language):</b> USD 6.00 per USD 1,000 of value plus duty, USD 100.00 minimum; "
            "MPF 0.3464% with USD 33.58 minimum / USD 651.50 maximum (per broker). "
            "<i>Final Sea Coast and broker invoices may differ slightly from this schedule.</i>",
            body,
        )
    )
    story.append(
        _bullets(
            [
                "ALL SHIPMENTS ARE SUBJECT TO U.S. CUSTOMS INSPECTION AND EXAMS AT CBP DISCRETION.",
                "EXAM CHARGES ARE AT COST PLUS USD $125.00 HANDLING PER EXAM (per broker).",
            ],
            small_li,
            left_indent=18,
            bullet_indent=6,
        )
    )

    story.append(Paragraph("4. Import representation", h2))
    story.append(
        _bullets(
            [
                "<b>U.S. import coordination:</b> entries are coordinated with <b>TrueTech Inc.</b>",
                "<b>FDA Importer of Record / CBP importer on file (as applicable):</b> TrueTech Inc.; "
                "EIN 88-3411514; CBP importer number 88-341151400.",
            ],
            body_li,
        )
    )

    story.append(Paragraph("5. Payment terms", h2))
    story.append(
        _bullets(
            [
                "<b>Deposit to start processing:</b> upon (i) Buyer&rsquo;s executed agreement and "
                "(ii) receipt of <b>fifty percent (50%)</b> of the combined "
                "<b>cost of cacao</b> (Section 1 product subtotal) and <b>freighting</b> per the "
                "<b>Sea Coast Logistics quoted line-item subtotal</b> in Section 3 "
                f"(USD ${QUOTED_LOGISTICS_SUBTOTAL:,.2f} as listed). "
                "<i>Duties, variable bond, and MPF</i> are reconciled when invoiced—not part of that 50% base.",
                f"<b>Illustrative deposit amount:</b> 50% &times; (USD ${PRODUCT_TOTAL:,.2f} + USD ${DEPOSIT_BASE_LOGISTICS:,.2f}) "
                f"= <b>USD ${DEPOSIT_50_PCT:,.2f}</b>.",
                f"<b>All-in planning range (not a cap):</b> per the &ldquo;estimated order total&rdquo; row in the Section 3 table "
                f"(<b>USD ${EST_TOTAL_EXCL_DUTIES:,.2f}</b> before duties/exams). "
                "Seller will true up against final forwarder, broker, and customs invoices.",
                "<b>Balance:</b> the remaining <b>fifty percent (50%)</b> for product and booked logistics is due when "
                "the cacao paste <b>arrives at Buyer&rsquo;s designated premises</b> (or as otherwise agreed in writing).",
            ],
            body_li,
        )
    )

    story.append(Paragraph("6. Payment methods", h2))
    story.append(
        _bullets(
            [
                "<b>ACH or domestic/international wire (USD):</b> use the Wells Fargo details in the table below.",
                "<b>Venmo:</b> <b>@garyjob</b>.",
                "<b>Payment memo / reference:</b> include &ldquo;3rd Eye Cafe &mdash; Oscar paste&rdquo; so the payment can be matched.",
            ],
            body_li,
        )
    )
    pay_data = [
        ["Field", "Details"],
        [
            "Bank",
            "Wells Fargo Bank, N.A.",
        ],
        [
            "Account number",
            "1990303099",
        ],
        [
            "ACH / domestic bank routing (ABA)",
            "Use the 9-digit routing number on file for <i>ACH</i> as shown on the account holder&rsquo;s "
            "Wells Fargo records (often found on checks or in online banking). "
            "Confirm with the account holder before first transfer.",
        ],
        [
            "Wire &mdash; SWIFT / BIC",
            "<b>WFBIUS6S</b> (confirm for recurring templates with Wells Fargo)",
        ],
        [
            "Wire &mdash; bank address",
            "Wells Fargo Bank, N.A., 420 Montgomery Street, San Francisco, CA 94104, USA",
        ],
        [
            "Wire &mdash; routing (FW)",
            "Use the <i>wire transfer</i> routing number from the account holder&rsquo;s Wells Fargo wire instructions "
            "(domestic wire routing differs by region; call Wells Fargo at 1-800-869-3557 if needed).",
        ],
        [
            "Beneficiary name",
            "Exact legal account name on the Wells Fargo account (confirm with Seller before sending).",
        ],
        ["International notes", "Correspondent bank details, if required by your bank, are provided on Wells Fargo wire instructions."],
    ]
    pyt = Table(
        _wrap_table_rows(pay_data, tbl_head, tbl_body_8),
        colWidths=[1.45 * inch, 4.8 * inch],
    )
    pyt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), green_header),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light_row]),
            ]
        )
    )
    story.append(pyt)

    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("7. General", h2))
    story.append(
        _bullets(
            [
                "This agreement reflects commercial terms discussed in March 2026.",
                "If any provision conflicts with an insurance certificate, bill of lading, or customs filing, "
                "the parties will align those documents in good faith with this intent.",
                "Electronic or PDF signatures are acceptable.",
            ],
            body_li,
        )
    )

    sig_style = ParagraphStyle("Sig", parent=styles["Normal"], fontSize=10, alignment=TA_LEFT)
    sig_caption = ParagraphStyle(
        "SigCaption",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#555555"),
        spaceAfter=2,
    )
    sig_note = ParagraphStyle(
        "SigNote",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#555555"),
        spaceAfter=6,
    )
    # Open signing area (height) + ruled line reads better than dense underscores for ink or e-sign.
    sign_area_w = doc.width
    sign_area_h = 0.58 * inch
    sig_box = Table(
        [[Paragraph("", sig_style)]],
        colWidths=[sign_area_w],
        rowHeights=[sign_area_h],
    )
    sig_box.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.75, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        )
    )
    # Keep signature block on one page (undivided lines / stray page breaks).
    story.append(
        KeepTogether(
            [
                Spacer(1, 0.18 * inch),
                Paragraph(
                    "<i>By signing below, Buyer confirms agreement with all pages. "
                    "Buyer should also initial each page footer.</i>",
                    sig_note,
                ),
                Spacer(1, 0.08 * inch),
                Paragraph(f"<b>Buyer</b> — {SIGNATORY_BUYER_LINE}", sig_style),
                Spacer(1, 0.12 * inch),
                Paragraph("Signature of authorized representative", sig_caption),
                sig_box,
                Spacer(1, 0.1 * inch),
                Paragraph("Name: Neil Dumra", sig_style),
                Paragraph("Title: Owner", sig_style),
                Paragraph("Date: ____________________", sig_style),
            ]
        )
    )

    doc.build(
        story,
        onFirstPage=_purchase_agreement_page_footer,
        onLaterPages=_purchase_agreement_page_footer,
    )
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
