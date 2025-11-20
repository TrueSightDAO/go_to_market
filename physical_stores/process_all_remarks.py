#!/usr/bin/env python3
"""
Process all unprocessed remarks in the DApp Remarks sheet.

For each unprocessed remark:
1. Extract structured data
2. Update Hit List
3. Create calendar event (if follow-up date exists)
4. Update Follow Up Event Link
5. Mark as processed
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
DAPP_REMARKS_SHEET = "DApp Remarks"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheets_client() -> gspread.Client:
    """Get authenticated Google Sheets client."""
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


def get_unprocessed_remarks() -> list[dict]:
    """Get all unprocessed remarks."""
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    remarks_ws = spreadsheet.worksheet(DAPP_REMARKS_SHEET)
    
    all_values = remarks_ws.get_all_values()
    if len(all_values) < 2:
        return []
    
    headers = all_values[0]
    headers_idx = {header: idx for idx, header in enumerate(headers)}
    
    if "Submission ID" not in headers_idx or "Processed" not in headers_idx:
        return []
    
    submission_id_idx = headers_idx["Submission ID"]
    processed_idx = headers_idx["Processed"]
    shop_name_idx = headers_idx.get("Shop Name", -1)
    
    unprocessed = []
    for row_num, row in enumerate(all_values[1:], start=2):
        if submission_id_idx < len(row) and processed_idx < len(row):
            submission_id = row[submission_id_idx].strip()
            processed = row[processed_idx].strip()
            
            if submission_id and processed.lower() != "yes":
                shop_name = row[shop_name_idx] if shop_name_idx >= 0 and shop_name_idx < len(row) else "Unknown"
                unprocessed.append({
                    "submission_id": submission_id,
                    "shop_name": shop_name,
                    "row_num": row_num,
                })
    
    return unprocessed


def process_remark(submission_id: str) -> bool:
    """Process a single remark. Returns True if successful."""
    script_dir = Path(__file__).parent
    
    try:
        # Step 1: Extract structured data
        print(f"\n{'='*80}")
        print(f"Processing remark: {submission_id}")
        print(f"{'='*80}")
        
        result = subprocess.run(
            [sys.executable, str(script_dir / "extract_remarks_data.py"), submission_id],
            capture_output=True,
            text=True,
            cwd=str(script_dir)
        )
        
        if result.returncode != 0:
            print(f"❌ Error extracting data: {result.stderr}")
            return False
        
        print(result.stdout)
        
        # Add delay to avoid rate limiting
        time.sleep(2)
        
        # Step 2: Check if follow-up date exists and create calendar event
        # First, get shop name from the remark
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        remarks_ws = spreadsheet.worksheet(DAPP_REMARKS_SHEET)
        
        all_values = remarks_ws.get_all_values()
        headers = all_values[0]
        headers_idx = {header: idx for idx, header in enumerate(headers)}
        
        shop_name = None
        for row in all_values[1:]:
            if headers_idx.get("Submission ID", -1) < len(row):
                if row[headers_idx["Submission ID"]].strip() == submission_id:
                    shop_name = row[headers_idx.get("Shop Name", -1)] if "Shop Name" in headers_idx else None
                    break
        
        if shop_name:
            # Check if shop has a follow-up date
            hit_list_ws = spreadsheet.worksheet("Hit List")
            hit_values = hit_list_ws.get_all_values()
            hit_headers = hit_values[0]
            hit_headers_idx = {h: i for i, h in enumerate(hit_headers)}
            
            for row in hit_values[1:]:
                shop_name_idx = hit_headers_idx.get("Shop Name", -1)
                if shop_name_idx >= 0 and shop_name_idx < len(row):
                    if shop_name.lower() in row[shop_name_idx].lower():
                        follow_up_date_idx = hit_headers_idx.get("Follow Up Date", -1)
                        follow_up_link_idx = hit_headers_idx.get("Follow Up Event Link", -1)
                        
                        if follow_up_date_idx >= 0 and follow_up_date_idx < len(row):
                            follow_up_date = row[follow_up_date_idx].strip()
                            
                            # Check if event link already exists
                            has_event_link = False
                            if follow_up_link_idx >= 0 and follow_up_link_idx < len(row):
                                existing_link = row[follow_up_link_idx].strip()
                                if existing_link and "google.com/calendar" in existing_link:
                                    has_event_link = True
                            
                            if follow_up_date and not has_event_link:
                                # Create calendar event
                                print(f"\n📅 Creating calendar event for {shop_name}...")
                                result = subprocess.run(
                                    [sys.executable, str(script_dir / "create_and_link_followup_event.py"), shop_name],
                                    capture_output=True,
                                    text=True,
                                    cwd=str(script_dir)
                                )
                                
                                if result.returncode == 0:
                                    print(result.stdout)
                                else:
                                    print(f"⚠️  Warning: Could not create calendar event: {result.stderr}")
                                
                                # Add delay after calendar event creation
                                time.sleep(2)
                        break
        
        # Step 3: Mark as processed
        print(f"\n✅ Marking remark as processed...")
        result = subprocess.run(
            [sys.executable, str(script_dir / "mark_remark_processed.py"), submission_id],
            capture_output=True,
            text=True,
            cwd=str(script_dir)
        )
        
        if result.returncode == 0:
            print(result.stdout)
            return True
        else:
            print(f"❌ Error marking as processed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error processing remark {submission_id}: {e}")
        return False


def main():
    print("=" * 80)
    print("PROCESSING ALL UNPROCESSED REMARKS")
    print("=" * 80)
    
    unprocessed = get_unprocessed_remarks()
    
    if not unprocessed:
        print("\n✅ No unprocessed remarks found. All done!")
        return
    
    print(f"\n📋 Found {len(unprocessed)} unprocessed remark(s)")
    print("\nRemarks to process:")
    for i, remark in enumerate(unprocessed, 1):
        print(f"  {i}. {remark['shop_name']} (ID: {remark['submission_id'][:8]}...)")
    
    print(f"\n🚀 Starting processing...\n")
    
    successful = 0
    failed = 0
    
    for i, remark in enumerate(unprocessed, 1):
        print(f"\n{'='*80}")
        print(f"Processing {i}/{len(unprocessed)}: {remark['shop_name']}")
        print(f"{'='*80}")
        
        if process_remark(remark["submission_id"]):
            successful += 1
        else:
            failed += 1
            print(f"\n⚠️  Failed to process remark for {remark['shop_name']}")
        
        # Add delay between processing each remark to avoid rate limiting
        if i < len(unprocessed):
            print(f"\n⏳ Waiting 3 seconds before next remark...")
            time.sleep(3)
    
    print("\n" + "=" * 80)
    print("PROCESSING COMPLETE")
    print("=" * 80)
    print(f"✅ Successfully processed: {successful}")
    if failed > 0:
        print(f"❌ Failed: {failed}")
    print("=" * 80)


if __name__ == "__main__":
    main()

