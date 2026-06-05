# Agroverse — DTC Paid Acquisition Brief

**For:** Hubert Yee (Growth / Performance Marketing / User Acquisition)
**From:** Gary Teh, Agroverse / TrueSight DAO
**Date:** June 5, 2026
**Status:** DRAFT v1 — for discussion

---

## 1. Why we're asking for your time

Agroverse sells ceremonial cacao. To date we've grown almost entirely through
in-person channels — retail partners, festivals, ceremony circles. We now have
hard evidence that customers will buy and **re-buy online, direct, with no
face-to-face contact**, and we believe there's an opportunity to open a paid
digital acquisition channel (DTC e-commerce).

Nobody on the team has run performance marketing at your level. Before we spend
a dollar on ads, we want your expert read on **what the shape of the process
should be** — how to structure the test, what to measure, what it takes to set
the process up properly — so we don't learn expensive lessons that are already
well-known to practitioners.

This is an advisory ask, not a pitch. Sections 2–5 give you the context;
Section 6 has the specific questions.

---

## 2. What Agroverse is (60-second version)

- **Product:** Ceremonial-grade cacao, sourced direct from family farms in
  Bahia and Pará, Brazil. Flagship SKU: **200 g bag, retails at USD $25**.
  Secondary SKUs: caramelized cacao beans, cacao tea.
- **Mission mechanics:** Agroverse is the commerce arm of
  [TrueSight DAO](https://truesight.me). Every bag funds Amazon rainforest
  regeneration — one bag → one tree financed, and every bag carries a **QR code
  that traces back to the actual farm and shipment ledger** the cacao came
  from. The entire supply chain is publicly ledgered (18 managed shipment /
  program ledgers to date, AGL0–AGL15 plus program funds).
- **Store:** [agroverse.shop](https://agroverse.shop) — static site + Stripe
  checkout. No app. Orders ship from a San Francisco warehouse.
- **Distribution today:** ~37 retail partners (apothecaries, metaphysical
  shops, wellness venues, co-working spaces) mostly on the US West Coast,
  largely on consignment; plus festivals, cacao ceremonies, and events run by
  partners.
- **Brand:** Provenance and verifiable impact are the differentiation. We are
  deliberately *not* a commodity chocolate brand; the story (farm → ledger →
  tree) is the product.

---

## 3. The signal that triggered this brief

### 3a. Customers re-order online, unprompted

A customer in **Shoreline, WA** (acquired in person at events run by our
Ashland, OR partner Kelly Springer / Love Wisdom Power) has now ordered twice
from agroverse.shop, entirely self-served:

| Order date | Items | Subtotal | Total (incl. shipping) |
|---|---|---|---|
| Dec 25, 2025 | 2× ceremonial cacao 200 g + 1× caramelized beans 200 g | $75.00 | $83.58 |
| May 29, 2026 | 2× ceremonial cacao 200 g | $50.00 | $58.61 |

That's a **~5-month reorder cycle on a multi-bag basket** — implying a
consumption rate of roughly **1 bag every 1.5 months** for an engaged
practitioner. If that rate holds, a retained customer is worth roughly
**$200/year in revenue** (≈8 bags), with zero incremental acquisition cost
after the first order.

### 3b. Zero-touch onboarding works

Our newest retail partner (The Way Home Shop, Portland, OR) was acquired
entirely over email: cold outreach Apr 24 → consignment terms agreed Apr 26 →
10 bags shipped Apr 28 → on the shop floor Apr 29 → first commission statement
and payment May 13. **No in-person visit at any point.** The product, story,
and packaging sell themselves when they reach the right person.

Together: the demand exists beyond arm's reach of our in-person presence, and
the funnel (site → Stripe → fulfillment → repeat) already works. What we've
never done is **pour paid traffic into the top of it**.

---

## 4. Unit economics & where the ad budget comes from

| Lever | Value |
|---|---|
| Retail price (200 g bag) | $25.00 |
| Retailer commission baked into that price | ~$8.00/bag (actual: $7.50 at our newest partner) |
| Consignment cost price to retailers | $17.00/bag (shipping included) |
| Observed DTC basket | 2–3 bags, $50–75 subtotal, customer pays shipping (~$8.60) |
| Observed reorder cycle | ~5 months on a multi-bag basket (~1 bag/1.5 months consumed) |

The core arbitrage: **on a DTC sale, the ~$8/bag that would have gone to a
retailer is unspent**. On an observed 2–3 bag basket that's **$16–24 of
first-order margin headroom available for CAC** — before counting repeat
purchases. If the Shoreline pattern generalizes (~$200/yr per retained
customer), the LTV-justifiable CAC is meaningfully higher than the first-order
headroom alone.

We don't yet know our blended margins well enough to commit to a target
CAC/ROAS — that's one of the things we want your help framing (Section 6).

---

## 5. Audience & competitive observations

- **Who buys:** ceremony facilitators, breathwork/yoga/meditation
  practitioners, apothecary customers, conscious-consumption households.
  Observed at festivals: skews 35–65, values-driven, **heavily on Facebook**
  (and Instagram); not a TikTok-first demographic.
- **Competitors:** ceremonial cacao brands (e.g. the larger Keith's/Cacao
  Laboratory tier of the market) are **buying Google ads heavily** on
  ceremonial-cacao search terms. Search volume for the category exists and is
  being monetized — currently without us.
- **Our edge in creative:** real farms, real farmers, real trees, QR-verifiable
  impact, and an existing library of farm photography/video from Bahia. The
  story is filmable and ownable.

**Brand guardrails** (these are firm):

1. No paid influencer / creator endorsements — paid endorsement flattens the
   provenance story. Earned mentions are fine.
2. The brand voice is community/lineage-centered, not founder-personality
   marketing.
3. We're a DAO — every dollar of spend and revenue is publicly ledgered. The
   ads process must produce clean enough numbers to ledger.

---

## 6. What we want your input on

We're trying to understand **the shape of the process**, not asking you to run
campaigns. Specifically:

1. **Channel sequencing.** Given the demographic (Facebook-heavy) and the
   competitor behavior (Google search), where would you start — Meta
   prospecting, Google search capture, or both in parallel? What's the minimum
   viable channel mix to learn anything?
2. **Budget floor.** What monthly spend is the realistic minimum to get
   statistically meaningful signal on a $25–75 AOV product? How long should a
   test run before we judge it?
3. **Measurement stack.** For a static site + Stripe checkout (no app, no
   existing pixel infrastructure): what's the right minimal setup? (Meta
   Pixel + Conversions API? GA4? Server-side events from Stripe webhooks?
   Anything you'd skip at our scale?)
4. **KPI framework.** How should we define target CAC / ROAS given the repeat
   behavior above? First-order breakeven vs. LTV-payback — what's the right
   frame for a consumable with a ~1.5-month consumption cycle?
5. **Creative requirements.** What formats and how many variants do we
   realistically need to start on Meta? Is founder-shot/UGC-style sufficient,
   or does this category need produced assets? How fast should we expect to
   iterate?
6. **Landing experience.** Send traffic to existing product pages, or build
   dedicated landers? Anything about our checkout flow you'd fix first
   (e.g. customer-paid shipping at $8.60 on a $25 item)?
7. **Process & people.** What does the operating cadence look like (weekly
   reviews? creative pipeline? budget reallocation rules)? At our stage, is
   this in-house-founder-run, fractional specialist, or agency work — and
   what would you watch for in each?
8. **Failure modes.** What are the classic ways a sub-$5k/month DTC ads
   program wastes its budget, and how do we pre-empt them?

---

## 7. Appendix — links & sources

- Store: <https://agroverse.shop>
- Example product page: <https://agroverse.shop/product-page/ceremonial-cacao-fazenda-santa-ana-2023-200g>
- Farm provenance example: <https://agroverse.shop/farms/oscar-bahia/index.html>
- Partner network: <https://agroverse.shop/partners/>
- DAO transparency: <https://truesight.me> (treasury, ledgers, stats)
- Shipment ledgers: TrueSight DAO Main Ledger, "Shipment Ledger Listing" tab
  (18 managed ledgers, AGL0–AGL15 + program funds)
- Repeat-order evidence: agroverse.shop Stripe order notifications,
  Dec 25 2025 & May 29 2026 (customer details withheld here; available on
  request)
- Remote-onboarding evidence: The Way Home Shop email thread,
  Apr 24 – May 13, 2026
