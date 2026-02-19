# Hit List — Credentials & Setup

## Spreadsheet

- **URL:** https://docs.google.com/spreadsheets/d/1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc/edit
- **ID:** `1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc`
- **Tab:** Hit List (or first sheet)

## How to Enable Editing via Code

### Option A: Service Account (recommended for automation)

1. **Share the spreadsheet** with the service account:
   - Email: `agroverse-market-research@get-data-io.iam.gserviceaccount.com` (from market_research/google_credentials.json)
   - Role: **Editor**
   - In Google Sheets: Share -> Add people -> paste email -> Editor

2. **Use the service account JSON** at:
   - `market_research/google_credentials.json` (already used by pull_from_sheets.py)

3. **Enable Google Sheets API** in the Google Cloud project `get-data-io`:
   - https://console.cloud.google.com/apis/library/sheets.googleapis.com?project=get-data-io

### Option B: OAuth2 (interactive, user-owned)

1. Create OAuth 2.0 credentials in Google Cloud Console (Desktop app)
2. Save as `credentials.json` in this directory
3. First run will open browser for consent; token cached for reuse

## Hit List Column Schema

| Col | Name | Type | Notes |
|-----|------|------|-------|
| A | Shop Name | String | |
| B | Status | String | Partnered, Rejected, On Hold, Manager Follow-up, Contacted, Research, Shortlisted, Not Appropriate |
| C | Priority | String | High, Medium, Low, Existing Partner |
| D | Address | String | |
| E | City | String | |
| F | State | String | CA, AZ, OR, WA |
| G | Shop Type | String | Metaphysical/Spiritual, Wellness Center, etc. |
| H | Phone | String | |
| I | Cell Phone | String | |
| J | Website | String | |
| K | Email | String | |
| L | Instagram | String | Required for qualified leads |
| M | Notes | String | |
| N-AB | Contact Date, Contact Method, Follow Up Date, etc. | | See sheet |
| AC | Store Key | String | shop-name__address__city__state (lowercase, hyphens) |

## Store Key Format

`{shop-name}__{address}__{city}__{state}` — lowercase, spaces to hyphens, special chars removed.
Example: `go-ask-alice__1125-pacific-ave__santa-cruz__ca`
