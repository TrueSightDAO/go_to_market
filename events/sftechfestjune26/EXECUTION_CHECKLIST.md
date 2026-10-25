# SF Tech Fest 2026 — Execution checklist

**Companion to:** `proposal.md` (plan-of-record) · `implementation_roadmap.md` (phasing)
**Event:** June 12, 2026 (Friday) · ICC, 525 Los Coches St, Milpitas, CA 95035 · 11:00 AM – 5:00 PM PT
**Format (updated Jun 9):** Gary attending with comp student ticket. Cacao pour at happy hour (after 4-5 PM) — setup coordinated on-site with Soniya. Arrive at lunch to coordinate.
**How to use:** check items as done; each phase is time-bounded.

Legend: `[x]` done · `[ ]` open · `[~]` drafted, pending review · 🔒 blocked on a dependency

---

## Phase 0a — Original plan (superseded by WhatsApp Jun 9)

Soniya confirmed via WhatsApp: snack table / self-serve / stage shoutout coordination is "a little too late now." The original Phase 0 items (0.1–0.5) are superseded. Gary has a **comp student ticket**. She'll set him up for happy hour (after 4-5 PM).

- [x] ~~0.1 Confirm snack table location~~ → **Superseded.** Will coordinate on-site.
- [x] ~~0.2 Confirm self-serve~~ → **Superseded.**
- [x] ~~0.3 Confirm stage shoutout~~ → **Superseded.**
- [x] ~~0.4 Confirm Gary + friend passes~~ → **Comp student ticket confirmed** (singular).
- [x] ~~0.5 Confirm venue restrictions~~ → **Superseded.**

---

## Phase 0b — On-site coordination (new) · Jun 12 · Gary

- [ ] **0b.1** Arrive at **lunch time** (not 11 AM opening)
- [ ] **0b.2** Find Soniya, check in, thank her for the comp ticket
- [ ] **0b.3** Coordinate **happy hour setup** — where to place flasks + cups, what time, any table available
- [ ] **0b.4** Confirm happy hour timing (she said "after 4 or 5 PM")
- [ ] **0b.5** Decide on the spot: one flask or two? (Oscar's ceremonial + Paulo's tea, or just one depending on space)

---

## Phase 1 — QR codes + placard · now → Jun 11 · Claude

- [ ] **1.1** Generate QR codes via `AGROVERSE_QR_CODE_BATCH_GENERATION.md`:
  - `SFTF_CC_2026` → agl4 (Oscar's ceremonial cacao)
  - `SFTF_CT_2026` → agl8 (Paulo's cacao tea)
- [ ] **1.2** Publish QR PNGs + manifests to `TrueSightDAO/lineage-assets` repo
- [ ] **1.3** Verify provenance QR resolves correctly (agl4/agl8 landing pages with consent + subscribe)
- [ ] **1.4** Add UTM parameters: `?utm_source=event&utm_medium=qr&utm_campaign=sftf-2026`
- [ ] **1.5** Draft placard copy → `field_assets.md` (farm names, taste notes, two QRs, footer)
- [ ] **1.6** Design placard layout (5x7, print-ready)

---

## Phase 2 — DRY RUN · Jun 10–11 · Claude  ← gate

- [ ] **2.1** Print **test placard** with both QRs
- [ ] **2.2** Scan provenance QR → confirm it resolves to the correct agl4/agl8 page (no dead link / CORS)
- [ ] **2.3** Scan opt-in QR → fill test signup → confirm it lands in `Agroverse News Letter Subscribers` tab (check `subscribed:true`)
- [ ] **2.4** Confirm `send_newsletter.py` reads the subscribers tab + dedup works on the test entry
- [ ] **2.5** Clean up test entry from subscribers tab
- [ ] **2.6** Fix any issues found
- [ ] **✅ Dry run passed → printing is unblocked**

---

## Phase 3 — Print + prep · Jun 10–11 · Gary

- [ ] **3.1** Print **2 copies** of the placard (5x7) — one for the table, one backup
- [ ] **3.2** Pull cacao for **1–2 flasks** from inventory (decide on-site with Soniya):
  - Oscar's Farm ceremonial cacao (Bahia) — enough for 1 full thermal flask
  - Paulo's cacao tea (Pará) — enough for 1 full thermal flask
- [ ] **3.3** Log `[INVENTORY MOVEMENT]` for the cacao pulled
- [ ] **3.4** Gather cups (3 oz, compostable) + napkins — enough for ~30-50 servings
- [ ] **3.5** Day-of: pre-brew flask(s) (Kirsten or Gary). Hot, ready to go. No kettle needed.
- [ ] **3.6** Pack kit: 1-2 flasks (sealed tight), cups, napkins, placard x2, tape

---

## Phase 4 — Event day · Jun 12 · Gary

### 4.1 Arrival & coordination
- [ ] **4.1.1** Arrive at **lunch time** (not 11 AM)
- [ ] **4.1.2** Check in with Soniya — thank her, coordinate happy hour setup
- [ ] **4.1.3** Confirm where and when to place flasks for happy hour (after 4-5 PM)
- [ ] **4.1.4** Keep kit in car / bag until happy hour timing is confirmed

### 4.2 During event (before happy hour)
- [ ] **4.2.1** Network as an attendee — you're not on shift
- [ ] **4.2.2** Note any conversations about cacao (who, what they asked, any retail interest)

### 4.3 Happy hour setup (after 4-5 PM)
- [ ] **4.3.1** Set up flask(s) + cups + napkins + placard at the happy hour location
- [ ] **4.3.2** Take a photo of the setup
- [ ] **4.3.3** Pour and talk story — this is the primary activation moment
- [ ] **4.3.4** Cacao as the non-alcoholic, focus-enhancing counterpoint to flowing drinks

### 4.4 End of event
- [ ] **4.4.1** Collect flask(s) and any remaining cups (leave the table clean)
- [ ] **4.4.2** Photo of the setup at end-of-day
- [ ] **4.4.3** Mental notes → jot down before you forget: names, conversations, what people said

---

## Phase 5 — Immediate post-event · Jun 13–14 · Claude + Gary

- [ ] **5.1** Verify opt-in signups landed in `Agroverse News Letter Subscribers` tab *(Claude)*
- [ ] **5.2** Count new subscribers → note delta *(Claude)*
- [ ] **5.3** Add warm leads to Hit List (`Source: SF Tech Fest 2026`, `Status: Research`, Notes: what they tasted, what they said) *(Gary)*
- [ ] **5.4** Verify `suggest_manager_followup_drafts.py` picked up new leads *(Claude)*
- [ ] **5.5** Log activation as a **DApp Remark** — date, servings, farms served, notable conversations, what landed/didn't, photos *(Gary)*

---

## Phase 6 — Follow-up + story · Jun 15–26

- [ ] **6.1** Manager Follow-up drafts for event leads *(Grok → Gary sends)*
- [ ] **6.2** Personal 1:1 follow-ups with any contacts Gary made *(Gary)*
- [ ] **6.3** Thank-you note to Soniya (warm, not transactional) *(Gary)*
- [ ] **6.4** **No full-list newsletter** — skip unless a compelling story emerged *(decision: Gary)*
- [ ] **6.5** Optional truesight.me reflection essay — if the day produced a real observation *(Claude drafts → Gary publishes)*

---

## Reminders — per-phase follow-ups

| Phase | Target date | Follow-up due |
|---|---|---|
| 0b | Jun 12 (on-site) | Coordinate happy hour setup with Soniya |
| 1 | Jun 10–11 | QR codes minted, placard designed |
| 2 | Jun 10–11 | Dry run passes |
| 3 | Jun 11 | Placard printed, kit assembled |
| 4 | Jun 12 | Arrive lunch, coordinate, happy hour pour |
| 5 | Jun 13–14 | Signups verified, leads in Hit List |
| 6 | Jun 15+ | Thank-you to Soniya, follow-ups |

---

*Created 2026-05-26 by Claude (Anthropic). Updated 2026-06-09 per Soniya WhatsApp — format shifted from snack-table self-serve to happy-hour pour.*