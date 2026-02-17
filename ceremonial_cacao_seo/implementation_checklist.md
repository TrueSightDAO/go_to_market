# Implementation Checklist — SEO Strategy on agroverse.shop

After updating `seo_keyword_strategy.md`, apply changes below and run the content-alignment tests.

---

## Checklist

- [ ] **Homepage** (`agroverse_shop/index.html`)
  - [ ] Title includes primary target (e.g. ceremonial cacao) and brand
  - [ ] Meta description 150–160 chars, includes “ceremonial cacao” and differentiators (regeneration, traceability / cacao circles)
  - [ ] H1 and first paragraph align with strategy

- [ ] **Product pages** (e.g. `product-page/*/index.html`)
  - [ ] Each has unique `<title>` and `<meta name="description">` per `docs/PRODUCT_CREATION_CHECKLIST.md`
  - [ ] Product titles/descriptions include “ceremonial cacao” and origin where relevant
  - [ ] JSON-LD Product schema present and valid

- [ ] **Category / key landing pages**
  - [ ] Category pages have target keywords in title and meta
  - [ ] Cacao Journeys / Blog: headings and intros use strategy keywords where natural

- [ ] **Farms & Shipments**
  - [ ] Farm/shipment pages mention “single origin,” “traceability,” “ceremonial cacao” where relevant

- [ ] **Tests**
  - [ ] Run `cd agroverse_shop && npm test` (includes `seo-content-alignment.spec.ts`)
  - [ ] Fix any failing assertions (meta length, required keywords, alignment)

---

## Reference

- Strategy (research): `market_research/ceremonial_cacao_seo/seo_keyword_strategy.md`
- Strategy (in agroverse_shop): `agroverse_shop/docs/SEO_KEYWORD_STRATEGY.md`
- Full-site index & mapping: `market_research/ceremonial_cacao_seo/competitor_site_index.json` + `competitor_site_mapping.md`
- Product checklist: `agroverse_shop/docs/PRODUCT_CREATION_CHECKLIST.md`
- SEO tests: `agroverse_shop/tests/seo-content-alignment.spec.ts`
