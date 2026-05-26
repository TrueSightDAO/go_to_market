# Onsen Global Leaders Forum 2026 — Execution checklist

**Companion to:** `proposal.md` (plan-of-record) · `implementation_roadmap.md` (phasing)
**Event:** June 23, 2026 (Tuesday) · 5:30 PM – 7:30 PM · Palo Alto, CA (Japan Innovation Campus)
**Format:** small basket of 20 sealed cacao tea bags on the snack table — each bag labeled with provenance QR + Onsen Global x Agroverse co-branding. No flasks, no pour, no booth.
**How to use:** check items as done; each phase is time-bounded.

Legend: `[x]` done · `[ ]` open · `[~]` drafted, pending review · 🔒 blocked on a dependency

---

## Phase 0 — Confirm with Tiffine · now → Jun 16 · Gary

- [ ] **0.1** Request Onsen Global logo — single-color (black), vector or high-res PNG, for the tea bag labels
- [ ] **0.2** Confirm snack table placement — small basket, unobtrusive; any venue-specific notes?
- [ ] **0.3** Confirm Gary's registration is approved (registered May 21)
- [ ] **0.4** Confirm tea bags are in sealed packaging — meets Japanese venue's sealed-package policy
- [ ] **0.5** (Optional) Ask Tiffine's preference: mention Gary + cacao verbally, or just word-of-mouth at the snack table?

> **Draft message to Tiffine** *(send now)*:
>
> Hi Tiffine — excited for the forum on the 23rd! Locking in the cacao tea logistics:
>
> - We're doing ~20 individually sealed cacao tea bags in a small basket on the snack table — each bag labeled with the farm story + provenance QR so people can trace it back to the tree. No pour, no cups — clean and sealed per the venue's preference.
> - If you have a single-color (black) version of Onsen Global's logo, we'd love to include it on the label. If not, no worries — we'll typeset it.
>
> Anything else I should know about the snack table setup or venue?
>
> Really looking forward to it! 🍵

---

## Phase 1 — QR code + label design · Jun 1–16 · Claude

- [ ] **1.1** Generate provenance QR code `OGLF_CT_20260623_1` via `AGROVERSE_QR_CODE_BATCH_GENERATION.md`:
  - Target: agl8 (Paulo's cacao tea)
  - UTM: `?utm_source=event&utm_medium=qr&utm_campaign=oglf-2026`
- [ ] **1.2** Publish QR PNG + manifest to `TrueSightDAO/lineage-assets` repo
- [ ] **1.3** Verify provenance QR resolves correctly (agl8 landing page with consent + subscribe)
- [ ] **1.4** Design tea bag label template (`label_template_OGLF.svg`):
  - Onsen Global logo (top band) — or typeset "ONSEN GLOBAL" wordmark if logo unavailable
  - Event name: *Global Expansion & Cross-Border Leaders Forum · June 23, 2026*
  - Farm name: *Paulo's Farm — Pará, Brazil*
  - Taste note: *Light, gently fruity, low-stimulant cacao-fruit tea*
  - Provenance QR (center)
  - Footer: *agroverse.shop*
- [ ] **1.5** Draft basket card copy: *"Cacao tea from the Brazilian Amazon. Take one. Scan the QR to meet the farmer."* → `field_assets.md`

---

## Phase 2 — DRY RUN · Jun 16–19 · Claude  ← gate

- [ ] **2.1** Print **one** test tea bag label with QR
- [ ] **2.2** Scan provenance QR → confirm it resolves to the correct agl8 page (no dead link / CORS)
- [ ] **2.3** Scan opt-in (subscribe checkbox on agl8 page) → fill test signup → confirm it lands in `Agroverse News Letter Subscribers` tab (check `subscribed:true`)
- [ ] **2.4** Confirm `send_newsletter.py` reads the subscribers tab + dedup works on the test entry
- [ ] **2.5** Confirm QR is scannable at tea bag label size (~40mm) — not too dense
- [ ] **2.6** Clean up test entry from subscribers tab
- [ ] **2.7** Fix any issues found
- [ ] **✅ Dry run passed → printing is unblocked**

---

## Phase 3 — Print + assemble · Jun 19–22 · Gary

- [ ] **3.1** Print 20 tea bag labels + 5 spares (black-and-white label printer)
- [ ] **3.2** Affix labels to 20 sealed Paulo's cacao tea bags
- [ ] **3.3** Pull 20 Paulo's cacao tea bags from inventory
- [ ] **3.4** Log `[INVENTORY MOVEMENT]` for the 20 tea bags
- [ ] **3.5** Verify each tea bag packaging is sealed (Japanese venue policy)
- [ ] **3.6** Print or hand-write basket card
- [ ] **3.7** Assemble basket: 20 labeled tea bags + basket card
- [ ] **3.8** Pack: basket, a few spare tea bags, phone (for photos)
- [ ] **3.9** Final confirm with Tiffine (arrival time, snack table location) — 📞 Tiffine check-in

---

## Phase 4 — Event day · Jun 23 · Gary

### 4.1 Setup
- [ ] **4.1.1** Arrive ~5:15 PM — find Tiffine, locate the snack table
- [ ] **4.1.2** Place basket on snack table — visible but not center-stage
- [ ] **4.1.3** Place basket card beside or in the basket
- [ ] **4.1.4** Take a quick photo of the basket setup

### 4.2 During event
- [ ] **4.2.1** Network as an attendee — don't hover near the snack table
- [ ] **4.2.2** If someone picks up a tea bag near you → tell the story: *"That's single-estate cacao tea from a farmer named Paulo in the Brazilian Amazon. Scan the QR — it shows you his farm."*
- [ ] **4.2.3** Note any conversations: who, what they asked, any retail/partnership interest
- [ ] **4.2.4** Tiffine introductions → pay attention to anyone she connects you with
- [ ] **4.2.5** Mid-event check (~7:00 PM): count remaining tea bags in the basket

### 4.3 End of event
- [ ] **4.3.1** Count remaining tea bags (if any) — rough metrics
- [ ] **4.3.2** Retrieve basket from snack table (leave nothing behind)
- [ ] **4.3.3** Mental notes → jot down before you forget: names, conversations, what people asked about
- [ ] **4.3.4** Drop a send-time note re: "what happened" — it's easy data

---

## Phase 5 — Immediate post-event · Jun 24–25 · Claude + Gary

- [ ] **5.1** Check QR scan count for `OGLF_CT_20260623_1` *(Claude)*
- [ ] **5.2** Verify any opt-in signups landed in `Agroverse News Letter Subscribers` tab *(Claude)*
- [ ] **5.3** Count new subscribers → note delta *(Claude)*
- [ ] **5.4** Add warm leads to Hit List (`Source: Onsen Global Leaders Forum 2026`, `Status: Research`, Notes: what they said/tasted) *(Gary)*
- [ ] **5.5** Verify `suggest_manager_followup_drafts.py` picked up new leads *(Claude)*
- [ ] **5.6** Log activation as a **DApp Remark** — date, tea bags taken, notable conversations, what landed/didn't, photo *(Gary)*
- [ ] **5.7** Thank-you to Tiffine (warm, non-transactional) *(Gary)*

---

## Phase 6 — Follow-up · Jun 26–30

- [ ] **6.1** Manager Follow-up drafts for event leads *(Grok → Gary sends)*
- [ ] **6.2** Personal 1:1 follow-ups with any contacts made *(Gary)*
- [ ] **6.3** **No full-list newsletter** — skip entirely. This audience doesn't match the wellness list.
- [ ] **6.4** Optional truesight.me essay if the evening produced a real observation *(Claude drafts → Gary publishes)*

---

## Reminders — per-phase follow-ups

| Phase | Target date | Follow-up due |
|---|---|---|
| 0 | ASAP (by Jun 16) | Request Onsen Global logo, confirm snack table, confirm sealed packaging |
| 1 | Jun 1–16 | QR code minted, label designed |
| 2 | Jun 16–19 | Dry run passes |
| 3 | Jun 19–22 | Labels printed, tea bags labeled, basket assembled |
| 4 | Jun 23 | Basket on snack table, Gary networks |
| 5 | Jun 24–25 | Signups verified, leads in Hit List, thank-you to Tiffine |
| 6 | Jun 26–30 | Follow-ups, essay (if warranted) |

---

*Created 2026-05-26 by Claude (Anthropic). Mirrors `implementation_roadmap.md`; update both if phasing changes.*
