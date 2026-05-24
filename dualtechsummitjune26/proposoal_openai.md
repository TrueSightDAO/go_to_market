# Dual Tech Summit (June 26) — Cacao Service + Publicity Plan

Status: Proposal v0.1 (for Ken + team review)

## Owner Recommendation (per cross-proposal verdict)

- Lead owner: Claude (Anthropic) — narrative/messaging, provenance-first framing, truesight.me methodology essay.
- Onsite co-owner: Kimi — human flow, serving cadence, materials/logistics on the day.
- Support: OpenAI — asset templates (QR batch brief, table-tent/cup-sticker copy), doc hygiene, follow-up checklists.
- Not recommended as lead: Deepseek — heavier promo posture; misaligned with permission-first, no-announcement rule.

Rationale: audience fit (defense/dual-use founders, VCs, veterans) responds best to verifiable provenance and primary-source claims; Claude’s draft centers that and preserves our house style (method > announcement, zero pressure, proofs over promises).

— This plan follows our established operating patterns: place-first Agroverse storytelling, zero-pressure invites, QR trace-back measurement, and human-in-the-loop outreach (see EDITORIAL_TONE.md, PARTNER_OUTREACH_PROTOCOL.md, GROWTH_MODEL.md).

## Objectives

- Trees financed: Convert tastings to scans → tree pages → purchases.
- Partner leads: Identify 3–5 qualified venues to trial consignment.
- Story surface: Capture assets for one Bean to Bliss micro-post and a truesight.me methods write-up post-event.
- Telemetry: Attribute engagement via event-unique QR and UTM.

## Positioning (public copy guardrails)

- Mantra: “Regenerating our Amazon rainforest, One Cacao at a time.”
- Tone: Warm-professional; invite to taste and learn (no hard CTA).
- Place-first: Name venue/city and the farmers/co-ops by name.
- Promise only what we can deliver (consignment starter: 5 bags).

## Channels by Phase

### Pre-Event (T-10 to T-1)

- Event landing: `agroverse.shop/events/dual-tech-summit-2026-06-26` (slug TBD). Content: date/place, who’s pouring, farms featured, “scan to see your tree.”
- Luma page blurb (ask Ken): 2–3 lines + link to landing page.
- Email warm-up: Draft 3–5 follow-ups to likely venue leads near [City], referencing attendance (use Hit List → Manager Follow-up; samples offer on consignment).
- Social: 2 posts + 2 story frames (schedule via existing social workflow):
  - Post 1 (T-7): “Cacao meets [Event]. Taste Bahia + Pará.”
  - Post 2 (T-1): “Find us at breaks — one cup → one tree.”

### Onsite (Event day)

- Cacao bar: Small-cup tastings of ceremonial cacao; optional cacao tea.
- Signage: Table tent with “One cup → one tree” + QR to event landing.
- QR-coded cups: Stickers with event-unique QR (batch: `QR_BATCH=DTS-2026-06-26`).
- Program mention (ask Ken): 60-second invite during opening or first break.
- “Meet the farms” mini-cards: Oscar (Bahia) + Paulo (Pará) page links.

### Post-Event (T+1 to T+14)

- Attendee follow-up: Short thank-you page auto-resolved from QR (shows tree trace-back + shop links; soft invite to partner/samples form).
- Lead follow-up: Human-in-loop emails to conversations from the floor; offer consignment starter (5 bags) and delivery details.
- Content: 
  - Bean to Bliss micro-post with 2–3 photos (warm, place-anchored).
  - truesight.me “method, not announcement” piece (what worked/why QR trace-back matters for events), optional if there’s a clear learning.

## Deliverables

- Event landing page (copy + images + QR target).
- QR batch for tracking (see AGROVERSE_QR_CODE_BATCH_GENERATION.md):
  - Code: `DTS-2026-06-26`
  - Target: event landing with `utm_source=event&utm_medium=qr&utm_campaign=dts-20260626`
- Table signage PDF (A5) and cup stickers (1–1.5”).
- Mini “Meet the farms” cards (URLs to Oscar + Paulo pages).
- Social assets (2 feed, 2 story) aligned with tone guide.

## Pre-Event — Website Tasks (checklist)

- Create event page at `agroverse.shop/events/dual-tech-summit-2026-06-26` with:
  - Place-first opener, farms featured (Oscar—Bahia; Paulo—Pará), tasting times (breaks), and “One cup → one tree.”
  - SEO: title/description, OpenGraph/Twitter image, canonical URL.
  - Schema.org `Event` block (name, startDate, location, organizer, `offers` as free tasting).
  - UTM-ready CTA buttons: `View on Luma`, `Meet the farms`, `What is ceremonial cacao?`.
- Avoid site-wide hero/banner per no-announcement norm; keep event page discoverable (events index), not promoted across the homepage.
- Add `/events/` index if not present; list this event with thumbnail.
- Cross-link farm pages with a small “Pouring at Dual Tech Summit” ribbon linking back to the event page.
- Provision the QR target route and confirm UTM handling for `dts-20260626`.
- Update `sitemap.xml` and ensure robots allow the page; verify 200/OG preview.
- Compress and upload hero/social images; add alt text (accessibility).

## Pre-Event — Newsletter Plan (revised per verdict)

- Audience: do not blast full list. If sending, limit to SF-local segment or do 1:1 personal messages; otherwise defer to post-event if there’s a real story.
- Timing: Optional T-7 segmented send only; no T-2 resend. Prefer post-event single dispatch if earned by substantive field learnings.
- UTM: `utm_source=newsletter&utm_medium=email&utm_campaign=dts-20260626` on all links.
- Subject lines (pick one; stay warm, zero-pressure):
  - “Taste Brazil’s regenerative cacao at Dual Tech Summit — one cup → one tree”
  - “[City], we’re pouring cacao at Dual Tech Summit (Bahia ↔ Pará)”
- Preheader: “Find us at the breaks; scan to see your tree.”
- Body shape (Agroverse tone): place-first opener → farms by name → where to find us → one cup → one tree → add to calendar.
- CTAs: `Add to calendar (Luma)`, `Meet the farms`, `What is ceremonial cacao?`.
- How to ship: use `market_research/scripts/send_newsletter.py` or your ESP; paste the copy below and update links. Mark campaign as segmented/local-only.

### Newsletter draft (ready-to-send)

Subject: Taste Brazil’s regenerative cacao at Dual Tech Summit — one cup → one tree

Hi there,

We’ll be pouring ceremonial cacao at the Dual Tech Summit in [City] on June 26. Find us at the refreshment breaks and taste cacao from Bahia and Pará in Brazil.

One cup → one tree. Scan at the table to see the tree your tasting helps plant.

Meet the farms:
- Oscar — Bahia: https://agroverse.shop/farms/oscar-bahia/index.html
- Paulo — La do Sitio, Pará: https://agroverse.shop/farms/paulo-la-do-sitio-para/index.html

Add to calendar / RSVP: https://luma.com/dualtechsummitjune26
Event details: https://agroverse.shop/events/dual-tech-summit-2026-06-26?utm_source=newsletter&utm_medium=email&utm_campaign=dts-20260626

Regenerating our Amazon rainforest, One Cacao at a time.  
415-300-0019

## Measurement

- QR scans (unique + total) for `DTS-2026-06-26`.
- Landing page CTR to farm/product pages.
- Email signups or partner-interest form submissions.
- Partner leads created (Hit List rows moved to Contacted/Manager Follow-up).
- Trees financed attributable to campaign window (see GROWTH_GOALS pipeline).

## Dependencies / Asks (Ken + event org)

- Space: 1 table near coffee/tea breaks; access to power/hot water or allowance to bring thermos.
- Program: 60s mention in opening or first break; logo placement near refreshments (if allowed).
- Luma: Add event blurb + link to landing page; optional RSVP reminder note.
- Onsite: Permission for small signage and QR stickers on cups.

## Logistics (draft)

- Product: 3–5 kg ceremonial cacao (adjust to expected footfall), cacao tea optional.
- Gear: Kettle/thermos, pitchers, compostable cups (4–6 oz), ladle, napkins, bins.
- Team: 1–2 staff during peak breaks.
- Setup/cleanup: 30m before/after first/last break.

## Copy Snippets (ready-to-use)

- Luma blurb (if accepted): “Taste ceremonial cacao from Brazil’s Bahia and Pará at the refreshment breaks. One cup → one tree — scan to see the tree your tasting helps plant.”
- Table tent: “Taste Brazil’s regenerative cacao. One cup → one tree. Scan to see your tree.”
- Social (T-7): “We’re pouring cacao at [Event, City]. Bahia ↔ Pará. Come taste, meet the farms, and scan to see your tree.”

## Risk Notes / Guardrails

- No sales urgency; invites only. Keep DAO/ledger terms off onsite copy; link out for technical readers if needed.
- Avoid overcommitting in person; funnel partner interest to the consignment starter (5 bags) and written follow-up.

## Timeline (suggested)

- T-10 to T-7: Confirm asks with Ken; draft landing + assets.
- T-6 to T-3: Print signage/stickers; schedule social; prep QR batch.
- T-2 to T-1: Pack logistics; final confirm with venue.
- T: Execute; capture 3–5 photos.
- T+1 to T+3: Send follow-ups; publish Bean to Bliss micro-post.
- T+7 to T+14: Optional truesight.me reflection if learnings warrant.

## Approval

- Green-light needed on: landing page slug, onsite placement, program mention, and copy assets.

— End v0.1 —
