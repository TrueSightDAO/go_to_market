# Airfreight Costing Information

This folder contains scripts and data for managing airfreight costing information from various freight companies. The data is organized and stored in a Google Sheet for easy analysis and projection calculations.

## Overview

This module processes quotations from freight companies and organizes them into a structured format in Google Sheets. The goal is to:
- Collect and organize freight quotations from multiple companies
- Store data in a standardized format for easy comparison
- Enable projections for various cargo levels
- Support decision-making for freight logistics

## Google Sheet

**Sheet URL**: https://docs.google.com/spreadsheets/d/10Ps8BYcTa3sIqtoLwlQ13upuxIG_DgJIpfzchLjm9og/edit?gid=0#gid=0

**Sheet Name**: "Costing estimates"

**Service Account**: `agroverse-market-research@get-data-io.iam.gserviceaccount.com`

The service account credentials are stored in:
- `/Users/garyjob/Applications/market_research/google_credentials.json`
- `/Users/garyjob/Applications/krake_local/google-service-account.json`

## Freight Companies

### SeaCoast Logistics
- **Contact**: Graziela Vedana
- **PDF File**: `graziela_vedana_seacoast_logistics.pdf` (stored in Downloads folder)
- **Status**: Initial quotation received

### Additional Companies
- More quotations will be added as they are received

## Sheet Structure

The Google Sheet contains 4 main sheets:

### 1. Quick Estimate (Main Dashboard)
This is the primary interface for cost estimation. It includes:

**Input Section:**
- Freight Weight (kg): Enter weight or use common values (200, 300, 500, 750, 1000)
- Cargo Value (USD): Auto-calculated as weight × $5/kg (adjustable)
- FDA Required?: Yes/No dropdown
- Bond Required?: Yes/No dropdown
- Extra Invoice Lines: Number beyond the first 3 (which are free)
- Expected Customs Exams: Number of exams
- Duty Estimate: Percentage of cargo value (formatted as %)

**Cost Breakdown Table:**
- All cost components calculated dynamically based on inputs
- Air freight uses linear interpolation for weights between brackets
- All values are numeric for easy calculations
- Formulas automatically update when inputs change

**Grand Total:**
- Sum of all cost components
- Updates automatically

### 2. Cost Breakdown (Detailed Data)
Detailed breakdown showing costs for each weight tier (200, 300, 500, 750, 1000 kg):
- Each cost component as a separate row
- Each weight tier as a separate column
- All values are numeric (not formatted strings)
- Formulas reference input section for conditional fees
- Subtotal row for each weight tier

**Cost Components:**
- Air Freight (airport to airport) - variable by weight
- Export Documentation - fixed
- Inland Transport (Brazil) - fixed base + 0.15% ad valorem
- Brazil Airport Charges - 0.30/kg, minimum 250
- US Airline Terminal Fee - fixed (midpoint 212.50)
- US Import Handling Fee - fixed
- US Customs Clearance - fixed
- Invoice Line Items - conditional (first 3 free)
- FDA Processing - conditional
- Bond - conditional (if required)
- MPF - percentage of value with min/max
- US Customs Exam Charges - conditional

### 3. Totals by Weight
Summary table showing:
- Total cost for each weight tier
- Per-kg cost calculation
- Pulls data from Cost Breakdown sheet

### 4. Notes & Assumptions
Documentation including:
- Notes on estimates and calculations
- Interpolation methodology
- Missing information
- Contact details
- Quotation dates

## Scripts

### `parse_seacoast_quotation.py`
Creates a comprehensive Google Sheet structure for SeaCoast Logistics airfreight costing with:
- Quick Estimate dashboard for instant cost calculations
- Detailed Cost Breakdown by weight tier
- Totals summary
- Documentation

**Usage**:
```bash
cd /Users/garyjob/Applications/market_research
source venv/bin/activate
python airfreight_costing/parse_seacoast_quotation.py
```

**Requirements**:
- Google credentials must be configured (`google_credentials.json` in repo root)
- Required Python packages: `gspread`, `google-auth`
- PDF parsing not required (data is hardcoded from email thread)

**Features**:
- **Numeric values only**: All prices are actual numbers, not formatted strings
- **Linear interpolation**: Air freight rates interpolate between weight brackets
- **Dynamic calculations**: All formulas update automatically when inputs change
- **Each line item = one row**: Clean structure for projections
- **Weight tiers as columns**: Easy comparison across weight levels

## How to Use

### Quick Estimate Dashboard
1. Open the "Quick Estimate" sheet
2. Enter freight weight in cell B4 (or use common values: 200, 300, 500, 750, 1000)
3. Adjust cargo value in B5 if needed (defaults to weight × $5/kg)
4. Set FDA and Bond requirements (Yes/No)
5. Enter any extra invoice lines or expected exams
6. Set duty percentage if applicable
7. **Total cost updates automatically in B27**

### Cost Breakdown Sheet
- View detailed costs for each weight tier
- Modify input values in rows 4-10 to see how they affect all weight tiers
- Use for comparing costs across different weight scenarios

### Projections
To create projections:
1. Use the numeric values in Cost Breakdown sheet
2. Create formulas that reference these cells
3. Multiply weight tiers by quantities to project volume scenarios
4. All values are numeric, making calculations straightforward

## Future Enhancements

- Add scripts for other freight companies as quotations are received
- Add data validation dropdowns for weight input
- Create comparison tools to compare quotes across companies
- Automate data extraction from email attachments
- Add charts and visualizations to dashboard
- Create scenario planning templates

## Notes

- All PDF quotations should be stored in the Downloads folder initially
- Processed data is stored in the Google Sheet for centralized access
- Keep original PDFs for reference
- Update this README as new companies and scripts are added

