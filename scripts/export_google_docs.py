#!/usr/bin/env python3
"""
Export partnership agreements (and any other reference Google Docs we want LLMs to read)
from Google Drive into a public static repo as Markdown.

Why this exists: a Google Doc URL is readable by humans but NOT by external LLMs — a
WebFetch against ``docs.google.com/document/d/...`` returns the Drive nav shell, not the
document body. Publishing a nightly Markdown mirror under
``ecosystem_change_logs/agreements/`` makes each agreement LLM-fetchable via its raw
GitHub URL (``raw.githubusercontent.com/TrueSightDAO/ecosystem_change_logs/main/...``).

Authentication: expects a service-account JSON at ``credentials/white_paper_google_sa.json``
(override with ``--credentials``; CI writes the file from repo secret
``WHITEPAPER_GOOGLE_SA_JSON``). Each Google Doc in DOCS below must be shared with the
service account's ``client_email`` as at least Viewer.

Usage (from ``market_research/``):

  python3 scripts/export_google_docs.py --output-dir ../ecosystem_change_logs/agreements

  # dry-run — print first 500 chars of each export to stdout, write nothing
  python3 scripts/export_google_docs.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

_REPO = Path(__file__).resolve().parent.parent

# Docs to mirror. Each entry pins the canonical Google Doc ID and the output filename under
# --output-dir. Keep titles in sync with the anchor text on truesight.me (PR #42).
DOCS: list[dict[str, str]] = [
    {
        "doc_id": "1n3wKmVa-kOjmbVJlfVvskep6rNbOfGGPF1QUTNrUi08",
        "title": "Agroverse Community Distributors Agreement",
        "filename": "community-distributors-agreement.md",
    },
    {
        "doc_id": "1FA_NpmwbnnCuV0m46UlfjbVdQvdF92594xcwUDu3JvI",
        "title": "Community Warehouse Manager Service Level Agreement",
        "filename": "warehouse-manager-sla.md",
    },
]

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _header(doc: dict[str, str], doc_meta: dict[str, str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    modified = doc_meta.get("modifiedTime", "")
    return (
        f"<!-- AUTO-GENERATED: do not edit in place. "
        f"Source of truth: https://docs.google.com/document/d/{doc['doc_id']}/edit\n"
        f"     Exported by market_research/scripts/export_google_docs.py on {now}.\n"
        f"     Google Doc last modified: {modified} -->\n\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--credentials",
        type=Path,
        default=_REPO / "credentials" / "white_paper_google_sa.json",
        help="Path to service-account JSON (default: credentials/white_paper_google_sa.json).",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Target directory for Markdown exports. Required unless --dry-run.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print the first 500 chars of each export; write nothing.")
    args = ap.parse_args()

    if not args.credentials.is_file():
        sys.stderr.write(f"Missing credentials file: {args.credentials}\n")
        return 2

    if not args.dry_run and args.output_dir is None:
        sys.stderr.write("--output-dir is required unless --dry-run is passed.\n")
        return 2

    creds = Credentials.from_service_account_file(str(args.credentials), scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for doc in DOCS:
        try:
            meta = drive.files().get(fileId=doc["doc_id"], fields="name,modifiedTime").execute()
            body = drive.files().export(fileId=doc["doc_id"], mimeType="text/markdown").execute()
            content = _header(doc, meta) + body.decode("utf-8")
            print(f"OK {doc['title']}: {meta['name']!r} ({len(content)} chars)", file=sys.stderr)
            if args.dry_run:
                print(f"\n----- {doc['filename']} -----")
                print(content[:500])
                print("...")
                continue
            out = args.output_dir / doc["filename"]
            out.write_text(content, encoding="utf-8")
            print(f"   → {out}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 — surface raw error for CI log
            sys.stderr.write(f"FAIL {doc['title']} ({doc['doc_id']}): {e}\n")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
