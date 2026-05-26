# Dual Tech Summit 2026 — Execution checklist

**Companion to:** `proposal_finalized.md` (plan-of-record) · `implementation_roadmap.md` (phasing)
**Event:** June 26, 2026 *(confirm date)* · War Memorial Veterans Building, SF *(venue confirmed 2026-05-26)*
**Format:** two flasks — **Oscar's ceremonial cacao + Paulo's cacao tea** — in 3 oz cups, poured at a table Ken provides *(confirmed 2026-05-23; contents 2026-05-24)*
**How to use:** check items as done; each phase is time-bounded. The **Ken check-in** column flags where a partner-host touch is due (see "Reminders" at the bottom for how those are tracked).

Legend: `[x]` done · `[ ]` open · `[~]` drafted, pending review · 🔒 blocked on a dependency

---

## Phase 0 — Confirm with Ken · now → ~May 31 (T-4wk) · Gary
- [x] **0.0** Offer made + accepted — two flasks + cups *(2026-05-23)*
- [ ] **0.1** Confirm **date** (June 26?) — 📞 Ken check-in · *venue = **War Memorial Veterans Building, SF** (confirmed 2026-05-26)*
- [ ] **0.2** Confirm **the table** (size, location near breaks) + pouring is fine — 📞 Ken check-in
- [ ] **0.3** Confirm **ClawCamp block timing** + point person — 📞 Ken check-in
- [ ] **0.4** Ask (no pressure) about a 60-sec program mention at a break — 📞 Ken check-in
- [~] **0.5** Flasks decided: **Oscar's ceremonial cacao + Paulo's cacao tea** *(2026-05-24)*; still confirm Kirsten pre-brews both

## Phase 1 — Narrative + strategy · Jun 1–10 (T-3wk)
- [x] **1.1** truesight.me methodology essay — *"The most tracked thing in the room is a cup of cacao"* — **published** → [truesight.me](https://truesight.me/blog/posts/the-most-tracked-thing-in-the-room-is-a-cup-of-cacao.html) *(byline Claude (Anthropic); draft `truesight_essay_draft.md`)*
- [~] **1.2** One-line on-the-day story — **drafted** → `field_assets.md` §1 *(→ Gary)*
- [~] **1.3** Field-asset copy (placard, table-tent, cup-sticker, farm cards) — **drafted** → `field_assets.md` *(→ Gary/OpenAI to refine before print)*
- [x] **1.4** Strategy / risk / measurement kept as plan-of-record *(DeepSeek — `proposal_finalized.md`)*

## Phase 2 — Build site + pipeline · ✅ core DONE, live on prod (2026-05-25) · Claude
> **Architecture note:** instead of a new event page, the opt-in rides on the existing **AGL shipment pages** (agl4/agl8) + the QR reader web service (`web_app.gs`, project `1y6JVYwq…`, deployment `AKfycbxig…`). Simpler — those pages are already the QR landing.
- [ ] **2.1** Dedicated event page — *skipped* (using existing agl4/agl8 landing pages instead)
- [x] **2.2** Opt-in QR destination = agl4/agl8 landing pages (consent checkbox, live on prod)
- [x] **2.3** QR scan → newsletter signup → Main Ledger `Agroverse News Letter Subscribers` (`Source=qr:<code>`); send-time dedup confirmed
- [ ] **2.4** "interested in carrying cacao?" → Hit List — *not built* (optional; pour ≠ retail pitch)
- [ ] **2.5 / 2.6** SEO/Schema event block, `/wholesale` line — *n/a* (no event page)
- [x] **2.7** Event QR codes minted (promo / `SAMPLE`): **`DTS_CC_20260626_1`** → agl4 (Oscar's ceremonial cacao), **`DTS_CT_20260626_1`** → agl8 (Paulo's cacao tea). Canonical artifacts in **`TrueSightDAO/lineage-assets`** (PR #1): manifest `qrs/<id>.json` + raw PNG `pngs/<id>.png` (encodes the Edgar check URL) + `qrs_index.json`. Scan target `truesight.me/qr/?id=<id>`; PNG for printing: `raw.githubusercontent.com/TrueSightDAO/lineage-assets/main/pngs/<id>.png`.

## Phase 3 — DRY RUN + publish · ✅ dry-run PASSED (2026-05-25) · Claude
- [x] **3.1** Scan → signup lands in subscribers tab (verified `subscribed:true`; test row cleaned up)
- [x] **3.2** `send_newsletter.py` reads the subscribers tab + dedups by email at send (confirmed in code)
- [ ] **3.3** "carry cacao?" → Hit List path — *not built* (see 2.4)
- [x] **3.4** End-to-end verified — GAS recognizes the `DTS_…` codes; Edgar `302` → agl4/agl8; no CORS/dead-link
- [x] **3.5** Publish the truesight.me essay — **live** at [truesight.me](https://truesight.me/blog/posts/the-most-tracked-thing-in-the-room-is-a-cup-of-cacao.html) (beta→prod, CNAME preserved)
- **✅ Dry run passed → printing is unblocked** (cards can be printed; see `field_assets.md` + the `qr_DTS_*.png` files).

## Phase 4 — Outreach + final prep · Jun 20–25 (T-1wk→T-1d) · Gary
- [ ] **4.1** Newsletter: **no full-list blast** — personal 1:1 / segmented / piggyback / skip
- [ ] **4.2** Print "scan to verify" placard + cup stickers (after dry run)
- [ ] **4.3** Pull cacao for two flasks + 1–2 display bags; log `[INVENTORY MOVEMENT]`
- [ ] **4.4** Day-of: pre-brew two flasks; pack cups, napkins, placard, display bags *(no kettle)*
- [ ] **4.5** Final confirm with Ken (table location, ClawCamp timing) — 📞 Ken check-in

## Phase 5 — Event day · Jun 26 (T-0) · Gary
- [ ] **5.1** Set up on Ken's table: two flasks + cups + placard + 1–2 display bags
- [ ] **5.2** Taste first, provenance second; pour at pause moments
- [ ] **5.3** Capture permission via opt-in QR; note retail-interest conversations
- [ ] **5.4** 3–5 photos + rough observations for the essay

## Phase 6 — Immediate post-event · Jun 27–28 (T+2d) · Claude + Gary
- [ ] **6.1** Verify opt-in signups landed in subscribers tab *(Claude)*
- [ ] **6.2** Add warm leads to Hit List (`Source: Dual Tech Summit 2026`) *(Gary)*
- [ ] **6.3** Verify `suggest_manager_followup_drafts.py` picked up leads *(Claude)*
- [ ] **6.4** Log activation as a DApp Remark *(Gary)*
- [ ] **6.5** Update event page → past-tense *(Claude/Gary)*

## Phase 7 — Follow-up + story · Jun 29 – Jul 10 (T+1–2wk)
- [ ] **7.1** Manager Follow-up drafts for event leads *(Grok → Gary sends)*
- [ ] **7.2** Field-dispatch newsletter (only if a real story) *(Kimi → review → send)*
- [ ] **7.3** Update `OUTREACH_QUALITATIVE_LOOP.md` *(DeepSeek)*
- [ ] **7.4** Optional truesight.me reflection essay *(Kimi or Claude)*

---

## Reminders — per-phase follow-ups

These are **internal follow-ups for the team** (Gary / Claude / another LLM) — *not* DAO partner-ledger events. They live in the cross-session backlog **`agentic_ai_context/OPEN_FOLLOWUPS.md`** so any session can pick up the next due one, with the phase target dates below as the schedule. (We deliberately do *not* use `dao_client check_in_partner` here — that tool is for inventory-carrying retail partners, not an event host.)

| Phase | Target date | Follow-up due |
|---|---|---|
| 0 | by ~May 31 | Confirm date, venue, table, ClawCamp timing |
| 4 | ~Jun 22–25 | Final table location + ClawCamp timing |
| 6 | ~Jun 28 | Thank-you + any follow-up from the day |

---

*Created 2026-05-24 by Claude (Anthropic). Mirrors `implementation_roadmap.md`; update both if phasing changes.*
