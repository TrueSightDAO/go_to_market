#!/usr/bin/env python3
"""
Append discovered apothecaries to the Hit List Google Sheet.
Reads from apothecary_discovery.csv (from research_apothecaries.ts).
Share sheet with agroverse-market-research@get-data-io.iam.gserviceaccount.com
"""
import csv, sys
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
CREDS = Path(__file__).parent / "google_credentials.json"
SHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
CSV = Path(__file__).parent / "ceremonial_cacao_seo" / "apothecary_discovery.csv"

def main():
    if not CSV.exists():
        print("Run research_apothecaries.ts first")
        sys.exit(1)
    with open(CSV) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("No rows")
        return
    creds = Credentials.from_service_account_file(str(CREDS), scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).worksheet("Hit List")
    cols = ["Shop Name","Status","Priority","Address","City","State","Shop Type","Phone","Cell Phone","Website","Email","Instagram","Notes","Contact Date","Contact Method","Follow Up Date","Contact Person","Owner Name","Referral","Product Interest","Follow Up Event Link","Visit Date","Outcome","Sales Process Notes","Latitude","Longitude","Status Updated By","Status Updated Date","Instagram Follow Count","Store Key"]
    vals = [[r.get(c, "") for c in cols] for r in rows]
    sheet.append_rows(vals, value_input_option="USER_ENTERED")
    print(f"Appended {len(vals)} rows")

if __name__ == "__main__": main()
