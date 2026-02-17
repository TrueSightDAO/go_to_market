/**
 * Step 3: Crawl each competitor URL and extract title, meta description, h1, main content snippets.
 * Reads competitors_list.json, writes competitor_analysis.json.
 * Run: npx ts-node crawl_competitors.ts
 */

const { chromium } = require('@playwright/test');
import * as fs from 'fs';
import * as path from 'path';

const LIST_PATH = path.join(__dirname, '..', 'competitors_list.json');
const OUT_PATH = path.join(__dirname, '..', 'competitor_analysis.json');

interface Competitor {
  name: string;
  url: string;
  region: string;
  notes?: string;
}

interface CrawlResult {
  url: string;
  name: string;
  title: string | null;
  metaDescription: string | null;
  h1: string | null;
  h2s: string[];
  mainSnippet: string | null;
  wordCount: number;
  error?: string;
  crawledAt: string;
}

async function crawlUrl(url: string, name: string): Promise<CrawlResult> {
  const headless = process.env.HEADLESS !== '0';
  const browser = await chromium.launch({ headless });
  const result: CrawlResult = {
    url,
    name,
    title: null,
    metaDescription: null,
    h1: null,
    h2s: [],
    mainSnippet: null,
    wordCount: 0,
    crawledAt: new Date().toISOString(),
  };

  try {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });

    result.title = await page.evaluate(() => document.title || null);
    result.metaDescription = await page.evaluate(() => {
      const el = document.querySelector('meta[name="description"]');
      return el ? (el.getAttribute('content') || null) : null;
    });
    result.h1 = await page.evaluate(() => {
      const h1 = document.querySelector('h1');
      return h1 ? h1.textContent?.trim() || null : null;
    });
    result.h2s = await page.evaluate(() => {
      const h2s = Array.from(document.querySelectorAll('h2'));
      return h2s.map((h) => h.textContent?.trim()).filter(Boolean) as string[];
    });

    const mainContent = await page.evaluate(() => {
      const main = document.querySelector('main') || document.querySelector('article') || document.querySelector('[role="main"]') || document.body;
      const text = main.innerText || '';
      const paragraphs = text.split(/\n\n+/).map((p) => p.trim()).filter((p) => p.length > 80);
      return paragraphs.slice(0, 2).join(' ');
    });
    result.mainSnippet = mainContent.length > 0 ? mainContent.slice(0, 800) : null;
    result.wordCount = (result.mainSnippet || '').split(/\s+/).length;
  } catch (e) {
    result.error = e instanceof Error ? e.message : String(e);
  } finally {
    await browser.close();
  }
  return result;
}

async function main() {
  const list = JSON.parse(fs.readFileSync(LIST_PATH, 'utf-8'));
  const competitors: Competitor[] = list.competitors || [];
  if (competitors.length === 0) {
    console.log('No competitors in competitors_list.json. Run search_competitors.ts or add URLs manually.');
    process.exit(0);
  }

  const results: CrawlResult[] = [];
  for (let i = 0; i < competitors.length; i++) {
    const c = competitors[i];
    console.log(`[${i + 1}/${competitors.length}] ${c.name} - ${c.url}`);
    const r = await crawlUrl(c.url, c.name);
    results.push(r);
  }

  const out = {
    targetMarket: list.targetMarket,
    crawledAt: new Date().toISOString(),
    results,
  };
  fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2), 'utf-8');
  console.log(`Wrote ${OUT_PATH}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
