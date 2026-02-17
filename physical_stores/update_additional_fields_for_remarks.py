#!/usr/bin/env python3
"""
Update additional fields for specific remarks that were already processed but may be missing fields.

This script processes the 22 specific remarks we identified, updating:
- Contact Person (with special handling for EarthTones - Mary, not Greg)
- Cell Phone
- Instagram
- Outcome
- Visit Date
- Contact Method
- Follow Up Date
- Calendar events where needed
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_SHEET = "Hit List"
DAPP_REMARKS_SHEET = "DApp Remarks"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheets_client() -> gspread.Client:
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(f"Google credentials not found at {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


def extract_cell_phone(text: str) -> Optional[str]:
    """Extract cell phone number."""
    pattern = r'(?:cell\s+phone|cell|mobile)\s*:?\s*\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\d{10}', match.group())
        if phone_match:
            phone = re.sub(r'[^\d]', '', phone_match.group())
            if len(phone) == 10:
                return f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
    return None


def extract_instagram(text: str) -> Optional[str]:
    """Extract Instagram URL."""
    pattern = r'(https?://(?:www\.)?instagram\.com/[^\s]+)'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def extract_contact_person(text: str, shop_name: str) -> Optional[str]:
    """Extract contact person - special case for EarthTones (Mary, not Greg)."""
    if "earthtones" in shop_name.lower() and "mary" in text.lower():
        return "Mary"
    
    # Look for priority names
    priority_names = ['Stephanie', 'Mary', 'Holley', 'Holly', 'Niccolina', 'Nicolina']
    for name in priority_names:
        if name.lower() in text.lower():
            return name
    
    # Pattern matching
    patterns = [
        r'([A-Z][a-z]+)\s+(?:is|was|will be|mentioned|said|handles|takes)',
        r'signed\s+(?:consignment|agreement)\s+with\s+([A-Z][a-z]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name.lower() not in ['the', 'this', 'that', 'next', 'last', 'first']:
                return name
    return None


def extract_follow_up_date(text: str) -> Optional[str]:
    """Extract follow-up date."""
    # Look for specific dates
    if '3rd dec' in text.lower() or 'dec 3' in text.lower():
        return "2025-12-03"
    elif '28th nov' in text.lower() or 'nov 28' in text.lower():
        return "2025-11-28"
    elif 'next monday' in text.lower() and '10' in text.lower():
        today = datetime.now()
        days_ahead = (0 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        next_monday = today + timedelta(days=days_ahead)
        return next_monday.strftime('%Y-%m-%d 10:00')
    elif 'thursday' in text.lower():
        today = datetime.now()
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        next_thursday = today + timedelta(days=days_ahead)
        return next_thursday.strftime('%Y-%m-%d')
    return None


def main():
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    hit_list_ws = spreadsheet.worksheet(HIT_LIST_SHEET)
    remarks_ws = spreadsheet.worksheet(DAPP_REMARKS_SHEET)
    
    # Get all data
    hit_values = hit_list_ws.get_all_values()
    remarks_values = remarks_ws.get_all_values()
    
    hit_headers = hit_values[0]
    hit_index = {h.strip().replace('\ufeff', ''): i for i, h in enumerate(hit_headers)}
    
    remarks_headers = remarks_values[0]
    remarks_index = {h.strip().replace('\ufeff', ''): i for i, h in enumerate(remarks_headers)}
    
    # Build shop lookup
    shop_lookup = {}
    for row_num, row in enumerate(hit_values[1:], start=2):
        name = row[hit_index["Shop Name"]].strip() if hit_index["Shop Name"] < len(row) else ""
        if name:
            shop_lookup[name.lower()] = row_num
    
    # The 22 specific remarks we identified (shop name, status, expected updates)
    target_remarks = [
        ("Earth Impact", "Manager Follow-up", {"contact_person": "Stephanie", "follow_up_date": "next Monday 10am"}),
        ("Go Ask Alice", "Manager Follow-up", {"contact_method": "In Person", "visit_date": True}),
        ("Moon Kissed", "Not Appropriate", {}),
        ("Go Ask Alice", "Partnered", {"contact_person": "Niccolina", "outcome": "Partnered - Consignment agreement signed", "contact_method": "In Person", "visit_date": True}),
        ("Go Ask Alice", "Partnered", {"contact_person": "Niccolina", "outcome": "Partnered - Consignment agreement signed", "contact_method": "In Person", "visit_date": True}),  # Duplicate
        ("Apotheca", "Rejected", {"outcome": "Rejected - Not set up for consignment, already carry own cacao"}),
        ("Unique Shop", "Rejected", {"outcome": "Rejected - Theme not aligned"}),
        ("Hacker Dojo", "Partnered", {"outcome": "Partnered - Consignment agreement signed"}),
        ("Mystic Soul Ritual Shop", "Shortlisted", {"instagram": "https://www.instagram.com/mysticsoulritualshop/"}),
        ("The Mindshop (Gifts from the Heart)", "Rejected", {"outcome": "Rejected - No space, doesn't know product"}),
        ("The Mindshop (Gifts from the Heart)", "Rejected", {"outcome": "Rejected - Space constraints, doesn't offer food"}),
        ("The Mindshop (Gifts from the Heart)", "Rejected", {"outcome": "Rejected - Did not check email"}),
        ("Air and Fire, A Mystical Bazaar", "On Hold", {}),
        ("Infinity Coven", "On Hold", {}),
        ("Small Town Sweets", "On Hold", {}),
        ("EarthTones Gifts, Gallery & Center for Healing", "Manager Follow-up", {"contact_person": "Mary", "follow_up_date": "Thursday"}),
        ("Spice of Life", "Manager Follow-up", {"cell_phone": "(805) 610-4130", "follow_up_date": "2025-12-03"}),
        ("Spice of Life", "Manager Follow-up", {}),
        ("The Natural Alternative Nutrition Center", "Manager Follow-up", {"contact_person": "Holley", "follow_up_date": "2025-11-28"}),
        ("The Natural Alternative Nutrition Center", "Manager Follow-up", {"contact_person": "Holley"}),
        ("The Natural Alternative Nutrition Center", "Manager Follow-up", {"contact_person": "Holley"}),
        ("The Natural Alternative Nutrition Center", "Manager Follow-up", {"contact_person": "Holley"}),
    ]
    
    print("=" * 80)
    print("UPDATING ADDITIONAL FIELDS FOR IDENTIFIED REMARKS")
    print("=" * 80)
    print()
    
    # Find and process each remark
    updated_count = 0
    
    for shop_name, status, expected_updates in target_remarks:
        # Find the remark
        remark_row = None
        remarks_text = ""
        
        for row_num, row in enumerate(remarks_values[1:], start=2):
            r_shop = row[remarks_index["Shop Name"]].strip() if remarks_index["Shop Name"] < len(row) else ""
            r_status = row[remarks_index["Status"]].strip() if remarks_index["Status"] < len(row) else ""
            
            if r_shop == shop_name and r_status == status:
                remark_row = row
                remarks_text = row[remarks_index["Remarks"]].strip() if remarks_index["Remarks"] < len(row) else ""
                break
        
        if not remark_row:
            print(f"[SKIP] {shop_name} ({status}) - Remark not found")
            continue
        
        # Find shop in Hit List
        shop_row_num = shop_lookup.get(shop_name.lower())
        if not shop_row_num:
            print(f"[SKIP] {shop_name} - Not found in Hit List")
            continue
        
        print(f"\n[PROCESSING] {shop_name} ({status})")
        
        # Extract data from remarks
        cell_phone = extract_cell_phone(remarks_text)
        instagram = extract_instagram(remarks_text)
        contact_person = extract_contact_person(remarks_text, shop_name)
        follow_up_date = extract_follow_up_date(remarks_text)
        
        # Determine outcome based on status
        outcome = None
        if status == "Partnered":
            outcome = "Partnered - Consignment agreement signed"
        elif status == "Rejected":
            reason = remarks_text[:80] if remarks_text else "Rejected"
            outcome = f"Rejected - {reason}"
        
        # Determine contact method and visit date
        contact_method = None
        visit_date = None
        if status == "Partnered" and ('dropped off' in remarks_text.lower() or 'visit' in remarks_text.lower()):
            contact_method = "In Person"
            visit_date = datetime.now().strftime('%Y-%m-%d')
        elif status == "Manager Follow-up":
            if 'popped by' in remarks_text.lower() or 'visit' in remarks_text.lower():
                contact_method = "In Person"
                visit_date = datetime.now().strftime('%Y-%m-%d')
            elif 'call' in remarks_text.lower():
                contact_method = "Phone"
        
        # Update fields
        updates_made = []
        
        if cell_phone and "Cell Phone" in hit_index:
            current = hit_values[shop_row_num - 1][hit_index["Cell Phone"]].strip() if hit_index["Cell Phone"] < len(hit_values[shop_row_num - 1]) else ""
            if not current:
                hit_list_ws.update_cell(shop_row_num, hit_index["Cell Phone"] + 1, cell_phone)
                updates_made.append(f"Cell Phone: {cell_phone}")
        
        if instagram and "Instagram" in hit_index:
            current = hit_values[shop_row_num - 1][hit_index["Instagram"]].strip() if hit_index["Instagram"] < len(hit_values[shop_row_num - 1]) else ""
            if not current:
                hit_list_ws.update_cell(shop_row_num, hit_index["Instagram"] + 1, instagram)
                updates_made.append(f"Instagram: {instagram}")
        
        if contact_person and "Contact Person" in hit_index:
            current = hit_values[shop_row_num - 1][hit_index["Contact Person"]].strip() if hit_index["Contact Person"] < len(hit_values[shop_row_num - 1]) else ""
            if not current or (shop_name == "EarthTones Gifts, Gallery & Center for Healing" and "Mary" in contact_person):
                hit_list_ws.update_cell(shop_row_num, hit_index["Contact Person"] + 1, contact_person)
                updates_made.append(f"Contact Person: {contact_person}")
        
        if follow_up_date and "Follow Up Date" in hit_index:
            current = hit_values[shop_row_num - 1][hit_index["Follow Up Date"]].strip() if hit_index["Follow Up Date"] < len(hit_values[shop_row_num - 1]) else ""
            if not current:
                hit_list_ws.update_cell(shop_row_num, hit_index["Follow Up Date"] + 1, follow_up_date)
                updates_made.append(f"Follow Up Date: {follow_up_date}")
                print(f"       📅 Calendar event needed for: {follow_up_date}")
        
        if outcome and "Outcome" in hit_index:
            current = hit_values[shop_row_num - 1][hit_index["Outcome"]].strip() if hit_index["Outcome"] < len(hit_values[shop_row_num - 1]) else ""
            if not current:
                hit_list_ws.update_cell(shop_row_num, hit_index["Outcome"] + 1, outcome)
                updates_made.append(f"Outcome: {outcome}")
        
        if contact_method and "Contact Method" in hit_index:
            current = hit_values[shop_row_num - 1][hit_index["Contact Method"]].strip() if hit_index["Contact Method"] < len(hit_values[shop_row_num - 1]) else ""
            if not current:
                hit_list_ws.update_cell(shop_row_num, hit_index["Contact Method"] + 1, contact_method)
                updates_made.append(f"Contact Method: {contact_method}")
        
        if visit_date and "Visit Date" in hit_index:
            current = hit_values[shop_row_num - 1][hit_index["Visit Date"]].strip() if hit_index["Visit Date"] < len(hit_values[shop_row_num - 1]) else ""
            if not current:
                hit_list_ws.update_cell(shop_row_num, hit_index["Visit Date"] + 1, visit_date)
                updates_made.append(f"Visit Date: {visit_date}")
        
        if updates_made:
            print(f"       ✅ Updated: {', '.join(updates_made)}")
            updated_count += 1
        else:
            print(f"       ℹ️  No updates needed (fields already populated)")
    
    print(f"\n{'=' * 80}")
    print(f"✅ Complete! Updated {updated_count} shops with additional fields.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()






