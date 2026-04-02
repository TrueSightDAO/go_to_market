#!/usr/bin/env python3
"""
Create a container-bound Google Apps Script project on the SEO monitoring spreadsheet
and upload the weekly GSC sources from google_app_scripts/seo_monitoring_gsc/.

Prerequisites (human, one-time)
--------------------------------
1. Turn ON "Google Apps Script API" for your account:
   https://script.google.com/home/usersettings
2. Enable Apps Script API on the GCP project tied to your OAuth client.
3. OAuth consent: add scope https://www.googleapis.com/auth/script.projects
4. Share the spreadsheet with the Google account you sign in as (Owner/Editor).

Credentials
-----------
- token.json + client_secret.json under credentials/apps_script/, OR
- client_secret.json in credentials/search_console/ (fallback)

Usage (from market_research/)
-----------------------------
  python3 scripts/create_bound_seo_apps_script_project.py
  python3 scripts/create_bound_seo_apps_script_project.py --spreadsheet-id OTHER_ID
  python3 scripts/create_bound_seo_apps_script_project.py --only-content SCRIPT_ID
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CRED_DIR = REPO_ROOT / "credentials" / "apps_script"
FALLBACK_CLIENT = REPO_ROOT / "credentials" / "search_console" / "client_secret.json"
TOKEN_PATH = CRED_DIR / "token.json"
GAS_SOURCES = REPO_ROOT / "google_app_scripts" / "seo_monitoring_gsc"
CLASP_JSON = GAS_SOURCES / ".clasp.json"

DEFAULT_SPREADSHEET_ID = "1qRlufSUQusQbJc3AwonIvHtfiAQjwhnMtl79FFkGBt8"

SCOPES = ["https://www.googleapis.com/auth/script.projects"]


def resolve_client_secret() -> Path:
    a = CRED_DIR / "client_secret.json"
    if a.is_file():
        return a
    if FALLBACK_CLIENT.is_file():
        return FALLBACK_CLIENT
    sys.stderr.write(
        f"Missing OAuth client secret. Add one of:\n  {a}\n  {FALLBACK_CLIENT}\n"
    )
    sys.exit(1)


def get_credentials() -> Credentials:
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    client = resolve_client_secret()
    creds: Credentials | None = None
    if TOKEN_PATH.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
            creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        print(f"Saved OAuth token to {TOKEN_PATH}")
    return creds


def load_gas_files() -> list[dict]:
    manifest = GAS_SOURCES / "appsscript.json"
    if not manifest.is_file():
        sys.stderr.write(f"Missing {manifest}\n")
        sys.exit(1)
    app_body = manifest.read_text(encoding="utf-8")
    files: list[dict] = [
        {"name": "appsscript", "type": "JSON", "source": app_body},
    ]
    for path in sorted(GAS_SOURCES.glob("*.gs")):
        name = path.stem  # API: no .gs suffix
        src = path.read_text(encoding="utf-8")
        files.append({"name": name, "type": "SERVER_JS", "source": src})
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Create bound Apps Script + upload SEO GAS files")
    parser.add_argument(
        "--spreadsheet-id",
        default=DEFAULT_SPREADSHEET_ID,
        help="Spreadsheet Drive ID (container parent)",
    )
    parser.add_argument(
        "--only-content",
        default=None,
        metavar="SCRIPT_ID",
        help="Skip create; only PUT content to this existing script project",
    )
    parser.add_argument(
        "--title",
        default="Agroverse SEO weekly GSC",
        help="New project title (create only)",
    )
    args = parser.parse_args()

    creds = get_credentials()
    service = build("script", "v1", credentials=creds)

    if args.only_content:
        script_id = args.only_content
        print(f"Updating content for scriptId={script_id}")
    else:
        try:
            project = (
                service.projects()
                .create(body={"title": args.title, "parentId": args.spreadsheet_id})
                .execute()
            )
        except HttpError as e:
            sys.stderr.write(
                f"projects.create failed: {e}\n\n"
                "Common fixes:\n"
                "  • Enable Google Apps Script API: https://script.google.com/home/usersettings\n"
                "  • Enable Apps Script API in Google Cloud for your OAuth client project\n"
                "  • Add oauth scope script.projects to consent screen; delete token.json and retry\n"
                "  • Use an account that can edit the spreadsheet\n"
            )
            raise SystemExit(1) from e
        script_id = project.get("scriptId")
        if not script_id:
            sys.stderr.write(f"Unexpected create response: {project!r}\n")
            sys.exit(1)
        print(f"Created bound project scriptId={script_id}")

    files = load_gas_files()
    try:
        service.projects().updateContent(scriptId=script_id, body={"files": files}).execute()
    except HttpError as e:
        sys.stderr.write(f"updateContent failed: {e}\n")
        raise SystemExit(1) from e
    print(f"Uploaded {len(files)} files (manifest + .gs).")

    CLASP_JSON.write_text(
        json.dumps({"scriptId": script_id, "rootDir": "."}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {CLASP_JSON}")
    print("\nNext:")
    print("  1) Open the spreadsheet → Extensions → Apps Script → authorize when prompted.")
    print("  2) Run installWeeklyTrigger() once, then runWeeklyGscSnapshotNow() to test.")
    print(f"  3) clasp push (optional): cd {GAS_SOURCES} && clasp push")


if __name__ == "__main__":
    main()
