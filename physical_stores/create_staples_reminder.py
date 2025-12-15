#!/usr/bin/env python3
"""
Create a Google Calendar reminder for picking up name cards at Staples.

Usage:
    1. Ensure the target Google Calendar is shared with the service account:
       agroverse-market-research@get-data-io.iam.gserviceaccount.com
    2. Optionally set GOOGLE_CALENDAR_ID environment variable, or the script will use 'primary'
    3. Run: python3 create_staples_reminder.py
"""

from __future__ import annotations

import os
from datetime import datetime
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

# Default timezone
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "America/Los_Angeles")


def create_calendar_event():
    """Create a calendar event for Staples pickup."""
    load_dotenv()
    load_dotenv(".env.local", override=True)

    # Get calendar ID (default to 'primary' if not set)
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    # Load credentials
    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )

    # Build calendar service
    calendar_service = build("calendar", "v3", credentials=credentials)

    # Event details
    event_datetime = datetime(
        year=2024,
        month=11,
        day=20,
        hour=19,  # 7pm
        minute=0,
        tzinfo=ZoneInfo(DEFAULT_TIMEZONE)
    )

    # End time is 1 hour later
    end_datetime = event_datetime.replace(hour=20)

    event = {
        "summary": "Pickup name cards at Staples",
        "description": "Pickup name cards at Staples Retail Store 1385 - Atascadero CA",
        "location": "815 El Camino Real, Atascadero, CA 93422",
        "start": {
            "dateTime": event_datetime.isoformat(),
            "timeZone": DEFAULT_TIMEZONE
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": DEFAULT_TIMEZONE
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 1440},  # 1 day before
                {"method": "popup", "minutes": 60}      # 1 hour before
            ]
        }
    }

    try:
        print(f"Creating calendar event in calendar: {calendar_id}")
        print(f"Event: {event['summary']}")
        print(f"Date/Time: {event_datetime.strftime('%A, %B %d, %Y at %I:%M %p %Z')}")
        print(f"Location: {event['location']}")

        event_response = calendar_service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()

        event_link = event_response.get("htmlLink", "")
        event_id = event_response.get("id", "")

        print(f"\n✅ Successfully created calendar event!")
        print(f"Event ID: {event_id}")
        if event_link:
            print(f"View event: {event_link}")

        return event_response

    except HttpError as err:
        print(f"❌ Error creating calendar event: {err}")
        if err.resp.status == 403:
            print("\n💡 Tip: Make sure the calendar is shared with the service account:")
            print("   agroverse-market-research@get-data-io.iam.gserviceaccount.com")
            print("   Grant at least 'Make changes to events' permission.")
        elif err.resp.status == 404:
            print(f"\n💡 Tip: Calendar ID '{calendar_id}' not found. Check your GOOGLE_CALENDAR_ID environment variable.")
        raise


if __name__ == "__main__":
    create_calendar_event()


