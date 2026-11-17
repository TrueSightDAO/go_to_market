# Week 2 · Nov 19, 2026 — "28 flavor worlds"

**Slot:** `Instagram Content Schedule!e293d67e` · Thursday 2026-11-19 · **Carousel**
**Theme Focus:** 28 flavor worlds: taste cacao like you taste wine
**Theme:** Recipes & Food

## Status: ASSEMBLED, NOT POSTED

7 slides built from **AI-generated** imagery, not farm photography. Real farm photos
(358 in `farm_media_manifests`, ~95% `.HEIC`) are reserved for slots whose CTA points at
a *specific* farm record — see "Why generated, not real" below.

## Slide order

| # | File | Beat | On-page overlay |
|---|---|---|---|
| 1 | `generated/flavor_00_hero.jpg` | Hook | You've been **eating** cacao. |
| 2 | `generated/flavor_01_fruit.jpg` | Fruit | **Fruit** |
| 3 | `generated/flavor_02_floral.jpg` | Floral | **Floral** |
| 4 | `generated/flavor_03_nut.jpg` | Nut | **Nut** |
| 5 | `generated/flavor_04_spice.jpg` | Spice | **Spice** |
| 6 | `generated/flavor_05_earth.jpg` | Earth | **Earth** |
| 7 | `generated/flavor_06_cta.jpg` | CTA | Scan the bag's QR → this farm's record |

Contact sheet: `generated/carousel_contact_sheet.jpg`

## Caption

> You've been eating cacao. You could be tasting 28 different flavor worlds.
>
> Fruit, floral, nut, spice and earth all live in the same bean. The difference between
> chewing and tasting isn't the bean — it's what happened to it before it reached you:
> the ferment, the drying, the roast. Roast a cacao hot and fast and it tastes like
> coffee. Roast it at 120°C for 25–30 minutes and the fruit comes forward.
>
> 28 flavor worlds, one species. Start with your nose, then your tongue.
>
> Scan the bag's QR to open this farm's record.

Hashtags: `#cacao #cacaonibs #cacaorecipes #beantobar #hotchocolate #cacaodrink #recipe`

## Why generated, not real

1. **HEIC.** 340 of 358 archive photos are `.HEIC` — not web-usable without transcoding,
   and I hold no S3 read credential for `media.agroverse.shop/raw/`.
2. **No descriptions.** The manifests carry filenames only, so I cannot caption a real
   photo or assert what it depicts. Guessing would be fabrication.
3. **Provenance.** The caption's CTA sends the reader to *this farm's record*. A generated
   image standing in for a farm photo would make that claim false.

Per `MEDIA_ARCHIVE_PIPELINE.md` §"Generated artifacts": these render at
`entity_type: "generated"`, `is_raw_footage: false`, and **must carry the `[GENERATED]`
label** wherever published. They do not inherit provenance from the farms.

## Blocked / open

- **Real farm imagery** needs S3 read on `s3://media.agroverse.shop/raw/` (or HEIC
  transcodes supplied). Once available, slides 2–6 should be re-shot as real macro
  photos of that farm's own fruit/nuts/spices, each credited in the slide.
- **On-page overlay text is not applied yet** — the plates are clean images. Typesetting
  needs a font decision (the brand's saffron/monochrome treatment).
- No audio is involved, so the ASR verification blocker from the Reel plan does **not**
  apply here.

## Governance

Nothing here is published. No sheet status change was made — `e293d67e` remains
`PLANNED` pending a governor call to move it to `SCHEDULED`/`PUBLISHED`.
