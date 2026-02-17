/**
 * Full-site index: discover all internal pages per competitor (sitemap + homepage links),
 * then crawl each page and build a complete index for analysis and mapping.
 * Run: npx ts-node index_competitor_sites.ts
 */

const { chromium } = require('@playwright/test');
import * as fs from 'fs';
import * as path from 'path';

const LIST_PATH = path.join(__dirname, '..', 'competitors_list.json');
const OUT_PATH = path.join(__dirname, '..', 'competitor_site_index.json');
const MAX_PAGES_PER_SITE = process.env.MAX_PAGES ? parseInt(process.env.MAX_PAGES, 10) : 80;
const CRAWL_TIMEOUT_MS = 15000;

interface Competitor {
  name: string;
  url: string;
  region: string;
  notes?: string;
}

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

function getOrigin(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return '';
  }
}

function normalizeSameOrigin(href: string, baseOrigin: string): string | null {
  try {
    const u = new URL(href, baseOrigin + '/');
    if (u.origin !== baseOrigin) return null;
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    const pathname = u.pathname.replace(/\/+$/, '') || '/';
    return u.origin + pathname;
  } catch {
    return null;
  }
}

async function discoverUrls(
  page: import('playwright').Page,
  baseOrigin: string,
  baseUrl: string
): Promise<string[]> {
  const seen = new Set<string>();

  // 1) Try sitemap.xml (and sitemap_index.xml)
  for (const sitemapPath of ['/sitemap.xml', '/sitemap_index.xml', '/sitemap-index.xml']) {
    try {
      const sitemapUrl = baseOrigin + sitemapPath;
      const res = await page.goto(sitemapUrl, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => null);
      if (res && res.ok()) {
        const body = await res.text();
        const locs = body.match(/<loc>([^<]+)<\/loc>/gi) || [];
        for (const loc of locs) {
          const url = loc.replace(/<\/?loc>/gi, '').trim();
          const norm = normalizeSameOrigin(url, baseOrigin);
          if (norm) seen.add(norm);
        }
        if (seen.size > 0) break;
      }
    } catch {
      /* try next */
    }
  }

  // 2) Homepage: collect all same-origin links
  try {
    const res = await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: CRAWL_TIMEOUT_MS }).catch(() => null);
    if (res && res.ok()) {
      seen.add(baseUrl);
      const links = await page.$$eval('a[href]', (anchors: unknown[]) =>
        (anchors as { href: string }[]).map((a) => a.href).filter(Boolean)
      );
      for (const href of links) {
        const norm = normalizeSameOrigin(href, baseOrigin);
        if (norm) seen.add(norm);
      }
    }
  } catch {
    /* ignore */
  }

  return [...seen];
}

async function crawlPage(
  page: import('playwright').Page,
  url: string,
  baseOrigin: string
): Promise<IndexedPage> {
  const pathname = new URL(url).pathname.replace(/\/+$/, '') || '/';
  const out: IndexedPage = {
    url,
    path: pathname,
    title: null,
    metaDescription: null,
    h1: null,
    h2s: [],
    mainSnippet: null,
    wordCount: 0,
  };
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: CRAWL_TIMEOUT_MS });
    out.title = await page.evaluate(() => document.title || null);
    out.metaDescription = await page.evaluate(() => {
      const el = document.querySelector('meta[name="description"]');
      return el ? (el.getAttribute('content') || null) : null;
    });
    out.h1 = await page.evaluate(() => {
      const h1 = document.querySelector('h1');
      return h1 ? h1.textContent?.trim() || null : null;
    });
    out.h2s = await page.evaluate(() => {
      const h2s = Array.from(document.querySelectorAll('h2'));
      return h2s.map((h) => (h.textContent || '').trim()).filter(Boolean);
    });
    const mainContent = await page.evaluate(() => {
      const main =
        document.querySelector('main') ||
        document.querySelector('article') ||
        document.querySelector('[role="main"]') ||
        document.body;
      const text = (main as HTMLElement).innerText || '';
      const paragraphs = text.split(/\n\n+/).map((p) => p.trim()).filter((p) => p.length > 60);
      return paragraphs.slice(0, 2).join(' ');
    });
    out.mainSnippet = mainContent.length > 0 ? mainContent.slice(0, 600) : null;
    out.wordCount = (out.mainSnippet || '').split(/\s+/).length;
  } catch (e) {
    out.error = e instanceof Error ? e.message : String(e);
  }
  return out;
}

async function indexOneSite(
  browser: import('playwright').Browser,
  competitor: Competitor
): Promise<SiteIndex> {
  const baseOrigin = getOrigin(competitor.url);
  const baseUrl = baseOrigin + (new URL(competitor.url).pathname.replace(/\/+$/, '') || '/');
  const page = await browser.newPage();

  const allUrls = await discoverUrls(page, baseOrigin, baseUrl);
  const toCrawl = allUrls.slice(0, MAX_PAGES_PER_SITE);
  const pages: IndexedPage[] = [];

  for (let i = 0; i < toCrawl.length; i++) {
    const url = toCrawl[i];
    process.stdout.write(`  [${i + 1}/${toCrawl.length}] ${url.slice(0, 60)}...\r`);
    const entry = await crawlPage(page, url, baseOrigin);
    pages.push(entry);
  }
  await page.close();

  return {
    competitor: competitor.name,
    baseUrl,
    baseOrigin,
    indexedAt: new Date().toISOString(),
    pageCount: pages.length,
    pages,
  };
}

async function main() {
  const list = JSON.parse(fs.readFileSync(LIST_PATH, 'utf-8'));
  const competitors: Competitor[] = list.competitors || [];
  if (competitors.length === 0) {
    console.log('No competitors in competitors_list.json.');
    process.exit(0);
  }

  const headless = process.env.HEADLESS !== '0';
  const browser = await chromium.launch({ headless });

  const indexes: SiteIndex[] = [];
  for (let i = 0; i < competitors.length; i++) {
    const c = competitors[i];
    console.log(`\n[${i + 1}/${competitors.length}] Indexing ${c.name} (${c.url})`);
    try {
      const index = await indexOneSite(browser, c);
      indexes.push(index);
      console.log(`  -> ${index.pageCount} pages indexed`);
    } catch (e) {
      console.error(`  Error:`, e);
      indexes.push({
        competitor: c.name,
        baseUrl: c.url,
        baseOrigin: getOrigin(c.url),
        indexedAt: new Date().toISOString(),
        pageCount: 0,
        pages: [],
      });
    }
  }

  await browser.close();

  const out = {
    targetMarket: list.targetMarket,
    indexedAt: new Date().toISOString(),
    sites: indexes,
  };
  fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2), 'utf-8');
  console.log(`\nWrote ${OUT_PATH}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
