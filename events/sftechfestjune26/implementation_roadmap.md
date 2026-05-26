# SF Tech Fest 2026 — Implementation roadmap

**Companion to:** `proposal.md` (plan-of-record)
**Event:** TECH FEST 2026 — Silicon Valley · India Community Center (ICC), Milpitas, CA
**Date:** June 12, 2026 (Friday) · 11:00 AM – 5:00 PM PT
**Format (confirmed):** two flasks — **Oscar's ceremonial cacao + Paulo's cacao tea** — + 3 oz cups + placard, self-serve at the snack table. No booth, no dedicated pourer, no selling.
**Lead:** Claude (infra + narrative + QR pipeline) · **On the ground:** Gary · **Follow-up:** Grok

---

## Critical path (the chain the event rises and falls on)

```
Confirm date / venue / snack-table placement with Soniya
        ↓
Build placard copy + generate QR codes (provenance + opt-in)
        ↓
DRY RUN: scan a test QR, confirm signup lands + send_newsletter.py can address it   ← do NOT skip
        ↓
Print placard + assemble kit (flasks, cups, napkins)
        ↓
Event day: place flasks at snack table, placard visible → self-serve
        ↓
Post-event: verify signups → Hit List → DApp Remark
```

**Gate rule:** nothing gets printed until the dry run in Phase 2 passes.

---

## Phase 0 — Confirm remaining logistics with Soniya (now → Jun 5, T-1wk)  · Owner: Gary

**Already confirmed:** two flasks + 3 oz cups + placard by the snack table. Gary + friend get free passes. **Date confirmed:** June 12, 2026 (Fri), 11:00 AM – 5:00 PM PT, ICC Milpitas.

| # | Task | Output | Blocks |
|---|---|---|---|
| 0.1 | ~~Confirm date~~ → **June 12, 2026 confirmed** (from Luma schema + sftechfest.com) | Done | — |
| 0.2 | Confirm **snack table location** — where is it relative to the main hall? Can we place the flasks there? | Setup plan | Placard placement |
| 0.3 | Confirm **self-serve** is fine (no dedicated pourer) | Format lock | — |
| 0.4 | Confirm **stage shoutout** — still on? Suggested timing? | Yes/no + when | Placard urgency (less needed if announced) |
| 0.5 | Confirm **Gary + friend passes** — logistics | Entry plan | — |

**Exit criteria:** snack table location, self-serve approval, and pass logistics locked. → unblocks Phase 1–2.

---

## Phase 1 — Build QR codes + placard (now → Jun 5, T-1wk)  · Owner: Claude

| # | Task | Output |
|---|---|---|
| 1.1 | Generate QR batch `SFTF_CC_2026` (Oscar's ceremonial) + `SFTF_CT_2026` (Paulo's tea) via existing pipeline; publish to `lineage-assets` repo | QR PNGs + `qrs_index.json` entries |
| 1.2 | Produce provenance QR targets (agl4/agl8 landing pages with consent + subscribe) — reuse existing pages, no new build | Working QR → signup pipeline |
| 1.3 | Draft placard copy: farm names, taste notes, provenance QR, opt-in QR, agroverse.shop footer | Placard text (→ `field_assets.md`) |
| 1.4 | Design placard layout (5x7, print-ready, two QRs + copy) | Placard PDF/PNG |

**Register guardrails:** placard copy stays curatorial — no prices, no urgency, no blockchain jargon. Taste notes from `AGROVERSE_PRICE_LIST_AND_ASSETS.md`.

---

## Phase 2 — DRY RUN (Jun 5–7)  · Owner: Claude  ← gate

| # | Task | Output |
|---|---|---|
| 2.1 | **Dry run:** print one test QR placard, scan both codes, confirm signup lands in `Agroverse News Letter Subscribers` tab | Pass/fail |
| 2.2 | Confirm `send_newsletter.py` can address the new test subscriber | Pass/fail |
| 2.3 | Verify provenance QR resolves to the correct lineage-assets page (no dead link / CORS) | Pass/fail |
| 2.4 | Fix any issues | Green pipeline |

**⛔ Gate:** Phase 3 printing proceeds **only when 2.1–2.3 pass.**

---

## Phase 3 — Print + assemble kit (Jun 8–11)  · Owner: Gary

| # | Task | Output |
|---|---|---|
| 3.1 | Print the placard (5x7) — 2 copies (backup) | Physical placard |
| 3.2 | Pull cacao for two flasks; log `[INVENTORY MOVEMENT]` | Stock + ledger entry |
| 3.3 | Assemble kit: 2 flasks, cups, napkins, placard x2 | Event kit |
| 3.4 | Day-of: pre-brew both flasks (Kirsten or Gary) | Flasks ready to go |

**No kettle needed** — flasks arrive pre-brewed and hot.

---

## Phase 4 — Event day (Jun 12)  · Owner: Gary

- **Arrive early.** Find Soniya, confirm the snack table location.
- **Place two flasks + cups + napkins + placard** at the snack table. Self-serve. Visible. Unfussy.
- **The placard is the whole presence.** No backdrop, no banner, no standing at the table.
- **Gary networks** — free passes, full attendee.
- **If Soniya does the stage shoutout:** great. If not, the placard handles it.
- **Note conversations:** anyone who specifically mentions the cacao → mental note (name, what they asked, next step).
- **Check midday:** is a flask empty? Reposition the placard if it got moved.
- **3-5 photos** of the setup (for DApp Remark + internal record).

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
| 6.3 | **No full-list newsletter** — skip unless there's a specific story worth telling (Gary's call) | — | — |
| 6.4 | Optional truesight.me essay if the day produced an observation | Claude (draft) → Gary (review/publish) | Essay |

---

## Milestone checklist (one-glance)

- [ ] **M0** — Date, snack table, self-serve, passes confirmed with Soniya *(Gary)*
- [ ] **M1** — QR codes minted + placard copy ready *(Claude)*
- [ ] **M2** — ✅ **Dry run passes** ← gate
- [ ] **M3** — Placard printed, kit assembled, flasks pre-brewed *(Gary)*
- [ ] **M4** — Event executed: flasks at snack table, self-serve, Gary networks *(Gary)*
- [ ] **M5** — Signups verified, leads in Hit List, DApp Remark logged *(Claude/Gary)*
- [ ] **M6** — Follow-ups sent, essay (if warranted) *(Grok/Claude)*

---

## Decision points for Gary

1. **Flasks** — Oscar's ceremonial + Paulo's tea (same pairing as Dual Tech Summit)? *Recommended: yes — proven combination, different taste registers.*
2. **Stage shoutout** — push for it or let it go? *Recommended: ask Soniya gently, but don't press. The placard works either way.*
3. **Newsletter** — skip full-list entirely? *Recommended: yes. This audience doesn't match the wellness list. 1:1 follow-ups only.*
4. **Post-event essay** — worth writing? *Recommended: decide after the event based on what actually happened.*

---

*Roadmap authored 2026-05-26 by Claude (Anthropic). Date confirmed June 12, 2026 from Luma schema + sftechfest.com.*
