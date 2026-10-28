#!/usr/bin/env python3
"""
Generate the Agroverse 81% single-estate dark chocolate wholesale price list PDF.

Winery / tasting-room channel edition.

Usage:
    python3 generate_81_bar_price_list.py
Output:
    agroverse_81_bar_wholesale_price_list_2026.pdf (overwrites existing)

All commercial terms live in the constants block below so a price change happens
in exactly one place.

COGS_PER_BAR derivation (50 g bar; from the DAO ledger `Currencies` tab, already
USD-denominated so no FX assumption is involved):
    Cacao Mass Bar CP340992687BR (50grams) ... $2.154026  landed, incl. freight
    Sticker Mule 4x2in label (per piece) ..... $0.554
    Chocolate wrapper die cutter ............. $0.00      one-off die, no per-unit
    ------------------------------------------------------
    TOTAL .................................... $2.708026  (~$2.71)

WARNING: an earlier $5.62/bar figure came from costing 50 g off
`Cacao Almonds KG - Organic` = $100.886/kg -- a row ~2.6x every other cacao
currency row (the real farmgate rows run $7.87-$42.93/kg) and already tombstoned
DEPRECATED in the ledger. It implies a 6% gross margin on a $10 RRP artisan bar,
which is not credible. Do not reuse it.
"""

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(
    SCRIPT_DIR, "20230711 - Agroverse logo for trademark filing.jpeg"
)
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "agroverse_81_bar_wholesale_price_list_2026.pdf")

# -- Commercial terms -------------------------------------------------------
WHOLESALE_PER_BAR_USD = 6.00
RRP_PER_BAR_USD = 10.00
COGS_PER_BAR_USD = 2.71
BAR_WEIGHT_G = 50
# Only estates we can actually ship are listed. Stock truth at time of writing
# (store inventory): Oscar's 40, Vivi's 40, Sao Jorge 4 (nearly out), Santa Ana 0
# (not being stocked this year). Gary's instruction: pitch Oscar's only, mention
# Vivi's as coming online, do NOT pitch Sao Jorge or Santa Ana.
#   - Sao Jorge: about to go out of stock, so pitching it invites an order we
#     cannot fill.
#   - Santa Ana: not stocked this year, so it must not appear at all.
ORIGINS_PER_FLIGHT = 1
FLIGHT_BARS = 12
FREE_SHIPPING_BARS = 24

# Real product photography, pulled from the live storefront asset for the bar SKU.
# Only one bar image exists (the same file backs all four bar SKUs), so this is a
# single photo -- there is no separate front/back pair for bars.
BAR_PHOTO_PATH = os.path.join(SCRIPT_DIR, "agroverse_81_bar_packaging.jpeg")
BAR_PHOTO_WIDTH_IN = 3.1

_HEADER_BG = colors.HexColor("#2d5a27")
_ROW_BG = colors.HexColor("#f5f5f5")
_MUTED = colors.HexColor("#555555")
_BODY = colors.HexColor("#444444")

# Origin list. `taste` is verbatim from templates/farm_taste_profiles.md where a
# profile exists. Where it does not, `note` carries only what we can actually
# stand behind -- we never invent tasting descriptors for a wholesale document.
#
# TODO(gary): Santa Ana and Sao Jorge have no taste descriptors in
# templates/farm_taste_profiles.md. Supply them and they drop straight in here.
ORIGINS = [
    {
        "name": "Oscar's Farm",
        "location": "Bahia, Brazil",
        "taste": (
            "Deep, dark European chocolate profile with exceptionally buttery, "
            "velvety mouthfeel. Intense chocolate notes with subtle undertones of "
            "earth and wood. Smooth, low-acidity finish."
        ),
        "note": None,
    },
]


def _table_style(zebra=True):
    """Shared table styling, matching the existing cacao price list."""
    rules = [
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -1), _ROW_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]
    if zebra:
        rules.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_BG]))
    return TableStyle(rules)


def _money(value):
    return f"${value:,.2f}"


def build_story(styles):
    """Assemble the PDF flowables."""
    story = []

    if os.path.exists(LOGO_PATH):
        from PIL import Image as PILImage

        with PILImage.open(LOGO_PATH) as pil_img:
            w, h = pil_img.size
        max_w = 0.625 * inch
        scale = max_w / w
        img = Image(LOGO_PATH, width=max_w, height=h * scale)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 0.2 * inch))

    story.append(
        Paragraph(
            "Single-Estate Dark Chocolate",
            ParagraphStyle(
                name="Title",
                parent=styles["Heading1"],
                fontSize=18,
                spaceAfter=6,
                alignment=TA_CENTER,
            ),
        )
    )
    story.append(
        Paragraph(
            "Wholesale Price List &mdash; 81% Cacao Bars",
            ParagraphStyle(
                name="SubTitle",
                parent=styles["Normal"],
                fontSize=12,
                alignment=TA_CENTER,
            ),
        )
    )
    story.append(
        Paragraph(
            "<i>Effective 2026 &middot; Tasting rooms, wineries &amp; gift retail</i>",
            ParagraphStyle(
                name="Year",
                parent=styles["Normal"],
                alignment=TA_CENTER,
                fontSize=10,
                textColor=_MUTED,
            ),
        )
    )
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("The Price", styles["Heading2"]))
    price_rows = [
        ["Item", "Wholesale", "Suggested retail"],
        [
            f"81% dark chocolate bar, {BAR_WEIGHT_G} g",
            _money(WHOLESALE_PER_BAR_USD) + " / bar",
            _money(RRP_PER_BAR_USD) + " / bar",
        ],
        [
            f"Opening case — {FLIGHT_BARS} bars, {ORIGINS_PER_FLIGHT} estate",
            _money(WHOLESALE_PER_BAR_USD * FLIGHT_BARS),
            _money(RRP_PER_BAR_USD * FLIGHT_BARS),
        ],
    ]
    price_table = Table(price_rows, colWidths=[3.0 * inch, 1.5 * inch, 1.5 * inch])
    price_table.setStyle(_table_style())
    story.append(price_table)
    story.append(Spacer(1, 0.12 * inch))
    story.append(
        Paragraph(
            f"Retailer margin at suggested price: "
            f"<b>{_money(RRP_PER_BAR_USD - WHOLESALE_PER_BAR_USD)} per bar "
            f"({(RRP_PER_BAR_USD - WHOLESALE_PER_BAR_USD) / RRP_PER_BAR_USD:.0%})</b>.",
            ParagraphStyle(
                name="Margin", parent=styles["Normal"], fontSize=9, textColor=_MUTED
            ),
        )
    )
    story.append(Spacer(1, 0.35 * inch))

    story.append(Paragraph("Why Single Estate", styles["Heading2"]))
    story.append(
        Paragraph(
            "We grow on separate estates and we do not blend them &mdash; every bar "
            "is a single origin, made from one farm's fruit. That is the whole "
            "point: the same 81% recipe reads completely differently depending on "
            "the soil it came from, and a single-estate bar is a claim about a "
            "place rather than a house style. It is the same reason your tasting "
            "room exists.",
            ParagraphStyle(name="Intro", parent=styles["Normal"], fontSize=10),
        )
    )
    story.append(Spacer(1, 0.15 * inch))
    if os.path.isfile(BAR_PHOTO_PATH):
        from PIL import Image as PILImage

        with PILImage.open(BAR_PHOTO_PATH) as pil_img:
            _w, _h = pil_img.size
        _photo_w = BAR_PHOTO_WIDTH_IN * inch
        story.append(
            Image(
                BAR_PHOTO_PATH,
                width=_photo_w,
                height=_h * (_photo_w / _w),
            )
        )
        story.append(
            Paragraph(
                f"{BAR_WEIGHT_G} g bar, wrapped.",
                ParagraphStyle(
                    name="Caption",
                    parent=styles["Normal"],
                    fontSize=8,
                    textColor=_MUTED,
                    alignment=TA_CENTER,
                ),
            )
        )
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("The Origins", styles["Heading2"]))
    for origin in ORIGINS:
        story.append(
            Paragraph(
                f"<b>{origin['name']}</b> &mdash; {origin['location']}",
                styles["Normal"],
            )
        )
        body = origin["taste"] or origin["note"]
        story.append(
            Paragraph(
                body,
                ParagraphStyle(
                    name="Origin",
                    parent=styles["Normal"],
                    fontSize=9,
                    leftIndent=12,
                    textColor=_BODY,
                ),
            )
        )
        story.append(Spacer(1, 0.12 * inch))

    story.append(
        Paragraph(
            "<b>Coming online:</b> Vivi's Jesus Do Deus Farm, Itacar&eacute; "
            "&mdash; a former cattle ranch turned regenerative cacao forest. "
            "Ask us for availability.",
            ParagraphStyle(
                name="ComingOnline",
                parent=styles["Normal"],
                fontSize=9,
                textColor=_MUTED,
                leftIndent=12,
            ),
        )
    )
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Ordering &amp; Shipping", styles["Heading2"]))
    order_rows = [
        ["Order size", "Terms"],
        [
            f"{FLIGHT_BARS} bars (opening order)",
            f"{_money(WHOLESALE_PER_BAR_USD * FLIGHT_BARS)} — the low-risk way to find out how it moves",
        ],
        [
            "Reorder",
            "Same per-bar price, no volume tiers — reorder deeper as it sells",
        ],
        [
            f"{FREE_SHIPPING_BARS}+ bars",
            "Free shipping within the contiguous US",
        ],
        [
            f"Under {FREE_SHIPPING_BARS} bars",
            "Shipping billed at cost",
        ],
    ]
    order_table = Table(order_rows, colWidths=[2.2 * inch, 3.8 * inch])
    order_table.setStyle(_table_style())
    story.append(order_table)
    story.append(Spacer(1, 0.12 * inch))
    story.append(
        Paragraph(
            "Start with one case rather than over-committing: the per-bar price does not "
            "change with volume, so there is no reason to buy deep before you know how it "
            "sells. Reorder when it moves.",
            ParagraphStyle(
                name="Reorder", parent=styles["Normal"], fontSize=9, textColor=_MUTED
            ),
        )
    )
    story.append(Spacer(1, 0.12 * inch))
    story.append(
        Paragraph(
            "<b>Note:</b> prices exclude shipping unless stated. Bars ship from our "
            "San Francisco warehouse. Availability depends on the current "
            "harvesting season, so please confirm stock when ordering.",
            ParagraphStyle(
                name="Note", parent=styles["Normal"], fontSize=9, textColor=_MUTED
            ),
        )
    )
    story.append(Spacer(1, 0.3 * inch))

    story.append(
        Paragraph(
            "Every bar sold helps plant a tree as part of our mission to restore "
            "10,000 hectares of Amazon rainforest.",
            ParagraphStyle(
                name="Mission",
                parent=styles["Normal"],
                fontSize=10,
                alignment=TA_CENTER,
            ),
        )
    )
    story.append(Spacer(1, 0.3 * inch))

    story.append(
        Paragraph(
            "<b>Contact</b><br/>Agroverse | Phone: 415-300-0019 | agroverse.shop",
            ParagraphStyle(
                name="Contact",
                parent=styles["Normal"],
                fontSize=10,
                alignment=TA_CENTER,
            ),
        )
    )
    return story


def _rendered_pdf_text() -> str:
    """Extract the visible text of the generated PDF (test-only helper).

    Renders the same story main() builds into a throwaway buffer so tests can
    assert on what a reader actually sees, independent of the committed PDF.
    """
    import io

    from pypdf import PdfReader

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(build_story(getSampleStyleSheet()))
    buf.seek(0)
    return "\n".join((p.extract_text() or "") for p in PdfReader(buf).pages)


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
    doc.build(build_story(styles))
    print(f"Generated: {OUTPUT_PATH}")
    gross = WHOLESALE_PER_BAR_USD - COGS_PER_BAR_USD
    print(
        f"Gross margin per bar: {_money(gross)} "
        f"({gross / WHOLESALE_PER_BAR_USD:.0%}) at COGS {_money(COGS_PER_BAR_USD)}"
    )


if __name__ == "__main__":
    main()
