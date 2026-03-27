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
| B | Status | String | See **States** tab — Research, Shortlisted, Instagram Followed, Contacted, Manager Follow-up, Meeting Scheduled, Followed Up, Partnered, On Hold, Rejected, Not Appropriate |
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

## Store Key Format

`{shop-name}__{address}__{city}__{state}` — lowercase, spaces to hyphens, special chars removed.
Example: `go-ask-alice__1125-pacific-ave__santa-cruz__ca`

---

## Email Agent Follow Up tab (Gmail ↔ Hit List)

**Purpose:** Append-only log of **sent** messages from the connected Gmail account (`credentials/gmail/token.json`), backfilled for leads on **Hit List** where **Status** is **`Manager Follow-up`** and **Email** is set.

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

Script: **`scripts/suggest_manager_followup_drafts.py`** — loads **Manager Follow-up** + **Email**, skips `store_key` that already has `pending_review` on this tab, builds a **Gmail draft** (template body + recent thread snippets), applies label **`Email Agent suggestions`**, appends a row here.

OAuth must include **`https://www.googleapis.com/auth/gmail.modify`**. If your `token.json` was created with older scopes, delete it and run `python3 scripts/gmail_oauth_authorize.py` again (add scope on Google Cloud consent screen first).

```bash
cd market_research
python3 scripts/suggest_manager_followup_drafts.py --dry-run
python3 scripts/suggest_manager_followup_drafts.py --max-drafts 1
```

Options: `--skip-label`, `--expected-mailbox other@domain` (default `garyjob@agroverse.shop`).

**Cadence / anti-spam:** Only one **pending** draft per **`to_email`** (see **Email Agent Suggestions** `status=pending_review`). The next draft is allowed only after **`min-days-since-sent`** (default **7**) since the latest **`sent_at`** for that address in **Email Agent Follow Up**. Recipients with no follow-up log row are eligible immediately. Use `--verbose` to print per-address skips. When you **Send** from Gmail, run `sync_email_agent_followup.py`, then set the suggestion row to `sent` (or `discarded`); the next scheduled run can draft again once cadence passes.

**Grok (optional):** With **`--use-grok`**, the script loads up to **`--grok-max-messages`** full Gmail messages (plain text preferred, HTML stripped) for that recipient, capped at **`--grok-max-context-chars`**, and calls the xAI **chat/completions** API (`grok-3` by default) for JSON `subject` + `body`. On API/parse errors, the script falls back to the built-in template. **`--dry-run` does not call Grok** (shows template preview only).

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
