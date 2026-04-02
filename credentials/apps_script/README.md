# Apps Script API — user OAuth (create bound projects / push content)

Secrets here are **gitignored**. Do not commit `client_secret.json` or `token.json`.

1. **Enable Google Apps Script API** for **your Google account**:  
   [script.google.com → Settings → Google Apps Script API](https://script.google.com/home/usersettings) → turn **on**.
2. In **Google Cloud Console** (same project as your Desktop OAuth client): enable **Google Apps Script API** / `script.googleapis.com`.
3. **OAuth consent screen:** add scope  
   `https://www.googleapis.com/auth/script.projects`  
   (e.g. same Desktop app used for Search Console / Gmail — add the scope and save).
4. Save your **Desktop app** JSON as **`client_secret.json`** here, **or** rely on  
   `credentials/search_console/client_secret.json` (script looks there second).
5. From `market_research/`:

   ```bash
   python3 scripts/create_bound_seo_apps_script_project.py
   ```

   Browser opens → sign in as a user who **owns or can edit** the SEO spreadsheet.

6. Re-run after scope changes (delete `token.json` first).

See **`agentic_ai_context/SEO_MONITORING_SHEET_WORKFLOW.md`**.
