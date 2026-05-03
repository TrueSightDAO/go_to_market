#!/usr/bin/env python3
"""
Audit Google Sheets that the codebase actually interacts with.

Walks the TrueSightDAO repos under ``~/Applications/``, extracts every
unique Google Sheets ID it finds in the source, queries the Drive API
for metadata + sharing permissions, queries the Sheets API for column
headers, and prints a tier-able Markdown report.

Useful as the first step toward separating sheets we expect to be
publicly readable (event metadata, contributor public keys) from
sheets that hold contact PII (Hit List, email-agent drafts, newsletter
subscribers, QR-code owner emails) and should not be link-shared.

Service-account access is best-effort: any sheet not shared with the
SA is reported as ``RESTRICTED?`` so the operator knows to inspect it
under their own credentials.

Usage:
    cd market_research
    python3 scripts/audit_codebase_google_sheets.py
    python3 scripts/audit_codebase_google_sheets.py --csv audit.csv
    python3 scripts/audit_codebase_google_sheets.py --show-refs
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


REPO_ROOT_PATTERNS = [
    Path.home() / "Applications" / r
    for r in [
        "tokenomics",
        "dapp",
        "dao_client",
        "sentiment_importer",
        "market_research",
        "agroverse_shop",
        "truesight_me",
        "agentic_ai_context",
        "agroverse-inventory",
        "treasury-cache",
    ]
]

SHEET_ID_RE = re.compile(r"docs\.google\.com/(?:a/[^/]+/)?spreadsheets/d/([A-Za-z0-9_-]{20,})")
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next"}
TEXTUAL_EXTS = {".py", ".gs", ".js", ".ts", ".html", ".md", ".json", ".yml", ".yaml",
                ".toml", ".rb", ".go", ".sh", ".txt", ".env"}

# Column-header substrings that suggest PII. Conservative — operator will triage.
PII_TOKENS = ("email", "e-mail", "phone", "mobile", "tel", "contact",
              "address", "street", "city", "zip", "postcode",
              "passport", "ssn", "tax_id", "license_number",
              "owner_email", "subscriber", "to_email", "from_email")

SA_PATH = Path(__file__).resolve().parents[1] / "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


def discover_sheet_refs(roots) -> dict[str, list[Path]]:
    """Walk repos, return ``{sheet_id: [files-that-reference-it]}``."""
    refs: dict[str, list[Path]] = defaultdict(list)
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in TEXTUAL_EXTS:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for sid in set(SHEET_ID_RE.findall(content)):
                refs[sid].append(p)
    return dict(refs)


def summarize_permissions(perms: list[dict]) -> dict:
    out = {
        "anyone_with_link": False,
        "anyone_can_find": False,
        "domain_shares": [],
        "user_count": 0,
        "group_count": 0,
        "owner": "",
        "user_emails": [],
    }
    for perm in perms or []:
        ptype = perm.get("type", "")
        if ptype == "anyone":
            if perm.get("allowFileDiscovery", False):
                out["anyone_can_find"] = True
            else:
                out["anyone_with_link"] = True
        elif ptype == "domain":
            out["domain_shares"].append(perm.get("domain", ""))
        elif ptype == "user":
            if perm.get("role") == "owner":
                out["owner"] = perm.get("emailAddress", "")
            else:
                out["user_emails"].append(perm.get("emailAddress", ""))
            out["user_count"] += 1
        elif ptype == "group":
            out["group_count"] += 1
    return out


def detect_pii_headers(headers: list[str]) -> list[str]:
    flagged = []
    for h in headers:
        h_low = (h or "").strip().lower()
        if not h_low:
            continue
        for tok in PII_TOKENS:
            if tok in h_low:
                flagged.append(h)
                break
    return flagged


def fetch_sheet_audit(drive, sheets_api, sheet_id: str) -> dict:
    rec = {
        "sheet_id": sheet_id,
        "title": "",
        "accessible": False,
        "error": "",
        "perms_summary": {},
        "pii_headers_by_tab": {},
        "n_tabs": 0,
    }
    try:
        meta = drive.files().get(
            fileId=sheet_id,
            fields=("id,name,owners(emailAddress),"
                    "permissions(type,role,emailAddress,domain,allowFileDiscovery)"),
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        # 404 here typically means "the SA isn't on the ACL".
        rec["error"] = f"drive {e.status_code}"
        return rec
    except Exception as e:
        rec["error"] = f"drive {type(e).__name__}: {e}"
        return rec

    rec["title"] = meta.get("name", "")
    rec["perms_summary"] = summarize_permissions(meta.get("permissions") or [])
    if meta.get("owners"):
        rec["perms_summary"]["owner"] = meta["owners"][0].get("emailAddress", "") or rec["perms_summary"].get("owner", "")
    rec["accessible"] = True

    try:
        ss = sheets_api.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields="sheets(properties(title))",
        ).execute()
        tabs = [s["properties"]["title"] for s in ss.get("sheets", [])]
    except HttpError as e:
        rec["error"] = f"sheets list-tabs {e.status_code}"
        return rec
    except Exception as e:
        rec["error"] = f"sheets list-tabs {type(e).__name__}: {e}"
        return rec
    rec["n_tabs"] = len(tabs)

    if tabs:
        ranges = [f"'{t}'!1:1" for t in tabs]
        try:
            batch = sheets_api.spreadsheets().values().batchGet(
                spreadsheetId=sheet_id,
                ranges=ranges,
                majorDimension="ROWS",
            ).execute()
            for tab, vrange in zip(tabs, batch.get("valueRanges", [])):
                rows = vrange.get("values") or []
                headers = rows[0] if rows else []
                pii = detect_pii_headers(headers)
                if pii:
                    rec["pii_headers_by_tab"][tab] = pii
        except HttpError as e:
            rec["error"] = f"sheets batchGet {e.status_code}"
        except Exception as e:
            rec["error"] = f"sheets batchGet {type(e).__name__}: {e}"
    return rec


TIER_VIOLATION = "VIOLATION (PII + link-public)"
TIER_INTERNAL_PII = "DAO-INTERNAL (PII; restricted-access OK)"
TIER_PUBLIC_OK = "Public-by-design (no PII columns)"
TIER_RESTRICTED = "Restricted (specific accounts)"
TIER_NO_ACCESS = "RESTRICTED? (SA cannot read)"

TIER_ORDER = {
    TIER_VIOLATION: 0,
    TIER_INTERNAL_PII: 1,
    TIER_PUBLIC_OK: 2,
    TIER_RESTRICTED: 3,
    TIER_NO_ACCESS: 4,
}


def classify(rec: dict) -> str:
    if not rec["accessible"]:
        return TIER_NO_ACCESS
    perms = rec["perms_summary"]
    pii_present = bool(rec["pii_headers_by_tab"])
    public_link = perms.get("anyone_with_link") or perms.get("anyone_can_find")
    if pii_present and public_link:
        return TIER_VIOLATION
    if pii_present:
        return TIER_INTERNAL_PII
    if public_link:
        return TIER_PUBLIC_OK
    return TIER_RESTRICTED


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None, help="Optional CSV output path.")
    parser.add_argument("--show-refs", action="store_true",
                        help="Include the per-sheet list of code paths that reference it.")
    parser.add_argument("--paths", nargs="*", default=None,
                        help="Override repo paths to scan (defaults to ~/Applications/<known repos>).")
    args = parser.parse_args(argv)

    if not SA_PATH.is_file():
        sys.stderr.write(f"Service account credentials missing: {SA_PATH}\n")
        return 1

    roots = [Path(p).expanduser().resolve() for p in args.paths] if args.paths else REPO_ROOT_PATTERNS
    refs = discover_sheet_refs(roots)
    sys.stderr.write(f"Discovered {len(refs)} unique sheet IDs across {len(roots)} repos.\n")

    creds = SACredentials.from_service_account_file(str(SA_PATH), scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    sheets_api = build("sheets", "v4", credentials=creds, cache_discovery=False)

    records = []
    for sid in sorted(refs):
        rec = fetch_sheet_audit(drive, sheets_api, sid)
        rec["referenced_by"] = sorted({str(p) for p in refs[sid]})
        rec["tier"] = classify(rec)
        records.append(rec)
        sys.stderr.write(f"  {rec['tier']:<48} {rec['title'] or sid}\n")

    print("# Codebase-referenced Google Sheets — audit\n")
    print(f"_{len(records)} unique sheets discovered across the codebase._")
    print()
    print("| Tier | Title | Sharing | PII columns | Files | Sheet ID |")
    print("|---|---|---|---|---|---|")
    for rec in sorted(records, key=lambda r: (TIER_ORDER.get(r["tier"], 9), r["title"] or r["sheet_id"])):
        perms = rec["perms_summary"]
        if not rec["accessible"]:
            sharing = f"_{rec['error']}_"
        else:
            bits = []
            if perms.get("anyone_can_find"): bits.append("anyone_can_find")
            elif perms.get("anyone_with_link"): bits.append("anyone_with_link")
            if perms.get("domain_shares"): bits.append("domain:" + ",".join(perms["domain_shares"]))
            bits.append(f"users={perms.get('user_count', 0)}")
            if perms.get("group_count"): bits.append(f"groups={perms.get('group_count')}")
            sharing = " · ".join(bits)
        pii_summary = ""
        if rec["pii_headers_by_tab"]:
            pii_summary = "; ".join(
                f"**{tab}**: {', '.join(cols)}" for tab, cols in rec["pii_headers_by_tab"].items()
            )
        title = rec["title"] or "(no access)"
        print(f"| {rec['tier']} | {title} | {sharing} | {pii_summary or '—'} | {len(rec['referenced_by'])} | `{rec['sheet_id']}` |")

    if args.show_refs:
        print("\n## References per sheet\n")
        for rec in sorted(records, key=lambda r: (TIER_ORDER.get(r["tier"], 9), r["title"] or r["sheet_id"])):
            title = rec["title"] or rec["sheet_id"]
            print(f"### {title}  \n_{rec['tier']} — {rec['sheet_id']}_\n")
            for r in rec["referenced_by"]:
                print(f"- `{r}`")
            print()

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["tier", "title", "sheet_id", "anyone_with_link", "anyone_can_find",
                        "domain_shares", "user_count", "owner", "pii_columns", "n_refs", "referenced_by"])
            for rec in records:
                perms = rec["perms_summary"]
                pii_join = "; ".join(
                    f"{tab}: {', '.join(cols)}" for tab, cols in rec["pii_headers_by_tab"].items()
                )
                w.writerow([
                    rec["tier"], rec["title"], rec["sheet_id"],
                    perms.get("anyone_with_link", False),
                    perms.get("anyone_can_find", False),
                    ",".join(perms.get("domain_shares", [])),
                    perms.get("user_count", 0),
                    perms.get("owner", ""),
                    pii_join,
                    len(rec["referenced_by"]),
                    " | ".join(rec["referenced_by"]),
                ])
        sys.stderr.write(f"\nCSV written to {args.csv}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
