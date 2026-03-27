#!/usr/bin/env python3
"""
Backfill Latitude and Longitude for Hit List rows that are missing them.
Targets rows where State is TX or NY (or any state) and Latitude is empty.
Uses Nominatim (OpenStreetMap) for geocoding. Rate limit: 1 req/sec.
"""
import sys
import time
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
CREDS = Path(__file__).parent / "google_credentials.json"
SHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"

# Column indices (1-based for gspread)
COLS = ["Shop Name","Status","Priority","Address","City","State","Shop Type","Phone","Cell Phone","Website","Email","Instagram","Notes","Contact Date","Contact Method","Follow Up Date","Contact Person","Owner Name","Referral","Product Interest","Follow Up Event Link","Visit Date","Outcome","Sales Process Notes","Latitude","Longitude","Status Updated By","Status Updated Date","Instagram Follow Count","Store Key"]
LAT_IDX = COLS.index("Latitude") + 1
LNG_IDX = COLS.index("Longitude") + 1
ADDR_IDX = COLS.index("Address") + 1
CITY_IDX = COLS.index("City") + 1
STATE_IDX = COLS.index("State") + 1


def geocode(address: str, city: str, state: str) -> tuple[str, str] | None:
    import urllib.request
    import json
    q = f"{address}, {city}, {state}"
    q_enc = urllib.request.quote(q)
    url = f"https://nominatim.openstreetmap.org/search?q={q_enc}&format=json&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Agroverse-HitList/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        if data and len(data) > 0:
            return (str(data[0]["lat"]), str(data[0]["lon"]))
    except Exception:
        pass
    return None


def main():
    states_filter = sys.argv[1:] if len(sys.argv) > 1 else None  # e.g. TX NY
    creds = Credentials.from_service_account_file(str(CREDS), scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).worksheet("Hit List")
    rows = sheet.get_all_values()
    if len(rows) < 2:
        print("No data rows")
        return
    header = rows[0]
    data_rows = rows[1:]
    updated = 0
    for i, row in enumerate(data_rows):
        row_num = i + 2
        if len(row) < max(LAT_IDX, LNG_IDX, ADDR_IDX, CITY_IDX, STATE_IDX):
            continue
        state = row[STATE_IDX - 1].strip() if STATE_IDX <= len(row) else ""
        lat = row[LAT_IDX - 1].strip() if LAT_IDX <= len(row) else ""
        if lat:
            continue
        if states_filter and state not in states_filter:
            continue
        address = row[ADDR_IDX - 1].strip() if ADDR_IDX <= len(row) else ""
        city = row[CITY_IDX - 1].strip() if CITY_IDX <= len(row) else ""
        if not address or len(address) < 10:
            continue
        coords = geocode(address, city, state)
        if coords:
            sheet.update_cell(row_num, LAT_IDX, coords[0])
            sheet.update_cell(row_num, LNG_IDX, coords[1])
            print(f"  Row {row_num}: {address[:40]}... -> {coords[0]}, {coords[1]}")
            updated += 1
        time.sleep(1.1)
    print(f"Updated {updated} rows with lat/long")


if __name__ == "__main__":
    main()
