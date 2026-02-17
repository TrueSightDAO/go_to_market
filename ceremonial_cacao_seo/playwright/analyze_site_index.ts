/**
 * Analyze full site index: keyword mapping, page-type breakdown, content themes.
 * Run after index_competitor_sites.ts. Reads competitor_site_index.json, writes
 * competitor_site_mapping.md and optionally updates positioning/strategy inputs.
 */

import * as fs from 'fs';
import * as path from 'path';

const INDEX_PATH = path.join(__dirname, '..', 'competitor_site_index.json');
const OUT_MAPPING = path.join(__dirname, '..', 'competitor_site_mapping.md');

interface IndexedPage {
  url: string;
  path: string;
  title: string | null;
  metaDescription: string | null;
  h1: string | null;
  h2s: string[];
  mainSnippet: string | null;
  wordCount: number;
  error?: string;
}

interface SiteIndex {
  competitor: string;
  baseUrl: string;
  baseOrigin: string;
  indexedAt: string;
  pageCount: number;
  pages: IndexedPage[];
}

const KEYWORD_GROUPS: Record<string, string[]> = {
  ceremonial: ['ceremonial', 'cacao ceremony', 'ceremony'],
  organic: ['organic', 'usda organic'],
  origin: ['single origin', 'single-origin', 'origin', 'belize', 'colombia', 'guatemala', 'ecuador', 'peru', 'brazil', 'amazon'],
  regenerative: ['regenerative', 'regeneration', 'sustainable', 'agroforestry'],
  traceability: ['traceability', 'traceable', 'farm', 'farmer', 'harvest'],
  community: ['community', 'circle', 'gathering', 'ritual'],
  retail: ['buy', 'shop', 'order', 'cart', 'wholesale', 'retail'],
};

function countKeywords(text: string | null): Record<string, number> {
  if (!text) return {};
  const lower = text.toLowerCase();
  const out: Record<string, number> = {};
  for (const [group, terms] of Object.entries(KEYWORD_GROUPS)) {
    out[group] = terms.filter((t) => lower.includes(t)).length;
  }
  return out;
}

function inferPageType(p: IndexedPage): string {
  const path = (p.path || '').toLowerCase();
  const title = (p.title || '').toLowerCase();
  if (path.includes('/product') || path.includes('/shop/') || title.includes('buy') || title.includes('shop')) return 'product/shop';
  if (path.includes('/blog') || path.includes('/post') || path.includes('/article')) return 'blog';
  if (path.includes('/about') || path.includes('/story') || path.includes('/our-story')) return 'about';
  if (path === '/' || path === '') return 'homepage';
  if (path.includes('/collection') || path.includes('/category')) return 'category';
  if (path.includes('/cart') || path.includes('/checkout')) return 'cart/checkout';
  return 'other';
}

function main() {
  if (!fs.existsSync(INDEX_PATH)) {
    console.log('Run index_competitor_sites.ts first to generate competitor_site_index.json');
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(INDEX_PATH, 'utf-8'));
  const sites: SiteIndex[] = data.sites || [];

  const lines: string[] = [
    '# Competitor site mapping (full index analysis)',
    '',
    'Generated from competitor_site_index.json. Use for keyword strategy and content mapping.',
    '',
  ];

  for (const site of sites) {
    lines.push(`## ${site.competitor} (${site.baseUrl})`);
    lines.push('');
    lines.push(`- **Pages indexed:** ${site.pageCount}`);
    lines.push(`- **Indexed at:** ${site.indexedAt}`);
    lines.push('');

    const pages = site.pages || [];
    const byType: Record<string, IndexedPage[]> = {};
    for (const p of pages) {
      const t = inferPageType(p);
      if (!byType[t]) byType[t] = [];
      byType[t].push(p);
    }
    lines.push('### Page types');
    lines.push('');
    for (const [type, list] of Object.entries(byType).sort((a, b) => b[1].length - a[1].length)) {
      lines.push(`- **${type}:** ${list.length} pages`);
    }
    lines.push('');

    const allText = pages
      .map((p) => [p.title, p.metaDescription, p.h1, (p.h2s || []).join(' '), p.mainSnippet].filter(Boolean).join(' '))
      .join(' ');
    const keywordCounts = countKeywords(allText);
    lines.push('### Keyword presence (across all pages)');
    lines.push('');
    for (const [group, count] of Object.entries(keywordCounts).sort((a, b) => b[1] - a[1])) {
      if (count > 0) lines.push(`- **${group}:** ${count}`);
    }
    lines.push('');

    lines.push('### Sample pages (title / path)');
    lines.push('');
    const sample = pages.filter((p) => p.title && !p.error).slice(0, 15);
    for (const p of sample) {
      lines.push(`- ${(p.title || '').slice(0, 60)} | \`${p.path}\``);
    }
    lines.push('');
  }

  lines.push('---');
  lines.push('');
  lines.push('*Use this mapping to refine seo_keyword_strategy.md and implementation on agroverse.shop.*');

  fs.writeFileSync(OUT_MAPPING, lines.join('\n'), 'utf-8');
  console.log(`Wrote ${OUT_MAPPING}`);
}

main();
