# Physical Stores Market Research

Complete guide for identifying, contacting, and partnering with physical retail stores for Agroverse ceremonial cacao products.

## 📁 Directory Structure

```
physical_stores/
├── README.md                          # This file (consolidated documentation)
├── data/                              # Hit List CSV data and backups
├── generate_shop_list.py              # Generate shop list from research
├── generate_shop_list_la_route.py     # Generate LA route shop list
├── route_optimizer.py                # Optimize visit routes
├── pull_hit_list.py                   # Pull latest data from Google Sheets
├── process_dapp_remarks.py            # Process DApp remarks into Hit List
├── extract_remarks_data.py            # Extract structured data from remarks
├── record_dapp_submission.py          # Record DApp submissions
├── create_followup_events.py          # Create Google Calendar follow-up events
├── find_nearby_stores.gs             # Google Apps Script for nearby stores API
├── shop_list_sf_to_quartzite.csv     # Route-specific shop list
└── [Documentation files - see below]
```

## 🎯 Overview

This directory contains all tools, scripts, and documentation for managing physical store partnerships. The workflow includes:

1. **Research & Targeting** - Identify potential partner stores
2. **Data Management** - Maintain Hit List in Google Sheets
3. **Store Visits** - In-person approach protocol
4. **Email Outreach** - Pre/post-visit communication
5. **Route Optimization** - Plan efficient visit routes
6. **Follow-up Management** - Track and schedule follow-ups

## 📊 Google Sheets Integration

**Spreadsheet ID:** `1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc`

**Key Worksheets:**
- **Hit List** - Main store database with status, contact info, notes
- **DApp Remarks** - Status updates and remarks from stores_nearby.html DApp

**Service Account:** `agroverse-market-research@get-data-io.iam.gserviceaccount.com`

## 🔧 Key Scripts

### `backup_hit_list_and_remarks.py`
**Recommended:** Backup both Hit List and DApp Remarks from Google Sheets to local CSV files:
```bash
cd physical_stores
source ../venv/bin/activate  # Activate virtual environment
python3 backup_hit_list_and_remarks.py
```

This script downloads:
- **Hit List** - Main store database with status, contact info, notes
- **DApp Remarks** - Status updates and remarks from stores_nearby.html DApp

Files are saved to:
- `data/hit_list.csv`
- `data/dapp_remarks.csv`

Existing files are automatically backed up with timestamps before overwriting.

### `pull_hit_list.py`
Pull the latest Hit List from Google Sheets to local CSV (Hit List only):
```bash
cd physical_stores
source ../venv/bin/activate  # Activate virtual environment
python3 pull_hit_list.py
```

### `process_dapp_remarks.py`
Process unprocessed DApp remarks and apply to Hit List:
```bash
python3 process_dapp_remarks.py              # Process all pending
python3 process_dapp_remarks.py --dry-run   # Preview changes
```

### `extract_remarks_data.py`
Extract structured data (phone, email, address, etc.) from remarks:
```bash
python3 extract_remarks_data.py <submission_id>
python3 extract_remarks_data.py 5f15fb03-cb19-4983-8d94-31be4e9a3956 --dry-run
```

### `create_followup_events.py`
Create Google Calendar events from Follow Up Date column:
```bash
python3 create_followup_events.py
```

### `generate_shop_list.py`
Generate shop list from research and sync to Google Sheets.

### `route_optimizer.py`
Optimize visit routes for efficiency.

## 🎯 Partner Targeting Strategy

### Target Shop Profile

**Must Have:**
- ✅ Focus on **100% chocolate or ceremonial cacao**
- ✅ Values alignment: regenerative, ethical sourcing, sustainability
- ✅ Community-focused or consciousness-oriented
- ✅ Retail space or product display capability

**Ideal Characteristics:**
- 🌟 Spiritual/metaphysical theme
- 🌟 Wellness/health focus
- 🌟 Boutique/premium positioning
- 🌟 Local/community hub
- 🌟 Conscious consumer base
- 🌟 **Tibetan prayer flags or Buddha statues** - Strong indicator of spiritual/meditation focus

**Exclude:**
- ❌ Mass market chocolate retailers
- ❌ Conventional grocery stores
- ❌ Places without retail capability
- ❌ No alignment with regenerative/ethical values
- ❌ **Shops that ONLY sell crystals/stones** (need broader product mix)
- ❌ **Shops that ONLY sell candles** (single-product focus)
- ❌ **Shops without food permit** (if required by local regulations)

### Successful Partner Categories

1. **Spiritual/Metaphysical Shops** - Love of Ganesha (SF), The Enchanted Forest Boutique
2. **Wellness Centers & Yoga Studios** - Green Gulch Farm Zen Center, Soulfulness Breath
3. **Boutique Chocolatiers** - Kiki's Cocoa (SF)
4. **Conscious Cafes & Restaurants** - Republic Cafe & Ming Lounge, Miss Tomato
5. **Tech/Innovation Hubs** (Secondary) - Block71 Silicon Valley, Hacker Dojo
6. **Unique/Lifestyle Spaces** - The Ponderosa, Slab City

## 📍 Route-Based Targeting

### Route Planning Framework

1. **Identify Cities Along Route** - Use Google Maps
2. **Research by City** - Search for metaphysical shops, spiritual stores, wellness centers
3. **Verify Potential Partners** - Use verification checklist
4. **Order by Route** - Sort shops by city in driving order

### Example Routes

**Route 1: SF → Quartzite (Direct)**
- Cities: SF → Oakland → Stockton → Modesto → Fresno → Bakersfield → Mojave → Barstow → Needles → Kingman → Lake Havasu → Parker → Quartzsite

**Route 2: SF → LA → Slab City → Quartzite**
- High-priority areas: Los Angeles, Santa Barbara, San Luis Obispo, Palm Springs, Quartzsite

## ✅ Verification Checklist

**Critical Exclusions:**
- ❌ Crystal/Stone-Only Shops (unless they sell other products too)
- ❌ Candle-Only Shops (unless they sell other products too)
- ❌ Shops Without Food Permits (where required)

**Verification Steps:**
1. **Product Mix Check** - Shop sells multiple product categories
2. **Food Permit Check** - Verify if shop can sell food/beverage products
3. **Values Alignment** - Regenerative/ethical sourcing, community focus
4. **Retail Capability** - Has retail space, can display products
5. **General Quality** - Address verified, website checked, not already a partner

## 💰 Sales Process & Pricing

### Key Insight: Pricing is the Real Barrier

Based on actual sales conversations:
- **Venue fit is good** - Shops are interested in the product
- **Sales process is the issue** - Consignment vs. purchase, markup requirements

### Consignment vs. Outright Purchase

**Option 1: Consignment**
- Pros: Lower risk for shop, no upfront cash
- Cons: Shop may want higher margins, you hold inventory risk
- When to use: New relationships, test market

**Option 2: Outright Purchase**
- Pros: Cash upfront, shop committed to selling
- Cons: Shop takes inventory risk
- When to use: Established relationships, proven demand
- Example: Love of Ganesha accepted this

**Recommendation:** Offer both options - start with whichever shop prefers

### Markup Requirements

**100% Markup Formula:**
- Shop sells at: $12
- Shop needs to buy at: $6 (allows 100% markup)

**50% Markup Formula:**
- Shop sells at: $12
- Shop needs to buy at: $8 (allows 50% markup)

**Calculation:**
```
Retail Price = Wholesale Price × (1 + Markup %)
```

### Sales Approach Template

1. **Introduce Product** - "We offer 100% ceremonial cacao, regenerative farming, direct from Brazilian farmers"
2. **Offer Options** - "We can work with consignment or outright purchase - whichever you prefer"
3. **Ask About Markup** - "What markup do you typically need? We can structure pricing to accommodate"
4. **Calculate Pricing** - Show the math transparently
5. **Be Flexible** - Adjust pricing structure based on their needs

## 🚪 Store Visit Protocol

### Pre-Visit Preparation

**Research (15-30 minutes):**
- [ ] Check store hours (Google Maps, Yelp, website)
- [ ] Review store's website/social media
- [ ] Note store owner/manager name
- [ ] Identify parking options
- [ ] Review product mix (verify not crystal-only or candle-only)
- [ ] Check if they have food permit

**Prepare Materials:**
- [ ] Product sample (small amount in sealed container)
- [ ] Business cards
- [ ] Product information sheet
- [ ] Pricing sheet
- [ ] Phone (for photos, notes, Google Maps)
- [ ] Notebook (for immediate notes)

### During Visit

**Opening Approach:**
- Enter naturally, browse for 30-60 seconds
- Observe the space, identify decision-maker
- Approach respectfully: "Hi, I'm [Name] from Agroverse. We make ceremonial cacao from regenerative farms in Brazil. I'm wondering if you might be interested in carrying our products. Is the owner or manager available?"

**Core Pitch (2-5 minutes):**
1. **Introduction (30 seconds)** - Who you are, what you do
2. **Why It Fits (30-60 seconds)** - Tailor to their store type
3. **Show Product (1-2 minutes)** - Sample or photos
4. **Values Alignment (30 seconds)** - Direct farmer relationships, regenerative practices

**Pricing Discussion:**
- Ask first: "What markup do you typically need?"
- Offer both: Consignment and purchase
- Calculate together: Show the math transparently
- Be flexible: "We're flexible on pricing structure"

### Post-Visit Actions (Do Immediately)

**Within 5 Minutes:**
1. **Take Notes** - Store name, contact, response, key points, follow-up needed
2. **Update Google Sheet** - Mark status, add visit date, outcome notes, sales process notes
3. **Take Photos** - Storefront, product placement ideas, business cards

**Follow-Up Actions:**
- **If Interested:** Send email within 24 hours, send product info, offer sample delivery
- **If Needs Time:** Send brief email, leave materials, set calendar reminder
- **If Rejected:** Update status, note reason, thank them for time

## 📧 Email Outreach Strategy

### When to Use Email

**Best Use Cases:**
1. **Pre-Visit Warm-Up** (1-2 weeks before visit) - Higher success rate
2. **Post-Visit Follow-Up** (within 24 hours) - Maintains momentum
3. **Distant Stores** - Can't visit in person
4. **Re-Engagement** (3-6 months later) - Reopens conversations
5. **Referral Follow-Up** - Mention referral source

**Avoid:**
- ❌ First contact for local stores (in-person better)
- ❌ Mass blasts without personalization
- ❌ Too frequent (spam territory)

### Email Best Practices

**Subject Lines:**
- ✅ Personal and specific: "Partnership opportunity: [Store Name]"
- ✅ Clear value: "Ceremonial cacao for spiritual shops"
- ✅ Referral: "[Name] suggested I reach out"
- ❌ Avoid: Generic, spammy, too long, all caps

**Personalization:**
- Always personalize: Store name, owner/manager name, specific thing about their store, their values/products, how you found them
- Research before sending: Check website, review social media, note product mix

**Timing:**
- Best Days: Tuesday-Thursday
- Best Times: 9-11 AM or 2-3 PM
- Time Zone: Send in their time zone
- Avoid: Monday (busy), Friday (weekend mode), early morning, late evening

**Length:**
- Keep it short: 100-200 words for initial outreach
- 50-100 words for follow-ups
- Use bullet points for clarity

**Clear Call-to-Action:**
- Good: "Would you be open to a 15-minute call?"
- Good: "Would [Date/Time] work for a brief meeting?"
- Avoid: "Let me know if you're interested" (too vague)

### Follow-Up Sequences

**Cold Outreach (No Response):**
- Email 1: Day 0 (initial)
- Email 2: Day 7 (gentle follow-up)
- Email 3: Day 14 (final try)
- After 3: Stop, move on

**Post-Visit Follow-Up:**
- Email 1: Day 0 (within 24 hours)
- Email 2: Day 7-10 (check-in)
- Email 3: Day 14-21 (final follow-up)

### Email Templates

See `EMAIL_OUTREACH_STRATEGY.md` for complete templates:
- Pre-visit warm-up
- Post-visit follow-up (interested)
- Post-visit follow-up (needs time)
- Cold outreach (distant stores)
- Re-engagement
- Referral follow-up

## 🗺️ Route Optimization

### Multi-Trip Approach (Recommended)

**Trip 1: Bay Area Loop** (2-3 days)
- SF → East Bay → South Bay → SF
- Advantage: Dense concentration, minimal backtracking

**Trip 2: Central Valley + Desert** (3-4 days)
- I-5 South → Desert Route
- Advantage: Natural highway progression

**Trip 3: Coastal Route** (2-3 days)
- Monterey → Big Sur → SLO → Santa Barbara → LA
- Advantage: Beautiful route, logical progression

**Trip 4: LA + Desert + Arizona** (4-5 days)
- LA → Palm Springs → Slab City → Quartzsite
- Advantage: Single continuous route, no backtracking

### Clustering Within Cities

**Geographic Proximity:**
- Use Google Maps to identify store clusters
- Group visits by neighborhood/street
- Example: In SF, visit all Mission District stores together

**Priority-Based Clustering:**
- Visit HIGH priority stores first
- Allows flexibility to skip low-priority if needed

**Time-of-Day Optimization:**
- Morning: Research-intensive stores
- Afternoon: Confirmed addresses and hours
- Late afternoon: Quick drop-ins

### Route Optimization Tools

**Option A: Manual Google Maps**
1. Create custom Google Map with all store locations
2. Use "Directions" with multiple stops
3. Drag stops to reorder for optimal route

**Option B: Automated Route Optimization**
- Use `route_optimizer.py` (if available)
- Calculates actual driving times
- Finds optimal visit order
- Accounts for traffic patterns

## 📱 DApp Remarks Workflow

### Capturing Remarks

1. From the DApp (`stores_nearby.html`), expand a store card
2. Choose the **Remarks** textarea
3. Pick any status (including **Shortlisted**)
4. Optionally enter notes
5. Click **Update Status**

The DApp calls the Apps Script endpoint, which:
- Updates the Hit List status immediately
- Logs the submission in the `DApp Remarks` sheet with a unique ID and timestamps

### Resolving Remarks

Run the helper script to merge stored remarks into the Hit List:

```bash
python3 process_dapp_remarks.py
```

**What the script does:**
- Reads all rows in `DApp Remarks` where **Processed != "Yes"**
- Finds the matching shop in the Hit List
- Updates the status (if present)
- Appends the remark to `Sales Process Notes` with a timestamp and submitter
- Stamps `Processed = Yes` and sets `Processed At`

**Dry run mode:**
```bash
python3 process_dapp_remarks.py --dry-run
```

### Extracting Structured Data

Use `extract_remarks_data.py` to extract structured information (phone, email, address, contact person, follow-up date) from remarks:

```bash
python3 extract_remarks_data.py <submission_id> --dry-run
```

## 📋 Google Calendar Integration

### Follow-Up Events

The `create_followup_events.py` script creates Google Calendar events from the `Follow Up Date` column:

```bash
python3 create_followup_events.py
```

**Setup Requirements:**
1. Share the target Google Calendar with the service account:
   - `agroverse-market-research@get-data-io.iam.gserviceaccount.com`
   - Grant at least "Make changes to events" permission
2. Set the environment variable `GOOGLE_CALENDAR_ID` to the calendar's ID:
   ```bash
   export GOOGLE_CALENDAR_ID="your-calendar-id@group.calendar.google.com"
   ```
   Or create a `.env` file in the repository root:
   ```
   GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
   ```

**Format:** `YYYY-MM-DD HH:MM` or `YYYY-MM-DD HH:MM-HH:MM` (for time ranges)

**Example:**
- `Earth Impact → 2025-11-13 10:00` (call Stephanie at 10 AM)
- `Go Ask Alice → 2025-11-14 11:00` (in-store pop-in)

**Features:**
- The script is idempotent—re-running it updates existing events rather than duplicating them
- Generates deterministic event IDs based on shop name and date
- Default timezone: `America/Los_Angeles` (can be overridden with `DEFAULT_TIMEZONE` env var)
- Creates events for all rows with a "Follow Up Date" value

## 🎯 Key Messaging Points

**Always Emphasize:**
1. **Product Quality** - 100% ceremonial cacao, single-origin from Brazil, no additives
2. **Sourcing Story** - Direct relationships with farmers (Oscar, Paulo, Vivi), regenerative farming practices, plant trees with every purchase
3. **Values Alignment** - Ethical sourcing, community impact, Amazon rainforest regeneration
4. **Use Cases** - Ceremonial circles, intention-setting, heart-opening practices, group rituals
5. **Flexibility** - Offer both consignment and purchase, flexible pricing structure, work with markup requirements

## 📊 Success Metrics to Track

**After Each Visit:**
- Response level (High interest / Thinking / Not interested / Rejected)
- Pricing discussion (What markup they need)
- Preferred model (Consignment / Purchase / Undecided)
- Follow-up needed (When, what)
- Learnings (What worked, what to improve)

**Track in Google Sheet:**
- Visit Date
- Outcome
- Sales Process Notes
- Follow Up Date
- Status (Visited/Contacted/Partnered/Rejected)

## 🚨 Common Mistakes to Avoid

**Don't:**
- ❌ Oversell - Let them show interest first
- ❌ Interrupt - If they're helping customers, wait
- ❌ Push pricing - If they're not interested, don't force it
- ❌ Forget to listen - Their needs matter more than your pitch
- ❌ Skip follow-up - Always update your sheet and follow up
- ❌ Take rejection personally - It's business, not personal
- ❌ Forget to ask for referrals - Even if they say no

**Do:**
- ✅ Be respectful - Of their time, space, customers
- ✅ Be genuine - Show real interest in their store
- ✅ Be flexible - Adapt to their needs
- ✅ Be prepared - Know your product, pricing, values
- ✅ Be persistent but not pushy - Follow up appropriately
- ✅ Be transparent - Honest about pricing, structure
- ✅ Be patient - Sales take time, relationships matter
- ✅ Be grateful - Thank them for their time, always

## 💡 Pro Tips

1. **First impressions matter** - Be confident, friendly, respectful
2. **Listen more than talk** - Understand their needs first
3. **Be flexible** - Every shop is different
4. **Follow up promptly** - Within 24 hours if they're interested
5. **Track everything** - Notes help you learn and improve
6. **Build relationships** - Even if they say no now, they might refer you
7. **Learn from each visit** - What worked? What didn't?
8. **Stay positive** - Rejections are part of the process

## 🔄 Continuous Improvement

**After Each Day of Visits:**
- Review what worked
- Note what didn't
- Adjust approach for next day
- Update your pitch based on feedback
- Refine your materials if needed

**Remember:** Every visit is a learning opportunity. Even rejections teach you something.

---

*Last updated: November 2025*
*This README consolidates all physical stores documentation for easy reference by Cursor AI*
