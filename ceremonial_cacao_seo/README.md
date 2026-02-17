# Ceremonial Cacao SEO — USA Competitor Research & Positioning

**Task scope:** Research top USA competitors offering ceremonial cacao, analyze their positioning, and define an SEO keyword strategy that lets Agroverse **match** category expectations while **differentiating** on our unique angles (Amazon regeneration, farm traceability, shipments, taste profiles).

Inspired by [The AI Corner — Claude SEO Cowork prompts](https://www.the-ai-corner.com/p/claude-seo-cowork-prompts-free-agency?r=1krivi). This workflow uses **Playwright** for search discovery, site crawling, and structured analysis.

---

## Workflow (6 steps)

| Step | Description | Output |
|------|-------------|--------|
| **1** | Search online for top 10 ceremonial cacao competitors targeting USA | `competitors_list.json` |
| **2** | Compile and maintain the list | Same file, versioned |
| **3a** | **Full-site index:** Discover all pages per competitor (sitemap + homepage links), crawl each, build complete index | `competitor_site_index.json` |
| **3b** | **Analysis & mapping:** Run analysis over full index (keyword presence, page types, sample pages) | `competitor_site_mapping.md` |
| **3c** | (Optional) Landing-only crawl and positioning summary | `competitor_analysis.json` + `positioning_summary.md` |
| **4** | Define SEO keyword positioning strategy (match + differentiate) | `seo_keyword_strategy.md` |
| **5** | Implement on agroverse.shop and add tests so new content stays aligned | agroverse_shop edits + Playwright tests in `agroverse_shop/tests/` |

---

## Repository layout

```
market_research/ceremonial_cacao_seo/
├── README.md                    # This file — task context and workflow
├── competitors_list.json        # Top 10 (or more) USA competitors — URLs and notes
├── competitor_analysis.json      # (Optional) Landing-page crawl: title, meta, h1 per competitor
├── competitor_site_index.json   # Full-site index: every discovered page per competitor
├── competitor_site_mapping.md    # Analysis over full index: keyword mapping, page types
├── positioning_summary.md        # Human-readable positioning summary (from landing crawl)
├── seo_keyword_strategy.md      # Target keywords, match vs differentiate, content briefs
├── implementation_checklist.md  # What to change on agroverse.shop + test checklist
└── playwright/                  # Playwright (Node) scripts
    ├── package.json
    ├── search_competitors.ts    # Step 1: discover competitor URLs
    ├── crawl_competitors.ts     # Step 3c: landing-only crawl
    ├── index_competitor_sites.ts # Step 3a: full-site index (sitemap + links, then crawl)
    ├── analyze_positioning.ts   # Step 3c: positioning_summary from landing crawl
    └── analyze_site_index.ts    # Step 3b: mapping from full site index
```

**Agroverse.shop (implementation & tests):**

- `agroverse_shop/docs/SEO_KEYWORD_STRATEGY.md` — copy or link from market_research strategy
- `agroverse_shop/tests/seo-content-alignment.spec.ts` — tests to ensure new/updated content aligns with strategy and existing tone

---

## Step 1 & 2: Competitor list

- **Source:** Run `playwright/search_competitors.ts` (DuckDuckGo/Bing search for “ceremonial cacao USA” / “buy ceremonial cacao USA”) **or** manually research and paste URLs into `competitors_list.json`.
- **Schema:** See `competitors_list.json`. Fields: `name`, `url`, `region` (e.g. USA), `notes`, `addedAt`.

---

## Step 3a–3c: Analyze competitor websites (full index + mapping)

- **Full-site index (recommended):** Run `playwright/index_competitor_sites.ts`. For each competitor, discovers URLs via **sitemap.xml** (if present) and **homepage links**, then crawls up to 80 pages per site. Builds a complete **competitor_site_index.json** (every page: title, meta, h1, path, snippet).
- **Mapping:** Run `playwright/analyze_site_index.ts` to produce **competitor_site_mapping.md**: page-type breakdown, keyword presence across all pages, sample pages. Use this for strategy and content mapping.
- **Landing-only (optional):** `playwright/crawl_competitors.ts` crawls only the homepage per competitor → `competitor_analysis.json`. Then `analyze_positioning.ts` → `positioning_summary.md`.
- **Positioning dimensions to infer:** quality/ritual vs convenience, origin (single-origin vs blend), certifications (organic, fair trade), community/ceremony vs retail-only, price tier.

---

## Step 4: SEO keyword positioning strategy

- **Inputs:** `competitor_analysis.json`, `positioning_summary.md`, and Agroverse differentiators:
  - Regenerative Amazon / rainforest
  - Farm-level traceability (farms, shipments)
  - Taste profiles and sensory language
  - Cacao circles / gatherings
  - Retail + wholesale
- **Output:** `seo_keyword_strategy.md` with:
  - **Match:** Core terms we must show up for (e.g. “ceremonial cacao”, “ceremonial cacao USA”, “organic ceremonial cacao”).
  - **Differentiate:** Long-tail and thematic terms (e.g. “regenerative cacao”, “single-origin ceremonial cacao Brazil”, “farm traceability cacao”).
  - Content briefs for homepage, product pages, and key landing pages.

---

## Step 5: Implement and test

- **Implement:** Apply `seo_keyword_strategy.md` to agroverse.shop (titles, meta descriptions, headings, copy) per `implementation_checklist.md`.
- **Tests:** Run `agroverse_shop` Playwright tests, including `seo-content-alignment.spec.ts`, to ensure:
  - Key pages have meta title and description in expected length ranges.
  - Target keywords (from strategy) appear where intended.
  - Tone and differentiators (regenerative, traceability, Amazon) remain present and consistent.

---

## Agroverse differentiators (reference)

Use these when writing the positioning summary and keyword strategy:

- **Regeneration:** Amazon rainforest regeneration, sustainable/regenerative farming.
- **Traceability:** Specific farms, shipments (e.g. AGL), harvest years.
- **Quality/sensory:** Taste profiles, flavor notes, origin (Brazil, etc.).
- **Community:** Cacao circles, gatherings, mindful connection.
- **Channel:** Direct retail + wholesale; not only B2C.

---

## Quick start

```bash
# 1. Install and run competitor search (or fill competitors_list.json manually)
cd market_research/ceremonial_cacao_seo/playwright
npm install
npx playwright install chromium
npx ts-node search_competitors.ts

# Run with browser visible (debug): HEADLESS=0 npm run search  # or npm run crawl

# 2. Full-site index (recommended: entire site per competitor)
npm run index

# 3. Analysis and mapping from full index
npm run analyze-site

# Optional: landing-only crawl + positioning summary
npx ts-node crawl_competitors.ts
npx ts-node analyze_positioning.ts

# 4. Implement in agroverse_shop using implementation_checklist.md

# 5. Run agroverse_shop tests (including SEO content alignment)
cd ../../../agroverse_shop
npm test
```

---

*Last updated: 2026-01-30*
