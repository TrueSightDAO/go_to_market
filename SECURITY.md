# Security — do not commit secrets

This repo is **not** a secrets store. Keep API keys, OAuth tokens, and service account keys **only on your machine** (or in CI secrets), never in git history.

## Never commit

- **`.env`**, **`.env.*`** (use a local file; see `DATAFORSEO_*` and other env-based scripts)
- **`google_credentials.json`** and other service-account key JSON
- **`credentials/**`** contents except **`README.md`** and **`.gitignore`** per subfolder
- **`client_secret.json`**, **`token.json`**, **`authorized_user.json`** (any path)
- **`.clasprc.json`** (clasp login; normally lives in your home directory)
- **Private keys:** `*.pem`, `*.key`, `*.p8`, etc.

## Allowed in git

- **`.clasp.json`** under `google_app_scripts/*/` (contains **script id** only — public identifier; **optional** to commit; use `.clasp.json.example` if you prefer each clone to set `scriptId` locally)
- **Docs** such as `credentials/*/README.md` describing where to put files

## Enforcement

- **`.gitignore`** is the first line of defense; review `git status` before every commit.
- If something sensitive was committed, **rotate the credential** and use `git filter-repo` or support guidance to purge history — ignoring alone is not enough after push.

## References

- **`credentials/gmail/README.md`**, **`credentials/search_console/README.md`**, **`credentials/apps_script/README.md`**
- **`agentic_ai_context/GMAIL_OAUTH_WORKFLOW.md`**, **`SEARCH_CONSOLE_API_WORKFLOW.md`**, **`SEO_MONITORING_SHEET_WORKFLOW.md`**
