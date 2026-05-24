# Dual Tech Summit June 2026 — Agroverse cacao activation proposal

**Event:** SVH Capital Presents: Dual Tech Summit 2026  
**Date:** June 2026 (exact date TBD from Luma)  
**Venue:** War Memorial Veterans Building, 401 Van Ness Ave, San Francisco, CA 94102  
**Hosts:** Orbis86, OffChain Global, SVH Capital  
**Contact:** Ken (Orbis86) — warm offer to make cacao available  
**Status:** Proposal — awaiting operator review

---

## 1. Opportunity

Ken at Orbis86 offered for Agroverse ceremonial cacao to be available at the Dual Tech Summit. Agroverse is already listed as a past Orbis86 partner on the event page. This is a warm-path opportunity — not a cold ask.

The event sits at an unusual intersection that matches our story:

- **Veteran-focused** — dual-use tech (commercial + defense), veteran founders pitching to veteran VCs, ClawCamp workshop for veteran builders
- **AI infrastructure** — ClawCamp is a full-day workshop on personal orchestration agents (the same multi-agent pattern TrueSight DAO's autopilot, partner poke scheduler, and cron-driven Hit List run on)
- **Community** — OffChain Global (70+ chapters, Web3 professionals), Orbis86 (50k+ followers), SF-local

The audience includes people who would understand *both* halves of what we do: the AI plumbing and the regenerative cacao.

---

## 2. Strategic framing (CMO lens)

**Who it's for:** Two smallest viable audiences in the room —

1. **Veteran builders at ClawCamp** — they're learning to build AI agents. The cacao is the output of a system that runs on AI agents. Taste the thing the machines help route from Bahia to San Francisco.
2. **Potential retail partners** — SF-local wellness practitioners, circle hosts, apothecary owners who attend Orbis86 events. The warmup pipeline already knows how to convert this profile.

**What change we want:**
- Short: People taste single-estate Bahia cacao from a named farm, scan a QR code, and opt into hearing more.
- Medium: One or two new Partnered stores in the SF Bay Area from attendee connections.
- Long: The story of "AI agents routing regenerative cacao from the Amazon to San Francisco" becomes something a roomful of tech builders remark on.

**Is it remarkable?** Cacao at a defense-tech summit is already a purple cow. The packaging carries the farm name, the QR code proves the tree was planted. Someone will say "wait, this chocolate bar traces to a specific tree in Bahia?"

**Do we have permission?** Ken invited us. Attendees who scan a QR code and opt into the newsletter give permission for follow-up. No cold blast. No booth pitch.

---

## 3. What we do NOT do

Per `EDITORIAL_TONE.md` and the operational DNA:

- **No demo booth.** We don't do table displays with signage and pitch decks. The product on a side table with hot water and QR codes is more Agroverse than a branded 6-foot table.
- **No announcement.** Neither truesight.me nor agroverse.shop does the "we're excited to announce" genre. If we write about this afterward, it's a methodology essay (truesight.me) or a place-anchored story (agroverse.shop).
- **No cold email blast to attendees.** The attendee list is not ours to scrape. Permission comes through the QR code scan → newsletter opt-in path.
- **No pricing negotiation or consignment terms on the floor.** This is a tasting, not a sales meeting. If someone wants to carry cacao, they get routed to the existing warmup pipeline.

---

## 4. Tactical plan

### 4.1 Product presence (the cacao itself)

| Element | Detail |
|---|---|
| **Format** | Pre-grated ceremonial cacao in a bowl/hot water dispenser — ready to drink. No prep friction. |
| **Farms represented** | Oscar's Farm (deep European chocolate, buttery) and/or Paulo's Farm (smoky, tobaccoy, floral). One or both depending on available stock. |
| **Bags on display** | 3-5 retail bags (200g) with QR codes visible. People can handle the packaging, scan, and see the traceability proof on their phone. |
| **Location** | ClawCamp room (11AM-4PM) — natural fit. Optionally at the closing reception (5PM) if the venue allows. |
| **Prep card** | Small handwritten or printed card next to the cacao: *"Fazenda Analuana, Bahia, Brazil — operated by Ana Luana. Each bag plants a tree. Scan the QR code."* No logo. No tagline. Farm name + action. |

### 4.2 QR codes

Two QR codes printed and placed next to the cacao:

| QR code | Destination | Purpose |
|---|---|---|
| **Product traceability** | A specific bag's tree-planting proof page (the `compiled_` URL from the Agroverse QR batch) | Shows the mission is real, not copy. |
| **Newsletter signup** | agroverse.shop newsletter subscribe page or a simple form | Permission capture. "Want to know when new harvests land?" |

The QR generation pipeline (`AGROVERSE_QR_CODE_BATCH_GENERATION.md`) already produces these. No new tooling needed.

### 4.3 The one-line story (what Gary says when someone asks "what's this?")

> "Ceremonial cacao from Bahia, Brazil. Single-estate, named after the farmer who runs it. Each bag plants a tree — the QR code shows you exactly which one. The supply chain runs on AI agents we built."

That's it. Not a pitch. A fact with an invitation to scan.

If they ask about the AI agents: point to the ClawCamp room. "Same pattern they're teaching in there."

### 4.4 Newsletter opt-in flow

The QR code for newsletter signup routes to a landing page or form that:
- Captures email + optional "interested in carrying cacao?" checkbox
- Drops into Main Ledger → `Agroverse News Letter Subscribers` tab (status: `CONFIRMED` after double opt-in, or `PENDING` if single-step)
- The existing `send_newsletter.py` infrastructure picks them up for future sends

If someone expresses retail interest on the spot, Gary can manually add them to the Hit List at `Research` or `Shortlisted` with a note: "Met at Dual Tech Summit June 2026."

### 4.5 Pre-event — agroverse.shop surface

Two small additions to the site, neither of which breaks the anti-announcement rule:

#### 4.5a Wholesale page — single sentence

On `agroverse.shop/wholesale`, add one line near the bottom (or wherever the existing stockist/partner list lives):

> *June 2026 — San Francisco: Find us at the Dual Tech Summit. Ceremonial cacao available at the ClawCamp workshop.*

No exclamation mark. No "come visit us." Just a place-anchored fact. Existing partners browsing the wholesale page see we're active locally; potential partners who land there after the event see the connection.

If the wholesale page doesn't have a natural slot for this, add it to the existing partner/stockist section — same treatment as the partner venue list, just a date instead of a permanent location.

#### 4.5b Cacao Journeys — optional placeholder page

Create a minimal page at `agroverse.shop/cacao-journeys/dual-tech-summit-2026/` (or under `/events/` if that namespace exists). Content shape:

- **Headline:** "San Francisco, June 2026 — Dual Tech Summit"
- **Body:** 2-3 sentences. Place-anchored: War Memorial Veterans Building, ClawCamp workshop, ceremonial cacao from Bahia. No hype. No schedule. No "tickets here."
- **QR code:** The same newsletter signup QR used at the event. One sentence: "Taste it at the event, or sign up for harvest updates."
- **Link back:** From the page to agroverse.shop/shop so anyone who lands there can browse product.

Purpose: gives the QR code a human-readable destination that isn't just a form. Someone scanning the code later (from a photo, from the bag they took home) lands on a named place + farm story, not a generic subscribe page.

**Ship decision:** If building a new page is too heavy for the return, ship only the wholesale-page one-liner (§4.5a). The QR code can point directly to the newsletter signup. The page is nice-to-have, not must-have.

### 4.6 Pre-event — newsletter send

Send one newsletter to the existing subscriber list (`Agroverse News Letter Subscribers`, status `CONFIRMED`) 5–7 days before the event. Use the existing `send_newsletter.py` pipeline. Gmail label: `Newsletter/Dual-Tech-Summit-June-2026`.

#### Voice constraint

Per `EDITORIAL_TONE.md` §2.4 (agroverse.shop): warm-professional, collective "we," no sales urgency, no "we're excited to announce." The newsletter should read like a note from someone who'll be in the room, not a promo blast.

#### Structure

| Section | Content |
|---|---|
| **Subject** | "Ceremonial cacao in San Francisco — June [date]" |
| **Opening** | One sentence naming the place, the host, and the fact we'll have cacao there. Example: *"On June [date], we'll have ceremonial cacao from Bahia at the Dual Tech Summit in San Francisco's War Memorial Veterans Building — hosted by Orbis86 and SVH Capital."* |
| **The story beat** | 2-3 sentences connecting cacao to the event's theme. Frame: the supply chain that routes Bahia cacao to SF runs on the same AI agent patterns ClawCamp teaches. Farm name + taste descriptor. No blockchain jargon. |
| **What's there** | One line: *"Ceremonial cacao available at the ClawCamp workshop (11AM–4PM). Come taste Oscar's Farm — deep European chocolate, buttery."* |
| **Not attending?** | One line: *"If you're not in SF, the same cacao ships from agroverse.shop — each bag plants a tree, traceable by QR code."* |
| **Link** | agroverse.shop (shop link, not event link). No ticket link. |

#### Details

- **To:** `Agroverse News Letter Subscribers` (CONFIRMED only)
- **From:** `garyjob@agroverse.shop`
- **Label:** `Newsletter/Dual-Tech-Summit-June-2026`
- **Tracking:** `--track-opens` via Edgar pixel (optional — the event send is low enough volume that open rate matters less than the qualitative "did anyone reply?")
- **Opt-out footer:** Standard unsubscribe link (existing `send_newsletter.py` template includes this)

#### What we explicitly avoid in the newsletter

- "Tickets available now" / "Register here" — we are not selling the event.
- "Come visit our booth" — we don't have one.
- "Exclusive offer for subscribers" — undermines the harvest-cycle truthfulness.
- Event agenda dump — the reader doesn't need the full schedule. They need to know we'll be there with cacao.

#### Optional: segment by geography

If the subscriber list has location data (city/state from signup), split into two cohorts:

1. **Bay Area subscribers** — add: *"If you're in SF that day, stop by ClawCamp and say hello."*
2. **Everyone else** — the "Not attending?" paragraph carries the weight.

If segmentation isn't trivial with the current subscriber data, skip it. The single send works for everyone.

---

## 5. Post-event loop

### 5.1 Immediate (within 48 hours)

1. **Newsletter:** If we captured any signups, send a short welcome note from `garyjob@agroverse.shop` — one paragraph, farm-first, link to agroverse.shop/wholesale. Use the existing `send_newsletter.py` pipeline.
2. **Hit List:** Any warm leads (someone who said "I want to carry this") get added to the Hit List as `Shortlisted` with full context in Notes. The existing state machine picks them up from there.

### 5.2 Within 1 week

1. **Manager Follow-up drafts:** For any leads that entered the pipeline, run `suggest_manager_followup_drafts.py` — the follow-up drafts land in Gmail under `AI/Follow-up` for Gary's review and send.
2. **Partner Check-in:** If any existing Partnered stores were at the event and expressed restock interest, the Partner Poke Scheduler (`partner_poke_drafts.gs`) already handles that surface.

### 5.3 Optional: truesight.me essay

If the event produces an interesting observation about the intersection of AI infrastructure and regenerative supply chains, write a truesight.me blog post. Frame as a methodology essay, not an event recap. Example angle: *"What happened when we put cacao in a room full of dual-use tech builders."* Per `EDITORIAL_TONE.md` §1.1: concrete data point in the opener, then a paradox. No announcement language.

---

## 6. Logistics checklist

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Confirm event date with Ken | Gary | ☐ |
| 2 | Confirm we can have cacao + hot water in the ClawCamp room | Gary / Ken | ☐ |
| 3 | **Pre-event: add one-line mention to agroverse.shop/wholesale** (§4.5a) | Gary | ☐ |
| 4 | **Pre-event: send newsletter** via `send_newsletter.py` (5-7 days before) (§4.6) | Gary | ☐ |
| 5 | **Pre-event (optional):** create minimal `/cacao-journeys/dual-tech-summit-2026/` page (§4.5b) | Gary | ☐ |
| 6 | Determine which farm's cacao to bring (check inventory: Partner Stock tab) | Gary / tokenomics | ☐ |
| 7 | Pull 3-5 retail bags from inventory; log depletion via `[INVENTORY MOVEMENT]` | Gary | ☐ |
| 8 | Generate QR code prints (traceability + newsletter signup) | `AGROVERSE_QR_CODE_BATCH_GENERATION.md` pipeline | ☐ |
| 9 | Prepare one-line farm/place-anchored card | Gary | ☐ |
| 10 | Bring hot water dispenser / electric kettle | Gary | ☐ |
| 11 | Post-event: import newsletter signups to Main Ledger | Gary / `send_newsletter.py` | ☐ |
| 12 | Post-event: add warm leads to Hit List | Gary | ☐ |

---

## 7. What we measure

| Metric | How | Why |
|---|---|---|
| **QR scans (traceability)** | Short-lived redirect counter or sheet log | Did anyone actually verify the tree? |
| **Newsletter signups** | `Agroverse News Letter Subscribers` tab row count delta | Permission captured. |
| **Retail interest expressed** | Hit List rows added with "Dual Tech Summit" in Notes | Pipeline input. |
| **Qualitative** | What did people say when they tasted it? Capture in DApp Remarks or a quick note. | Taste profile feedback, new objection patterns, unexpected use cases. |

---

## 8. Cost

| Item | Estimate |
|---|---|
| Cacao (3-5 retail bags, already in inventory) | ~$85–$140 at retail value; cost basis lower |
| QR code prints | Near zero (existing pipeline) |
| Prep card printing | Near zero |
| Hot water setup | If venue doesn't provide: ~$30 kettle + cups |
| Gary's time | 1 day (event attendance already planned) |

No new tooling, no new infrastructure, no paid sponsorship. The event already lists Agroverse as a past partner.

---

## 9. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Venue doesn't allow outside food/beverage | Medium | Confirm with Ken before event. Fallback: bring sealed retail bags only (no hot water), let people take them home. |
| No one scans the QR codes | Low-Medium | Place QR codes where people stand (next to cups, not on a far wall). The packaging itself has the QR code — anyone who picks up a bag can scan it. |
| Event audience is too technical, doesn't care about cacao | Low | The ClawCamp room is the right filter — people already opted into a hands-on workshop. Cacao as fuel for a 5-hour build session is a different frame than "wellness product." |
| Existing partners feel overlooked if we're visibly at an event but didn't invite them | Low | If any SF Partnered stores are interested, invite them to stop by. This isn't a retail activation — it's a tasting at a tech event. |

---

## 10. Decision

- [ ] **Proceed** — Gary confirms date + venue logistics with Ken; checklist in §6 activates.
- [ ] **Defer** — Revisit if a future Orbis86 event has stronger overlap.
- [ ] **Scale down** — Send sealed retail bags only (no hot water setup). Simpler, lower risk, still gets product in hands.
- [ ] **Scale up** — Add a dedicated person to staff the cacao table during ClawCamp so Gary can attend sessions without leaving the cacao unattended.

---

## 11. Multi-model execution assessment

Four models submitted proposals for this undertaking: DeepSeek (this doc — strategy), Claude, OpenAI, and Kimi. Each was asked to self-assess what they would own vs. delegate. The following is the comparative verdict on who should execute the pre-event and post-event work.

### 11.1 Scope claimed by each model

| Model | Deliverables claimed | Best surface |
|---|---|---|
| **DeepSeek** | Strategy, tactical plan, risk register, measurement framework | System design, anti-pattern identification, comprehensive planning |
| **Claude** | Site prep + deploy, pipeline verification, newsletter body, essay, post-event verification (5 items) | Infrastructure, pipeline verification, coordination without handoffs |
| **OpenAI** | All copy surfaces (6 items): newsletter, wholesale one-liner, Cacao Journeys page, Gary's one-line story, essay, welcome newsletter | Content coherence across surfaces, constrained creative voice |
| **Kimi** | Essay, Cacao Journeys page, newsletter body (3 items) | Long-form narrative, place-anchored storytelling |

### 11.2 Critical path — what this event actually rises and falls on

| Priority | Requirement | Failure mode if missed |
|---|---|---|
| **1** | QR code → newsletter signup → sheet tab works end-to-end | 200 people scan a dead link. Zero permission captured. |
| **2** | Newsletter sends 5-7 days before event | Nobody knows we're there. Subscriber base silent. |
| **3** | Post-event: warm leads enter Hit List state machine | The whole point of the event (new Partnered stores) evaporates — no pipeline input. |
| **4** | Copy quality (newsletter, site, one-line story) | A B+ newsletter and a C- newsletter produce the same outcome. A broken pipeline produces zero outcome. |

### 11.3 Which model addressed the real risks

| Risk | DeepSeek | Claude | OpenAI | Kimi |
|---|---|---|---|---|
| QR pipeline breaks | Mentioned in risk register (§9) | **Proposed pre-event dry run** (§Key decisions #3) | Not addressed | Not addressed |
| Newsletter send fails | Not addressed specifically | Pipeline verification covers it | Not addressed | Not addressed |
| Sheet permission error | Not addressed | Addressed via dry run | Not addressed | Not addressed |
| Content incoherence across surfaces | Not addressed | Not addressed | Proposed unified-voice principle | Not addressed |
| Leads don't enter Hit List | Assigned to Gary (§5.1) | Post-event verification step | Assigned to Claude | Assigned to Gary |

Claude is the only model that identified the pre-event dry run — testing the full QR→signup→sheet loop one week before the event — as a discrete action. This alone makes Claude's proposal the highest-leverage contribution across all four. It prevents the single failure mode that kills the entire activation.

### 11.4 Coordination quality

| Model | Handoff count | Handoff risk |
|---|---|---|
| **Claude** | 1 (warmup drafts → Grok, but Grok's pipeline is existing cron — no net-new handoff) | Low. Writes copy and deploys in one session. Coordination is self-contained. |
| **OpenAI** | 2 (copy → Claude for deploy; pipeline verify → Claude) | Medium. Content→deploy handoff introduces a dependency. If Claude is unavailable when OpenAI finishes copy, the site doesn't update. |
| **Kimi** | 4+ (everything except essay, Cacao Journeys page, and newsletter body → Gary or Grok) | High. Leaves infrastructure, coordination, and verification entirely unfilled. No one else is filling those gaps in her proposal. |

### 11.5 Verdict: Claude

Three reasons:

**1. The dry run.** Claude is the only model that proposed verifying the QR→signup→sheet pipeline before the event. That one paragraph is the highest-leverage contribution across all four proposals. It prevents the single failure mode that kills the entire activation — 200 people scanning a dead link.

**2. Self-contained execution.** Claude can write the site copy and deploy it in the same session. No content→deploy handoff gap. No waiting for another model to place the words. For a pre-event window measured in weeks, this eliminates the most common failure mode in multi-model work: the handoff that never gets picked up.

**3. Precise delegation.** Claude explicitly hands warmup/follow-up drafts to Grok (the established pipeline that is already tuned with objection tables and taste profiles) and physical-world tasks to Gary. It claims what it built (the pipeline, the state machine, the review surface) and refuses what it didn't (Grok's draft generation, the tokenomics QR pipeline).

### 11.6 The one thing Claude gets wrong

Claude slightly overclaims the truesight.me essay (§5.3). Kimi is stronger at narrative warmth for the long-form agroverse voice. But the essay is a post-event concern with no scheduling pressure — Gary can decide at that point whether Claude or Kimi drafts it. It does not affect the pre-event critical path.

### 11.7 Recommended division of labor (final)

```
Pre-event (2-3 weeks before):
  Strategy (this doc) ................... DeepSeek (complete)
  Site edits + deploy ................... Claude
  Pipeline verification + dry run ....... Claude
  Newsletter body ....................... Claude (draft) → Gary (review + send)
  One-line story refinement ............. Claude or OpenAI (draft) → Gary (memorize)

During event:
  Everything ............................ Gary (on the ground)

Post-event (within 48 hours):
  Verify signups + Hit List entries ..... Claude
  Manager Follow-up drafts .............. Grok (existing pipeline)
  Welcome newsletter .................... send_newsletter.py + Gary

Post-event (1-2 weeks):
  truesight.me essay .................... Claude or Kimi (Gary's call based on angle)
  Qualitative loop update ............... DeepSeek (update OUTREACH_QUALITATIVE_LOOP.md
                                         with event observations)
```

### 11.8 What DeepSeek retains

DeepSeek does not execute day-to-day event tasks. DeepSeek's role in this undertaking is:
- **Strategy doc** (this file) — the plan-of-record all other models read from.
- **Risk register** (§9) — maintained here as ground truth.
- **Measurement framework** (§7) — defines what success looks like; Claude verifies against it post-event.
- **Qualitative loop** — after the event, DeepSeek updates `OUTREACH_QUALITATIVE_LOOP.md` with any new objection patterns, conversion signals, or taste feedback surfaced at the event.

---

*Proposal drafted 2026-05-24. Refresh when event date is confirmed and logistics decisions are made.*
