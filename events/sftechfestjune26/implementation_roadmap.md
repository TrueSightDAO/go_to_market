# SF Tech Fest 2026 — Implementation roadmap

**Companion to:** `proposal.md` (plan-of-record)
**Event:** TECH FEST 2026 — Silicon Valley · India Community Center (ICC), Milpitas, CA
**Date:** June 12, 2026 (Friday) · 11:00 AM – 5:00 PM PT
**Format (updated Jun 9 per Soniya WhatsApp):** Gary attending with comp student ticket. Cacao pour at happy hour (after 4-5 PM) — setup coordinated on-site with Soniya. Arrive at lunch to coordinate.
**Lead:** Claude (infra + narrative + QR pipeline) · **On the ground:** Gary · **Follow-up:** Grok

---

## Critical path (the chain the event rises and falls on)

```
Confirm comp ticket + happy hour timing with Soniya (DONE via WhatsApp)
        ↓
Build placard copy + generate QR codes (provenance + opt-in)
        ↓
DRY RUN: scan a test QR, confirm signup lands + send_newsletter.py can address it   ← do NOT skip
        ↓
Print placard + assemble kit (flask(s), cups, napkins)
        ↓
Event day: arrive at lunch → coordinate happy hour setup with Soniya → pour at happy hour (after 4-5 PM)
        ↓
Post-event: verify signups → Hit List → DApp Remark
```

**Gate rule:** nothing gets printed until the dry run in Phase 2 passes.

---

## Phase 0a — Original plan (superseded by WhatsApp Jun 9)

Soniya confirmed via WhatsApp: snack table / self-serve / stage shoutout coordination is "a little too late now." The original Phase 0 items are superseded. Gary has a **comp student ticket**. She'll set him up for happy hour (after 4-5 PM).

**Exit criteria:** Superseded. Move to Phase 0b.

---

## Phase 0b — On-site coordination · Jun 12 (event day) · Owner: Gary

| # | Task | Output |
|---|---|---|
| 0b.1 | Arrive at **lunch time** (not 11 AM opening) | On-site |
| 0b.2 | Find Soniya, check in, thank her for the comp ticket | Connection made |
| 0b.3 | Coordinate **happy hour setup** — where to place flasks + cups, what time, any table available | Setup plan |
| 0b.4 | Confirm happy hour timing (she said "after 4 or 5 PM") | Time locked |
| 0b.5 | Decide on the spot: one flask or two? | Format locked |

**Exit criteria:** happy hour location + timing confirmed on-site. → unblocks Phase 4.

---

## Phase 1 — Build QR codes + placard (now → Jun 11)  · Owner: Claude

| # | Task | Output |
|---|---|---|
| 1.1 | Generate QR batch `SFTF_CC_2026` (Oscar's ceremonial) + `SFTF_CT_2026` (Paulo's tea) via existing pipeline; publish to `lineage-assets` repo | QR PNGs + `qrs_index.json` entries |
| 1.2 | Produce provenance QR targets (agl4/agl8 landing pages with consent + subscribe) — reuse existing pages, no new build | Working QR → signup pipeline |
| 1.3 | Draft placard copy: farm names, taste notes, provenance QR, opt-in QR, agroverse.shop footer | Placard text (→ `field_assets.md`) |
| 1.4 | Design placard layout (5x7, print-ready, two QRs + copy) | Placard PDF/PNG |

**Register guardrails:** placard copy stays curatorial — no prices, no urgency, no blockchain jargon. Taste notes from `AGROVERSE_PRICE_LIST_AND_ASSETS.md`.

---

## Phase 2 — DRY RUN (Jun 10–11)  · Owner: Claude  ← gate

| # | Task | Output |
|---|---|---|
| 2.1 | **Dry run:** print one test QR placard, scan both codes, confirm signup lands in `Agroverse News Letter Subscribers` tab | Pass/fail |
| 2.2 | Confirm `send_newsletter.py` can address the new test subscriber | Pass/fail |
| 2.3 | Verify provenance QR resolves to the correct lineage-assets page (no dead link / CORS) | Pass/fail |
| 2.4 | Fix any issues | Green pipeline |

**⛔ Gate:** Phase 3 printing proceeds **only when 2.1–2.3 pass.**

---

## Phase 3 — Print + assemble kit (Jun 10–11)  · Owner: Gary

| # | Task | Output |
|---|---|---|
| 3.1 | Print the placard (5x7) — 2 copies (backup) | Physical placard |
| 3.2 | Pull cacao for **1–2 flasks** from inventory (decide on-site with Soniya); log `[INVENTORY MOVEMENT]` | Stock + ledger entry |
| 3.3 | Assemble kit: 1-2 flasks, cups, napkins, placard x2 | Event kit |
| 3.4 | Day-of: pre-brew flask(s) (Kirsten or Gary) | Flasks ready to go |

**No kettle needed** — flasks arrive pre-brewed and hot.

---

## Phase 4 — Event day (Jun 12)  · Owner: Gary

### 4.1 Arrival & coordination
- **Arrive at lunch time.** Find Soniya, check in, coordinate happy hour setup.
- Keep kit in car/bag until happy hour timing is confirmed.

### 4.2 Before happy hour
- **Network as an attendee** — you're not on shift.
- Note any cacao conversations.

### 4.3 Happy hour (after 4-5 PM) — the primary activation moment
- Set up flask(s) + cups + napkins + placard at the happy hour location.
- **Cacao as the non-alcoholic, focus-enhancing counterpoint** to flowing drinks.
- Pour and talk story. This is the moment the proposal's §4.1 table described.
- Take a photo of the setup.

### 4.4 End of event
- Collect flask(s) and any remaining cups. Leave the table clean.
- Jot down notes: names, conversations, what people said.

---

## Phase 5 — Immediate post-event (Jun 13–14)  · Owner: Claude

| # | Task | Output |
|---|---|---|
| 5.1 | Verify opt-in signups landed in subscribers tab | Confirmed list |
| 5.2 | Add warm leads to Hit List (`Source: SF Tech Fest 2026`, Notes) | Pipeline input |
| 5.3 | Verify `suggest_manager_followup_drafts.py` picks up any new leads | Queued drafts |
| 5.4 | Log activation as a **DApp Remark** (date, servings, farms, notable conversations, photos) | Training data |

---

## Phase 6 — Follow-up (Jun 15–26)

| # | Task | Owner | Output |
|---|---|---|---|
| 6.1 | Manager Follow-up drafts for event leads | Grok (existing pipeline) → Gary sends | Warm-up touches |
| 6.2 | Personal 1:1 follow-up with any contacts Gary made | Gary | Relationship |
| 6.3 | Thank-you note to Soniya | Gary | Gratitude |
| 6.4 | **No full-list newsletter** — skip unless there's a specific story worth telling (Gary's call) | — | — |
| 6.5 | Optional truesight.me essay if the day produced an observation | Claude (draft) → Gary (review/publish) | Essay |

---

## Milestone checklist (one-glance)

- [x] **M0a** — Original Phase 0 superseded by WhatsApp *(Soniya, Jun 9)*
- [ ] **M0b** — On-site coordination: arrive lunch, find Soniya, lock happy hour setup *(Gary, Jun 12)*
- [ ] **M1** — QR codes minted + placard copy ready *(Claude)*
- [ ] **M2** — ✅ **Dry run passes** ← gate
- [ ] **M3** — Placard printed, kit assembled, flasks pre-brewed *(Gary)*
- [ ] **M4** — Event executed: happy hour pour, Gary networks *(Gary)*
- [ ] **M5** — Signups verified, leads in Hit List, DApp Remark logged *(Claude/Gary)*
- [ ] **M6** — Follow-ups sent, essay (if warranted) *(Grok/Claude)*

---

## Decision points for Gary

1. **Flasks** — Oscar's ceremonial + Paulo's tea (same pairing as Dual Tech Summit)? *Recommended: yes — proven combination, different taste registers. But decide on-site with Soniya based on space.*
2. **Happy hour timing** — she said "after 4 or 5 PM." Confirm exact time on-site.
3. **Newsletter** — skip full-list entirely? *Recommended: yes. 1:1 follow-ups only.*
4. **Post-event essay** — worth writing? *Recommended: decide after the event based on what actually happened.*

---

*Roadmap authored 2026-05-26 by Claude (Anthropic). Updated 2026-06-09 per Soniya WhatsApp — format shifted from snack-table self-serve to happy-hour pour.*