#!/usr/bin/env python3
"""
Scrape partner addresses from agroverse.shop partner pages and populate
the Main Ledger → "Agroverse Partners" column J (address).

Usage:
  python3 scrape_partner_addresses.py --sheet "1GE7PUq-..." \
      --partners-tab "Agroverse Partners" \
      --base-url "https://agroverse.shop/partners/" \
      --dry-run

Notes:
  - Expects column A = partner_id, C = partner_page_url, J = address (target).
  - Extracts an address block from the partner page (heuristics):
      • elements with class/id containing "address"
      • <a href="https://maps.google.com/..."> anchor text
      • fallback: microdata/structured hints if present (basic)
  - Writes a normalized single-line address: "street1, city, ST ZIP, country"

Credentials:
  - Use a service account JSON via GOOGLE_APPLICATION_CREDENTIALS, or rely on
    gspread.service_account() default discovery if configured locally.

Idempotent: skips rows where column J already has a value unless
--refresh-existing is set.
"""

import argparse
import os
import re
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def extract_address_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')

    # Collect candidates from common cues
    candidates = []

    # 1) Obvious address containers
    for tag in soup.find_all(True):
        cls = ' '.join(tag.get('class') or [])
        idv = tag.get('id') or ''
        if not cls and not idv:
            continue
        if any(k in cls.lower() for k in ['address', 'addr']) or any(k in idv.lower() for k in ['address', 'addr']):
            txt = tag.get_text('\n', strip=True)
            if txt:
                candidates.append(txt)

    # 2) Google Maps links often contain the printable address
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'google.com/maps' in href or 'maps.google.com' in href:
            t = a.get_text(' ', strip=True)
            if t:
                candidates.append(t)

    # Normalize and pick the longest plausible block
    def normalize(s):
        s = re.sub(r'\s*,\s*', ', ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    candidates = [normalize(c) for c in candidates if c]
    best = max(candidates, key=len) if candidates else None
    if not best or ',' not in best:
        return None
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sheet', required=True, help='Main Ledger spreadsheet ID')
    ap.add_argument('--partners-tab', dest='partners_tab', default='Agroverse Partners')
    ap.add_argument('--base-url', default='https://agroverse.shop/partners/')
    ap.add_argument('--refresh-existing', action='store_true')
    ap.add_argument('--only', help='Comma-separated partner_id list to limit updates')
    ap.add_argument('--timeout', type=float, default=15.0)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    # Auth
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print('Missing deps. Run: pip install gspread google-auth beautifulsoup4 requests', file=sys.stderr)
        return 1

    gc = None
    sa_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') or os.environ.get('DAO_CLIENT_GOOGLE_CREDENTIALS')
    try:
        if sa_path and os.path.exists(sa_path):
            creds = Credentials.from_service_account_file(sa_path, scopes=['https://www.googleapis.com/auth/spreadsheets'])
            gc = gspread.authorize(creds)
        else:
            # Fallback to default discovery
            gc = gspread.service_account()
    except Exception as e:
        print(f'Google auth failed: {e}', file=sys.stderr)
        return 1

    sh = gc.open_by_key(args.sheet)
    ws = sh.worksheet(args.partners_tab)

    rows = ws.get_all_values()
    if not rows:
        print('No rows found', file=sys.stderr)
        return 1

    header = rows[0]

    def col_idx(name, default=None):
        for i, h in enumerate(header):
            if h.strip().lower() == name.strip().lower():
                return i
        return default

    idx_id = col_idx('partner_id', 0)
    idx_url = col_idx('partner_page_url', 2)
    idx_addr = col_idx('address', 9)  # J

    only_set = set([s.strip() for s in (args.only or '').split(',') if s.strip()]) if args.only else None

    updates = []  # (row_number, value)
    for r, row in enumerate(rows[1:], start=2):
        pid = (row[idx_id] or '').strip()
        if not pid:
            continue
        if only_set and pid not in only_set:
            continue

        existing = (row[idx_addr] or '').strip() if idx_addr is not None and idx_addr < len(row) else ''
        if existing and not args.refresh_existing:
            continue

        url = (row[idx_url] or '').strip() if idx_url is not None and idx_url < len(row) else ''
        if not url:
            url = urljoin(args.base_url, pid)

        try:
            resp = requests.get(url, timeout=args.timeout)
            if resp.ok:
                addr = extract_address_from_html(resp.text)
                if addr:
                    updates.append((r, addr))
                else:
                    print(f'No address found on page for {pid}: {url}', file=sys.stderr)
            else:
                print(f'HTTP {resp.status_code} for {pid}: {url}', file=sys.stderr)
        except Exception as e:
            print(f'Fetch error for {pid}: {e}', file=sys.stderr)

    if not updates:
        print('No updates to apply.')
        return 0

    if args.dry_run:
        for r, addr in updates:
            print(f'DRY RUN: Row {r} ← {addr}')
        return 0

    # Ensure the sheet has an Address column J; extend rows if needed
    # Batch update via range values
    addr_col = idx_addr + 1 if idx_addr is not None else 10  # default J=10
    for r, addr in updates:
        ws.update_cell(r, addr_col, addr)
    print(f'Updated {len(updates)} rows.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
