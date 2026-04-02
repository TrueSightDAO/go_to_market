# Agroverse Shop — Non-Brand Buyer Intent & SEO Positioning

This document filters high commercial-intent cacao keywords from the DataForSEO **Keywords For Keywords** export, removes **brand- and retailer-specific** queries Agroverse cannot own, and maps the remainder to **concrete site improvements** for [agroverse.shop](https://www.agroverse.shop/).

## Data & methodology

| Input | Path |
|--------|------|
| Raw export | `output/dataforseo/buyer_intent_keywords_20260402_060431.csv` |
| Brand / noise filter | `output/dataforseo/brand_keyword_blocklist.txt` (substring match, case-insensitive) |
| Filter script | `scripts/filter_buyer_intent_remove_brands.py` |
| **Positionable list (output)** | `buyer_intent_keywords_20260402_060431_nonbrand.csv` |
| Excluded (transparency) | `buyer_intent_keywords_20260402_060431_excluded_brands.csv` |

**Counts (after latest blocklist):** ~197 keywords kept, ~113 excluded.

**Excluded categories include:** competitor cacao brands (e.g. Navitas, Keith’s, Volupta, Ora, Firefly, etc.), mass retailers (Whole Foods, Costco, Vitamin Shoppe, Vitacost), **hair-treatment** noise (`brasil cacau`, keratin), off-intent platforms (`reddit`), and **carob**. The blocklist is editable; re-run the script after changes.

**Caveats:** Google Ads search volumes are directional, not guarantees. Some remaining terms (e.g. “sacred cacao”) blend **generic intent** with crowded spiritual SERPs—worth monitoring, not necessarily primary commerce targets.

---

## Priority clusters (non-brand, buyer-adjacent)

Volumes are monthly (US, from the export). Grouped for landing-page and merchandising decisions.

### A. Cacao nibs (highest scale)

| Keyword | Volume |
|---------|--------:|
| cacao nibs | 33,100 |
| raw cacao nibs | 2,900 |
| unsweetened cacao nibs | 2,900 |
| cocoa nibs raw | 2,900 |
| organic cacao nibs | 1,900 |
| cacao nibs organic | 1,900 |
| cocoa nibs where to buy | 480 |
| bulk cacao nibs | 320 |
| cocoa nibs bulk | 320 |
| buy cacao nibs | 90 |
| cacao nibs for sale | 90 |
| organic cacao nibs bulk | 40 |

**Current Agroverse coverage:** Strong relevance via [8 oz organic cacao nibs](https://www.agroverse.shop/product-page/8-ounce-organic-cacao-nibs-from-brazil) (Bahia / Oscar’s story, traceability). Wholesale path exists under [Wholesale bulk](https://www.agroverse.shop/category/wholesale-bulk) and bulk criollo nibs SKU.

**Gaps & improvements**

1. **Title / H1 vocabulary:** Product title leads with *“Amazon Rainforest Regenerative 8 Ounce…”* — on-brand but **underweights the exact head phrase “organic cacao nibs”** (1,900+2,900 overlap). Consider testing a primary keyword front-load on this PDP or a **collection H1**, e.g. *Organic cacao nibs — Oscar’s farm, Bahia* (keep regenerative/traceability in description and body).
2. **“Where to buy / for / sale / bulk”:** Add a short **buyer block** (above fold or FAQ): *Wholesale & bulk cacao nibs* with internal link to `/category/wholesale-bulk` and anchor text using *bulk cacao nibs* / *cacao nibs wholesale* where natural.
3. **Cannibalization:** Ensure one **primary URL** for generic “organic cacao nibs” (likely the 8 oz PDP or a future `/category/` nibs hub) and use `rel=canonical` consistently; avoid duplicating the same primary phrase across many thin URLs.

### B. Ceremonial cacao

| Keyword | Volume |
|---------|--------:|
| ceremonial cacao | 8,100 |
| best ceremonial cacao | 480 |
| ceremonial cacao powder | 480 |
| ceremonial cacao near me | 390 |
| ceremonial cacao paste | 210 |
| organic ceremonial cacao | 170 |
| ceremonial cacao ceremony | 140 |
| ceremonial chocolate | 110 |
| ceremonial cacao block | 110 |
| buy ceremonial cacao | 50 |
| ceremonial cacao for sale | 70 |
| raw ceremonial cacao | 40 |

**Current coverage:** [Retail packs / ceremonial hub](https://www.agroverse.shop/category/retail-packs) is well optimized for **“buy ceremonial cacao USA”** and single-estate story. Multiple PDPs (Oscar’s, La do Sitio, Fazenda Santa Ana, etc.) support long-tail farm names.

**Gaps & improvements**

1. **“Near me”:** High CPC, local pack heavy. Agroverse is **D2C national** — don’t chase local packs; instead own **“buy ceremonial cacao online USA”** / shipping clarity (already partly in category meta). Consider a one-line **shipping + origin** trust strip sitewide.
2. **Powder / paste / block:** Searchers differentiate product form. If you sell **solid ceremonial discs/blocks** but not **powder**, add an **honest comparison short section** (*ceremonial cacao paste vs powder*) to reduce bounce and capture *paste/block* modifiers without promising SKUs you don’t carry.
3. **Internal linking:** From each ceremonial PDP, link to **wholesale** where relevant (*ceremonial cacao wholesale* appears in tail) with a single clear CTA paragraph.

### C. Beans, origin, trade

| Keyword | Volume |
|---------|--------:|
| raw cacao beans | 3,600 |
| cacao beans for sale | 1,300 |
| organic cacao beans | 720 |
| origin cacao | 480 |
| cocoa origin | 1,300 |
| single origin cacao / cocoa (+ beans) | 110 each |
| fair trade cacao / cocoa / beans | 140+ |
| brazilian cacao | 40 |
| cocoa brazil | 140 |
| cacao amazon rainforest | 30 |
| direct trade cacao | 10 |
| regenerative cacao | 10 |

**Current coverage:** Multiple **per-kg bean** PDPs (Criollo, hybrid, La do Sitio) + strong **Amazon/Bahia** narrative on homepage.

**Gaps & improvements**

1. **Fair trade + regenerative:** Homepage/description already hint at ethics; add a **dedicated short page or expandable section** that spells out *fair trade / direct trade / regenerative* in plain language (even if certifications are partial)—targets *fair trade cacao*, *direct trade cacao*, *regenerative cacao* without naming competitors.
2. **“Cocoa origin” / “single origin”:** Ensure **one flagship beans PDP** or category intro uses those phrases in **H2** and body (maps to educational searches, not only transactional).

### D. Wholesale & bulk (B2B-shaped)

| Keyword | Volume |
|---------|--------:|
| wholesale cacao | 210 |
| cacao nibs wholesale | 210 |
| wholesale cacao beans | 210 |
| wholesale cocoa beans | 210 |
| cocoa nibs wholesale | 210 |
| bulk cacao powder | 210 |
| cocoa powder wholesale | 110 |
| wholesale cacao powder | 110 |
| bulk organic cacao powder | 140 |
| organic cacao powder wholesale | 20 |
| ceremonial cacao wholesale | 10 |
| wholesale ceremonial cacao | 10 |

**Current coverage:** [Wholesale bulk category](https://www.agroverse.shop/category/wholesale-bulk) has a solid meta description (bulk beans/nibs, Brazil). **Page title** is generic: *“Wholesale Bulk \| Agroverse”*.

**Gaps & improvements**

1. **Title tag upgrade:** Prefer *Wholesale cacao beans & nibs \| Bulk Brazil \| Agroverse* (or similar) so **wholesale cacao / cacao nibs wholesale** appear in the title without stuffing.
2. **Powder gap:** Volumes exist for **bulk cocoa / cacao powder**. If Agroverse **does not** sell powder at scale, state that clearly and pivot to **beans/nibs/paste** to avoid irrelevant traffic; if powder is planned, this cluster is a **priority SKU + landing** opportunity.

### E. Cocoa / cacao powder & baking (competitive / partial fit)

High volume examples: *fair trade cocoa* (9,900), *bulk cocoa powder* (880), *organic fair trade cacao powder* (1,000), *fair trade cocoa powder* (260), *bulk vanilla-adjacent hot cocoa* tails.

**Assessment:** These skew toward **processed powder** and **commodity baking** aisles. Unless Agroverse adds **powder SKUs**, treat as **secondary**: either informational content (“how our nibs relate to powder”) or **explicit non-focus** to preserve conversion quality.

### F. Ceremony & education (informational + funnel)

Examples: *ceremonial cacao ceremony*, *cacao ceremony what is it*, *preparing ceremonial cacao*, *mayan cacao ceremony*, *spiritual cacao*.

**Improvement:** A **single authoritative guide** (blog or `/learn/`) that links to retail ceremonial SKUs can capture mid-funnel and pass equity to money pages—without relying on competitor brands.

---

## Current page inventory (SEO-facing)

| URL (path) | Title (abridged) | Role |
|------------|------------------|------|
| `/` | Agroverse \| Regenerating our Amazon… | Brand + ceremonial + rainforest story |
| `/category/retail-packs` | Buy Ceremonial Cacao USA \| Organic Single-Estate | **Ceremonial hub** |
| `/category/wholesale-bulk` | Wholesale Bulk \| Agroverse | B2B bulk |
| `/product-page/8-ounce-organic-cacao-nibs-from-brazil` | …8 Ounce Organic Cacao Nibs | **Nibs PDP** |
| Multiple `/product-page/*ceremonial*` | Ceremonial cacao – farm-specific | Long-tail ceremonial |
| Bean PDPs | Organic/Criollo/La do Sitio… | Beans / origin |

---

## Recommended next steps (ordered)

1. **Re-run filters** when you refresh DataForSEO exports; diff `*_nonbrand.csv` vs prior month for new generic heads.
2. **Wholesale category title + H1** — align to *wholesale cacao / bulk beans / nibs* vocabulary (one clear primary).
3. **Nibs PDP** — A/B or iterate meta title toward **organic cacao nibs** + origin, keeping brand voice in description.
4. **Product-form clarity** on ceremonial pages (paste / block / powder) to match query intent.
5. **Powder / baking cocoa** — decide whether to sell at scale; align SEO and paid keywords with that decision.
6. **Optional:** Merge this list with **Search Console** queries (impressions × position) to prioritize “high volume × already near page 2.”

---

## Appendix: maintaining the blocklist

Add competitor or retailer names **one per line** in `brand_keyword_blocklist.txt`. Use phrases long enough to avoid accidental matches (e.g. prefer `whole foods` over `whole`). Re-run:

```bash
python3 scripts/filter_buyer_intent_remove_brands.py output/dataforseo/buyer_intent_keywords_YYYYMMDD_HHMMSS.csv
```

Generated as part of market research workflow; not legal or financial advice.
