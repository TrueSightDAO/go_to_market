#!/usr/bin/env python3
"""
Gmail OAuth 2.0 — browser sign-in for a user mailbox (e.g. garyjob@agroverse.shop).

Prerequisites
-------------
1. Gmail API enabled on your Google Cloud project:
   https://console.cloud.google.com/apis/library/gmail.googleapis.com
2. OAuth consent screen configured; add yourself as a test user if app is in Testing.
3. Create OAuth client ID → Application type: **Desktop app**.
4. Download the JSON and save as:
       market_research/credentials/gmail/client_secret.json

Run (from repo root or any cwd):
    python3 scripts/gmail_oauth_authorize.py

Output
------
Writes credentials/gmail/token.json (gitignored). Re-run if you revoke access or change scopes.

For **GitHub Actions**, copy the **entire** JSON from that file into a secret **`GMAIL_TOKEN_JSON`**
and set `env: GMAIL_TOKEN_JSON: ${{ secrets.GMAIL_TOKEN_JSON }}` on the job (see
`scripts/gmail_user_credentials.py` and GMAIL_OAUTH_WORKFLOW.md). Do not commit the file.

Scopes: **gmail.modify** (read/search, send, create/edit drafts, labels). Required for
`suggest_manager_followup_drafts.py`. If you change scopes, delete token.json and authorize again.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Changing this list requires deleting token.json and re-authorizing.
# gmail.modify covers read, send, drafts.create, and labels (manager follow-up draft script).
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_CRED_DIR = _REPO_ROOT / "credentials" / "gmail"
_CLIENT_SECRET = _CRED_DIR / "client_secret.json"
_TOKEN_PATH = _CRED_DIR / "token.json"


def main() -> None:
    _CRED_DIR.mkdir(parents=True, exist_ok=True)

    if not _CLIENT_SECRET.is_file():
        sys.stderr.write(
            f"Missing OAuth client secret file:\n  {_CLIENT_SECRET}\n\n"
            "Google Cloud Console → APIs & Services → Credentials →\n"
            "Create OAuth client ID → Desktop app → Download JSON → save path above.\n"
        )
        sys.exit(1)

    creds: Credentials | None = None
    if _TOKEN_PATH.is_file():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CLIENT_SECRET), SCOPES
            )
            creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        print(f"Saved credentials to {_TOKEN_PATH}")
    else:
        print(f"Existing token is still valid: {_TOKEN_PATH}")

    payload = json.loads(creds.to_json())
    print("\n--- Status (safe to share) ---")
    print(f"token_file: {_TOKEN_PATH}")
    print(f"scopes: {payload.get('scopes')}")
    print(f"expiry: {payload.get('expiry')}")
    print(f"has_refresh_token: {bool(payload.get('refresh_token'))}")
    print("\nDo not commit token.json or client_secret.json. Do not paste tokens into Git repos.")


if __name__ == "__main__":
    main()
