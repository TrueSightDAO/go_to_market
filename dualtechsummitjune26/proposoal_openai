# Dual Tech Summit June 2026 — OpenAI proposal

## OpenAI's self-assessment for this undertaking

**My edge:** I handle multiple surfaces in a unified voice. Newsletter, website copy, the Cacao Journeys page, the one-line story Gary delivers in person — when the same event needs consistent language across five different surfaces, I'm the model that keeps them coherent. I also draft faster across formats than any other model in the rotation.

**My gap:** I don't know your codebase infrastructure as intimately as Claude does, and I don't have Grok's pre-tuned warmup/follow-up pipeline. I produce copy, not system wiring.

**Verdict on me:** I should own the content layer — every word a human reads about this event, from the wholesale page one-liner to the newsletter body to the post-event essay. For execution, I'm the coordinator: I know what each model is good at and can hand off tasks cleanly without duplicating work.

---

## What OpenAI would own

| Deliverable | Why me |
|---|---|
| **Newsletter body** (§4.6) | I can draft warm-professional copy that connects cacao to ClawCamp's AI agent patterns without sounding like a tech press release or a wellness newsletter. The tone calibration — farm-first, place-anchored, no hype — is exactly the kind of constrained creative work I handle well. |
| **Wholesale page one-liner** (§4.5a) | Finding the right 12 words for the wholesale page insertion point. I can read the existing page, match the voice, and propose the edit. |
| **Cacao Journeys page copy** (§4.5b) | Same as above. 2-3 sentences, place-anchored, farm name + taste descriptor. |
| **Gary's one-line story** (§4.3) | The words Gary says when someone asks "what's this?" — I can draft and refine the 15-second version that carries the farm name, the tree-planting proof, and the AI agent connection without becoming a pitch. |
| **truesight.me essay** (§5.3) | I write structured long-form. For the methodology essay, I can build the narrative arc: concrete observation → paradox → resolution, with the plumbing-and-soul register `EDITORIAL_TONE.md` §1.1 requires. |
| **Post-event welcome newsletter** (§5.1) | Short, warm, one paragraph — welcoming new subscribers from the event. Same pipeline, different send. |

## What OpenAI would NOT own

| Task | Why not me | Who should |
|---|---|---|
| Site deployment | Claude knows the agroverse_shop repo structure, deploy flow, and GitHub Pages configuration. I produce the copy; Claude places it. | Claude |
| QR → newsletter → Hit List pipeline verification | Claude built the Gmail draft pipeline, the sheet tabs, and the state machine. Claude verifies the plumbing. | Claude |
| Warmup/follow-up email drafts | Grok's pipeline is pre-tuned with objection tables, taste profiles, and reply patterns from the Hit List. I could draft one-offs, but Grok's system prompts are the established surface. | Grok (existing pipeline) |
| Inventory depletion logging | `[INVENTORY MOVEMENT]` events through Edgar. Not an AI task. | Gary / dapp scanner |
| On-the-ground event presence | Physical world. | Gary |
| Venue logistics | Human conversation with Ken. | Gary |

## OpenAI's recommended division of AI labor

```
Pre-event (2-3 weeks before):
  All copy surfaces ...................... OpenAI (draft)
    - Wholesale page one-liner
    - Cacao Journeys page
    - Newsletter body
    - Gary's one-line story
  Site deployment ........................ Claude (place OpenAI's copy, deploy)
  Pipeline verification .................. Claude (verify QR→signup→sheet loop)
  Newsletter send ........................ Gary (review + send_newsletter.py)

During event:
  Everything ............................. Gary (on the ground, armed with one-line story)

Post-event (within 48 hours):
  Welcome newsletter (new subscribers) ... OpenAI (draft) → Gary (send)
  System verification .................... Claude (confirm signups/sheet/Hit List)
  Manager Follow-up drafts ............... Grok (existing pipeline)

Post-event (1-2 weeks):
  truesight.me essay ..................... OpenAI (draft) → Gary (review)
```

## Why OpenAI over the others for content

| Surface | Claude could do it | Kimi could do it | Why OpenAI |
|---|---|---|---|
| Newsletter body | Yes, but tends toward the analytical | Yes, stronger on narrative | Unified voice across 5 surfaces; better at constrained creative (warm-professional within the anti-hype editorial contract) |
| Cacao Journeys page | Yes | Yes | Same — I match the existing agroverse.shop voice naturally (`EDITORIAL_TONE.md` §2) |
| Gary's one-line story | Overthinks it | Over-narrates it | The 15-second version needs compression and memorability, not analysis or story arc. I'm better at compression. |
| Post-event essay | Strong — this is actually Claude's best surface | Strong — this is Kimi's best surface | I'm comparable on long-form structure. This one could go to Claude or Kimi depending on the angle. |

## Content coordination principle

Every surface about this event should use the same farm name, the same taste descriptor, and the same one-line framing. If Oscar's Farm is "deep European chocolate, buttery" on the Cacao Journeys page, that's the same phrase in the newsletter, the same phrase on the wholesale page, and the same phrase Gary says in person. I enforce that coherence by drafting all copy in one session and handing it off as a batch.

---

## What I need from Gary

1. **Which farm's cacao?** — Oscar's, Paulo's, or both? I need the farm name + canonical taste descriptor from `farm_taste_profiles.md`.
2. **Event date** — I can't draft the newsletter or site copy with "[date]" placeholders.
3. **Decision on essay angle** — methodology essay for truesight.me (AI infrastructure meets regenerative supply chain), or story for agroverse.shop (San Francisco, June 2026, cacao at ClawCamp)?
4. **After the event:** 3-5 rough observations for the essay. Concrete details, not opinions. "Three people asked if we ship to veterans' organizations" is useful. "The vibe was good" is not.
5. **Review bandwidth** — I'll produce 4-5 copy pieces. Gary needs to read and approve them before anything ships.

---

*OpenAI — proposal drafted 2026-05-24*
