#!/usr/bin/env python3
"""
Extract partner addresses from local repo HTML (agroverse_shop/partners/*/index.html)
and populate the Main Ledger → "Agroverse Partners" column J (address).

Usage:
  python3 extract_partner_addresses_from_repo.py \
    --sheet 1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU \
    --partners-tab "Agroverse Partners" \
    [--refresh-existing] [--only slug1,slug2]

Notes:
  - Reads HTML from local repo: agroverse_shop/partners/<partner_id>/index.html
  - Extract strategy (in order):
      1) .partner-hero-content > p (often contains the address line)
      2) .info-row where .info-label == 'Location' → sibling .info-value text
  - Normalizes to single line: "street1, city, ST ZIP, country?" (no hard country append)
  - Writes to "Agroverse Partners" column J (header = address)

Credentials:
  - Set GOOGLE_APPLICATION_CREDENTIALS or DAO_CLIENT_GOOGLE_CREDENTIALS to a
    service account JSON with Sheets write access.
"""

import argparse
import os
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[2]
PARTNERS_DIR = REPO_ROOT / 'agroverse_shop' / 'partners'


def normalize_address(text: str) -> str:
    s = re.sub(r"\s*,\s*", ", ", text or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def extract_from_html_file(html_path: Path) -> str | None:
    try:
        html = html_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return None
    soup = BeautifulSoup(html, 'html.parser')

    # Strategy 1: .partner-hero-content > p
    hero = soup.select_one('.partner-hero-content p')
    if hero:
        t = normalize_address(hero.get_text(" ", strip=True))
        # Heuristic: require comma ("street, city") or ZIP-like digits
        if "," in t or re.search(r"\b\d{5}(?:-\d{4})?\b", t):
            return t

    # Strategy 2: info-row with Location label
    for row in soup.select('.info-row'):
        label = row.select_one('.info-label')
        value = row.select_one('.info-value')
        if label and value and label.get_text(strip=True).lower() == 'location':
            t = normalize_address(value.get_text(" ", strip=True))
            if t:
                return t

    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sheet', required=True)
    ap.add_argument('--partners-tab', dest='partners_tab', default=None,
                    help='Partners tab name (legacy). When omitted, looks up by --partners-gid.')
    ap.add_argument('--partners-gid', dest='partners_gid', type=int, default=1983902109,
                    help='Partners tab gid (stable across renames). Default is the current '
                         'Main Ledger partners tab; only override for testing alternate workbooks.')
    ap.add_argument('--only', help='Comma-separated partner_id list to limit updates')
    ap.add_argument('--refresh-existing', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    # Collect local partner pages
    if not PARTNERS_DIR.exists():
        print(f"Partners directory not found: {PARTNERS_DIR}", file=sys.stderr)
        return 1

    local_map = {}
    for entry in sorted(PARTNERS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        slug = entry.name
        if slug == 'index.html':
            continue
        if args.only and slug not in {s.strip() for s in args.only.split(',')}:
            continue
        html_file = entry / 'index.html'
        if not html_file.exists():
            continue
        addr = extract_from_html_file(html_file)
        if addr:
            local_map[slug] = addr

    if not local_map:
        print('No addresses extracted from local partner pages.')
        return 0

    # Write to Google Sheet column J
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print('Missing deps. Run: pip install gspread google-auth beautifulsoup4', file=sys.stderr)
        return 1

    sa_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') or os.environ.get('DAO_CLIENT_GOOGLE_CREDENTIALS')
    if not sa_path or not os.path.exists(sa_path):
        print('Set GOOGLE_APPLICATION_CREDENTIALS (or DAO_CLIENT_GOOGLE_CREDENTIALS) to a service account JSON.', file=sys.stderr)
        return 1

    creds = Credentials.from_service_account_file(sa_path, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(args.sheet)
    if args.partners_tab:
        ws = sh.worksheet(args.partners_tab)
    else:
        ws = sh.get_worksheet_by_id(args.partners_gid)
        if ws is None:
            print(f'Partners tab not found by gid {args.partners_gid}', file=sys.stderr)
            return 1

    rows = ws.get_all_values()
    if not rows:
        print('No rows found in sheet', file=sys.stderr)
        return 1

    header = rows[0]
    def col_idx(name, default=None):
        for i, h in enumerate(header):
            if h.strip().lower() == name.strip().lower():
                return i
        return default

    idx_id = col_idx('partner_id', 0)
    idx_addr = col_idx('address', 9)  # J
    if idx_addr is None:
        # If no Address column, append it
        header.append('address')
        ws.update_cell(1, len(header), 'address')
        idx_addr = len(header) - 1

    # Build row map by partner_id
    pid_to_row = {}
    for r, row in enumerate(rows[1:], start=2):
        if idx_id < len(row):
            pid = (row[idx_id] or '').strip()
            if pid:
                pid_to_row[pid] = r

    updates = []
    for pid, addr in local_map.items():
        r = pid_to_row.get(pid)
        if not r:
            continue
        existing = ''
        if r - 1 < len(rows) and idx_addr < len(rows[r - 1]):
            existing = (rows[r - 1][idx_addr] or '').strip()
        if existing and not args.refresh_existing:
            continue
        updates.append((r, addr))

    if not updates:
        print('No updates to apply (addresses already present or no matching rows).')
        return 0

    if args.dry_run:
        for r, addr in updates:
            print(f'DRY RUN: Row {r} ← {addr}')
        return 0

    for r, addr in updates:
        ws.update_cell(r, idx_addr + 1, addr)
    print(f'Updated {len(updates)} rows.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

