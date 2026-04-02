#!/usr/bin/env python3
"""
Google Search Console API — OAuth 2.0 browser sign-in (read-only site data).

Use this to create or renew **user** credentials for organic search analytics
(`searchanalytics.query`, dimensions such as `query`, `page`, etc.).

Prerequisites
-------------
1. Search Console API enabled:
   https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
2. Site verified in Search Console (same Google account you use to sign in).
3. OAuth consent screen includes scope:
   https://www.googleapis.com/auth/webmasters.readonly
4. OAuth client ID → **Desktop app** JSON saved as:
       market_research/credentials/search_console/client_secret.json
   (You may copy the same Desktop client JSON used for Gmail if both scopes
   are on the consent screen.)

Run (from repo root or any cwd):
    python3 scripts/search_console_oauth_authorize.py

A local server opens your **browser** to complete consent (Google OAuth page).

Output
------
Writes credentials/search_console/token.json (gitignored). Delete that file and
re-run to pick up new scopes or after revocation.

Do not commit token.json or client_secret.json. Do not paste refresh tokens into chat.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Changing this list requires deleting token.json and re-authorizing.
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
]

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_CRED_DIR = _REPO_ROOT / "credentials" / "search_console"
_CLIENT_SECRET = _CRED_DIR / "client_secret.json"
_TOKEN_PATH = _CRED_DIR / "token.json"


def main() -> None:
    _CRED_DIR.mkdir(parents=True, exist_ok=True)

    if not _CLIENT_SECRET.is_file():
        sys.stderr.write(
            f"Missing OAuth client secret file:\n  {_CLIENT_SECRET}\n\n"
            "Google Cloud Console → APIs & Services → Credentials →\n"
            "Create OAuth client ID → Desktop app → Download JSON → save path above.\n"
            "See agentic_ai_context/SEARCH_CONSOLE_API_WORKFLOW.md\n"
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
    print("\nNext: call Search Console API with googleapiclient (service searchconsole v1)")
    print("or see SEARCH_CONSOLE_API_WORKFLOW.md for a minimal query example.")
    print("Do not commit token.json or paste it into Git or chat.\n")


if __name__ == "__main__":
    main()
