# Dual Tech Summit 2026 — Implementation roadmap

**Companion to:** `proposal_finalized.md` (plan-of-record)
**Event:** June 26, 2026 *(confirm)* · War Memorial Veterans Building, SF *(confirm)*
**Format (confirmed 2026-05-23; contents 2026-05-24):** two flasks — **Oscar's ceremonial cacao + Paulo's cacao tea** — + 3 oz cups, poured at a table Ken provides. Not retail, not a booth.
**Today:** 2026-05-24 (~T-4.5 weeks)
**Lead:** Claude (infra + narrative) · **On the ground:** Gary · **Strategy:** DeepSeek · **Post-event essay:** Kimi · **Follow-up drafts:** Grok · **Asset templates:** OpenAI

---

## Critical path (the chain that the event rises and falls on) *(DeepSeek §11.2)*

```
Confirm date/venue/scope with Ken
        ↓
Build opt-in landing page + wire QR → signup → Main Ledger subscribers tab
        ↓
DRY RUN: scan a test QR, confirm signup lands + send_newsletter.py can address it   ← do NOT skip
        ↓
Print QR codes / cards  (only AFTER dry run passes)
        ↓
Event day: taste first, provenance second, capture permission
        ↓
Post-event: leads → Hit List → Grok follow-up;  field-dispatch newsletter
```

**Gate rule:** nothing gets printed (QR codes, cards, table tent) until the dry run in Phase 3 passes. A dead link discovered on the day = zero permission captured from ~200 people.

---

## Phase 0 — Confirm with Ken (now → ~May 31, T-4wk)  · Owner: Gary

**✅ Already confirmed (2026-05-23):** Gary offered two flasks of cacao + cups; Ken replied *"Yes, of course. Love to have you there."* Attendance and format are locked. Remaining confirmations:

| # | Task | Output | Blocks |
|---|---|---|---|
| 0.1 | Confirm **date** (June 26?) and **venue** (War Memorial per Luma vs Kimi's "American Legion") | Locked event facts | All printed materials, essay, page |
| 0.2 | Confirm **the table** Ken provides (size, location near breaks) + that pouring is fine | Setup plan | Placard/table layout |
| 0.3 | Confirm **ClawCamp block timing** + point person | Pour timing | Placement (§4.1) |
| 0.4 | Ask (no pressure) about a 60-sec program mention at a break | Yes/no | Optional |
| 0.5 | Flasks = **Oscar's ceremonial cacao + Paulo's cacao tea** *(decided 2026-05-24)*; confirm Kirsten pre-brews both | Flask plan | Prep |

**Exit criteria:** date, venue, table, and the two flask origins are known. → unblocks Phase 1–2.

---

## Phase 1 — Narrative + strategy (June 1–10, T-3wk)

| # | Task | Owner | Depends on | Output |
|---|---|---|---|---|
| 1.1 | Draft truesight.me essay — *"provenance is a dual-use problem"* | Claude | 0.1 | Essay draft (2–4k words) → Gary review |
| 1.2 | Refine the one-line on-the-day story | Claude/OpenAI | — | Memorizable script for Gary (§4.3) |
| 1.3 | Asset templates: QR/UTM brief (`DTS-2026-06-26`), table-tent + cup-sticker copy, "Meet the farms" mini-cards | OpenAI | 0.1 | Copy/specs ready for print |
| 1.4 | Maintain strategy/risk/measurement as plan-of-record | DeepSeek | — | `proposal_finalized.md` §10–11 kept current |

**Register guardrails:** essay = plumbing-and-soul, byline "long time contributor," no announcement language. Table-tent copy stays curatorial — avoid slogan-y urgency.

---

## Phase 2 — Build the site + pipeline (June 8–17, T-2wk)  · Owner: Claude

| # | Task | Depends on | Output |
|---|---|---|---|
| 2.1 | Create `event-details-registration/dual-tech-summit-2026/index.html` (existing pattern; discoverable, no RSVP funnel) | 0.1 | Event page |
| 2.2 | Make that page the **opt-in QR destination** (farm story + signup, served from our repo — not a Google Form) | 2.1 | Durable landing page |
| 2.3 | Wire **QR → newsletter signup → Main Ledger `Agroverse News Letter Subscribers`** end-to-end; reuse existing signup pipe, don't fork it | 2.2 | Working opt-in pipeline |
| 2.4 | Wire **"interested in carrying cacao?" → Hit List** routing | 2.3 | Lead-capture pipeline |
| 2.5 | SEO/Schema.org `Event` block on the page; update `sitemap.xml`; verify OG preview | 2.1 | Indexed, shareable page |
| 2.6 | Optional one quiet line on `/wholesale` near stockist list | 0.1 | — |
| 2.7 | Generate QR batch `DTS-2026-06-26` (traceability + opt-in) via `AGROVERSE_QR_CODE_BATCH_GENERATION.md` | 2.3 | QR PNGs in `to_print/` (NOT printed yet — see gate) |

**Do NOT:** homepage banner, announcement bar, countdown, or pre-event agroverse blog post.

---

## Phase 3 — DRY RUN + publish (June 18–20, T-1wk)  · Owner: Claude  ← gate

| # | Task | Output |
|---|---|---|
| 3.1 | **Dry run:** print one test QR, scan it, confirm signup lands in subscribers tab | Pass/fail |
| 3.2 | Confirm `send_newsletter.py` can address the new test subscriber | Pass/fail |
| 3.3 | Check the "carry cacao?" path lands in Hit List with correct Status | Pass/fail |
| 3.4 | Fix any dead link / CORS / sheet-permission error | Green pipeline |
| 3.5 | **Publish the truesight.me essay** (seeds narrative before the day) | Live essay URL |

**⛔ Gate:** Phase 4 printing proceeds **only when 3.1–3.4 pass.**

---

## Phase 4 — Pre-event outreach + final prep (June 20–25, T-1wk → T-1d)

| # | Task | Owner | Output |
|---|---|---|---|
| 4.1 | **Newsletter (no full-list blast):** personal 1:1 notes to in-network folks; segmented/local send only if cleanly possible; or piggyback on a scheduled send; else skip | Gary (+ Claude/Kimi draft) | Permission-respecting touches |
| 4.2 | Print the "scan to verify" placard + cup stickers (after dry run) | Gary | Physical materials |
| 4.3 | Pull cacao for two flasks + 1–2 display bags; log `[INVENTORY MOVEMENT]` | Gary | Stock + ledger entry |
| 4.4 | Day-of: pre-brew the two flasks; pack cups, napkins, placard, display bags | Gary / Kirsten | Event kit (no kettle needed) |
| 4.5 | Final confirm with Ken (table location, ClawCamp timing) | Gary | Locked logistics |

---

## Phase 5 — Event day (June 26, T-0)  · Owner: Gary

- **Set up on Ken's table:** two flasks + cups + the "scan to verify" placard + 1–2 display bags. Light footprint, no backdrop.
- **Taste first, provenance second.** Pour the cup → let them taste Oscar's/Paulo's → mention the QR/ledger only if they ask.
- Serve at pause moments (§4.1); coordinate with ClawCamp block.
- No booth, no pitch, no checkout. Capture permission via opt-in QR.
- Note retail-interest conversations on the spot (name, what they tasted, next step).
- Capture 3–5 photos + rough observations for the post-event essay.

---

## Phase 6 — Immediate post-event (June 27–28, T+2d)  · Owner: Claude + Gary

| # | Task | Owner | Output |
|---|---|---|---|
| 6.1 | Verify opt-in signups landed in subscribers tab | Claude | Confirmed list |
| 6.2 | Add warm leads to Hit List (`Source: Dual Tech Summit 2026`, Notes) | Gary | Pipeline input |
| 6.3 | Verify `suggest_manager_followup_drafts.py` picked up new leads | Claude | Queued drafts |
| 6.4 | Log activation as a **DApp Remark** (servings, farms, conversations) | Gary | Training data |
| 6.5 | Update event page → past-tense marker | Claude/Gary | Honest site state |

---

## Phase 7 — Follow-up + story (June 29 – July 10, T+1–2wk)

| # | Task | Owner | Output |
|---|---|---|---|
| 7.1 | Manager Follow-up drafts for event leads | Grok (existing pipeline) → Gary sends | Warm-up touches |
| 7.2 | **Field-dispatch newsletter** (one human moment, grounded taste note, quiet commerce link) — only if a real story exists | Kimi (draft) → Kirsten/Fatima review → `send_newsletter.py` + Gary | Post-event send |
| 7.3 | Update `OUTREACH_QUALITATIVE_LOOP.md` with objection/conversion/taste signals | DeepSeek | Living loop |
| 7.4 | Optional truesight.me reflection essay (if the day warranted one) | Kimi or Claude (Gary's call) | Essay |

---

## Milestone checklist (one-glance)

- [x] **M0a** — Ken confirms attendance + two-flask format *(done 2026-05-23)*  ·  [ ] **M0b** — date, venue, table specifics *(Gary)*
- [ ] **M1** — truesight.me essay drafted *(Claude)* + asset templates ready *(OpenAI)*
- [ ] **M2** — Event page live + QR→signup→sheet pipeline wired *(Claude)*
- [ ] **M3** — ✅ **Dry run passes** + essay published *(Claude)* ← gate
- [ ] **M4** — Materials printed, inventory pulled, kit packed, 1:1 outreach done *(Gary)*
- [ ] **M5** — Event executed: taste-first, permission captured *(Gary)*
- [ ] **M6** — Signups verified, leads in Hit List, DApp Remark logged *(Claude/Gary)*
- [ ] **M7** — Follow-ups sent, field-dispatch newsletter (if earned), qualitative loop updated *(Grok/Kimi/DeepSeek)*

---

## Decision points for Gary (resolve to start)

1. **Cacao Journeys page** — build the dedicated landing, or point the opt-in QR at the existing signup form? *(Recommended: build it — durable, on-brand, survives the event.)*
2. **Newsletter** — segment Bay Area vs everyone, or personal 1:1 only? *(Recommended: 1:1 + skip full-list pre-event.)*
3. **Essay author for the post-event reflection** — Claude or Kimi? *(No rush; decide after the event based on the angle.)*
4. ~~**Scale** — pour hot vs sealed bags?~~ **Resolved (2026-05-23):** two flasks pre-brewed + cups, poured at Ken's table. No kettle, no bag handout.

---

*Roadmap authored 2026-05-24 by Claude (Anthropic). Owners and phasing synthesized from all four LLM proposals (see `proposal_finalized.md` §13–14). Adjust dates once Ken confirms the event date.*
