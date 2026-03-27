/**
 * Research apothecaries and metaphysical shops for ceremonial cacao Hit List.
 * Uses Playwright to scrape Google Maps and Yelp (with throttling).
 * Focus: CA, AZ, OR, WA. Filters for Instagram presence.
 *
 * Run: npx ts-node research_apothecaries.ts
 * Env: HEADLESS=0 for visible browser, YELP_MAX_PAGES=2 to limit Yelp (default 2)
 */

const { chromium } = require('@playwright/test');
import * as fs from 'fs';
import * as path from 'path';

const OUT_JSON = path.join(__dirname, '..', 'apothecary_discovery.json');
const OUT_CSV = path.join(__dirname, '..', 'apothecary_discovery.csv');

const NAV_TIMEOUT = 25000;
const HEADLESS = process.env.HEADLESS !== '0';
const YELP_MAX_PAGES = parseInt(process.env.YELP_MAX_PAGES || '2', 10);
// REGIONS=TX,NY to run only Austin + Rochester areas; omit to run all states
const REGIONS_FILTER = process.env.REGIONS ? process.env.REGIONS.split(',').map((s) => s.trim().toUpperCase()) : null;

const STATES = [
  { state: 'CA', cities: ['San Francisco', 'Los Angeles', 'Oakland', 'Santa Cruz'] },
  { state: 'AZ', cities: ['Phoenix', 'Tucson', 'Sedona'] },
  { state: 'OR', cities: ['Portland', 'Eugene', 'Ashland'] },
  { state: 'WA', cities: ['Seattle', 'Tacoma', 'Olympia'] },
  { state: 'TX', cities: ['Austin', 'Round Rock', 'Cedar Park', 'Georgetown'] },
  { state: 'NY', cities: ['Rochester', 'Henrietta', 'Brighton', 'Pittsford'] },
];

const JUNK_NAMES = ['results', 'suggest an edit', 'add a missing place', 'see all', 'view all', 'directions', 'save', 'share', 'nearby', 'search', 'sponsored'];
function isJunkName(name: string): boolean {
  const n = (name || '').trim().toLowerCase();
  return !n || n.length < 2 || JUNK_NAMES.some((j) => n === j || n.startsWith(j));
}

function hasValidAddress(addr: string): boolean {
  const a = (addr || '').trim();
  return a.length >= 10 && /\d/.test(a);
}

function cleanAddress(addr: string): string {
  return (addr || '').replace(/^[\uE000-\uF8FF\s]+/, '').trim();
}

interface DiscoveredStore {
  shopName: string;
  address: string;
  city: string;
  state: string;
  phone?: string;
  website?: string;
  email?: string;
  instagram?: string;
  instagramFollowers?: string;
  latitude?: string;
  longitude?: string;
  shopType: string;
  source: string;
  storeKey: string;
}

function parseCoordsFromGoogleMapsUrl(url: string): { lat: string; lng: string } | null {
  const m = url.match(/!3d(-?\d+\.?\d*)!4d(-?\d+\.?\d*)/);
  if (m) return { lat: m[1], lng: m[2] };
  const n = url.match(/@(-?\d+\.?\d*),(-?\d+\.?\d*)/);
  if (n) return { lat: n[1], lng: n[2] };
  return null;
}

async function geocodeAddress(address: string, city: string, state: string): Promise<{ lat: string; lng: string } | null> {
  const q = encodeURIComponent(`${address}, ${city}, ${state}`);
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1`,
      { headers: { 'User-Agent': 'Agroverse-HitList/1.0' } }
    );
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) {
      return { lat: String(data[0].lat), lng: String(data[0].lon) };
    }
  } catch {
    /* ignore */
  }
  return null;
}

function toStoreKey(name: string, address: string, city: string, state: string): string {
  const slug = (s: string) => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return `${slug(name)}__${slug(address)}__${slug(city)}__${state.toLowerCase()}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function randomDelay(minMs: number, maxMs: number): Promise<void> {
  return sleep(minMs + Math.random() * (maxMs - minMs));
}

function extractInstagram(text: string, links: string[]): string | undefined {
  // Prefer explicit Instagram links (handle only, no trailing path)
  for (const link of links) {
    const m = link.match(/instagram\.com\/([a-zA-Z0-9_.]+)(?:\/|$|\?)/i);
    if (m) return m[1];
  }
  const t = text.match(/instagram\.com\/([a-zA-Z0-9_.]+)/i);
  if (t) return t[1];
  return undefined;
}

async function extractInstagramFromPage(page: any): Promise<string | undefined> {
  const links = await page.$$eval('a[href*="instagram"]', (as: HTMLAnchorElement[]) =>
    as.map((a) => a.href)
  );
  const handle = extractInstagram('', links);
  if (handle) return handle;
  const bodyText = await page.evaluate(() => document.body.innerText);
  const allLinks = await page.$$eval('a[href]', (as: HTMLAnchorElement[]) => as.map((a) => a.href));
  return extractInstagram(bodyText, allLinks);
}

async function extractInstagramFromWebsite(page: any, url: string): Promise<string | undefined> {
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 12000 });
    await sleep(2000);
    const links = await page.$$eval('a[href*="instagram"]', (as: HTMLAnchorElement[]) =>
      as.map((a) => a.href)
    );
    return extractInstagram('', links);
  } catch {
    return undefined;
  }
}

async function fetchInstagramFollowers(page: any, handle: string): Promise<string | undefined> {
  const clean = (handle || '').replace(/^@/, '').trim();
  if (!clean) return undefined;
  try {
    await page.goto(`https://www.instagram.com/${clean}/`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    await sleep(3000);
    const html = await page.content();
    const m = html.match(/"edge_followed_by":\s*\{\s*"count":\s*(\d+)/);
    if (m) return m[1];
    const text = await page.evaluate(() => document.body.innerText);
    const fm = text.match(/([\d,.]+[KkMm]?)\s*followers?/);
    if (fm) return fm[1].trim();
  } catch {
    // ignore
  }
  return undefined;
}

async function searchGoogleMaps(page: any, term: string, city: string, state: string): Promise<DiscoveredStore[]> {
  const results: DiscoveredStore[] = [];
  const query = encodeURIComponent(`${term} ${city} ${state}`);
  const url = `https://www.google.com/maps/search/${query}`;

  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
    await sleep(2500);

    const items = await page.$$('a[href*="/maps/place/"]');
    const seen = new Set<string>();

    for (let i = 0; i < Math.min(items.length, 8); i++) {
      try {
        const href = await items[i].getAttribute('href');
        if (!href || seen.has(href)) continue;
        seen.add(href);
        await items[i].click();
        await sleep(1800);

        const nameEl = await page.$('h1');
        let name = nameEl ? (await nameEl.textContent())?.trim() || '' : '';
        if (isJunkName(name)) {
          const websiteEl = await page.$('a[data-item-id="authority"]');
          const website = websiteEl ? await websiteEl.getAttribute('href') : undefined;
          if (website) {
            try {
              const host = new URL(website).hostname.replace(/^www\./, '');
              name = host.split('.')[0].replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
            } catch {
              /* ignore */
            }
          }
        }
        if (!name || isJunkName(name)) continue;

        const addressEl = await page.$('[data-item-id="address"]');
        const address = cleanAddress(addressEl ? (await addressEl.textContent())?.trim() : '');
        if (!hasValidAddress(address)) continue;
        const phoneEl = await page.$('a[data-item-id^="phone"]');
        const phone = phoneEl ? (await phoneEl.textContent())?.trim() : undefined;
        const websiteEl = await page.$('a[data-item-id="authority"]');
        const website = websiteEl ? await websiteEl.getAttribute('href') : undefined;

        const instagram = await extractInstagramFromPage(page);

        const cityMatch = address?.match(/,?\s*([^,]+),\s*([A-Z]{2})\s*\d/);
        const parsedCity = cityMatch ? cityMatch[1].trim() : city;
        const parsedState = cityMatch ? cityMatch[2] : state;

        let coords: { lat: string; lng: string } | null = parseCoordsFromGoogleMapsUrl(page.url());
        if (!coords) coords = await geocodeAddress(address || '', parsedCity, parsedState);
        if (coords) await sleep(1100);

        results.push({
          shopName: name,
          address: address || '',
          city: parsedCity,
          state: parsedState,
          phone,
          website,
          instagram: instagram ? `@${instagram}` : undefined,
          latitude: coords?.lat,
          longitude: coords?.lng,
          shopType: 'Metaphysical/Spiritual',
          source: 'google_maps',
          storeKey: toStoreKey(name, address || '', parsedCity, parsedState),
        });
      } catch {
        // skip
      }
    }
  } catch (e) {
    console.warn(`Google Maps failed for ${term} ${city} ${state}:`, (e as Error).message);
  }
  return results;
}

async function searchYelp(page: any, term: string, location: string): Promise<DiscoveredStore[]> {
  const results: DiscoveredStore[] = [];
  const baseUrl = `https://www.yelp.com/search?find_desc=${encodeURIComponent(term)}&find_loc=${encodeURIComponent(location)}`;

  for (let p = 0; p < YELP_MAX_PAGES; p++) {
    const url = p === 0 ? baseUrl : `${baseUrl}&start=${p * 10}`;
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
      await randomDelay(4000, 8000);

      const cards = await page.$$('a[href*="/biz/"]');
      const seen = new Set<string>();

      for (const card of cards) {
        const href = await card.getAttribute('href');
        if (!href || !href.includes('/biz/') || seen.has(href)) continue;
        seen.add(href);

        try {
          await card.click();
          await randomDelay(2000, 4000);

          const nameEl = await page.$('h1');
          const name = nameEl ? (await nameEl.textContent())?.trim() : '';
          if (!name || isJunkName(name)) continue;

          const addressEl = await page.$('address');
          const address = cleanAddress(addressEl ? (await addressEl.textContent())?.trim().replace(/\s+/g, ' ') : '');
          if (!hasValidAddress(address)) continue;
          const phoneEl = await page.$('a[href^="tel:"]');
          const phone = phoneEl ? (await phoneEl.textContent())?.trim() : undefined;
          const websiteEl = await page.$('a[href*="biz_redir"]');
          const website = websiteEl ? await websiteEl.getAttribute('href') : undefined;

          const instagram = await extractInstagramFromPage(page);

          const cityMatch = address?.match(/,?\s*([^,]+),\s*([A-Z]{2})\s*\d/);
          const parsedCity = cityMatch ? cityMatch[1].trim() : '';
          const parsedState = cityMatch ? cityMatch[2] : '';

          const coords = await geocodeAddress(address || '', parsedCity, parsedState);
          if (coords) await sleep(1100);

          results.push({
            shopName: name,
            address: address || '',
            city: parsedCity,
            state: parsedState,
            phone,
            website,
            instagram: instagram ? `@${instagram}` : undefined,
            latitude: coords?.lat,
            longitude: coords?.lng,
            shopType: 'Metaphysical/Spiritual',
            source: 'yelp',
            storeKey: toStoreKey(name, address || '', parsedCity, parsedState),
          });
        } catch {
          // skip
        }
      }
    } catch (e) {
      console.warn(`Yelp failed for ${term} ${location} page ${p}:`, (e as Error).message);
    }
    if (p < YELP_MAX_PAGES - 1) await randomDelay(5000, 10000);
  }
  return results;
}

function toCsvRow(s: DiscoveredStore): string[] {
  return [
    s.shopName,
    'Research',
    'Medium',
    s.address,
    s.city,
    s.state,
    s.shopType,
    s.phone || '',
    s.website || '',
    s.email || '',
    s.instagram || '',
    '',
    '', '', '', '', '', '', '', '', '', '', '', // Notes through Sales Process Notes
    s.latitude || '',
    s.longitude || '',
    '', '', // Status Updated By, Date
    s.instagramFollowers || '',
    s.storeKey,
  ];
}

function escapeCsv(val: string): string {
  if (val.includes(',') || val.includes('"')) return `"${val.replace(/"/g, '""')}"`;
  return val;
}

async function main() {
  const allStores: DiscoveredStore[] = [];
  const seenKeys = new Set<string>();

  const browser = await chromium.launch({ headless: HEADLESS });

  const page = await browser.newPage();
  page.setDefaultTimeout(NAV_TIMEOUT);
  await page.setViewportSize({ width: 1280, height: 800 });

  const statesToRun = REGIONS_FILTER
    ? STATES.filter((s) => REGIONS_FILTER.includes(s.state))
    : STATES;
  if (statesToRun.length === 0) {
    console.error('No states match REGIONS filter:', process.env.REGIONS);
    process.exit(1);
  }
  console.log('Searching Google Maps...', REGIONS_FILTER ? `(regions: ${REGIONS_FILTER.join(', ')})` : '(all regions)');
  for (const { state, cities } of statesToRun) {
    for (const city of cities.slice(0, 2)) {
      const term = 'apothecary metaphysical';
      console.log(`  ${term} in ${city}, ${state}`);
      const stores = await searchGoogleMaps(page, term, city, state);
      for (const s of stores) {
        if (!seenKeys.has(s.storeKey)) {
          seenKeys.add(s.storeKey);
          allStores.push(s);
        }
      }
      await randomDelay(2000, 4000);
    }
  }

  console.log('Searching Yelp (throttled)...');
  const yelpPage = await browser.newPage();
  yelpPage.setDefaultTimeout(NAV_TIMEOUT);
  for (const { state, cities } of statesToRun) {
    for (const city of cities.slice(0, 2)) {
      const location = `${city}, ${state}`;
      console.log(`  apothecary in ${location}`);
      const stores = await searchYelp(yelpPage, 'apothecary', location);
      for (const s of stores) {
        if (!seenKeys.has(s.storeKey)) {
          seenKeys.add(s.storeKey);
          allStores.push(s);
        }
      }
    }
  }

  await page.close();
  await yelpPage.close();

  const needInstagram = allStores.filter((s) => !s.instagram && s.website);
  if (needInstagram.length > 0) {
    console.log(`Checking ${needInstagram.length} store websites for Instagram...`);
    const webPage = await browser.newPage();
    webPage.setDefaultTimeout(12000);
    for (const s of needInstagram) {
      if (s.website) {
        const ig = await extractInstagramFromWebsite(webPage, s.website);
        if (ig) s.instagram = `@${ig}`;
        await randomDelay(1500, 3000);
      }
    }
    await webPage.close();
  }

  const withInstagram = allStores.filter((s) => s.instagram);
  if (withInstagram.length > 0) {
    console.log(`Fetching Instagram follower counts for ${withInstagram.length} stores...`);
    const igPage = await browser.newPage();
    igPage.setDefaultTimeout(15000);
    for (const s of withInstagram) {
      const handle = (s.instagram || '').replace(/^@/, '');
      if (handle) {
        const count = await fetchInstagramFollowers(igPage, handle);
        if (count) s.instagramFollowers = count;
        await randomDelay(3000, 6000);
      }
    }
    await igPage.close();
  }

  await browser.close();

  console.log(`\nTotal: ${allStores.length}, With Instagram: ${withInstagram.length}`);

  const out = {
    discoveredAt: new Date().toISOString(),
    total: allStores.length,
    withInstagram: withInstagram.length,
    stores: allStores,
  };
  fs.writeFileSync(OUT_JSON, JSON.stringify(out, null, 2), 'utf-8');
  console.log(`Wrote ${OUT_JSON}`);

  const header = [
    'Shop Name', 'Status', 'Priority', 'Address', 'City', 'State', 'Shop Type',
    'Phone', 'Website', 'Email', 'Instagram', 'Notes',
    'Contact Date', 'Contact Method', 'Follow Up Date', 'Contact Person', 'Owner Name',
    'Referral', 'Product Interest', 'Follow Up Event Link', 'Visit Date', 'Outcome',
    'Sales Process Notes', 'Latitude', 'Longitude', 'Status Updated By', 'Status Updated Date',
    'Instagram Follow Count', 'Store Key',
  ];
  const csvRows = [header.join(','), ...allStores.map((s) => toCsvRow(s).map(escapeCsv).join(','))];
  fs.writeFileSync(OUT_CSV, csvRows.join('\n'), 'utf-8');
  console.log(`Wrote ${OUT_CSV}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
