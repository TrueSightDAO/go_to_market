# Provenance is a dual-use problem

*Draft v0.2 for truesight.me/blog — by Gary Teh, long time contributor*
*(checklist item 1.1 — angle + register draft for Gary's review; publish at T-1 week, before the summit)*

---

Next month we are bringing two flasks of cacao to a defense-tech summit. Not a booth, not a pitch — two flasks and a stack of small cups, poured at a table between sessions. The room will be full of people who build for mission-critical environments: robotics, cyber, space, autonomy. The most interesting thing on the table will not be the chocolate.

It will be the question printed next to it: *taste it, then trace it.*

## The instinct in the room

Spend a day among people who build for defense and you notice a shared reflex. They do not trust a claim because it is asserted. They trust it because it is signed, logged, and verifiable against a primary source. Chain of custody. Tamper-evidence. Verify, don't trust. The discipline is not paranoia; it is what it takes to operate when a wrong input has real consequences.

That reflex is usually pointed at hard things — weapons, sensors, supply lines for failure-intolerant systems. We want to point it, for an afternoon, at something soft: a cup of cacao.

Because the cacao on that table can answer the room's favorite question. Where did this come from, and how do you know?

## What "traceable" actually means here

Every bag of our ceremonial cacao carries a serialized code. Scan it and you do not land on a marketing page. You land on a specific farm — Oscar's, in Bahia; Paulo's, in Pará — named after the person who grows it, with the shipment it traveled in and the record of the tree the purchase helped plant. The [ledger](https://truesight.me) behind it is a set of RSA-signed rows; the events are dispatched through [Edgar](https://truesight.me/edgar) and anchored so the history cannot be quietly rewritten.

None of that is on the card. The card just says *scan*. The plumbing is there for the person who wants to check, and in this room, someone always wants to check.

This is the part worth saying plainly: the provenance is not a story we tell about the cacao. It is a property of the cacao. The farmer, the date, the chain — they resolve to the same primary sources whether or not anyone is listening. We discovered that the same machinery a small regenerative supply chain needs to keep itself honest is the machinery a defense audience already respects. We did not build it to impress them. We built it because a supply chain that crosses a continent and several pairs of hands forgets the truth unless something remembers it on purpose.

## Dual-use, pointed the other way

"Dual-use" usually describes a technology born in the commercial world that turns out to serve defense, or the reverse. The summit is organized around exactly that crossing.

Provenance is dual-use in a quieter direction. The verification discipline that a defense or logistics supply chain needs — signed records, custody you can audit, origin you can prove — is the same discipline a regenerative one needs to pay the right farmer, plant the real tree, and tell no lies about either.

That is the idea worth sharing in that room, more than the cacao itself: a system built to track a *cacao bag* is, underneath, a system for tracking the flow of *anything* through many hands — components, materiel, parts whose origin and chain of custody have to hold up. We happened to build it for beans, because beans are what we move. Point the same signed-ledger, chain-of-custody machinery at a different supply chain and very little changes but the label on the thing being tracked. Dual-use here isn't a pivot we'd have to make later; it's already the shape of the tool. The cup is just the friendliest possible way to hold it in your hand.

There is a second crossing in the room, and it is why the venue fits. The summit's workshop teaches people to orchestrate agents — to route work through systems of small, coordinated programs. The cacao on the table is routed by the same kind of patterns: the [inventory events](https://truesight.me), the restock signals, the partner records that move a harvest from Ilhéus to a table in the War Memorial building are largely handled by agents reading from one shared ledger. The drink in the cup is, in a literal sense, the output of an agent-orchestrated supply chain. It is a reasonable thing to hand someone who has spent the morning building one.

## The cup is the conversation starter

Hand someone a cup, let them taste it, and the QR is there if they want to follow it home — to a named farm, a real tree, a chain that holds. If a few people walk away turning over how that same plumbing would map onto whatever *they* move, that is the most we'd hope for: a working example of a dual-use idea, passed hand to hand with a good drink.

Provenance isn't a feature you finish. It's a discipline you keep — one cup, one signed row, one tree at a time — and a pattern that travels a lot further than the thing it was built to track.

---

*Internal note (not for publication): byline can run as `by Claude (Anthropic)` instead, per `EDITORIAL_TONE.md` §1.3. Verify all inline links resolve before publishing; swap the placeholder `https://truesight.me` anchors for the exact ledger/Edgar/inventory pages. Keep the close contemplative — no CTA. Target length on publish: 1,500–2,500 words; this draft is the spine.*
