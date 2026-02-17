/**
 * Step 1: Search for top ceremonial cacao competitors targeting USA.
 * Uses DuckDuckGo HTML to get result links, then merges into competitors_list.json.
 * Run: npx ts-node search_competitors.ts
 */

// Use playwright (bundled with @playwright/test) for browser launch
const { chromium } = require('@playwright/test');
import * as fs from 'fs';
import * as path from 'path';

const LIST_PATH = path.join(__dirname, '..', 'competitors_list.json');
const QUERIES = [
  'ceremonial cacao USA buy',
  'best ceremonial cacao USA',
  'organic ceremonial cacao USA',
];

const SKIP_DOMAINS = new Set([
  'wikipedia.org', 'pinterest.com', 'facebook.com', 'youtube.com',
  'instagram.com', 'twitter.com', 'linkedin.com', 'reddit.com',
  'amazon.com', 'ebay.com', 'walmart.com', 'duckduckgo.com', 'google.com',
]);

function normalizeUrl(href: string): string | null {
  try {
    const u = new URL(href);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    const host = u.hostname.toLowerCase();
    if (SKIP_DOMAINS.has(host) || [...SKIP_DOMAINS].some(d => host.endsWith('.' + d))) return null;
    return u.origin + u.pathname.replace(/\/+$/, '') || u.origin;
  } catch {
    return null;
  }
}

async function searchDuckDuckGo(query: string): Promise<string[]> {
  const headless = process.env.HEADLESS !== '0';
  const browser = await chromium.launch({ headless });
  const page = await browser.newPage();
  const seen = new Set<string>();
  const links: string[] = [];

  try {
    await page.goto(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    const rawLinks = await page.$$eval('a.result__a', (anchors: unknown[]) =>
      (anchors as { href: string }[]).map((a) => a.href).filter(Boolean)
    );
    for (const href of rawLinks) {
      const norm = normalizeUrl(href);
      if (norm && !seen.has(norm)) {
        seen.add(norm);
        links.push(norm);
      }
    }
  } finally {
    await browser.close();
  }
  return links;
}

async function main() {
  const allLinks = new Map<string, { count: number; queries: string[] }>();

  for (const q of QUERIES) {
    console.log(`Searching: "${q}"`);
    const links = await searchDuckDuckGo(q);
    for (const url of links) {
      const prev = allLinks.get(url) || { count: 0, queries: [] };
      prev.count++;
      prev.queries.push(q);
      allLinks.set(url, prev);
    }
  }

  const sorted = [...allLinks.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 15)
    .map(([url, { queries }]) => ({ url, queries }));

  let list: { targetMarket: string; updatedAt: string | null; competitors: { name: string; url: string; region: string; notes: string }[] } = {
    targetMarket: 'USA',
    updatedAt: null,
    competitors: [],
  };
  if (fs.existsSync(LIST_PATH)) {
    list = JSON.parse(fs.readFileSync(LIST_PATH, 'utf-8'));
  }
  const existingUrls = new Set(list.competitors.map((c) => c.url));

  for (const { url } of sorted) {
    if (existingUrls.has(url)) continue;
    const name = new URL(url).hostname.replace(/^www\./, '');
    list.competitors.push({
      name,
      url,
      region: 'USA',
      notes: `Discovered by search. Add product/positioning notes.`,
    });
    existingUrls.add(url);
  }
  list.updatedAt = new Date().toISOString();
  fs.writeFileSync(LIST_PATH, JSON.stringify(list, null, 2), 'utf-8');
  console.log(`Updated ${LIST_PATH}. Total competitors: ${list.competitors.length}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
