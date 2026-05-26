# Onsen Global Leaders Forum 2026 — Implementation roadmap

**Companion to:** `proposal.md` (plan-of-record)
**Event:** Global Expansion & Cross-Border Leaders Forum · June 23, 2026 · 5:30–7:30 PM · Palo Alto, CA
**Format (confirmed):** small basket of 20 sealed cacao tea bags on the snack table — each labeled with provenance QR + Onsen Global x Agroverse co-branding. No flasks, no pour, no booth.
**Lead:** Claude (QR pipeline + label design) · **On the ground:** Gary · **Follow-up:** Grok

---

## Critical path (the chain the event rises and falls on)

```
Request Onsen Global logo from Tiffine (or settle on wordmark fallback)
        ↓
Generate provenance QR code (OGLF_CT_20260623_1) + publish to lineage-assets
        ↓
Design tea bag label template (Onsen logo, farm name, QR)
        ↓
DRY RUN: print one test label, scan QR, confirm signup lands   ← gate
        ↓
Print 20+ labels → affix to tea bags → assemble basket
        ↓
Event day: place basket on snack table → Gary networks
        ↓
Post-event: verify scans → Hit List → DApp Remark → thank-you to Tiffine
```

**Gate rule:** nothing gets printed until the dry run in Phase 2 passes.

---

## Phase 0 — Confirm logistics with Tiffine (now → Jun 16, T-1wk)  · Owner: Gary

**Already confirmed:** small basket of sealed cacao tea bags on the snack table. Gary registered (May 21).

| # | Task | Output | Blocks |
|---|---|---|---|
| 0.1 | Request Onsen Global logo (black, single-color) from Tiffine | Logo file [or wordmark fallback] | Label design |
| 0.2 | Confirm snack table placement — any venue-specific notes? | Setup plan | — |
| 0.3 | Confirm Gary's registration is approved | Entry confirmed | — |
| 0.4 | Confirm tea bag packaging is sealed (meets JIC policy) | Compliance check | — |
| 0.5 | (Optional) preference on verbal mention vs word-of-mouth | Tone guide | — |

**Exit criteria:** logo received (or wordmark fallback chosen), snack table placement confirmed. → unblocks Phase 1.

---

## Phase 1 — Build QR code + label design (now → Jun 16, T-1wk)  · Owner: Claude

| # | Task | Output |
|---|---|---|
| 1.1 | Generate QR batch `OGLF_CT_20260623_1` (Paulo's cacao tea) via existing pipeline; publish to `lineage-assets` repo | QR PNG + `qrs_index.json` entry |
| 1.2 | Provenance QR target = agl8 landing page (consent + subscribe) — reuse existing page, no new build | Working QR → signup pipeline |
| 1.3 | Add UTM: `?utm_source=event&utm_medium=qr&utm_campaign=oglf-2026` | Scan attribution |
| 1.4 | Design tea bag label (`label_template_OGLF.svg`): Onsen logo, event name, farm, taste note, QR, agroverse.shop footer | Print-ready label template |
| 1.5 | Draft basket card copy → `field_assets.md` | Basket card text |

**Register guardrails:** label copy stays curatorial — no prices, no urgency, no blockchain jargon. Taste notes from `AGROVERSE_PRICE_LIST_AND_ASSETS.md`. Only one QR per label (provenance; subscribe rides on the landing page).

---

## Phase 2 — DRY RUN (Jun 16–19)  · Owner: Claude  ← gate

| # | Task | Output |
|---|---|---|
| 2.1 | **Dry run:** print one test label, scan QR, confirm agl8 page resolves | Pass/fail |
| 2.2 | Fill test signup on agl8 page → confirm it lands in `Agroverse News Letter Subscribers` tab | Pass/fail |
| 2.3 | Confirm `send_newsletter.py` can address the new test subscriber | Pass/fail |
| 2.4 | Confirm QR is scannable at tea bag label size (~40mm) | Pass/fail |
| 2.5 | Fix any issues | Green pipeline |

**⛔ Gate:** Phase 3 printing proceeds **only when 2.1–2.4 pass.**

---

## Phase 3 — Print + assemble kit (Jun 19–22)  · Owner: Gary

| # | Task | Output |
|---|---|---|
| 3.1 | Print 20 tea bag labels + 5 spares (black-and-white label printer) | Labeled bags |
| 3.2 | Affix labels to 20 sealed Paulo's cacao tea bags | Finished tea bags |
| 3.3 | Pull 20 tea bags from inventory; log `[INVENTORY MOVEMENT]` | Stock + ledger entry |
| 3.4 | Verify each bag is sealed (JIC policy) | Compliance check |
| 3.5 | Print or write basket card | Basket card |
| 3.6 | Assemble basket: 20 labeled tea bags + basket card | Event-ready basket |

---

## Phase 4 — Event day (Jun 23)  · Owner: Gary

- **Arrive ~5:15 PM.** Find Tiffine, confirm the snack table location.
- **Place basket on snack table.** Visible but unobtrusive. Basket card beside it.
- **Quick photo** of the basket setup before people arrive.
- **The basket is the whole presence.** No signage, no banner, no standing at the table.
- **Gary networks** — registered attendee, not on shift.
- **If someone picks up a tea bag / mentions it** → tell the one-line story (§2.3 of proposal).
- **Don't initiate** the cacao conversation unprompted. Let the basket pull.
- **Mid-event (~7:00 PM):** glance at the basket, note how many bags remain.
- **End of event:** collect basket, count remaining bags, jot notes.
- **If Tiffine introduces you to anyone** → pay attention, note names and context.

---

## Phase 5 — Immediate post-event (Jun 24–25)  · Owner: Claude

| # | Task | Output |
|---|---|---|
| 5.1 | Check QR scan count for `OGLF_CT_20260623_1` | Scan metrics |
| 5.2 | Verify any opt-in signups landed in `Agroverse News Letter Subscribers` tab | Confirmed list |
| 5.3 | Count new subscribers → note delta | Subscriber delta |
| 5.4 | Add warm leads to Hit List (`Source: Onsen Global Leaders Forum 2026`, Notes) | Pipeline input |
| 5.5 | Verify `suggest_manager_followup_drafts.py` picks up any new leads | Queued drafts |
| 5.6 | Log activation as a **DApp Remark** (date, tea bags taken, notable conversations, photo) | Training data |
| 5.7 | Thank-you to Tiffine (warm, non-transactional) *(Gary)* | Relationship |

---

## Phase 6 — Follow-up (Jun 26–30)

| # | Task | Owner | Output |
|---|---|---|---|
| 6.1 | Manager Follow-up drafts for event leads | Grok (existing pipeline) → Gary sends | Warm-up touches |
| 6.2 | Personal 1:1 follow-ups with any contacts Gary made | Gary | Relationship |
| 6.3 | **No full-list newsletter** — skip entirely. Wrong audience for the wellness list. | — | — |
| 6.4 | Optional truesight.me essay if the evening produced an observation | Claude (draft) → Gary (review/publish) | Essay |

---

## Milestone checklist (one-glance)

- [ ] **M0** — Logo received (or wordmark fallback), snack table confirmed *(Gary)*
- [ ] **M1** — QR code minted + label template designed *(Claude)*
- [ ] **M2** — ✅ **Dry run passes** ← gate
- [ ] **M3** — Labels printed, tea bags labeled, basket assembled *(Gary)*
- [ ] **M4** — Event executed: basket on snack table, Gary networks *(Gary)*
- [ ] **M5** — Signups verified, leads in Hit List, thank-you to Tiffine, DApp Remark logged *(Claude/Gary)*
- [ ] **M6** — Follow-ups sent, essay (if warranted) *(Grok/Claude)*

---

## Decision points for Gary

1. **Tea bags** — Paulo's cacao tea (Pará) only, or include a few Oscar's ceremonial cacao bags too? *Recommended: Paulo's only — tea format, lighter, lower-stimulant for an evening event. Oscar's is a drink, not a tea-bag product.*
2. **Label branding** — wait for Onsen Global logo or proceed with wordmark fallback? *Recommended: request logo now, set a Jun 14 deadline. If no response by then, proceed with typeset wordmark.*
3. **Quantity** — 20 tea bags for ~50 people. Enough? *Recommended: yes. Scarcity is signal. If all 20 get taken, that's a 40% conversion rate from room to scan — excellent. If only 10 get taken, that's still 25% and no wasted inventory.*
4. **Newsletter** — skip full-list entirely. *Yes.*
5. **Post-event essay** — worth writing? *Recommended: decide after the event. A quiet tea-bag basket at a private forum may or may not generate a publishable observation. No pressure.*

---

## Differences from DTS / SFTF — why this event is simpler

| Factor | DTS / SFTF | This event |
|---|---|---|
| Format | Pour (flasks + cups) | Sealed tea bags in a basket |
| Venue constraint | Standard (confirm with host) | Japanese venue — sealed packages only |
| Setup time | Flasks pre-brewed, cups stacked, placard placed | Basket dropped on snack table |
| Staffing | Gary pours or it's self-serve | Zero staffing — basket is fully unattended |
| Artifact | QR placard + cup stickers | QR on the tea bag label itself |
| Scale | Dozens of pours | 20 sealed bags |
| Co-branding | Agroverse only | Onsen Global + Agroverse on the label |
| Duration | All-day | 2-hour evening |

---

*Roadmap authored 2026-05-26 by Claude (Anthropic).*
