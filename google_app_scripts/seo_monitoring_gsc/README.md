# SEO monitoring — Google Apps Script (GSC weekly)

**Production project:** [script editor](https://script.google.com/home/projects/1QTacKltsTY7MBTL1N_JwemzUCLTGvTvZDhm_zf2kzsWXBQUV-iUtWnai/edit) · script id `1QTacKltsTY7MBTL1N_JwemzUCLTGvTvZDhm_zf2kzsWXBQUV-iUtWnai` (see `.clasp.json`).

**Deployment:** Files here are the **source of truth in git**. Push with `clasp push` after `clasp login` — see **`agentic_ai_context/SEO_MONITORING_SHEET_WORKFLOW.md`** → *Deployment status (clasp)*.

**Spreadsheet tabs** are created by `market_research/scripts/bootstrap_seo_monitoring_sheet.py`.

This folder holds the **container-bound** Apps Script: weekly Search Console export into `Weekly_GSC`, and **monthly** DataForSEO keyword ideas into **`DataForSEO_monthly_discovery`**.

## Conventions (aligned with tokenomics `google_app_scripts`)

- File headers describe purpose and repo path.
- Config in `Config.gs`; GSC in `WeeklyGscSnapshot.gs`; DataForSEO in `MonthlyDataForSeoDiscovery.gs`; triggers in `Triggers.gs`.
- **GSC access:** `appsscript.json` declares `webmasters.readonly`; code calls Search Analytics via **UrlFetch** (not the Search Console advanced service), so **`clasp push`** is not blocked by the “Service not found: searchconsole v1” manifest error.

## Prerequisites

1. Spreadsheet exists and tabs match `SEO_MONITORING_CONFIG` names.
2. **Google account** running the script has access to the Search Console property (`GSC_SITE_URL` in `Config.gs`).
3. After a manifest change, **re-authorize** the project once so the new OAuth scopes are granted (Sheets, webmasters, `script.external_request`, `script.scriptapp`).
4. **Google Cloud:** `UrlFetch` + `ScriptApp.getOAuthToken()` run against whatever **GCP project is linked to this Apps Script** (Project Settings → **Google Cloud Platform (GCP) Project**). **Recommended:** link **`get-data-io`** (`project_id` in `credentials/search_console/client_secret.json`) — **project number `667737028020`** — where **Search Console API** is already enabled for Python.
   - Apps Script → **Project Settings** → **Google Cloud Platform (GCP) Project** → **Change project** → enter **`667737028020`** (you need a role on that GCP project, e.g. Owner/Editor). Guide: [Change the Google Cloud project for a script](https://developers.google.com/apps-script/guides/cloud-platform-projects#change_the_google_cloud_project).
   - Confirm API: [Search Console API for this project](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com?project=667737028020).
   - After linking, wait a minute; **re-authorize** if prompted; run **`runWeeklyGscSnapshotNow()`** again.
   - **Do not rely on the default Apps Script project** (`sys-…` / e.g. project number `444333363325`): it is Google-managed, and enabling APIs there often fails with **`serviceusage.services.enable`** (“missing required permission”). **Link to a standard project** you own (**`667737028020`**) instead of trying to enable Search Console API on the default project.

## clasp (optional)

**clasp does not use** `market_research/credentials/gmail/token.json` or Search Console `token.json`. It uses its own login.

```bash
cd market_research/google_app_scripts/seo_monitoring_gsc
npm i -g @google/clasp   # if needed
clasp login              # authenticate as garyjob@agroverse.shop (browser)
```

### Bind to an existing spreadsheet

1. Open the spreadsheet → **Extensions** → **Apps Script**.
2. **Project Settings** → copy **Script ID**.
3. `cp .clasp.json.example .clasp.json` → set `scriptId`.
4. `clasp pull` (optional) then copy `.gs` / `appsscript.json` from this repo → `clasp push`.
5. In the editor, run `installWeeklyTrigger()` once.

### Create sheet + script in Drive folder (alternative)

```bash
clasp create --type sheets --title "Agroverse Shop — SEO monitoring (GSC weekly)" \
  --parentId 1esYnlwChRmv9-M3ymWYhWMPHRowhOluw
```

Then run the Python bootstrap with `--spreadsheet-id <id-from-clasp-output>` if you still need tab layout/keywords seeding, or recreate tabs manually to match the workflow doc.

## Manual install (no clasp)

1. Open the spreadsheet → **Extensions** → **Apps Script**.
2. Create files / paste contents: `Config.gs`, `WeeklyGscSnapshot.gs`, `MonthlyDataForSeoDiscovery.gs`, `Triggers.gs`, and manifest **`appsscript.json`** from this folder (`oauthScopes`: Sheets, `webmasters.readonly`, `script.external_request`, **`script.scriptapp`** for install*Trigger).
3. Save → **Authorize** (grant those scopes).
4. Run `installWeeklyTrigger()` once; use `runWeeklyGscSnapshotNow()` to test.

Full ops context: `agentic_ai_context/SEO_MONITORING_SHEET_WORKFLOW.md`.

---

## DataForSEO monthly discovery (Script properties)

Calls [DataForSEO Keywords For Keywords Live](https://docs.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live/) (same family as `scripts/dataforseo_buyer_intent_keywords.py`). Appends rows that are **not** already on **`Keywords_targets`** column A.

### You must set (Apps Script → **Project Settings** → **Script properties**)

| Property | Required | Description |
|----------|----------|-------------|
| **`DATAFORSEO_LOGIN`** | **Yes** | API login from [DataForSEO API access](https://app.dataforseo.com/api-access) (same as `DATAFORSEO_LOGIN` in `market_research/.env`). |
| **`DATAFORSEO_PASSWORD`** | **Yes** | API password (same as `DATAFORSEO_PASSWORD` in `.env`). **Never** paste these into `Config.gs` or git. |

### Optional Script properties

| Property | Description |
|----------|-------------|
| **`DATAFORSEO_SEEDS`** | Comma-separated seed keywords **(max 20 used)**. If omitted, **`Config.gs` → `DATAFORSEO_DEFAULT_SEEDS`** is used. |

### Config in `Config.gs` (non-secret; edit in repo)

- **`DATAFORSEO_LOCATION_CODE`** (default `2840` = United States) or set **`DATAFORSEO_LOCATION_NAME`** e.g. `"United States"` to override.
- **`DATAFORSEO_LANGUAGE_CODE`**, **`DATAFORSEO_SORT_BY`**, **`DATAFORSEO_MAX_ROWS_PER_RUN`**, **`SH_MONTHLY_DFS`** (tab name).

### Keywords_targets: chocolate-scope rows (Python)

From `market_research/`, after a successful `scripts/dataforseo_buyer_intent_keywords.py` run (CSV under `output/dataforseo/`), append deduped chocolate / bean-to-bar queries to **`Keywords_targets`** with DFS columns filled:

`python3 scripts/append_chocolate_keywords_to_targets.py`  
(`--dry-run` to preview; uses `brand_keyword_blocklist.txt` for substring excludes.)

### Python equivalent (local)

From `market_research/`, same logic as **`monthlyDataForSeoKeywordDiscovery()`** (append ideas not on **Keywords_targets** col A):

- Live API: `python3 scripts/sync_dataforseo_monthly_discovery.py` (uses `.env` DataForSEO creds).
- If the API returns **403** / errors: `python3 scripts/sync_dataforseo_monthly_discovery.py --use-latest-csv` after `dataforseo_buyer_intent_keywords.py` has written a CSV under `output/dataforseo/`.

### Triggers

1. After setting properties: run **`runMonthlyDataForSeoDiscoveryNow()`** once to verify billing and the **`DataForSEO_monthly_discovery`** tab (created automatically if missing).
2. Run **`installMonthlyDataForSeoTrigger()`** once — schedules **`monthlyDataForSeoKeywordDiscovery`** on the **1st of each month at 09:00** (timezone from `appsscript.json`, default `America/Los_Angeles`).

### Existing workbook without the new tab

Either run the manual function above (it **inserts** the sheet), or re-run bootstrap with `--spreadsheet-id` only if you accept it **rewriting** tab contents per `bootstrap_seo_monitoring_sheet.py` (keywords seed, etc.).
