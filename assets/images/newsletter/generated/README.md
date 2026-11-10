# `generated/` — derivative media for distribution

Governed by **`agentic_ai_context/sops/GENERATED_MEDIA_SOP.md`**. Parent runbook: `MEDIA_ARCHIVE_PIPELINE.md`.

**This directory is not an archive.** Per MAP: *"Distribution ≠ archive — Instagram/TikTok/shop-page posting are consumers of the archive, not the pipeline itself."* Nothing here may be copied into `raw/<farm>/`, `farm-media-raw/<farm-id>/photos/`, or uploaded to the public YouTube farm channel — `yt_id` is the manifest's binding to a real recorded event, and a derivative holding that field corrupts the archive's meaning retroactively (SOP R1).

## Every asset needs a manifest row

`generated_media.json` is the manifest of record. One asset ⇒ one row. The lane is a **field, not a convention**:

- **Lane A** — built from a real asset we hold. `derived_from: [sha256…]`, `disclosure_required: false`.
- **Lane B** — built from a text prompt. `derived_from: []`, `disclosure_required: true`, **visible AI label**.

An asset without a resolvable lane is unmanifested, and an unmanifested asset is invisible to every consumer.

## Batch 1 — 2026-11-10 (no inference used)

| | |
|---|---|
| Asset | `bar-81-motion-20261119-landscape.mp4` + `…-9x16.mp4` |
| Lane | **A** |
| Source | `../bar-81-dark-chocolate.jpg` (`9f2700aa…`) |
| Method | `ffmpeg` Ken Burns push-in — **no model, no inference, $0** |
| Placement | `primary_key 4ed72c3d` — Thu 2026-11-19, Carousel, `Recipes & Rituals` |
| Gate | `PASS_WITH_WARN` (label never names the farm — pre-existing) |

### Known constraint: source resolution

The source photograph is **800×451**. A true 9:16 crop would be 253 px wide and require a **4.3× upscale**, so the 9:16 build uses a blurred self-backdrop with the real photo inset instead.

**We do not hold a high-resolution product photograph.** Until that is fixed, inference spend is paying to animate a 451 px image. This is the same shape of constraint `tokenomics/SCHEMA.md` §5 records for the archive (108 of 1,107 items yield a usable frame): the bottleneck is source coverage, not generation.

### Blocked

SOP §11 **step 1** — provider credential — is not satisfiable by the autopilot (account + payment instrument = governor action). The vault holds no generation-related entry. Steps 2–5 are specified and ready.
