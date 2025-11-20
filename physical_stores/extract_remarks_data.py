#!/usr/bin/env python3
"""
Extract structured information from a specific DApp Remarks submission
and update the corresponding Hit List row with the extracted data.

Usage:
    python3 extract_remarks_data.py <submission_id>
    python3 extract_remarks_data.py 5f15fb03-cb19-4983-8d94-31be4e9a3956 --dry-run
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Optional

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
    # Look for credentials in parent directory (repository root)
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {creds_path}. "
            "Please add google_credentials.json with service account credentials in the repository root."
        )

    creds = Credentials.from_service_account_file(
        str(creds_path),
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    return client


def extract_phone(text: str) -> Optional[str]:
    """Extract phone number from text."""
    # Match various phone formats: (650) 420-5932, 650-420-5932, 650.420.5932, etc.
    patterns = [
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
        r'\d{10}',  # 10 digits
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            phone = re.sub(r'[^\d]', '', match.group())
            if len(phone) == 10:
                return f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
    return None


def extract_cell_phone(text: str) -> Optional[str]:
    """Extract cell phone number from text (specifically looking for 'cell phone' or 'mobile' patterns)."""
    # Look for "cell phone", "cell", "mobile", "mobile phone" followed by a phone number
    cell_patterns = [
        r'(?:cell\s+phone|cell|mobile\s+phone|mobile)\s*:?\s*\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'(?:cell\s+phone|cell|mobile\s+phone|mobile)\s*:?\s*\d{10}',
    ]
    for pattern in cell_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Extract just the phone number part
            phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\d{10}', match.group())
            if phone_match:
                phone = re.sub(r'[^\d]', '', phone_match.group())
                if len(phone) == 10:
                    return f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
    return None


def extract_email(text: str) -> Optional[str]:
    """Extract email address from text."""
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(pattern, text)
    return match.group() if match else None


def extract_website(text: str) -> Optional[str]:
    """Extract website URL from text."""
    patterns = [
        r'https?://[^\s]+',
        r'www\.[^\s]+',
        r'[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?',  # domain.com or domain.co.uk
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            url = match.strip('.,;')
            if not url.startswith('http'):
                url = 'http://' + url
            # Skip common non-website patterns
            if not any(skip in url.lower() for skip in ['instagram.com', 'facebook.com', '@']):
                return url
    return None


def extract_instagram(text: str) -> Optional[str]:
    """Extract Instagram handle or URL from text."""
    patterns = [
        r'instagram\.com/([a-zA-Z0-9_.]+)',
        r'@([a-zA-Z0-9_.]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            handle = match.group(1) if match.lastindex else match.group(0)
            if not handle.startswith('@'):
                handle = '@' + handle
            return handle
    return None


def extract_address(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract address, city, and state from text."""
    address = None
    city = None
    state = None
    
    # Common state abbreviations
    state_pattern = r'\b([A-Z]{2})\b'
    state_match = re.search(state_pattern, text)
    if state_match:
        state = state_match.group(1)
    
    # Try to find address patterns (number + street name with street suffix)
    # Must end with a street suffix to avoid false positives
    address_patterns = [
        r'(\d+\s+[A-Za-z0-9\s]+(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court|Pl|Place|Blvd|Parkway|Pkwy))',
    ]
    for pattern in address_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            potential_address = match.group(1).strip()
            # Filter out false positives (like "10 o'clock")
            if len(potential_address.split()) >= 2 and not any(word.lower() in ['o', 'clock', 'am', 'pm'] for word in potential_address.split()):
                address = potential_address
                break
    
    # Try to find city (word before state or common city patterns)
    if state:
        city_pattern = rf'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),?\s*{state}'
        city_match = re.search(city_pattern, text)
        if city_match:
            city = city_match.group(1).strip()
    
    return address, city, state


def extract_contact_person(text: str) -> Optional[str]:
    """Extract contact person name from text."""
    # Look for patterns like "[name] is", "[name] mentioned", "call [name]", etc.
    # Prioritize names that appear before "is", "was", "mentioned", etc.
    patterns = [
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:is|was|will be|mentioned|said|still)',
        r'(?:call|contact|speak with|talk to|meet with|schedule with|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        r'([A-Z][a-z]+)\s+(?:the|a|an)\s+(?:staff|manager|owner|contact)',
    ]
    found_names = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            name = match.group(1).strip()
            # Filter out common false positives
            if name.lower() not in ['the', 'this', 'that', 'next', 'last', 'first', 'her', 'him', 'them', 'to']:
                if name not in found_names:
                    found_names.append(name)
    
    # Return the first valid name found
    return found_names[0] if found_names else None


def extract_follow_up_date(text: str) -> Optional[str]:
    """Extract follow-up date information from text and convert to YYYY-MM-DD format."""
    from datetime import datetime, date
    
    # Look for specific date patterns like "3rd Dec", "Dec 3", "December 3rd", etc.
    date_patterns = [
        r'(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|September|Oct|October|Nov|November|Dec|December)',
        r'(Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|September|Oct|October|Nov|November|Dec|December)\s+(\d{1,2})(?:st|nd|rd|th)?',
        r'(\d{4})-(\d{2})-(\d{2})',  # ISO format
        r'(\d{1,2})/(\d{1,2})/(\d{4})',  # MM/DD/YYYY
        r'(\d{1,2})/(\d{1,2})/(\d{2})',  # MM/DD/YY
    ]
    
    month_map = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
        'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
        'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }
    
    # Try to find date patterns
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if len(match.groups()) == 2:  # Day Month or Month Day format
                    groups = match.groups()
                    # Check if first group is month name
                    if groups[0].lower() in month_map:
                        month = month_map[groups[0].lower()]
                        day = int(re.sub(r'[^\d]', '', groups[1]))
                    else:
                        day = int(re.sub(r'[^\d]', '', groups[0]))
                        month = month_map[groups[1].lower()]
                    
                    # Determine year (assume current year or next year if date has passed)
                    current_year = datetime.now().year
                    follow_date = date(current_year, month, day)
                    if follow_date < date.today():
                        follow_date = date(current_year + 1, month, day)
                    
                    return follow_date.strftime('%Y-%m-%d')
                elif len(match.groups()) == 3:  # ISO or MM/DD/YYYY format
                    groups = match.groups()
                    if len(groups[0]) == 4:  # ISO format YYYY-MM-DD
                        return f"{groups[0]}-{groups[1]}-{groups[2]}"
                    else:  # MM/DD/YYYY or MM/DD/YY
                        month = int(groups[0])
                        day = int(groups[1])
                        year = int(groups[2])
                        if year < 100:
                            year += 2000
                        return f"{year}-{month:02d}-{day:02d}"
            except (ValueError, KeyError):
                continue
    
    # Fallback: Look for relative date patterns
    relative_patterns = [
        r'(?:next|this|on)\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
        r'(?:next|this)\s+week',
        r'(?:next|this)\s+Friday',
    ]
    for pattern in relative_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    
    return None


def extract_structured_data(remarks: str) -> Dict[str, Optional[str]]:
    """Extract structured data from remarks text."""
    extracted = {
        'address': None,
        'city': None,
        'state': None,
        'phone': None,
        'cell_phone': None,
        'email': None,
        'website': None,
        'instagram': None,
        'contact_person': None,
        'follow_up_date': None,
    }
    
    if not remarks:
        return extracted
    
    # Extract phone (regular phone)
    extracted['phone'] = extract_phone(remarks)
    
    # Extract cell phone (specifically marked as cell/mobile)
    extracted['cell_phone'] = extract_cell_phone(remarks)
    
    # Extract email
    extracted['email'] = extract_email(remarks)
    
    # Extract website
    extracted['website'] = extract_website(remarks)
    
    # Extract Instagram
    extracted['instagram'] = extract_instagram(remarks)
    
    # Extract address components
    address, city, state = extract_address(remarks)
    extracted['address'] = address
    extracted['city'] = city
    extracted['state'] = state
    
    # Extract contact person
    extracted['contact_person'] = extract_contact_person(remarks)
    
    # Extract follow-up date
    extracted['follow_up_date'] = extract_follow_up_date(remarks)
    
    return extracted


def find_submission_by_id(client: gspread.Client, submission_id: str) -> Optional[Dict]:
    """Find a submission in DApp Remarks by submission ID."""
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    try:
        remarks_ws = spreadsheet.worksheet(DAPP_REMARKS_SHEET)
    except gspread.WorksheetNotFound:
        raise ValueError(f'Worksheet "{DAPP_REMARKS_SHEET}" not found.')
    
    remarks_values = remarks_ws.get_all_values()
    if len(remarks_values) < 2:
        return None
    
    headers = remarks_values[0]
    headers_idx = {header: idx for idx, header in enumerate(headers)}
    
    if "Submission ID" not in headers_idx:
        raise ValueError('Missing "Submission ID" column in DApp Remarks worksheet.')
    
    submission_idx = headers_idx["Submission ID"]
    
    for row_num, row in enumerate(remarks_values[1:], start=2):
        if row[submission_idx].strip() == submission_id:
            return {
                'row_num': row_num,
                'headers': headers,
                'row': row,
                'headers_idx': headers_idx,
            }
    
    return None


def find_shop_in_hit_list(client: gspread.Client, shop_name: str) -> Optional[Dict]:
    """Find a shop in Hit List by name."""
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    try:
        hit_list_ws = spreadsheet.worksheet(HIT_LIST_SHEET)
    except gspread.WorksheetNotFound:
        raise ValueError(f'Worksheet "{HIT_LIST_SHEET}" not found.')
    
    hit_values = hit_list_ws.get_all_values()
    if len(hit_values) < 2:
        return None
    
    headers = hit_values[0]
    headers_idx = {header: idx for idx, header in enumerate(headers)}
    
    if "Shop Name" not in headers_idx:
        raise ValueError('Missing "Shop Name" column in Hit List worksheet.')
    
    shop_name_idx = headers_idx["Shop Name"]
    
    for row_num, row in enumerate(hit_values[1:], start=2):
        if row[shop_name_idx].strip().lower() == shop_name.lower():
            return {
                'row_num': row_num,
                'headers': headers,
                'row': row,
                'headers_idx': headers_idx,
            }
    
    return None


def update_hit_list_row(
    client: gspread.Client,
    shop_data: Dict,
    extracted_data: Dict[str, Optional[str]],
    dry_run: bool = False
) -> None:
    """Update Hit List row with extracted data."""
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    hit_list_ws = spreadsheet.worksheet(HIT_LIST_SHEET)
    
    row_num = shop_data['row_num']
    headers_idx = shop_data['headers_idx']
    
    updates = []
    
    # Map extracted fields to Hit List columns
    field_mapping = {
        'address': 'Address',
        'city': 'City',
        'state': 'State',
        'phone': 'Phone',
        'cell_phone': 'Cell Phone',
        'email': 'Email',
        'website': 'Website',
        'instagram': 'Instagram',
        'contact_person': 'Contact Person',
        'follow_up_date': 'Follow Up Date',
    }
    
    for field, column_name in field_mapping.items():
        if column_name in headers_idx and extracted_data[field]:
            col_idx = headers_idx[column_name] + 1  # 1-indexed
            current_value = shop_data['row'][headers_idx[column_name]].strip()
            
            # Only update if current value is empty or different
            if not current_value or current_value != extracted_data[field]:
                updates.append({
                    'col': col_idx,
                    'value': extracted_data[field],
                    'column_name': column_name,
                    'current': current_value,
                })
    
    if not updates:
        print("  ℹ️  No new data to update (all fields already filled or no data extracted).")
        return
    
    print(f"\n  📝 Updates to apply:")
    for update in updates:
        print(f"    - {update['column_name']}: '{update['current']}' → '{update['value']}'")
    
    if not dry_run:
        for update in updates:
            hit_list_ws.update_cell(row_num, update['col'], update['value'])
        print(f"\n  ✅ Successfully updated {len(updates)} field(s) in Hit List.")
    else:
        print(f"\n  🔍 DRY RUN: Would update {len(updates)} field(s) in Hit List.")


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured data from DApp Remarks submission and update Hit List."
    )
    parser.add_argument(
        "submission_id",
        help="Submission ID to process (e.g., 5f15fb03-cb19-4983-8d94-31be4e9a3956)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without updating the sheet."
    )
    args = parser.parse_args()
    
    print("=" * 80)
    print("EXTRACTING DATA FROM DAPP REMARKS SUBMISSION")
    print("=" * 80)
    print(f"\n🔍 Looking for submission ID: {args.submission_id}")
    
    client = get_google_sheets_client()
    
    # Find the submission
    submission = find_submission_by_id(client, args.submission_id)
    if not submission:
        print(f"\n❌ Submission ID '{args.submission_id}' not found in DApp Remarks.")
        return
    
    print(f"✅ Found submission in DApp Remarks (row {submission['row_num']})")
    
    # Extract submission data
    headers_idx = submission['headers_idx']
    row = submission['row']
    
    shop_name = row[headers_idx.get("Shop Name", -1)].strip() if "Shop Name" in headers_idx else ""
    status = row[headers_idx.get("Status", -1)].strip() if "Status" in headers_idx else ""
    remarks = row[headers_idx.get("Remarks", -1)].strip() if "Remarks" in headers_idx else ""
    submitted_by = row[headers_idx.get("Submitted By", -1)].strip() if "Submitted By" in headers_idx else ""
    
    print(f"\n📋 Submission Details:")
    print(f"  - Shop Name: {shop_name}")
    print(f"  - Status: {status}")
    print(f"  - Submitted By: {submitted_by}")
    print(f"  - Remarks: {remarks[:200]}{'...' if len(remarks) > 200 else ''}")
    
    if not shop_name:
        print("\n❌ Shop Name is missing in submission. Cannot proceed.")
        return
    
    # Find shop in Hit List
    shop_data = find_shop_in_hit_list(client, shop_name)
    if not shop_data:
        print(f"\n❌ Shop '{shop_name}' not found in Hit List.")
        return
    
    print(f"\n✅ Found shop in Hit List (row {shop_data['row_num']})")
    
    # Extract structured data from remarks
    print(f"\n🔍 Extracting structured data from remarks...")
    extracted = extract_structured_data(remarks)
    
    print(f"\n📊 Extracted Data:")
    field_labels = {
        'address': 'Address',
        'city': 'City',
        'state': 'State',
        'phone': 'Phone',
        'cell_phone': 'Cell Phone',
        'email': 'Email',
        'website': 'Website',
        'instagram': 'Instagram',
        'contact_person': 'Contact Person',
        'follow_up_date': 'Follow Up Date',
    }
    for field, value in extracted.items():
        label = field_labels.get(field, field.capitalize())
        if value:
            print(f"  - {label}: {value}")
        else:
            print(f"  - {label}: (not found)")
    
    # Update Hit List
    print(f"\n🔄 Updating Hit List...")
    update_hit_list_row(client, shop_data, extracted, dry_run=args.dry_run)
    
    print("\n" + "=" * 80)
    print("✅ COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    main()

