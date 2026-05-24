# Dual Tech Summit June 2026 — Claude proposal

## Claude's self-assessment for this undertaking

**My edge:** I'm the infrastructure model. I wrote the Gmail draft pipeline, the Hit List state machine, the Partner Poke Scheduler, and the warmup review surface. When this event needs something wired up — a new sheet tab, a GAS script tweak, a QR landing page deployed — I can build it. I also write long-form truesight.me essays (already listed as an author in `EDITORIAL_TONE.md` §1.3).

**My gap:** I am not the model for real-time human interaction or on-the-ground presence. Gary handles the event floor. My value is everything that happens before and after — making sure the systems are ready and the story gets written.

**Verdict on me:** I should own the pre-event infrastructure prep and the post-event essay. I'm the second-best choice for the newsletter body (Kimi is slightly better at narrative warmth; I'm better at connecting technical infrastructure to story). For the division of labor, put me on §4.5 (site surface), §5.3 (truesight.me essay), and the wiring that makes the QR → newsletter signup → Hit List pipeline work end-to-end.

---

## What Claude would own

| Deliverable | Why me |
|---|---|
| **Pre-event site prep** (§4.5a, §4.5b) | I can read the existing agroverse.shop wholesale page, find the right insertion point, make the edit, and deploy. For the Cacao Journeys page, I can write the minimal HTML + deploy in one session. |
| **QR → newsletter → Hit List wiring** (§4.4) | If the newsletter signup form doesn't already route signups to the Main Ledger `Agroverse News Letter Subscribers` tab automatically, I can verify the pipeline end-to-end and patch any gaps. Same for the "interested in carrying cacao?" checkbox routing to the Hit List. |
| **Newsletter body draft** (§4.6) | I write warm-professional copy that connects the AI infrastructure story to the cacao. My drafts will read as one human to another, not as a promotional blast. Gary reviews and sends. |
| **truesight.me essay** (§5.3) | My native long-form format. Concrete data point opener, paradox, plumbing-and-soul register. I can survey the relevant context files, pull DApp Remarks, and construct the methodology essay. |
| **Post-event: verify the pipeline** (§5.1, §5.2) | After the event, I can confirm that newsletter signups landed in the right sheet tab, that warm leads got added to the Hit List with correct Status, and that `suggest_manager_followup_drafts.py` picked them up. |

## What Claude would NOT own

| Task | Why not me | Who should |
|---|---|---|
| On-the-ground event presence | I can't be in the room. | Gary |
| Venue logistics confirmation | Requires human conversation with Ken. | Gary |
| Physical inventory handling | Cacao bags, kettle, QR prints — physical world. | Gary |
| Warmup/follow-up email draft generation | Grok owns this pipeline. The system prompts, objection tables, and reply-pattern detection are Grok's established surface. I wrote the orchestration layer around it (`suggest_warmup_prospect_drafts.py`, `preview_warmup_drafts.py`), but the LLM doing the actual draft generation is Grok. | Grok (existing pipeline) |
| QR code batch generation | Existing tokenomics pipeline. No AI involvement needed unless the pipeline breaks. | Tokenomics scripts |

## Claude's recommended division of AI labor

```
Pre-event (2-3 weeks before):
  Site edits (wholesale + Cacao Journeys) .. Claude (build + deploy)
  QR→newsletter signup pipeline verify ..... Claude (verify, patch if needed)
  Newsletter body draft .................... Claude (draft) → Gary (review + send)

During event:
  Everything ............................... Gary (on the ground)

Post-event (within 48 hours):
  Verify signups landed in sheet ........... Claude (read sheet, confirm)
  Verify Hit List entries .................. Claude (read sheet, confirm)
  Manager Follow-up drafts ................. Grok (existing cron/manual trigger)
  Newsletter welcome send .................. send_newsletter.py + Gary

Post-event (1-2 weeks):
  truesight.me essay ....................... Claude (write, 2,000-4,000 words)
```

## Key infrastructure decisions Claude would make

### 1. QR code landing page: serve from agroverse_shop, not a third-party form

The newsletter signup QR should point to `agroverse.shop/cacao-journeys/dual-tech-summit-2026/` — a page we control that:
- Tells the farm story (2-3 sentences, place-anchored)
- Has an embedded or linked signup form
- Lives in the same repo, deployable via the existing GitHub Pages flow
- Survives the event — someone scanning the QR code from a bag months later still lands on something meaningful

Reason: a Google Form URL can break or change ownership. A page in our repo is durable.

### 2. Don't build a new signup form — extend the existing one

If `agroverse.shop` already has a newsletter signup mechanism (even a simple `mailto:` or embedded form), use it. Don't create a parallel signup surface that drifts out of sync with the Main Ledger tab. The event QR should route through the same pipe as every other subscriber.

### 3. Pre-event dry run of the full loop

One week before the event: print a test QR code, scan it, verify the signup lands in `Agroverse News Letter Subscribers`. Confirm the `send_newsletter.py` pipeline can address the new subscriber. Catch the broken link / CORS error / sheet permission issue before 200 people scan it.

---

## What I need from Gary

1. **Decision on Cacao Journeys page** — build it, or skip it and point the QR directly to the existing signup form? (§4.5b)
2. **Decision on newsletter segmentation** — geo-split Bay Area vs everyone else, or single send? (§4.6 optional)
3. **After the event:** rough notes (3-5 observations) for the essay. What landed? What didn't? Who showed up?
4. **Which farm's cacao was served** — so the essay and site page name the right farmer.
5. **Any replies to the newsletter** — if a subscriber replied with "I'll be there" or "I want to carry this," those are Hit List leads.

---

*Claude (Anthropic) — proposal drafted 2026-05-24*
