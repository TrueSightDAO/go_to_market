#!/usr/bin/env python3
"""
Create a Google Calendar event for a specific shop follow-up.

Usage:
    1. Set the environment variable GOOGLE_CALENDAR_ID to the calendar's ID.
    2. Run: python3 create_single_followup_event.py <shop_name> <date> [time]
    
Examples:
    python3 create_single_followup_event.py "Spice of Life" "2025-12-03"
    python3 create_single_followup_event.py "Spice of Life" "2025-12-03" "10:00"
    python3 create_single_followup_event.py "Spice of Life" "2025-12-03" "10:00-11:00"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from zoneinfo import ZoneInfo

# Look for credentials in parent directory (repository root)
SERVICE_ACCOUNT_FILE = str(Path(__file__).parent.parent / "google_credentials.json")

# Scopes for Calendar API
SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

# Default timezone for events (can be overridden with DEFAULT_TIMEZONE env var)
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "America/Los_Angeles")


def parse_date_time(date_str: str, time_str: str = None) -> tuple[datetime, datetime]:
    """Parse date and optional time string into start and end datetimes."""
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    
    # Parse date
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
    
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


def create_calendar_event(
    shop_name: str,
    date_str: str,
    time_str: str = None,
    description: str = None,
    phone: str = None,
    cell_phone: str = None
) -> dict:
    """Create a Google Calendar event for a shop follow-up."""
    # Load environment variables from .env files in repository root
    repo_root = Path(__file__).parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / ".env.local", override=True)
    
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        raise RuntimeError(
            "GOOGLE_CALENDAR_ID environment variable is required. "
            "Set it in .env or .env.local file, or as an environment variable."
        )
    
    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    
    calendar_service = build("calendar", "v3", credentials=credentials)
    
    start_dt, end_dt = parse_date_time(date_str, time_str)
    
    # Build description
    desc_lines = []
    if description:
        desc_lines.append(description)
    if phone:
        desc_lines.append(f"Phone: {phone}")
    if cell_phone:
        desc_lines.append(f"Cell Phone: {cell_phone}")
    if desc_lines:
        desc = "\n".join(desc_lines)
    else:
        desc = f"Follow-up reminder for {shop_name}"
    
    # Build event
    event = {
        "summary": f"Follow-up: {shop_name}",
        "description": desc,
        "source": {
            "title": "Shop Hit List",
            "url": "https://docs.google.com/spreadsheets/d/1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc/edit#gid=0"
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
        event["start"] = {"date": date_str}
        event["end"] = {"date": (start_dt.date() + timedelta(days=1)).isoformat()}
    
    try:
        event_response = calendar_service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        
        print(f"✅ Created calendar event: {event['summary']}")
        print(f"   Date: {date_str}" + (f" at {time_str}" if time_str else " (all-day)"))
        print(f"   Link: {event_response.get('htmlLink', 'N/A')}")
        
        return event_response
    except HttpError as err:
        print(f"❌ Failed to create calendar event: {err}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Create a Google Calendar event for a shop follow-up."
    )
    parser.add_argument(
        "shop_name",
        help="Name of the shop"
    )
    parser.add_argument(
        "date",
        help="Follow-up date in YYYY-MM-DD format (e.g., 2025-12-03)"
    )
    parser.add_argument(
        "time",
        nargs="?",
        help="Optional time in HH:MM format or time range HH:MM-HH:MM (e.g., 10:00 or 10:00-11:00)"
    )
    parser.add_argument(
        "--description",
        help="Additional description for the event"
    )
    parser.add_argument(
        "--phone",
        help="Phone number to include in event description"
    )
    parser.add_argument(
        "--cell-phone",
        help="Cell phone number to include in event description"
    )
    
    args = parser.parse_args()
    
    try:
        create_calendar_event(
            shop_name=args.shop_name,
            date_str=args.date,
            time_str=args.time,
            description=args.description,
            phone=args.phone,
            cell_phone=getattr(args, 'cell_phone', None)
        )
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

