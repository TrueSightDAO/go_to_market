#!/usr/bin/env python3
"""
Gmail user OAuth credentials: **local file** or **CI environment**.

- **Local:** `market_research/credentials/gmail/token.json` (from `gmail_oauth_authorize.py`).
- **GitHub Actions / CI:** set **`GMAIL_TOKEN_JSON`** to the **full JSON** string of that file
  (repository secret). Never commit it.

If **`GMAIL_TOKEN_JSON`** is non-empty, it takes precedence over the file (same idea as
`GROK_API_KEY` + `load_dotenv(override=False)`). After a token **refresh**, only the **file**
path is updated; env-only runs keep refreshed credentials **in memory** for that process.

See `HIT_LIST_CREDENTIALS.md` and `GMAIL_OAUTH_WORKFLOW.md`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials

# Full JSON body of credentials/gmail/token.json (same keys as google-auth token dump).
GMAIL_TOKEN_JSON_ENV = "GMAIL_TOKEN_JSON"


def load_gmail_user_credentials(token_path: Path, scopes: list[str]) -> UserCredentials:
    raw = os.environ.get(GMAIL_TOKEN_JSON_ENV, "").strip()

    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"{GMAIL_TOKEN_JSON_ENV} is set but is not valid JSON: {e}\n")
            sys.exit(1)
        creds = UserCredentials.from_authorized_user_info(info, scopes)
        persist_path: Path | None = None
    else:
        if not token_path.is_file():
            sys.stderr.write(
                f"Missing Gmail token file:\n  {token_path}\n\n"
                "Locally: run  python3 scripts/gmail_oauth_authorize.py\n"
                f"In CI: set repository secret and env  {GMAIL_TOKEN_JSON_ENV}  "
                "to the full token.json contents.\n"
            )
            sys.exit(1)
        creds = UserCredentials.from_authorized_user_file(str(token_path), scopes)
        persist_path = token_path

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if persist_path is not None:
                persist_path.parent.mkdir(parents=True, exist_ok=True)
                persist_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            sys.stderr.write(
                "Gmail OAuth token invalid or missing refresh_token. "
                "Locally: delete token.json and re-run gmail_oauth_authorize.py. "
                f"In CI: update the {GMAIL_TOKEN_JSON_ENV} secret.\n"
            )
            sys.exit(1)

    return creds
