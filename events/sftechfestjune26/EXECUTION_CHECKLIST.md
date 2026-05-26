# SF Tech Fest 2026 — Execution checklist

**Companion to:** `proposal.md` (plan-of-record) · `implementation_roadmap.md` (phasing)
**Event:** June 12, 2026 (Friday) · ICC, 525 Los Coches St, Milpitas, CA 95035 · 11:00 AM – 5:00 PM PT
**Format:** two flasks — **Oscar's ceremonial cacao + Paulo's cacao tea** — in 3 oz cups, self-serve at the snack table. Placard does the talking.
**How to use:** check items as done; each phase is time-bounded.

Legend: `[x]` done · `[ ]` open · `[~]` drafted, pending review · 🔒 blocked on a dependency

---

## Phase 0 — Confirm with Soniya · now → ~Jun 5 · Gary

- [ ] **0.1** Confirm **snack table location** — is it accessible to all attendees? Where in the venue?
- [ ] **0.2** Confirm **self-serve** is approved — no dedicated pourer, no one staffing the table
- [ ] **0.3** Confirm **stage shoutout** — still offered? Preferred timing? *(Suggested: Sponsors Acknowledgement at 3:00 PM, or before a break)*
- [ ] **0.4** Confirm **Gary + friend passes** — logistics (names, how to get in, any registration needed)
- [ ] **0.5** Confirm any venue restrictions (outside food/beverage, alcohol policy, setup time)

> **Draft message to Soniya** *(send soon)*:
>
> Hi Soniya — circling back on the cacao for Tech Fest (June 12!). Just locking in a few logistics when you get a sec:
>
> - Where's the **snack table** located — is it in the main hall or a separate area? We'll just drop two flasks + cups + a small placard, fully self-serve, no one staffing it.
> - Is the **stage shoutout** still on? If so, happy to do ~30 seconds whenever fits the flow — Sponsors Acknowledgement or right before a break.
> - **Passes for me + my friend** — anything we need to do to get registered?
>
> Thanks for making space for this! 🍫

---

## Phase 1 — QR codes + placard · now → Jun 5 · Claude

- [ ] **1.1** Generate QR codes via `AGROVERSE_QR_CODE_BATCH_GENERATION.md`:
  - `SFTF_CC_2026` → agl4 (Oscar's ceremonial cacao)
  - `SFTF_CT_2026` → agl8 (Paulo's cacao tea)
- [ ] **1.2** Publish QR PNGs + manifests to `TrueSightDAO/lineage-assets` repo
- [ ] **1.3** Verify provenance QR resolves correctly (agl4/agl8 landing pages with consent + subscribe)
- [ ] **1.4** Add UTM parameters: `?utm_source=event&utm_medium=qr&utm_campaign=sftf-2026`
- [ ] **1.5** Draft placard copy → `field_assets.md` (farm names, taste notes, two QRs, footer)
- [ ] **1.6** Design placard layout (5x7, print-ready)

---

## Phase 2 — DRY RUN · Jun 5–7 · Claude  ← gate

- [ ] **2.1** Print **test placard** with both QRs
- [ ] **2.2** Scan provenance QR → confirm it resolves to the correct agl4/agl8 page (no dead link / CORS)
- [ ] **2.3** Scan opt-in QR → fill test signup → confirm it lands in `Agroverse News Letter Subscribers` tab (check `subscribed:true`)
- [ ] **2.4** Confirm `send_newsletter.py` reads the subscribers tab + dedup works on the test entry
- [ ] **2.5** Clean up test entry from subscribers tab
- [ ] **2.6** Fix any issues found
- [ ] **✅ Dry run passed → printing is unblocked**

---

## Phase 3 — Print + prep (Jun 8–11) · Gary

- [ ] **3.1** Print **2 copies** of the placard (5x7) — one for the table, one backup
- [ ] **3.2** Pull cacao for two flasks from inventory:
  - Oscar's Farm ceremonial cacao (Bahia) — enough for 1 full thermal flask
  - Paulo's cacao tea (Pará) — enough for 1 full thermal flask
- [ ] **3.3** Log `[INVENTORY MOVEMENT]` for the cacao pulled
- [ ] **3.4** Gather cups (3 oz, compostable) + napkins — enough for ~50 servings
- [ ] **3.5** Day-of: pre-brew both flasks (Kirsten or Gary). Hot, ready to go. No kettle needed.
- [ ] **3.6** Pack kit: 2 flasks (sealed tight), cups, napkins, placard x2, tape (to secure placard if needed)
- [ ] **3.7** Final confirm with Soniya (time to arrive, snack table location) — 📞 Soniya check-in

---

## Phase 4 — Event day · Jun 12 · Gary

### 4.1 Setup
- [ ] **4.1.1** Arrive early — check in with Soniya, find the snack table
- [ ] **4.1.2** Place two flasks + cups (stacked) + napkins + placard at the snack table
- [ ] **4.1.3** Place the second placard copy in your bag (backup)
- [ ] **4.1.4** Take a photo of the setup before attendees arrive

### 4.2 During event
- [ ] **4.2.1** Midday check: is a flask empty? Is the placard still visible and in place?
- [ ] **4.2.2** Note any conversations about the cacao (who, what they asked, any retail interest)
- [ ] **4.2.3** If Soniya does the stage shoutout: pay attention, note the timing
- [ ] **4.2.4** Network. You're an attendee, not on shift.

### 4.3 End of event
- [ ] **4.3.1** Collect flasks and any remaining cups (leave the table clean)
- [ ] **4.3.2** Quick photo of the setup at end-of-day (for contrast)
- [ ] **4.3.3** Mental notes → jot down before you forget: names, conversations, what people said

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
| 0 | ASAP (by Jun 5) | Confirm snack table, self-serve, shoutout, passes |
| 1 | Jun 1–5 | QR codes minted, placard designed |
| 2 | Jun 5–7 | Dry run passes |
| 3 | Jun 8–11 | Placard printed, kit assembled |
| 4 | Jun 12 | Setup, midday check, teardown |
| 5 | Jun 13–14 | Signups verified, leads in Hit List |
| 6 | Jun 15+ | Thank-you to Soniya, follow-ups |

---

*Created 2026-05-26 by Claude (Anthropic). Mirrors `implementation_roadmap.md`; update both if phasing changes.*
