#!/usr/bin/env python3
"""
Audit SCHEMA.md for potentially-PII columns.

SCHEMA.md (in the tokenomics repo) is hand-curated by operators and lists,
for every sheet the codebase interacts with: the URL, every column's name
and description, and the source files that read or write each tab. That
makes it the cleanest source of truth for "where does PII live in our
ledger" — better than a Drive-API scan, which is blocked on every sheet
the audit account is not on.

This script parses SCHEMA.md, flags any column whose NAME or DESCRIPTION
suggests PII (email / phone / address / etc.), groups results by
workbook, and prints a report ready for sharing-policy triage.

Usage:
    python3 scripts/audit_schema_pii.py
    python3 scripts/audit_schema_pii.py --detailed     # full per-tab listing
    python3 scripts/audit_schema_pii.py --schema /path/to/SCHEMA.md
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_SCHEMA = Path.home() / "Applications" / "tokenomics" / "SCHEMA.md"

PII_TOKENS = (
    "email", "e-mail", "phone", "mobile",
    "tel ", "telephone", "contact ", "owner email",
    "address", "street", "city", "zip", "postcode", "postal",
    "passport", "ssn", "tax id", "tax_id", "license",
    "subscriber", "to_email", "from_email", "recipient",
    "buyer email", "manager email", "phone_number",
)

# Allowed false positives — tokens that match PII_TOKENS but in context are
# not PII columns (e.g. "tel " catching "TELL" wouldn't, but "address" catches
# "store_address" which IS PII for a B2B partner; we keep that flagged on
# purpose — operator triages).
TOKEN_ALLOWLIST = {
    "addressed", "address book", "addressing",  # rare; precaution.
}

SHEET_HEADER_RE = re.compile(r"^#####\s*Sheet:\s*`?([^`\n]+?)`?\s*$", re.MULTILINE)
SHEET_URL_RE = re.compile(r"\*\*Sheet URL:\*\*\s*(\S+)", re.MULTILINE)
USED_BY_RE = re.compile(
    r"\*\*Used by:\*\*\s*\n((?:- .+\n?)+)", re.MULTILINE
)
COLUMN_ROW_RE = re.compile(
    r"^\|\s*([A-Z]{1,2})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$",
    re.MULTILINE,
)
WORKBOOK_ID_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})")
GID_RE = re.compile(r"[#&?]gid=(\d+)")


def looks_like_pii(name: str, desc: str) -> bool:
    blob = f"{name} {desc}".lower()
    if any(tok in blob for tok in TOKEN_ALLOWLIST):
        return False
    return any(tok in blob for tok in PII_TOKENS)


def parse_schema(text: str) -> list[dict]:
    """Return [{workbook_id, gid, tab, url, columns, pii_columns, used_by}]."""
    # Split by sheet header. Each section spans from one header to the next (or EOF).
    headers = list(SHEET_HEADER_RE.finditer(text))
    sections = []
    for i, m in enumerate(headers):
        start = m.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section_text = text[start:end]
        tab_name = m.group(1).strip()

        url_match = SHEET_URL_RE.search(section_text)
        url = url_match.group(1).rstrip(".,") if url_match else ""
        wb_match = WORKBOOK_ID_RE.search(url)
        gid_match = GID_RE.search(url)
        workbook_id = wb_match.group(1) if wb_match else ""
        gid = gid_match.group(1) if gid_match else ""

        columns = []
        pii_columns = []
        # Skip the header divider row(s); only collect rows whose first cell is a column letter.
        for col_match in COLUMN_ROW_RE.finditer(section_text):
            col_letter, col_name, col_type, col_desc = col_match.groups()
            # Skip the table's separator-pseudo-row (e.g. "|--------|------|...")
            if col_letter.upper() in {"-", "--", "---"}:
                continue
            columns.append({
                "letter": col_letter,
                "name": col_name.strip(),
                "type": col_type.strip(),
                "desc": col_desc.strip(),
            })
            if looks_like_pii(col_name, col_desc):
                pii_columns.append(columns[-1])

        used_by = []
        ub_match = USED_BY_RE.search(section_text)
        if ub_match:
            for line in ub_match.group(1).splitlines():
                line = line.strip()
                if line.startswith("- "):
                    used_by.append(line[2:].strip())

        sections.append({
            "tab": tab_name,
            "workbook_id": workbook_id,
            "gid": gid,
            "url": url,
            "columns": columns,
            "pii_columns": pii_columns,
            "used_by": used_by,
        })
    return sections


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA,
                        help=f"Path to SCHEMA.md (default: {DEFAULT_SCHEMA}).")
    parser.add_argument("--detailed", action="store_true",
                        help="Include per-tab column-level detail (long).")
    parser.add_argument("--include-clean", action="store_true",
                        help="Also list tabs with no PII columns (default: hide).")
    args = parser.parse_args(argv)

    if not args.schema.is_file():
        sys.stderr.write(f"SCHEMA.md not found: {args.schema}\n")
        return 1

    text = args.schema.read_text(encoding="utf-8")
    sections = parse_schema(text)

    by_workbook: dict[str, list[dict]] = defaultdict(list)
    for sec in sections:
        if sec["workbook_id"]:
            by_workbook[sec["workbook_id"]].append(sec)

    print(f"# SCHEMA.md PII audit\n")
    print(f"_Source: {args.schema}_\n")
    print(f"_{len(sections)} tabs across {len(by_workbook)} workbooks documented._\n")

    # Workbook-level summary (the actual sharing-policy unit).
    print("## Workbook summary\n")
    print("| Workbook ID | # tabs | # tabs w/ PII | PII column samples |")
    print("|---|---|---|---|")
    rows = []
    for wb_id, tabs in by_workbook.items():
        pii_tabs = [t for t in tabs if t["pii_columns"]]
        sample_cols = []
        for t in pii_tabs[:3]:
            for c in t["pii_columns"][:3]:
                sample_cols.append(f"{t['tab']}/{c['name']}")
        rows.append((len(pii_tabs), wb_id, len(tabs), sample_cols))
    rows.sort(key=lambda r: (-r[0], r[1]))
    for npii, wb_id, ntabs, sample in rows:
        sample_str = "; ".join(sample[:4]) if sample else "—"
        print(f"| `{wb_id}` | {ntabs} | {npii} | {sample_str} |")

    print("\n## Tabs flagged with PII columns\n")
    flagged = [s for s in sections if s["pii_columns"]]
    if not flagged:
        print("_No tabs flagged. Heuristic missed something? Pass --detailed to inspect._\n")
    else:
        print("| Workbook | Tab | gid | PII columns | Used-by files |")
        print("|---|---|---|---|---|")
        for sec in sorted(flagged, key=lambda s: (s["workbook_id"], s["tab"])):
            cols = "; ".join(f"**{c['letter']}** {c['name']}" for c in sec["pii_columns"])
            n_refs = len(sec["used_by"])
            print(f"| `{sec['workbook_id'][:14]}…` | {sec['tab']} | {sec['gid'] or '—'} | {cols} | {n_refs} |")

    if args.include_clean:
        clean = [s for s in sections if not s["pii_columns"]]
        print(f"\n## Tabs with no PII columns flagged ({len(clean)})\n")
        for sec in sorted(clean, key=lambda s: (s["workbook_id"], s["tab"])):
            print(f"- `{sec['workbook_id'][:14]}…` / {sec['tab']}")

    if args.detailed:
        print("\n## Detailed per-tab PII listing\n")
        for sec in sorted(flagged, key=lambda s: (s["workbook_id"], s["tab"])):
            print(f"### {sec['tab']}\n")
            print(f"**Workbook:** `{sec['workbook_id']}` · **gid:** {sec['gid'] or '—'}  ")
            print(f"**URL:** {sec['url']}\n")
            print("**PII columns:**\n")
            for c in sec["pii_columns"]:
                desc_truncated = c["desc"][:160] + ("…" if len(c["desc"]) > 160 else "")
                print(f"- **{c['letter']}** `{c['name']}` ({c['type']}): {desc_truncated}")
            if sec["used_by"]:
                print(f"\n**Used by ({len(sec['used_by'])}):**")
                for u in sec["used_by"]:
                    print(f"- {u}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
