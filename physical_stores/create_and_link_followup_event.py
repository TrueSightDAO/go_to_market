#!/usr/bin/env python3
"""
Create a Google Calendar event for a shop follow-up and update the Hit List with the event link.

This script:
1. Creates a calendar event based on the follow-up date in the Hit List
2. Updates the "Follow Up Event Link" column with the calendar event URL

Usage:
    python3 create_and_link_followup_event.py <shop_name>
    python3 create_and_link_followup_event.py "Spice of Life"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from zoneinfo import ZoneInfo

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_SHEET = "Hit List"

# Look for credentials in parent directory (repository root)
SERVICE_ACCOUNT_FILE = str(Path(__file__).parent.parent / "google_credentials.json")

# Scopes for both Sheets and Calendar APIs
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar"
]

# Default timezone for events
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "America/Los_Angeles")


def parse_date_time(date_str: str, time_str: str = None) -> tuple[datetime, datetime]:
    """Parse date and optional time string into start and end datetimes."""
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    
    # Parse date - handle both "YYYY-MM-DD" and "YYYY-MM-DD HH:MM" formats
    date_str_clean = date_str.strip()
    try:
        # Try parsing with time first
        if " " in date_str_clean and ":" in date_str_clean:
            date_time_obj = datetime.strptime(date_str_clean, "%Y-%m-%d %H:%M")
            date_obj = date_time_obj.date()
            # Extract time from the date string if time_str not provided
            if not time_str:
                time_str = date_time_obj.strftime("%H:%M")
        else:
            date_obj = datetime.strptime(date_str_clean, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD or YYYY-MM-DD HH:MM")
    
    if time_str:
        # Parse time range or single time
        if "-" in time_str:
            # Time range: "10:00-11:00"
            start_time_str, end_time_str = time_str.split("-", 1)
            start_time = datetime.strptime(start_time_str.strip(), "%H:%M").time()
            end_time = datetime.strptime(end_time_str.strip(), "%H:%M").time()
        else:
            # Single time: "10:00" (default 1 hour duration)
            start_time = datetime.strptime(time_str.strip(), "%H:%M").time()
            end_time = (datetime.combine(date_obj, start_time) + timedelta(hours=1)).time()
        
        start_dt = datetime.combine(date_obj, start_time, tz)
        end_dt = datetime.combine(date_obj, end_time, tz)
    else:
        # All-day event
        start_dt = datetime.combine(date_obj, datetime.min.time(), tz)
        end_dt = datetime.combine(date_obj + timedelta(days=1), datetime.min.time(), tz)
    
    return start_dt, end_dt


def get_shop_data(shop_name: str) -> dict:
    """Get shop data from Hit List."""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(HIT_LIST_SHEET)
    
    all_values = worksheet.get_all_values()
    if len(all_values) < 2:
        raise ValueError("Hit List is empty")
    
    headers = all_values[0]
    headers_idx = {header: idx for idx, header in enumerate(headers)}
    
    # Find the shop
    shop_name_idx = headers_idx.get("Shop Name", -1)
    if shop_name_idx < 0:
        raise ValueError("'Shop Name' column not found")
    
    for row_num, row in enumerate(all_values[1:], start=2):
        if shop_name_idx < len(row) and shop_name.lower() in row[shop_name_idx].lower():
            # Build shop data dict
            shop_data = {
                'row_num': row_num,
                'headers_idx': headers_idx,
                'row': row,
            }
            for header, idx in headers_idx.items():
                if idx < len(row):
                    shop_data[header] = row[idx]
                else:
                    shop_data[header] = ""
            return shop_data
    
    raise ValueError(f"Shop '{shop_name}' not found in Hit List")


def create_calendar_event(
    shop_data: dict,
    time_str: str = None
) -> dict:
    """Create a Google Calendar event for a shop follow-up."""
    # Load environment variables
    repo_root = Path(__file__).parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / ".env.local", override=True)
    
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        raise RuntimeError(
            "GOOGLE_CALENDAR_ID environment variable is required. "
            "Set it in .env or .env.local file, or as an environment variable."
        )
    
    credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    calendar_service = build("calendar", "v3", credentials=credentials)
    
    # Get follow-up date from shop data
    follow_up_date = shop_data.get("Follow Up Date", "").strip()
    if not follow_up_date:
        raise ValueError(f"No 'Follow Up Date' found for shop '{shop_data.get('Shop Name', 'Unknown')}'")
    
    # Extract time from date string if it contains time and time_str not provided
    extracted_time = None
    if " " in follow_up_date and ":" in follow_up_date and not time_str:
        # Date has time in it, extract it
        parts = follow_up_date.split()
        if len(parts) >= 2:
            date_part = parts[0]
            time_part = parts[1]
            follow_up_date = date_part
            extracted_time = time_part
    
    # Use extracted time or provided time_str
    final_time_str = time_str or extracted_time
    start_dt, end_dt = parse_date_time(follow_up_date, final_time_str)
    
    shop_name = shop_data.get("Shop Name", "Unknown Shop")
    status = shop_data.get("Status", "")
    phone = shop_data.get("Phone", "")
    cell_phone = shop_data.get("Cell Phone", "")
    contact_person = shop_data.get("Contact Person", "")
    sales_notes = shop_data.get("Sales Process Notes", "")
    
    # Build description
    desc_lines = []
    if status:
        desc_lines.append(f"Status: {status}")
    if contact_person:
        desc_lines.append(f"Contact: {contact_person}")
    if phone:
        desc_lines.append(f"Phone: {phone}")
    if cell_phone:
        desc_lines.append(f"Cell Phone: {cell_phone}")
    if sales_notes:
        # Take last 500 chars of sales notes to avoid overly long descriptions
        notes_preview = sales_notes[-500:] if len(sales_notes) > 500 else sales_notes
        desc_lines.append(f"\nNotes:\n{notes_preview}")
    
    desc = "\n".join(desc_lines) if desc_lines else f"Follow-up reminder for {shop_name}"
    
    # Build event
    event = {
        "summary": f"Follow-up: {shop_name}",
        "description": desc,
        "source": {
            "title": "Shop Hit List",
            "url": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0"
        }
    }
    
    if time_str:
        # Timed event
        event["start"] = {
            "dateTime": start_dt.isoformat(),
            "timeZone": DEFAULT_TIMEZONE
        }
        event["end"] = {
            "dateTime": end_dt.isoformat(),
            "timeZone": DEFAULT_TIMEZONE
        }
    else:
        # All-day event
        event["start"] = {"date": follow_up_date}
        event["end"] = {"date": (start_dt.date() + timedelta(days=1)).isoformat()}
    
    try:
        event_response = calendar_service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        
        return event_response
    except HttpError as err:
        print(f"❌ Failed to create calendar event: {err}")
        raise


def update_follow_up_event_link(shop_data: dict, event_link: str) -> None:
    """Update the Follow Up Event Link column in Hit List."""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(HIT_LIST_SHEET)
    
    headers_idx = shop_data['headers_idx']
    row_num = shop_data['row_num']
    
    if "Follow Up Event Link" not in headers_idx:
        raise ValueError("'Follow Up Event Link' column not found in Hit List")
    
    col_idx = headers_idx["Follow Up Event Link"] + 1  # 1-indexed
    worksheet.update_cell(row_num, col_idx, event_link)


def main():
    parser = argparse.ArgumentParser(
        description="Create a Google Calendar event for a shop follow-up and update the Hit List with the event link."
    )
    parser.add_argument(
        "shop_name",
        help="Name of the shop"
    )
    parser.add_argument(
        "time",
        nargs="?",
        help="Optional time in HH:MM format or time range HH:MM-HH:MM (e.g., 10:00 or 10:00-11:00). Defaults to all-day if not specified."
    )
    
    args = parser.parse_args()
    
    try:
        print("=" * 80)
        print("CREATING FOLLOW-UP CALENDAR EVENT AND UPDATING HIT LIST")
        print("=" * 80)
        print()
        
        # Get shop data
        print(f"📋 Looking up shop: {args.shop_name}")
        shop_data = get_shop_data(args.shop_name)
        print(f"✅ Found shop in Hit List (row {shop_data['row_num']})")
        
        follow_up_date = shop_data.get("Follow Up Date", "").strip()
        if not follow_up_date:
            print(f"❌ No 'Follow Up Date' found for this shop. Please add a follow-up date first.")
            sys.exit(1)
        
        print(f"📅 Follow Up Date: {follow_up_date}")
        if args.time:
            print(f"⏰ Time: {args.time}")
        else:
            print(f"⏰ Time: All-day event")
        print()
        
        # Create calendar event
        print("📅 Creating calendar event...")
        event_response = create_calendar_event(shop_data, args.time)
        event_link = event_response.get("htmlLink", "")
        
        print(f"✅ Created calendar event: {event_response.get('summary', 'N/A')}")
        print(f"   Link: {event_link}")
        print()
        
        # Update Hit List
        print("🔄 Updating Hit List with event link...")
        update_follow_up_event_link(shop_data, event_link)
        print(f"✅ Updated 'Follow Up Event Link' column in Hit List")
        print()
        
        print("=" * 80)
        print("✅ COMPLETE!")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

