/**
 * Brand-focused research: what is driving sales for each of the top 5 USA
 * ceremonial cacao brands? Each brand is the starting point; they may sell
 * on their site, Amazon, other retailers, wholesale, etc.
 *
 * Reads: competitors_brands_top5.json
 * Writes: brand_sales_drivers.json, brand_sales_drivers_report.md
 *
 * Run: npx ts-node research_brand_sales_drivers.ts
 */

const { chromium } = require('@playwright/test');
import * as fs from 'fs';
import * as path from 'path';

const BRANDS_PATH = path.join(__dirname, '..', 'competitors_brands_top5.json');
const OUT_JSON = path.join(__dirname, '..', 'brand_sales_drivers.json');
const OUT_MD = path.join(__dirname, '..', 'brand_sales_drivers_report.md');

const NAV_TIMEOUT = 40000;
const HEADLESS = process.env.HEADLESS !== '0';

interface Brand {
  name: string;
  primaryUrl: string;
  aliases: string[];
  region: string;
  notes?: string;
}

interface BrandResearch {
  brandName: string;
  primaryUrl: string;
  researchedAt: string;
  error?: string;
  ownSite?: {
    loadOk: boolean;
    shopUrl?: string;
    wholesaleUrl?: string;
    retailersStockistsUrl?: string;
    subscriptionOffered: boolean;
    freeShippingThreshold?: string;
    keyMessaging: string[];
    platform?: string;
  };
  searchWhereToBuy?: {
    searchQuery: string;
    snippetMentions: string[];
    retailerNames: string[];
  };
  searchAmazon?: {
    searchQuery: string;
    foundOnAmazon: boolean;
    snippetOrNote: string;
  };
  salesDrivers: string[];
  gapsOrRisks: string[];
}

function normalizeUrl(url: string): string {
  const u = url.replace(/\/+$/, '');
  return u.startsWith('http') ? u : `https://${u}`;
}

async function researchBrand(browser: any, brand: Brand, index: number, total: number): Promise<BrandResearch> {
  const baseUrl = normalizeUrl(brand.primaryUrl);
  const result: BrandResearch = {
    brandName: brand.name,
    primaryUrl: baseUrl,
    researchedAt: new Date().toISOString(),
    salesDrivers: [],
    gapsOrRisks: [],
  };

  const page = await browser.newPage();
  page.setDefaultTimeout(NAV_TIMEOUT);

  try {
    // --- Own site: homepage + key pages ---
    const t0 = Date.now();
    const homeResp = await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => null);
    const loadOk = !!homeResp && homeResp.ok();

    if (loadOk) {
      result.ownSite = {
        loadOk: true,
        keyMessaging: [],
        subscriptionOffered: false,
      };

      const platform = await page.evaluate(() => {
        const html = document.documentElement.outerHTML;
        if (html.includes('Shopify') || html.includes('shopify.com')) return 'Shopify';
        if (html.includes('bigcommerce')) return 'BigCommerce';
        if (html.includes('woocommerce')) return 'WooCommerce';
        return undefined;
      });
      result.ownSite.platform = platform;

      const links = await page.evaluate((origin: string) => {
        const as = Array.from(document.querySelectorAll('a[href]'));
        const out: { href: string; text: string }[] = [];
        for (const a of as) {
          const href = (a.getAttribute('href') || '').trim();
          const text = (a.textContent || '').trim().toLowerCase();
          if (!href || href.startsWith('#') || href.startsWith('mailto:')) continue;
          const full = href.startsWith('http') ? href : new URL(href, origin).href;
          if (!full.startsWith(origin) && !full.includes(new URL(origin).hostname)) continue;
          out.push({ href: full, text });
        }
        return out;
      }, baseUrl);

      const shopLink = links.find((l: { href: string; text: string }) => l.text.includes('shop') || l.text.includes('store') || l.text.includes('buy') || l.href.includes('/shop') || l.href.includes('/collections'));
      if (shopLink) {
        result.ownSite.shopUrl = shopLink.href;
        result.salesDrivers.push('Own site has clear shop / store link');
      }

      const wholesaleLink = links.find((l: { href: string; text: string }) => l.text.includes('wholesale') || l.text.includes('trade') || l.text.includes('b2b') || l.href.includes('wholesale'));
      if (wholesaleLink) {
        result.ownSite.wholesaleUrl = wholesaleLink.href;
        result.salesDrivers.push('Wholesale / B2B channel on own site');
      }

      const retailersLink = links.find((l: { href: string; text: string }) => l.text.includes('retailer') || l.text.includes('stockist') || l.text.includes('where to buy') || l.text.includes('find us'));
      if (retailersLink) {
        result.ownSite.retailersStockistsUrl = retailersLink.href;
        result.salesDrivers.push('Retailers / stockists page (drives in-store and multi-channel visibility)');
      }

      const bodyText = await page.evaluate(() => document.body.innerText || '');
      const subMatch = bodyText.match(/subscription|subscribe\s*(&|and)\s*save|recurring|subscribe\s*to\s*save/i);
      if (subMatch) {
        result.ownSite.subscriptionOffered = true;
        result.salesDrivers.push('Subscription / subscribe & save on own site');
      }

      const shipMatch = bodyText.match(/free\s*shipping\s*(on\s*orders?\s*over\s*\$?\s*(\d+)|[\s\S]{0,30}\$(\d+))/i) || bodyText.match(/\$(\d+)[\s\S]{0,40}free\s*ship/i);
      if (shipMatch) {
        const amount = shipMatch[2] || shipMatch[3] || shipMatch[1];
        result.ownSite.freeShippingThreshold = `$${amount}`;
        result.salesDrivers.push(`Free shipping threshold (e.g. over $${amount})`);
      }

      if (bodyText.toLowerCase().includes('organic')) result.ownSite.keyMessaging.push('Organic');
      if (bodyText.toLowerCase().includes('ceremonial')) result.ownSite.keyMessaging.push('Ceremonial');
      if (bodyText.toLowerCase().includes('single origin') || bodyText.toLowerCase().includes('single-origin')) result.ownSite.keyMessaging.push('Single origin');
      if (bodyText.toLowerCase().includes('regenerative')) result.ownSite.keyMessaging.push('Regenerative');
      if (bodyText.toLowerCase().includes('direct trade') || bodyText.toLowerCase().includes('directly traded')) result.ownSite.keyMessaging.push('Direct trade');
    } else {
      result.ownSite = { loadOk: false, keyMessaging: [], subscriptionOffered: false };
      result.gapsOrRisks.push('Own site did not load or returned error');
    }

    // --- Search: "[Brand] where to buy" / "buy [Brand]" ---
    const searchBrand = brand.aliases[0] || brand.name.split('/')[0].trim();
    const searchQuery = `${searchBrand} ceremonial cacao buy`;
    await page.goto(`https://duckduckgo.com/?q=${encodeURIComponent(searchQuery)}`, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => null);

    const searchSnippets = await page.evaluate(() => {
      const results = Array.from(document.querySelectorAll('[data-result], .result, article, .web-result'));
      return results.map((r) => (r.textContent || '').slice(0, 400)).filter((t) => t.length > 50);
    });
    const retailerNames: string[] = [];
    const fullSearchText = searchSnippets.join(' ').toLowerCase();
    if (fullSearchText.includes('amazon')) retailerNames.push('Amazon');
    if (fullSearchText.includes('bar and cocoa') || fullSearchText.includes('barandcocoa')) retailerNames.push('Bar and Cocoa');
    if (fullSearchText.includes('whole foods')) retailerNames.push('Whole Foods');
    if (fullSearchText.includes('thrive') || fullSearchText.includes('thrivemarket')) retailerNames.push('Thrive Market');
    if (fullSearchText.includes('iherb')) retailerNames.push('iHerb');
    if (fullSearchText.includes('etsy')) retailerNames.push('Etsy');
    if (fullSearchText.includes('ebay')) retailerNames.push('eBay');

    result.searchWhereToBuy = {
      searchQuery,
      snippetMentions: searchSnippets.slice(0, 5),
      retailerNames: [...new Set(retailerNames)],
    };
    if (retailerNames.length > 0) result.salesDrivers.push(`Appears in search alongside retailers: ${retailerNames.join(', ')}`);

    // --- Search: "[Brand] Amazon" ---
    const amazonQuery = `${searchBrand} Amazon`;
    await page.goto(`https://duckduckgo.com/?q=${encodeURIComponent(amazonQuery)}`, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => null);
    const amazonSnippet = await page.evaluate(() => {
      const first = document.querySelector('[data-result], .result, article');
      return first ? (first.textContent || '').slice(0, 500) : '';
    });
    const foundOnAmazon = amazonSnippet.toLowerCase().includes('amazon') && (amazonSnippet.toLowerCase().includes(brand.name.toLowerCase().split('/')[0]) || amazonSnippet.toLowerCase().includes('ora') || amazonSnippet.toLowerCase().includes('cacao'));
    result.searchAmazon = {
      searchQuery: amazonQuery,
      foundOnAmazon,
      snippetOrNote: foundOnAmazon ? 'Brand or product appears in Amazon-related search results' : amazonSnippet.slice(0, 200) || 'No clear Amazon presence in first result',
    };
    if (foundOnAmazon) result.salesDrivers.push('Presence on or associated with Amazon (discovery & sales)');
    else result.gapsOrRisks.push('No clear Amazon presence in search');

  } catch (e) {
    result.error = e instanceof Error ? e.message : String(e);
    result.gapsOrRisks.push(`Research error: ${result.error}`);
  } finally {
    await page.close();
  }

  return result;
}

function writeReport(results: BrandResearch[]): string {
  const lines: string[] = [
    '# Brand Sales Drivers Report — Top 5 USA Ceremonial Cacao Competitors',
    '',
    'Research focus: **what is obviously driving sales** for each brand. The brand is the starting point; each may sell on their own site and on multiple other online channels (Amazon, retailers, wholesale).',
    '',
    '---',
    '',
  ];

  for (const r of results) {
    lines.push(`## ${r.brandName}`);
    lines.push('');
    lines.push(`- **Primary URL:** ${r.primaryUrl}`);
    lines.push(`- **Researched:** ${r.researchedAt}`);
    if (r.error) {
      lines.push(`- **Error:** ${r.error}`);
      lines.push('');
      continue;
    }
    lines.push('');
    lines.push('### What appears to be driving sales');
    lines.push('');
    for (const d of r.salesDrivers) lines.push(`- ${d}`);
    if (r.salesDrivers.length === 0) lines.push('- (Could not determine from this research pass.)');
    lines.push('');
    lines.push('### Gaps / risks');
    lines.push('');
    for (const g of r.gapsOrRisks) lines.push(`- ${g}`);
    if (r.gapsOrRisks.length === 0) lines.push('- (None noted.)');
    lines.push('');
    if (r.ownSite?.loadOk) {
      lines.push('### Own site');
      lines.push('');
      if (r.ownSite.shopUrl) lines.push(`- Shop: ${r.ownSite.shopUrl}`);
      if (r.ownSite.wholesaleUrl) lines.push(`- Wholesale: ${r.ownSite.wholesaleUrl}`);
      if (r.ownSite.retailersStockistsUrl) lines.push(`- Retailers / stockists: ${r.ownSite.retailersStockistsUrl}`);
      if (r.ownSite.subscriptionOffered) lines.push('- Subscription / subscribe & save: Yes');
      if (r.ownSite.freeShippingThreshold) lines.push(`- Free shipping threshold: ${r.ownSite.freeShippingThreshold}`);
      if (r.ownSite.keyMessaging.length) lines.push(`- Key messaging: ${r.ownSite.keyMessaging.join(', ')}`);
      if (r.ownSite.platform) lines.push(`- Platform: ${r.ownSite.platform}`);
      lines.push('');
    }
    if (r.searchWhereToBuy && r.searchWhereToBuy.retailerNames.length) {
      lines.push('### Appears alongside (search)');
      lines.push('');
      lines.push(r.searchWhereToBuy.retailerNames.join(', '));
      lines.push('');
    }
    if (r.searchAmazon?.foundOnAmazon) {
      lines.push('### Amazon');
      lines.push('');
      lines.push('Brand or products appear in Amazon-related search results.');
      lines.push('');
    }
    lines.push('---');
    lines.push('');
  }

  lines.push('## Summary: What’s driving sales across the 5 brands');
  lines.push('');
  lines.push('| Brand | Own site shop | Wholesale | Retailers page | Subscription | Free ship | Amazon / other retail visibility |');
  lines.push('|-------|---------------|-----------|-----------------|--------------|-----------|-----------------------------------|');
  for (const r of results) {
    const shop = r.ownSite?.shopUrl ? 'Yes' : 'No';
    const wholesale = r.ownSite?.wholesaleUrl ? 'Yes' : 'No';
    const retailers = r.ownSite?.retailersStockistsUrl ? 'Yes' : 'No';
    const sub = r.ownSite?.subscriptionOffered ? 'Yes' : 'No';
    const ship = r.ownSite?.freeShippingThreshold || '—';
    const other = r.searchAmazon?.foundOnAmazon || (r.searchWhereToBuy?.retailerNames.length ?? 0) > 0 ? 'Yes' : 'No';
    lines.push(`| ${r.brandName} | ${shop} | ${wholesale} | ${retailers} | ${sub} | ${ship} | ${other} |`);
  }
  lines.push('');
  lines.push('---');
  lines.push('');
  lines.push('## Suggestions for Agroverse.shop');
  lines.push('');
  lines.push('Based on what is driving sales for the top 5 competitors, here are concrete actions Agroverse can take:');
  lines.push('');
  const drivers = results.flatMap((r) => r.salesDrivers);
  const hasWholesale = results.some((r) => r.ownSite?.wholesaleUrl);
  const hasRetailers = results.some((r) => r.ownSite?.retailersStockistsUrl);
  const hasSub = results.some((r) => r.ownSite?.subscriptionOffered);
  const hasFreeShip = results.filter((r) => r.ownSite?.freeShippingThreshold).length;
  const amazonPresence = results.filter((r) => r.searchAmazon?.foundOnAmazon).length;
  lines.push('1. **Own site as flagship** — Every brand leads with their site. Ensure agroverse.shop has a clear Shop/Products path, fast load, and mobile-friendly checkout.');
  lines.push('2. **Wholesale / B2B** — Competitors use dedicated wholesale or trade pages. Consider a clear Wholesale or For Retailers page with contact or application flow.');
  lines.push('3. **Where to buy / Stockists** — Brands that list retailers or stockists gain trust and multi-channel visibility. Add a “Find us” or “Stockists” page and keep it updated.');
  lines.push('4. **Subscription** — Subscription and “subscribe & save” are common. If inventory allows, offer a subscription option on key SKUs to match and capture recurring revenue.');
  lines.push('5. **Free shipping threshold** — Promote a clear free-shipping threshold (e.g. over $X) on homepage and cart to reduce drop-off.');
  lines.push('6. **Multi-channel presence** — Several competitors appear on Amazon or other retailers. Evaluate listing on Amazon (or a curated retailer like Bar and Cocoa) for discovery and sales, while keeping agroverse.shop as the primary brand home.');
  lines.push('7. **Messaging** — Emphasize organic, ceremonial, single-origin, regenerative, and direct/farm traceability consistently on site and in any retailer listings.');
  lines.push('8. **Site reliability** — One competitor (Ora) had load issues in past research; ensure agroverse.shop is fast and stable so the brand is always reachable.');
  lines.push('');
  lines.push('---');
  lines.push('');
  return lines.join('\n');
}

async function main() {
  const data = JSON.parse(fs.readFileSync(BRANDS_PATH, 'utf-8'));
  const brands: Brand[] = data.brands || [];
  if (brands.length === 0) {
    console.log('No brands in competitors_brands_top5.json.');
    process.exit(0);
  }

  console.log(`Researching ${brands.length} brands (sales drivers, multi-channel)...\n`);
  const browser = await chromium.launch({ headless: HEADLESS });

  const results: BrandResearch[] = [];
  for (let i = 0; i < brands.length; i++) {
    const b = brands[i];
    console.log(`[${i + 1}/${brands.length}] ${b.name} — ${b.primaryUrl}`);
    const r = await researchBrand(browser, b, i, brands.length);
    results.push(r);
    console.log(`  Sales drivers: ${r.salesDrivers.length}, Gaps: ${r.gapsOrRisks.length}`);
  }

  await browser.close();

  const out = {
    targetMarket: data.targetMarket,
    researchedAt: new Date().toISOString(),
    brands: data.brands,
    results,
  };
  fs.writeFileSync(OUT_JSON, JSON.stringify(out, null, 2), 'utf-8');
  console.log(`\nWrote ${OUT_JSON}`);

  const md = writeReport(results);
  fs.writeFileSync(OUT_MD, md, 'utf-8');
  console.log(`Wrote ${OUT_MD}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
