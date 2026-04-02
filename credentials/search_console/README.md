# Search Console API — user OAuth (local)

Secrets in this directory are **gitignored**. Do not commit `client_secret.json` or `token.json`.

1. Add **Google Search Console API** and configure the **OAuth consent screen** with scope `webmasters.readonly` — see **`agentic_ai_context/SEARCH_CONSOLE_API_WORKFLOW.md`**.
2. Download your **OAuth client ID → Desktop app** JSON from Google Cloud and save it here as **`client_secret.json`** (can be the same Desktop client you use for Gmail if that client’s consent screen lists both API scopes).
3. From `market_research/`:

   ```bash
   python3 scripts/search_console_oauth_authorize.py
   ```

   A **browser window** opens (localhost redirect) to sign in and grant access. On success, **`token.json`** is written here.

4. Re-run after changing scopes, revoking access, or rotating the OAuth client (delete `token.json` first if needed).
