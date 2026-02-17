#!/usr/bin/env python3
"""Update EarthTones follow-up date to Thursday."""
import gspread
from google.oauth2.service_account import Credentials
from pathlib import Path
from datetime import datetime, timedelta

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_SHEET = "Hit List"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds_path = Path(__file__).parent.parent / "google_credentials.json"
creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)
hit_list_ws = spreadsheet.worksheet(HIT_LIST_SHEET)

all_values = hit_list_ws.get_all_values()
headers = all_values[0]
headers_idx = {h.strip().replace('\ufeff', ''): i for i, h in enumerate(headers)}

# Find EarthTones and update follow-up date to Thursday
for row_num, row in enumerate(all_values[1:], start=2):
    shop_name = row[headers_idx["Shop Name"]].strip() if headers_idx["Shop Name"] < len(row) else ""
    if "EarthTones" in shop_name:
        follow_up = row[headers_idx["Follow Up Date"]].strip() if headers_idx["Follow Up Date"] < len(row) else ""
        status = row[headers_idx["Status"]].strip() if headers_idx["Status"] < len(row) else ""
        
        if status == "Manager Follow-up":
            # Update to this Thursday
            today = datetime.now()
            days_ahead = (3 - today.weekday()) % 7  # Thursday is 3
            if days_ahead == 0:
                days_ahead = 7
            next_thursday = today + timedelta(days=days_ahead)
            new_date = next_thursday.strftime('%Y-%m-%d')
            
            hit_list_ws.update_cell(row_num, headers_idx["Follow Up Date"] + 1, new_date)
            print(f"✅ Updated EarthTones Follow Up Date to: {new_date} (Thursday)")
            break






