# Hit List — Credentials & Setup

**Playbook (interim):** Retail / consignment outreach stages and human-in-the-loop follow-up workflow are documented in **`agentic_ai_context/PARTNER_OUTREACH_PROTOCOL.md`** (evidence: Email Agent Training Data, Follow Up tab, this sheet).

## Spreadsheet

- **URL:** https://docs.google.com/spreadsheets/d/1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc/edit
- **ID:** `1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc`
- **Tab:** Hit List (or first sheet)

## How to Enable Editing via Code

### Option A: Service Account (recommended for automation)

1. **Share the spreadsheet** with the service account:
   - Email: `agroverse-market-research@get-data-io.iam.gserviceaccount.com` (from market_research/google_credentials.json)
   - Role: **Editor**
   - In Google Sheets: Share -> Add people -> paste email -> Editor

2. **Use the service account JSON** at:
   - `market_research/google_credentials.json` (already used by pull_from_sheets.py)

3. **Enable Google Sheets API** in the Google Cloud project `get-data-io`:
   - https://console.cloud.google.com/apis/library/sheets.googleapis.com?project=get-data-io

### Option B: OAuth2 (interactive, user-owned)

1. Create OAuth 2.0 credentials in Google Cloud Console (Desktop app)
2. Save as `credentials.json` in this directory
3. First run will open browser for consent; token cached for reuse

## Field agent location — **Recent Field Agent Location** → Places → Hit List

**Tab:** **`Recent Field Agent Location`** on the same spreadsheet (`gid=881847228`).

1. **DApp → GAS:** Signed **`stores_nearby.html`** attaches **`save_location=true`** + **`digital_signature`** on the normal store-search **`GET`** (throttled in **`localStorage`**, ~24h; page query **`save_location=true`** forces intent for testing). **Stores Nearby** web app: `tokenomics/clasp_mirrors/1NpHrKJW8Q4suu6-f5gXQcbjHqUZtGOG-KcIf81M1GG8lDShm5-fLphD2/Code.js` — **`clasp push`** then **Deploy → New version** for `/exec` to pick up changes.
2. **Row shape:** Row 1 must be **`Logged At` | `Latitude` | `Longitude` | `Digital Signature` | `Location ID` | `Status`**. New pings append with **`Status` = `pending`**.
3. **Automation:** **`scripts/field_agent_location_places_pull.py`** — processes **`pending`**; skips a new Places pull if another **`pulled`** row is within **20 miles** and **24 hours** (override with **`--dedupe-miles`** / **`--dedupe-hours`**, or **`--no-recent-dedupe`**); otherwise **Places Nearby** + dedupe → append **Hit List** (**Research**); sets **`pulled`** or **`ignored because already pulled`**; appends a summary row to **DApp Remarks** (Processed = Yes).
4. **CI:** **`.github/workflows/field_agent_location_places_pull.yml`** — `workflow_dispatch` + schedule; secrets **`GOOGLE_CREDENTIALS_JSON`**, **`GOOGLE_MAPS_API_KEY`** (or **`GOOGLE_PLACES_API_KEY`**).

**CLI:**

```bash
cd market_research
python3 scripts/field_agent_location_places_pull.py --dry-run --limit 3
python3 scripts/field_agent_location_places_pull.py --limit 10
```

Cross-links: **`agentic_ai_context/DAPP_PAGE_CONVENTIONS.md`** §14 (*Field agent location*), **`tokenomics/SCHEMA.md`** §4.

---

## Research queue — Google Places + Grok photo review

Rows with **Status = Research** are the default input for **`scripts/hit_list_research_photo_review.py`** (see also **`agentic_ai_context/WORKSPACE_CONTEXT.md`** — bullets under *Hit List — Status = Research*).

1. **Places:** find + details + download up to **5** listing photos (`maxwidth` 1200). Requires **`GOOGLE_MAPS_API_KEY`** (server-usable key) in **`market_research/.env`**.
2. **Vision:** **Grok** returns JSON → suggested status **`AI: Shortlisted`**, **`AI: Photo rejected`**, or **`AI: Photo needs review`** (`GROK_API_KEY`).
3. **DApp Remarks:** append a row; column **Remarks** (D) is **plain text with blank lines** between sections (Location, Google Places review, bullet lists, model summary) so operators can enable **wrap** in Sheets and read it like mini memo.
4. **Hit List:** status and **Sales Process Notes** updated in one pass (same semantics as **`physical_stores/process_dapp_remarks.py`**), and the new **DApp Remarks** row is marked **Processed**.

**CLI:** `python3 scripts/hit_list_research_photo_review.py --limit 5` · one shop: `--shop "Naturales Elementa Apothecary"`. **`--dry-run`** prints the **Remarks** preview without writing.

**GitHub Actions:** `.github/workflows/hit_list_research_photo_review.yml` — **hourly** schedule (UTC) with default **20** shops when not using `workflow_dispatch`; manual runs can set a different **`limit`**. Secrets (repo **Actions**): **`GOOGLE_CREDENTIALS_JSON`**, **`GOOGLE_MAPS_API_KEY`**, **`GROK_API_KEY`**. (`GMAIL_TOKEN_JSON` is only for Gmail sync workflows.)

## Bulk discovery — append `Research` rows (Google Places Nearby)

**Script:** `scripts/discover_apothecaries_la_hit_list.py` (multi-region; filename is historical).

**What it does:** Runs [Nearby Search](https://developers.google.com/maps/documentation/places/web-service/search-nearby) from several **centroids** per metro (radius up to **50 km** per Google), keyword default **`apothecary`**, dedupes by **`place_id`**, excludes obvious pharmacies / mall beauty / cannabis via **`should_exclude`**, constrains to a **lat/lng bounding box** and **state** (default **CA**), loads [Place Details](https://developers.google.com/maps/documentation/places/web-service/details) for survivors, then **appends** rows to the **Hit List** tab with **Status = Research**, **Priority = Low**, and **Notes** containing `Auto-discovered (Google Places Nearby, <region label>). place_id: …` for dedupe and audit.

**Credentials (local):**

- **`GOOGLE_MAPS_API_KEY`** or **`GOOGLE_PLACES_API_KEY`** in **`market_research/.env`** (server/IP–allowed key with Places enabled).
- **`google_credentials.json`** — service account with **Editor** on the spreadsheet (same as other Hit List automation).

**CLI:**

```bash
cd market_research
python3 scripts/discover_apothecaries_la_hit_list.py --region la --dry-run
python3 scripts/discover_apothecaries_la_hit_list.py --region sf_bay --dry-run
python3 scripts/discover_apothecaries_la_hit_list.py --region sf_bay --max-new 200
python3 scripts/discover_apothecaries_la_hit_list.py --region i5_corridor --max-new 400
python3 scripts/discover_apothecaries_la_hit_list.py --region ca_hwy_101 --max-new 400
python3 scripts/discover_apothecaries_la_hit_list.py --region ca_i280 --max-new 150
```

**California Hwy 101 / I-280** — presets **`ca_hwy_101`** (San Diego metro → Crescent City along the 101 corridor) and **`ca_i280`** (San Francisco south through the Peninsula to San Jose). Same Nearby + Details flow, **CA-only** bbox; existing Hit List dedupe applies. Optional one-shot + Instagram:  
`python3 scripts/discover_apothecaries_i5_pipeline.py --region ca_hwy_101 --max-new 400 --instagram-limit 200`.

**I-5 corridor (San Diego → Seattle)** — region preset **`i5_corridor`**: multi-centroid Nearby search along **CA / OR / WA** with a west-coast bounding box and **`allowed_states`**. One-shot discovery + optional Instagram pass: **`python3 scripts/discover_apothecaries_i5_pipeline.py`** (`--dry-run` skips the sheet write and the Instagram step; `--instagram-ddg` enables slower DuckDuckGo fallback for handles).

**Regions:** Presets live in **`REGIONS`** in that script: **`la`**, **`sf_bay`**, **`i5_corridor`**, **`i5_sd_portland`**, **`ca_hwy_101`**, **`ca_i280`**, etc. Each preset defines **`notes_label`** (appears in **Notes**), **centroids** `(lat, lng, radius_m, label)`, **min/max lat/lng** (post-details filter), **`fallback_city`** when Places omits a city, **`required_state`**, and optionally **`allowed_states`** for multi-state corridors.

**Adding a new metro:** Copy a **`RegionConfig` entry** in **`REGIONS`**: pick **6–10 overlapping circles** so union covers the target area without huge ocean-only overlap; tighten **bbox** to drop adjacent states or the wrong MSA; set **`notes_label`** to a human-readable region name; open a PR or edit locally and document the preset here (key + intent).

**After append:** Optional Instagram backfill — **`scripts/backfill_instagram_la_discovery.py`** keys off **Notes** containing `Auto-discovered (Google Places Nearby` (not LA-specific). New **Research** rows are picked up by **`hit_list_research_photo_review.py`** / the hourly Actions workflow like any other **Research** row.

**Dedupe (why duplicates can appear):** Older rows often have **no `place_id` in Notes**, so a second discovery pass only sees **`place_id`** on the new row; **Store Key** can also differ when Google’s street line differs slightly (`St` vs `Street`, suite text). The discovery script indexes **literal + normalized + legacy Store Keys**, **`place_id`** (flexible regex), a **name + lat/lng (4 decimals)** fingerprint, and a **normalized Shop Name + Address (columns A + D)** key so reruns skip the same storefront even when city/state parsing differs. To audit the sheet: **`python3 scripts/hit_list_report_duplicates.py`** — groups rows by repeated **`place_id`**, repeated keys, same name+coordinates, or same name+address. To **remove** duplicate name+address rows while **keeping the oldest row** (lowest row number): **`python3 scripts/hit_list_dedupe_name_address.py`** (dry-run), then **`python3 scripts/hit_list_dedupe_name_address.py --apply`**.

**Contact enrichment (AI: Enrich with contact):** Script **`scripts/hit_list_enrich_contact.py`** processes rows with that exact Status (default **10** per run): fetches **Website** (or Places **website** via `place_id` in **Notes**), scans pages for **email** and **contact-form** heuristics, optional **Grok** disambiguation, then sets **AI: Email found** (fills **Email**), **AI: Contact Form found** (fills **Contact Form URL**), or **AI: Enrich — manual**. **Audit trail:** Each run appends a row on tab **`DApp Remarks`** (same columns as human DApp / photo review) with **`Remarks`** text **`[enrich-contact <ISO8601 Z>] outcome=…`** and **`Submitted By` = `hit_list_enrich_contact`**, then applies **Hit List** **Status**, **`Sales Process Notes`** (prefixed line), **Status Updated By/Date**, and marks the remark **Processed** — implemented in **`scripts/hit_list_dapp_remarks_sheet.py`** (shared with **`hit_list_research_photo_review.py`**). **Hit List → Notes** is **not** amended with these lines (keep **Notes** for discovery / `place_id`). **Required columns** on Hit List for the apply step: **Sales Process Notes**, **Status Updated By**, **Status Updated Date**. **GitHub Actions:** `.github/workflows/hit_list_enrich_contact.yml` — same secrets as photo review (`GOOGLE_CREDENTIALS_JSON`, `GOOGLE_MAPS_API_KEY`, `GROK_API_KEY`); scheduled **every hour at :35 UTC** (staggered from photo review on the hour), default **10** rows, plus **`workflow_dispatch`**. **Design / discussion summary for future agents:** **`agentic_ai_context/HIT_LIST_CONTACT_ENRICHMENT.md`**.

## States tab (canonical dapp / Hit List values)

The worksheet **`States`** is the reference for **exact strings** used by [Stores Nearby](https://dapp.truesight.me/stores_nearby.html) and the Hit List (Status, Shop Type, US state codes, Priority). Re-populate after you change enums in `dapp/stores_nearby.html`:

```bash
cd market_research
python3 scripts/populate_states_reference_sheet.py
python3 scripts/populate_states_reference_sheet.py --dry-run   # preview TSV
```

Columns written: `field`, `exact_value`, `notes`, `hit_list_column`. Important: **Shop Type** must use `Metaphysical/Spiritual` (slash), not only spaces—matches `<option value=` and URL `shop_type=`.

## Hit List Column Schema

| Col | Name | Type | Notes |
|-----|------|------|-------|
| A | Shop Name | String | |
| B | Status | String | See **States** tab — includes Research; AI: Shortlisted / Photo rejected / Photo needs review; **AI: Enrich with contact**, **AI: Email found**, **AI: Contact Form found**, **AI: Enrich — manual**, **AI: Warm up prospect**, **AI: Prospect replied**; Shortlisted; Instagram Followed; Contacted; Manager Follow-up; Bulk Info Requested; Meeting Scheduled; Followed Up; Partnered; On Hold; Rejected; Not Appropriate |
| C | Priority | String | High, Medium, Low, Existing Partner (sheet-only; not on dapp suggest form) |
| D | Address | String | |
| E | City | String | |
| F | State | String | Two-letter codes (50 states + DC) — see **States** tab |
| G | Shop Type | String | See **States** tab — includes `Metaphysical/Spiritual`, Wellness Center, Health Food Store, … |
| H | Phone | String | |
| I | Cell Phone | String | |
| J | Website | String | |
| K | Email | String | |
| L | Instagram | String | Required for qualified leads |
| M | Notes | String | |
| N-AB | Contact Date, Contact Method, Follow Up Date, etc. | | See sheet |
| AC | Instagram Follow Count | String | Follower count from Instagram profile |
| AD | Store Key | String | shop-name__address__city__state (lowercase, hyphens) |
| AE | Contact Form URL | String | Public contact-page or form URL when status is **AI: Contact Form found** (empty otherwise) |

After adding **AE**, run **`python3 scripts/populate_states_reference_sheet.py`** and **`python3 scripts/format_states_reference_sheet.py`** so the **States** tab lists the new status strings for the dapp and operators.

## Store Key Format

`{shop-name}__{address}__{city}__{state}` — lowercase, spaces to hyphens, special chars removed.
Example: `go-ask-alice__1125-pacific-ave__santa-cruz__ca`

---

## Email Agent Follow Up tab (Gmail ↔ Hit List)

**Purpose:** Append-only log of **sent** messages from the connected Gmail account (`credentials/gmail/token.json`), backfilled for leads on **Hit List** where **Status** is **`Manager Follow-up`**, **`Bulk Info Requested`**, **`AI: Warm up prospect`**, **`AI: Prospect replied`**, and **Email** is set.

**Sheet:** Same spreadsheet — tab name **`Email Agent Follow Up`**.  
If the tab is missing, `scripts/sync_email_agent_followup.py` creates it and writes the header row.

### Log columns (row 1)

| Column | Description |
|--------|-------------|
| `gmail_message_id` | Stable Gmail id — used to avoid duplicate rows. |
| `synced_at_utc` | When this row was written by the sync script. |
| `store_key` | From Hit List **Store Key** (join hint). |
| `shop_name` | From Hit List **Shop Name**. |
| `to_email` | Recipient (normalized lowercase). |
| `subject` | Message subject from Gmail. |
| `sent_at` | `Date` header from Gmail (as returned by the API). |
| `snippet` | Short preview text. |
| `sync_source` | e.g. `gmail_sent_sync`. |

### Run sync (after Gmail OAuth + service account sheet share)

```bash
cd market_research
source venv/bin/activate
python3 scripts/sync_email_agent_followup.py --dry-run    # preview
python3 scripts/sync_email_agent_followup.py            # append new rows
```

Options: `--limit N` (max distinct addresses), `--per-address-cap` (max messages per address, default 200).

**Auth:** Sheets = **service account** (`google_credentials.json`). Gmail = **user OAuth** (`credentials/gmail/`). Future “draft + send + update Status” flows can extend this script or call the same libraries.

### Readable layout (formatting)

After syncing (or after manual edits), re-apply column widths, frozen header, filters, and banded rows:

```bash
python3 scripts/format_email_agent_followup_sheet.py
```

Safe to run multiple times. If Google returns an error about an existing banded range, remove banding manually once in Sheets (**Format → Alternating colors → Remove alternating colors**) and run the script again.

---

## Email Agent Suggestions tab (draft queue + registry)

**Purpose:** One row per **proposed follow-up** while the human reviews in **Gmail**. The canonical editable message lives as a **Gmail draft**; this tab is the **audit / queue** (join to Hit List via `store_key` / `hit_list_row`). Pairs with **Email Agent Follow Up**, which logs **sent** mail after you hit Send.

**Sheet:** Same spreadsheet — tab name **`Email Agent Suggestions`**.

**Gmail (optional but recommended):** Apply user label **`Email Agent suggestions`** to drafts the automation creates so they are easy to filter in the Gmail UI (create the label once manually, or use `users.labels.create` in a future script). The tab also stores the label name in column `gmail_label` for documentation.

### Create tab + header row

```bash
cd market_research
python3 scripts/ensure_email_agent_suggestions_sheet.py
python3 scripts/format_email_agent_suggestions_sheet.py
```

### Columns (row 1)

| Column | Description |
|--------|-------------|
| `suggestion_id` | Stable id (e.g. UUID) for this suggestion row. |
| `created_at_utc` | When the draft was created. |
| `store_key` | Hit List **Store Key**. |
| `shop_name` | Hit List **Shop Name**. |
| `to_email` | Intended recipient (lowercase). |
| `hit_list_row` | Sheet row number(s) on Hit List, comma-separated if multiple. |
| `gmail_draft_id` | Gmail **Draft** id from `drafts.create` / API. |
| `subject` | Draft subject (mirror of Gmail). |
| `body_preview` | First ~500 characters of body for quick scan in Sheets. |
| `status` | `pending_review` · `sent` · `discarded` · `superseded` (conventions; adjust as needed). |
| `gmail_label` | e.g. `Email Agent suggestions`. |
| `protocol_version` | e.g. `PARTNER_OUTREACH_PROTOCOL v0.1`. |
| `notes` | Free text — why this touch, thread summary, etc. |

**Workflow:** Automation (or you) creates a Gmail draft → append a row here → you **edit/send** from Gmail → run `sync_email_agent_followup.py` so **Email Agent Follow Up** captures the sent message → set `status` to `sent` on this row (manual or future script).

### Create drafts from Hit List (`garyjob@agroverse.shop`)

Script: **`scripts/suggest_manager_followup_drafts.py`** — loads **Manager Follow-up** + **Email**, skips recipients that already have **`pending_review`** (and an open Gmail draft), builds a **Gmail draft** (optional **Grok** + DApp Remarks context), applies label **`Email Agent suggestions`**, appends a row here.

**Warm up prospect (first touch + PDF):** **`scripts/suggest_warmup_prospect_drafts.py`** — **Status** **`AI: Warm up prospect`** + **Email**; same cadence (**7** days default since last logged send in **Email Agent Follow Up**), **`Email Agent Suggestions`** queue, and optional **`--use-grok`** (same xAI API as manager follow-up). Attaches **`retail_price_list/agroverse_wholesale_price_list_2026.pdf`**. Style reference: **`templates/warmup_outreach_reference.md`**. Before drafting, promotes **AI: Warm up prospect → AI: Prospect replied** when Gmail shows an **inbound** from the prospect **after** your latest logged **sent** to that address. CI: **`manager-followup-drafts.yml`** runs this step after manager drafts. Flags: **`--reply-promotion-only`**, **`--skip-reply-promotion`**.

OAuth must include **`https://www.googleapis.com/auth/gmail.modify`**. If your `token.json` was created with older scopes, delete it and run `python3 scripts/gmail_oauth_authorize.py` again (add scope on Google Cloud consent screen first).

```bash
cd market_research
python3 scripts/suggest_manager_followup_drafts.py --dry-run
python3 scripts/suggest_manager_followup_drafts.py --max-drafts 1
```

Options: `--skip-label`, `--expected-mailbox other@domain` (default `garyjob@agroverse.shop`).

**Cadence / anti-spam:** Only one **pending** draft per **`to_email`** (see **Email Agent Suggestions** `status=pending_review`). The next draft is allowed only after **`min-days-since-sent`** (default **7**) since the latest **`sent_at`** for that address in **Email Agent Follow Up**. Recipients with no follow-up log row are eligible immediately. Use `--verbose` to print per-address skips. When you **Send** from Gmail, run `sync_email_agent_followup.py`, then set the suggestion row to `sent` (or `discarded`); the next scheduled run can draft again once cadence passes.

**`Bulk Info Requested`:** **`scripts/suggest_bulk_info_drafts.py`** — wholesale-focused template + same PDF attachment; same cadence rules.

**Grok (optional):** With **`--use-grok`**, **manager** follow-up and **warmup** scripts load Gmail thread context and call the xAI **chat/completions** API (`grok-3` by default) for JSON `subject` + `body`. On API/parse errors, each script falls back to its built-in template. **`--dry-run` does not call Grok** (shows template preview only). **Bulk info** drafts use a **fixed template** only unless extended later.

**Draft tone (system prompt + template):** Suggested copy does **not** invite **in-person meetings** or another on-site visit (Gary’s travel pattern). When Hit List **Notes**, **DApp Remarks**, or the thread show staff routed follow-up to **owner / buyer / decision-maker**, the draft should **address that person**, not staff — see **`agentic_ai_context/PARTNER_OUTREACH_PROTOCOL.md`** §6 and **`STORE_FOLLOW_UP_EMAIL_TEMPLATE.md`**.

**`GROK_API_KEY` — local vs GitHub Actions**

| Where you run | How to provide the key |
|---------------|-------------------------|
| **This machine** | Add `GROK_API_KEY=...` to **`market_research/.env`** (gitignored if you add `.env` to `.gitignore`), or `export GROK_API_KEY=...` before running. |
| **GitHub Actions** | Repo **Settings → Secrets and variables → Actions** → create **`GROK_API_KEY`**. In the workflow job, set `env: GROK_API_KEY: ${{ secrets.GROK_API_KEY }}` (job-level or step-level). Do not commit the key. |

The script calls `load_dotenv(..., override=False)`: variables **already in the environment** (e.g. injected by Actions) are **not** replaced by `.env`, so CI secrets win if both exist.

Example workflow fragment:

```yaml
jobs:
  followup-drafts:
    runs-on: ubuntu-latest
    env:
      GROK_API_KEY: ${{ secrets.GROK_API_KEY }}
      # Full contents of credentials/gmail/token.json (multi-line JSON secret):
      GMAIL_TOKEN_JSON: ${{ secrets.GMAIL_TOKEN_JSON }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r market_research/requirements.txt
      - run: python3 scripts/suggest_manager_followup_drafts.py --use-grok --max-drafts 1
        working-directory: market_research
      # Sheets: provide google_credentials.json (e.g. write from secret to file in a prior step).
```

**Gmail OAuth in CI:** See **`scripts/gmail_user_credentials.py`** and **`agentic_ai_context/GMAIL_OAUTH_WORKFLOW.md`** — **`GMAIL_TOKEN_JSON`** overrides the local `token.json` path when set. **GitHub never updates that secret automatically:** OAuth may refresh access tokens only for the duration of the job; when the stored refresh token stops working, **replace `GMAIL_TOKEN_JSON`** with a new export of **`credentials/gmail/token.json`** from your machine after **`gmail_oauth_authorize.py`**.

### States tab — readability

After changing reference content (`populate_states_reference_sheet.py`), re-apply frozen panes, header row styling, filters, and banding:

```bash
python3 scripts/format_states_reference_sheet.py
```

### Email Agent Training Data (Partnered + Gmail)

**Purpose:** One row per Gmail message (sent **or** received) for each **distinct Email** on the Hit List where **Status = Partnered**. Sort order: partner email, then time. Use **`analysis_notes`** for your own tags (e.g. `commitment_yes`, `pricing_objection`) while you design a human-in-the-loop follow-up protocol toward consignment **yes**.

**Prerequisites:** Same as Gmail sync — service account on the spreadsheet + `credentials/gmail/token.json`.

```bash
python3 scripts/sync_email_agent_training_data.py --dry-run
python3 scripts/sync_email_agent_training_data.py
python3 scripts/format_email_agent_training_data_sheet.py   # optional; sync runs it by default
```

Options: `--limit N` (max partner addresses), `--max-messages-per-address` (default 200), `--no-format`.

Each full run **replaces** all rows in that tab (header + fresh pull). Partner stores with no matching mail in the connected mailbox will not appear as rows (only addresses that return Gmail hits are listed).
