/**
 * Research online sales channels for USA ceremonial cacao competitors.
 * For each brand: shop discovery, product page, cart, checkout flow (no purchase).
 * Output: sales_channel_analysis.json + sales_channel_analysis.md
 *
 * Run: npx ts-node research_sales_channels.ts
 */

const { chromium } = require('@playwright/test');
import * as fs from 'fs';
import * as path from 'path';

const LIST_PATH = path.join(__dirname, '..', 'competitors_list.json');
const OUT_JSON = path.join(__dirname, '..', 'sales_channel_analysis.json');
const OUT_MD = path.join(__dirname, '..', 'sales_channel_analysis.md');

const NAV_TIMEOUT = 35000;
const HEADLESS = process.env.HEADLESS !== '0';

interface Competitor {
  name: string;
  url: string;
  region: string;
  notes?: string;
}

interface SalesChannelResult {
  name: string;
  baseUrl: string;
  crawledAt: string;
  error?: string;
  platform?: string;
  homepageLoadMs?: number;
  shopUrl?: string;
  shopDiscoverable?: boolean;
  productListing?: {
    url: string;
    productLinksCount: number;
    loadMs: number;
  };
  productPage?: {
    url: string;
    title: string | null;
    priceVisible: boolean;
    priceText: string | null;
    addToCartVisible: boolean;
    addToCartText: string | null;
    hasDescription: boolean;
    imageCount: number;
    loadMs: number;
  };
  cart?: {
    url: string;
    reachable: boolean;
    itemCount?: number;
    checkoutButtonVisible: boolean;
    loadMs: number;
  };
  checkout?: {
    reachable: boolean;
    stepsOrSections: string[];
    paymentMethodsMentioned: string[];
    trustSignals: string[];
    requiredFieldsSample: string[];
    loadMs: number;
  };
  working: string[];
  notWorking: string[];
}

function normalizeUrl(url: string): string {
  const u = url.replace(/\/+$/, '');
  return u.startsWith('http') ? u : `https://${u}`;
}

async function researchOne(
  browser: any,
  competitor: Competitor,
  index: number,
  total: number
): Promise<SalesChannelResult> {
  const baseUrl = normalizeUrl(competitor.url);
  const result: SalesChannelResult = {
    name: competitor.name,
    baseUrl,
    crawledAt: new Date().toISOString(),
    working: [],
    notWorking: [],
  };

  const page = await browser.newPage();
  page.setDefaultTimeout(NAV_TIMEOUT);

  try {
    // --- Homepage ---
    const t0 = Date.now();
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
    result.homepageLoadMs = Date.now() - t0;

    // Platform detection
    const platform = await page.evaluate(() => {
      const html = document.documentElement.outerHTML;
      if (html.includes('Shopify') || html.includes('shopify.com') || document.querySelector('[data-shopify]')) return 'Shopify';
      if (html.includes('woocommerce') || document.querySelector('.woocommerce')) return 'WooCommerce';
      if (html.includes('bigcommerce')) return 'BigCommerce';
      if (html.includes('squarespace')) return 'Squarespace';
      if (html.includes('wix.com')) return 'Wix';
      return null;
    });
    result.platform = platform || 'Unknown';

    // Find shop / products link
    const shopLink = await page.evaluate((origin: string) => {
      const links = Array.from(document.querySelectorAll('a[href]'));
      const hrefs = links.map((a) => (a.getAttribute('href') || '').trim());
      const text = links.map((a) => (a.textContent || '').toLowerCase());
      const shopKeywords = ['shop', 'store', 'products', 'buy', 'cacao', 'chocolate', 'collections'];
      for (let i = 0; i < hrefs.length; i++) {
        const h = hrefs[i];
        if (!h || h.startsWith('#') || h.startsWith('mailto:') || h.startsWith('tel:')) continue;
        const full = h.startsWith('http') ? h : new URL(h, origin).href;
        if (!full.startsWith(origin) && !full.includes(new URL(origin).hostname)) continue;
        const t = text[i];
        if (shopKeywords.some((k) => t.includes(k) || full.toLowerCase().includes(k))) {
          return full;
        }
      }
      // Fallback: common paths
      for (const p of ['/pages/shop-all', '/shop', '/collections/all', '/collections/cacao', '/products', '/shop-all']) {
        const u = origin + p;
        if (hrefs.some((h) => h === p || h === u || h.endsWith(p))) return origin + p;
      }
      return null;
    }, baseUrl);

    if (shopLink) {
      result.shopUrl = shopLink;
      result.shopDiscoverable = true;
      result.working.push('Shop link discoverable from homepage');
    } else {
      result.notWorking.push('Shop link not easily discoverable from homepage');
    }

    // --- Product listing ---
    const listingUrl = shopLink || `${baseUrl}/collections/all`;
    const t1 = Date.now();
    const listResp = await page.goto(listingUrl, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => null);
    const listLoadMs = Date.now() - t1;

    if (listResp && listResp.ok()) {
      const listInfo = await page.evaluate(() => {
        const productLinks = Array.from(document.querySelectorAll('a[href*="/products/"], a[href*="/product/"], a[href*="/collections/"]'));
        const hrefs = productLinks.map((a) => a.getAttribute('href')).filter(Boolean) as string[];
        const unique = [...new Set(hrefs)];
        return { productLinksCount: unique.length, sample: unique.slice(0, 5) };
      });
      result.productListing = {
        url: listingUrl,
        productLinksCount: listInfo.productLinksCount,
        loadMs: listLoadMs,
      };
      if (listInfo.productLinksCount > 0) {
        result.working.push(`Product listing has ${listInfo.productLinksCount} product links`);
      } else {
        result.notWorking.push('No product links found on listing page');
      }

      // --- First product page ---
      let productUrl: string | null = await page.evaluate(() => {
        const a = document.querySelector('a[href*="/products/"], a[href*="/product/"]') as HTMLAnchorElement;
        return a ? a.href : null;
      });
      if (!productUrl && listInfo.sample && listInfo.sample[0]) {
        productUrl = listInfo.sample[0].startsWith('http') ? listInfo.sample[0] : new URL(listInfo.sample[0], baseUrl).href;
      }
      if (productUrl) {
        const t2 = Date.now();
        await page.goto(productUrl, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
        const productLoadMs = Date.now() - t2;

        const productInfo = await page.evaluate(() => {
          const title = document.querySelector('h1')?.textContent?.trim() || document.querySelector('[data-product-title]')?.textContent?.trim() || null;
          const priceEl = document.querySelector('[data-product-price], .price, .product-price, [class*="price"]');
          const priceText = priceEl?.textContent?.trim() || null;
          const priceVisible = !!priceText && priceText.length > 0 && priceText.length < 50;
          const addToCart = document.querySelector('button[name="add"], [type="submit"][value="Add"], [data-add-to-cart], .add-to-cart, [class*="add-to-cart"]');
          const addToCartVisible = !!addToCart;
          const addToCartText = addToCart?.textContent?.trim() || null;
          const desc = document.querySelector('[data-product-description], .product-description, .product__description, [class*="description"]');
          const hasDescription = !!(desc?.textContent?.trim() && desc.textContent!.trim().length > 50);
          const images = document.querySelectorAll('img[src*="product"], .product__media img, [data-product-image] img, .product-gallery img');
          return {
            title,
            priceText,
            priceVisible,
            addToCartVisible,
            addToCartText: addToCartText ? addToCartText.slice(0, 80) : null,
            hasDescription,
            imageCount: images.length,
          };
        });

        result.productPage = {
          url: productUrl,
          title: productInfo.title,
          priceVisible: productInfo.priceVisible,
          priceText: productInfo.priceText,
          addToCartVisible: productInfo.addToCartVisible,
          addToCartText: productInfo.addToCartText,
          hasDescription: productInfo.hasDescription,
          imageCount: productInfo.imageCount,
          loadMs: productLoadMs,
        };

        if (productInfo.addToCartVisible) result.working.push('Add to cart CTA visible on product page');
        else result.notWorking.push('Add to cart not found on product page');
        if (productInfo.priceVisible) result.working.push('Price visible');
        else result.notWorking.push('Price not clearly visible');
        if (productInfo.hasDescription) result.working.push('Product description present');
      }
    } else {
      result.notWorking.push('Product listing page failed to load or not found');
    }

    // --- Cart ---
    const cartUrls = [
      baseUrl + '/cart',
      baseUrl + '/cart.php',
      baseUrl + '/bag',
      new URL('/cart', baseUrl).href,
    ];
    let cartReachable = false;
    let cartLoadMs = 0;
    let cartCheckoutVisible = false;
    let cartItemCount: number | undefined;

    for (const cartUrl of cartUrls) {
      const t3 = Date.now();
      const cartResp = await page.goto(cartUrl, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => null);
      cartLoadMs = Date.now() - t3;
      if (cartResp && cartResp.ok()) {
        const cartInfo = await page.evaluate(() => {
          const checkoutBtn = document.querySelector('button[name="checkout"], a[href*="checkout"], [data-checkout], input[value*="Checkout"]');
          const items = document.querySelectorAll('[data-cart-item], .cart-item, .line-item, tr.cart__row');
          return {
            checkoutButtonVisible: !!checkoutBtn,
            itemCount: items.length,
          };
        });
        cartReachable = true;
        result.cart = {
          url: cartUrl,
          reachable: true,
          itemCount: cartInfo.itemCount,
          checkoutButtonVisible: cartInfo.checkoutButtonVisible,
          loadMs: cartLoadMs,
        };
        cartCheckoutVisible = cartInfo.checkoutButtonVisible;
        cartItemCount = cartInfo.itemCount;
        result.working.push('Cart page reachable');
        if (cartInfo.checkoutButtonVisible) result.working.push('Checkout button visible on cart');
        else result.notWorking.push('Checkout CTA not obvious on cart');
        break;
      }
    }
    if (!cartReachable) {
      result.cart = { url: cartUrls[0], reachable: false, checkoutButtonVisible: false, loadMs: 0 };
      result.notWorking.push('Cart URL not reachable or 404');
    }

    // --- Checkout (do not submit) ---
    if (cartReachable && cartCheckoutVisible) {
      const checkoutLink = await page.evaluate(() => {
        const a = document.querySelector('a[href*="checkout"]');
        return a ? (a as HTMLAnchorElement).href : null;
      });
      if (checkoutLink) {
        const t4 = Date.now();
        const checkResp = await page.goto(checkoutLink, { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => null);
        const checkoutLoadMs = Date.now() - t4;
        if (checkResp && checkResp.ok()) {
          const checkoutInfo = await page.evaluate(() => {
            const steps = Array.from(document.querySelectorAll('[data-step], .step, .checkout-step, h2, .section__title')).map((e) => e.textContent?.trim()).filter(Boolean) as string[];
            const body = document.body.innerText || '';
            const paymentKeywords = ['card', 'credit', 'debit', 'paypal', 'apple pay', 'google pay', 'amazon pay', 'klarna', 'afterpay', 'venmo'];
            const paymentMethodsMentioned = paymentKeywords.filter((k) => body.toLowerCase().includes(k));
            const trustKeywords = ['secure', 'ssl', 'encrypted', 'safe', 'guarantee', 'refund', 'trust'];
            const trustSignals = trustKeywords.filter((k) => body.toLowerCase().includes(k));
            const labels = Array.from(document.querySelectorAll('label, [for]')).map((e) => e.textContent?.trim()).filter(Boolean).slice(0, 15);
            return {
              stepsOrSections: steps.slice(0, 10),
              paymentMethodsMentioned: [...new Set(paymentMethodsMentioned)],
              trustSignals: [...new Set(trustSignals)],
              requiredFieldsSample: labels.slice(0, 12),
            };
          });
          result.checkout = {
            reachable: true,
            stepsOrSections: checkoutInfo.stepsOrSections,
            paymentMethodsMentioned: checkoutInfo.paymentMethodsMentioned,
            trustSignals: checkoutInfo.trustSignals,
            requiredFieldsSample: checkoutInfo.requiredFieldsSample,
            loadMs: checkoutLoadMs,
          };
          result.working.push('Checkout page reachable');
          if (checkoutInfo.paymentMethodsMentioned.length > 0) result.working.push(`Payment options indicated: ${checkoutInfo.paymentMethodsMentioned.join(', ')}`);
          if (checkoutInfo.trustSignals.length > 0) result.working.push(`Trust signals: ${checkoutInfo.trustSignals.join(', ')}`);
        } else {
          result.checkout = { reachable: false, stepsOrSections: [], paymentMethodsMentioned: [], trustSignals: [], requiredFieldsSample: [], loadMs: 0 };
          result.notWorking.push('Checkout page did not load');
        }
      }
    }
  } catch (e) {
    result.error = e instanceof Error ? e.message : String(e);
    result.notWorking.push(`Error: ${result.error}`);
  } finally {
    await page.close();
  }

  return result;
}

function writeMarkdown(results: SalesChannelResult[]): string {
  const lines: string[] = [
    '# Online Sales Channel Analysis — USA Ceremonial Cacao Competitors',
    '',
    'Detailed research on online sales channels for the 5 competitor brands. Generated by Playwright.',
    '',
    '---',
    '',
  ];

  for (const r of results) {
    lines.push(`## ${r.name}`);
    lines.push('');
    lines.push(`- **URL:** ${r.baseUrl}`);
    lines.push(`- **Platform (detected):** ${r.platform || 'Unknown'}`);
    if (r.homepageLoadMs != null) lines.push(`- **Homepage load:** ${r.homepageLoadMs}ms`);
    if (r.error) {
      lines.push(`- **Error:** ${r.error}`);
      lines.push('');
      lines.push('### What\'s not working');
      lines.push('');
      lines.push('- Site or critical page failed to load.');
      lines.push('');
      continue;
    }
    lines.push('');
    lines.push('### What\'s working');
    lines.push('');
    for (const w of r.working) lines.push(`- ${w}`);
    if (r.working.length === 0) lines.push('- (None captured)');
    lines.push('');
    lines.push('### What\'s not working');
    lines.push('');
    for (const n of r.notWorking) lines.push(`- ${n}`);
    if (r.notWorking.length === 0) lines.push('- (None captured)');
    lines.push('');
    if (r.productPage) {
      lines.push('### Product page snapshot');
      lines.push('');
      lines.push(`- Product URL: ${r.productPage.url}`);
      lines.push(`- Title: ${r.productPage.title || '—'}`);
      lines.push(`- Price visible: ${r.productPage.priceVisible}; Price: ${r.productPage.priceText || '—'}`);
      lines.push(`- Add to cart visible: ${r.productPage.addToCartVisible} (${r.productPage.addToCartText || '—'})`);
      lines.push(`- Description: ${r.productPage.hasDescription}; Images: ${r.productPage.imageCount}`);
      lines.push('');
    }
    if (r.cart?.reachable) {
      lines.push('### Cart');
      lines.push('');
      lines.push(`- Checkout button visible: ${r.cart.checkoutButtonVisible}`);
      lines.push('');
    }
    if (r.checkout?.reachable) {
      lines.push('### Checkout (pre-payment)');
      lines.push('');
      lines.push(`- Payment methods mentioned: ${r.checkout.paymentMethodsMentioned.join(', ') || '—'}`);
      lines.push(`- Trust signals: ${r.checkout.trustSignals.join(', ') || '—'}`);
      lines.push('');
    }
    lines.push('---');
    lines.push('');
  }

  lines.push('## Summary comparison');
  lines.push('');
  lines.push('| Brand | Platform | Shop discoverable | Add to cart | Cart | Checkout |');
  lines.push('|-------|----------|-------------------|-------------|------|----------|');
  for (const r of results) {
    const shop = r.shopDiscoverable ? 'Yes' : 'No';
    const atc = r.productPage?.addToCartVisible ? 'Yes' : 'No';
    const cart = r.cart?.reachable ? 'Yes' : 'No';
    const co = r.checkout?.reachable ? 'Yes' : 'No';
    lines.push(`| ${r.name} | ${r.platform || '—'} | ${shop} | ${atc} | ${cart} | ${co} |`);
  }
  lines.push('');
  return lines.join('\n');
}

async function main() {
  const list = JSON.parse(fs.readFileSync(LIST_PATH, 'utf-8'));
  const competitors: Competitor[] = list.competitors || [];
  if (competitors.length === 0) {
    console.log('No competitors in competitors_list.json.');
    process.exit(0);
  }

  console.log(`Researching ${competitors.length} competitors (sales channels)...\n`);
  const browser = await chromium.launch({ headless: HEADLESS });

  const results: SalesChannelResult[] = [];
  for (let i = 0; i < competitors.length; i++) {
    const c = competitors[i];
    console.log(`[${i + 1}/${competitors.length}] ${c.name} — ${c.url}`);
    const r = await researchOne(browser, c, i, competitors.length);
    results.push(r);
    console.log(`  Working: ${r.working.length}, Not working: ${r.notWorking.length}`);
  }

  await browser.close();

  const out = {
    targetMarket: list.targetMarket,
    researchedAt: new Date().toISOString(),
    results,
  };
  fs.writeFileSync(OUT_JSON, JSON.stringify(out, null, 2), 'utf-8');
  console.log(`\nWrote ${OUT_JSON}`);

  const md = writeMarkdown(results);
  fs.writeFileSync(OUT_MD, md, 'utf-8');
  console.log(`Wrote ${OUT_MD}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
