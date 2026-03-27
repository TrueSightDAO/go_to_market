# Gmail OAuth (local secrets)

Place **only on your machine**:

| File | What it is |
|------|------------|
| `client_secret.json` | OAuth **Desktop app** client JSON from Google Cloud Console (download once). |
| `token.json` | Created by `scripts/gmail_oauth_authorize.py` after you sign in in the browser. Contains access + refresh tokens. |

**Do not** commit these files. **Do not** paste `token.json` or refresh tokens into GitHub, Slack, or public chat.

Authorize:

```bash
cd /path/to/market_research
python3 scripts/gmail_oauth_authorize.py
```

See **`agentic_ai_context/GMAIL_OAUTH_WORKFLOW.md`** for full setup (enable Gmail API, consent screen, scopes). Current scope is **`gmail.modify`** (drafts + labels + send + read). After a scope change, delete `token.json` and authorize again.

**CI (GitHub Actions):** Inject the same JSON as **`GMAIL_TOKEN_JSON`** (e.g. repository secret) instead of this file — see **`scripts/gmail_user_credentials.py`**. Refreshed access tokens are **not** written back to that secret; if mail stops working in CI, **re-export `token.json` after local re-auth** and **replace** the secret. Details: **`agentic_ai_context/GMAIL_OAUTH_WORKFLOW.md`** § CI / troubleshooting.
