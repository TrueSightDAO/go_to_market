#!/usr/bin/env python3
"""
Create comprehensive Google Sheet for SeaCoast Logistics airfreight costing.

Creates:
1. Quick Estimate dashboard (main sheet)
2. Cost Breakdown (detailed data by weight tier)
3. Totals by Weight (summary)
4. Notes & Assumptions (documentation)
"""

import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Please install: pip install gspread google-auth")
    sys.exit(1)

# Configuration
SPREADSHEET_ID = "10Ps8BYcTa3sIqtoLwlQ13upuxIG_DgJIpfzchLjm9og"

# Google Sheets API scopes
SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# Weight tiers in kg
WEIGHT_TIERS = [200, 300, 500, 750, 1000]
AIR_FREIGHT_RATES = {200: 3.50, 300: 3.40, 500: 3.30, 750: 3.30, 1000: 3.20}


def get_google_sheets_client():
    """Get authenticated Google Sheets client."""
    creds_paths = [
        Path(__file__).parent.parent / "google_credentials.json",
        Path(__file__).parent.parent.parent / "krake_local" / "google-service-account.json",
    ]
    
    creds_path = None
    for path in creds_paths:
        if path.exists():
            creds_path = path
            break
    
    if not creds_path:
        raise FileNotFoundError(f"Google credentials not found. Checked: {creds_paths}")
    
    print(f"✅ Using credentials from: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


def cleanup_unused_sheets(spreadsheet):
    """Remove unused sheets, keeping only our 4 main sheets."""
    print("🧹 Cleaning up unused sheets...")
    
    required_sheets = ["Quick Estimate", "Cost Breakdown", "Totals by Weight", "Notes & Assumptions"]
    all_sheets = spreadsheet.worksheets()
    
    deleted_count = 0
    for sheet in all_sheets:
        if sheet.title not in required_sheets:
            try:
                spreadsheet.del_worksheet(sheet)
                print(f"  🗑️  Deleted: {sheet.title}")
                deleted_count += 1
            except Exception as e:
                print(f"  ⚠️  Could not delete {sheet.title}: {e}")
    
    if deleted_count > 0:
        print(f"✅ Removed {deleted_count} unused sheet(s)")
    else:
        print("✅ No unused sheets to remove")


def create_quick_estimate_dashboard(spreadsheet):
    """Create the Quick Estimate dashboard sheet."""
    print("📊 Creating Quick Estimate dashboard...")
    
    try:
        worksheet = spreadsheet.worksheet("Quick Estimate")
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Quick Estimate", rows=100, cols=15)
    
    all_data = []
    
    # Title and subtitle
    all_data.append(['Air Freight Cost Estimator: Ilhéus to San Francisco', '', '', '', '', ''])
    all_data.append(['Enter details below for instant totals. All costs in USD.', '', '', '', '', ''])
    all_data.append([''])  # Empty row
    
    # Instructions section
    all_data.append(['📝 INSTRUCTIONS:', '', '', '', '', ''])
    all_data.append(['→ Enter values in the YELLOW highlighted cells below', '', '', '', '', ''])
    all_data.append(['→ Total cost will update automatically at the bottom', '', '', '', '', ''])
    all_data.append(['→ Weight can be any value between 200-1000 kg (interpolates between brackets)', '', '', '', '', ''])
    all_data.append([''])  # Empty row
    
    # Input section header
    all_data.append(['INPUT FIELDS (Enter values in yellow cells)', '', '', '', '', ''])  # Removed === to avoid formula parsing error
    
    # Input section
    all_data.append(['Freight Weight (kg):', 500, 'Common: 200, 300, 500, 750, 1000', '', '', ''])
    all_data.append(['Cargo Value (USD total):', '=B10*5', 'Auto-calculated (weight × $5/kg). Adjust if needed.', '', '', ''])
    all_data.append(['FDA Required? (Yes/No):', 'Yes', 'Enter "Yes" or "No"', '', '', ''])
    all_data.append(['Bond Required? (Yes/No):', 'No', 'Enter "Yes" or "No"', '', '', ''])
    all_data.append(['Extra Invoice Lines (beyond 3):', 0, 'Number of lines beyond first 3 (which are free)', '', '', ''])
    all_data.append(['Expected Customs Exams (#):', 0, 'Number of exams expected (if any)', '', '', ''])
    all_data.append(['Duty Estimate (% of value):', 0, 'Enter as decimal (e.g., 0.05 for 5%)', '', '', ''])
    
    all_data.append([''])  # Empty row
    
    all_data.append([''])  # Empty row
    
    # Cost breakdown section header
    all_data.append(['COST BREAKDOWN (Auto-calculated)', '', ''])  # Removed === to avoid formula parsing error
    
    # Cost breakdown table header
    all_data.append(['Cost Component', 'Amount (USD)', 'Notes/Formula'])
    
    # Air Freight (with interpolation)
    # Row 10 is weight input (after instructions and header rows)
    air_freight_formula = '''=IF(B10<200, "Min 200 kg", IF(B10>1000, "Max 1000 kg", 
IF(B10<=300, (3.5+(3.4-3.5)*(B10-200)/(300-200))*B10,
IF(B10<=500, (3.4+(3.3-3.4)*(B10-300)/(500-300))*B10,
IF(B10<=750, (3.3+(3.3-3.3)*(B10-500)/(750-500))*B10,
(3.3+(3.2-3.3)*(B10-750)/(1000-750))*B10)))))'''
    all_data.append(['Air Freight (airport to airport)', air_freight_formula, 'Interpolated rate * weight'])
    
    # Brazil Export Fees
    all_data.append(['Export Documentation', 95, 'Fixed per shipment'])
    # Row 11 is cargo value
    inland_formula = '=695+0.0015*B11'
    all_data.append(['Inland Transport (Brazil)', inland_formula, '695 + 0.15% of cargo value'])
    # Row 10 is weight
    airport_formula = '=MAX(0.3*B10, 250)'
    all_data.append(['Brazil Airport Charges', airport_formula, '0.30/kg, minimum 250'])
    
    # US Arrival Fees
    all_data.append(['US Airline Terminal Fee', 212.5, 'Midpoint (200-225 range)'])
    all_data.append(['US Import Handling Fee', 125, 'Fixed per shipment'])
    
    # US Customs
    all_data.append(['US Customs Clearance', 150, 'Base fee'])
    # Row 14 is extra invoice lines
    line_items_formula = '=MAX(0, B14*5)'
    all_data.append(['Invoice Line Items', line_items_formula, 'First 3 free, then $5/line'])
    # Row 12 is FDA
    fda_formula = '=IF(UPPER(B12)="YES", 100, 0)'
    all_data.append(['FDA Processing', fda_formula, 'If applicable'])
    # Row 13 is Bond, Row 11 is cargo value, Row 16 is duty %
    bond_formula = '=IF(UPPER(B13)="YES", MAX(100, 6*(B11/1000)+(B16*B11)), 0)'
    all_data.append(['Bond (Single-Entry)', bond_formula, 'If required, min $100. Duty as decimal (5% = 0.05)'])
    # Row 11 is cargo value
    mpf_formula = '=MIN(MAX(0.003464*B11, 33.58), 651.50)'
    all_data.append(['MPF (Merchandise Processing Fee)', mpf_formula, '0.3464% of value, min $33.58, max $651.50'])
    # Row 15 is exams
    exam_formula = '=B15*125'
    all_data.append(['US Customs Exam Charges', exam_formula, '125 per exam (cost assumed 0)'])
    
    all_data.append([''])  # Empty row
    
    # Grand Total section
    all_data.append(['TOTAL COST', '', ''])  # Removed === to avoid formula parsing error
    # Calculate sum of all cost components (starting from row 21, which is after header row 20)
    # Count: Air Freight (21), Export Doc (22), Inland (23), Airport (24), Terminal (25), 
    # Handling (26), Customs (27), Line Items (28), FDA (29), Bond (30), MPF (31), Exam (32)
    total_formula = '=SUM(B21:B32)'
    all_data.append(['Estimated Total Cost:', total_formula, ''])
    
    all_data.append([''])  # Empty row
    
    # Hyperlinks section (will be updated after sheets are created)
    all_data.append(['View Detailed Breakdown', 'Cost Breakdown', ''])
    all_data.append(['View Notes', 'Notes & Assumptions', ''])
    
    # Batch update
    worksheet.update('A1', all_data, value_input_option='USER_ENTERED')
    
    # Formatting
    # Title
    worksheet.format('A1:F1', {
        'textFormat': {'bold': True, 'fontSize': 16},
        'horizontalAlignment': 'LEFT'
    })
    worksheet.merge_cells('A1:F1')
    
    # Instructions section (rows 5-7)
    worksheet.format('A5:A7', {
        'textFormat': {'bold': True, 'italic': True},
        'backgroundColor': {'red': 0.9, 'green': 0.95, 'blue': 1.0}  # Light blue
    })
    
    # Input section header (row 9)
    worksheet.format('A9', {
        'textFormat': {'bold': True, 'fontSize': 12},
        'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95}  # Light gray
    })
    
    # Input labels (rows 10-16)
    worksheet.format('A10:A16', {'textFormat': {'bold': True}})
    
    # Highlight input cells in YELLOW with borders
    input_cells = ['B10', 'B11', 'B12', 'B13', 'B14', 'B15', 'B16']
    for cell in input_cells:
        worksheet.format(cell, {
            'backgroundColor': {'red': 1.0, 'green': 0.95, 'blue': 0.8},  # Yellow
            'borders': {
                'top': {'style': 'SOLID', 'width': 2, 'color': {'red': 0.8, 'green': 0.6, 'blue': 0.2}},
                'bottom': {'style': 'SOLID', 'width': 2, 'color': {'red': 0.8, 'green': 0.6, 'blue': 0.2}},
                'left': {'style': 'SOLID', 'width': 2, 'color': {'red': 0.8, 'green': 0.6, 'blue': 0.2}},
                'right': {'style': 'SOLID', 'width': 2, 'color': {'red': 0.8, 'green': 0.6, 'blue': 0.2}}
            }
        })
    
    # Format input cells
    worksheet.format('B10', {'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0'}})  # Weight as integer
    worksheet.format('B11', {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}})  # Cargo value as currency
    worksheet.format('B16', {'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}})  # Duty as percentage
    
    # Cost breakdown section header (row 18)
    worksheet.format('A18', {
        'textFormat': {'bold': True, 'fontSize': 12},
        'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95}  # Light gray
    })
    
    # Cost breakdown table header (row 19)
    worksheet.format('A19:C19', {
        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},  # Gray
        'textFormat': {'bold': True}
    })
    
    # Format amount column as currency (rows 20-31)
    worksheet.format('B20:B31', {
        'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}
    })
    
    # Total section header (row 33)
    worksheet.format('A33', {
        'textFormat': {'bold': True, 'fontSize': 12},
        'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95}  # Light gray
    })
    
    # Grand total row (row 34)
    worksheet.format('A34:B34', {
        'textFormat': {'bold': True, 'fontSize': 14},
        'backgroundColor': {'red': 0.85, 'green': 0.95, 'blue': 0.85},  # Light green
        'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'},
        'borders': {
            'top': {'style': 'SOLID', 'width': 3, 'color': {'red': 0.2, 'green': 0.6, 'blue': 0.2}},
            'bottom': {'style': 'SOLID', 'width': 3, 'color': {'red': 0.2, 'green': 0.6, 'blue': 0.2}},
            'left': {'style': 'SOLID', 'width': 3, 'color': {'red': 0.2, 'green': 0.6, 'blue': 0.2}},
            'right': {'style': 'SOLID', 'width': 3, 'color': {'red': 0.2, 'green': 0.6, 'blue': 0.2}}
        }
    })
    
    print("✅ Quick Estimate dashboard created")


def create_cost_breakdown_sheet(spreadsheet):
    """Create the Cost Breakdown sheet with detailed data by weight tier."""
    print("📊 Creating Cost Breakdown sheet...")
    
    try:
        worksheet = spreadsheet.worksheet("Cost Breakdown")
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Cost Breakdown", rows=1000, cols=15)
    
    all_data = []
    
    # Headers
    headers = ['Cost Component', 'Type', 'Formula/Notes'] + [f'{w} kg' for w in WEIGHT_TIERS]
    all_data.append(headers)
    
    # Input section
    all_data.append(['USER INPUTS', '', ''])  # Removed === to avoid formula parsing error
    input_data = [
        ['Cargo Value (USD total)', 1000, 'Enter total cargo value'],
        ['Duty Estimate (%)', 0, 'Enter duty percentage (e.g., 5 for 5%)'],
        ['FDA Required?', 'Yes', 'Yes or No'],
        ['Bond Required?', 'Yes', 'Yes or No (assumes no continuous bond)'],
        ['# Invoice Lines', 3, 'Number of invoice line items'],
        ['# Customs Exams', 0, 'Number of exams (if any)'],
        ['Delivery Address', 'TBD', 'For door delivery quote'],  # TBD as plain text, not formula
    ]
    all_data.extend(input_data)
    
    # Cost breakdown section
    all_data.append([''])
    all_data.append(['COST BREAKDOWN', '', ''])  # Removed === to avoid formula parsing error
    
    # Air Freight Rates
    air_freight_row = ['Air Freight (airport to airport)', 'Variable (per kg)', 'Rate per kg * weight']
    for weight in WEIGHT_TIERS:
        rate = AIR_FREIGHT_RATES[weight]
        formula = f'={rate}*{weight}'
        air_freight_row.append(formula)
    all_data.append(air_freight_row)
    
    # Export Documentation (fixed)
    export_doc_row = ['Export Documentation', 'Fixed', 'Per shipment'] + [95.00] * len(WEIGHT_TIERS)
    all_data.append(export_doc_row)
    
    # Inland Transport
    inland_row = ['Inland Transport (Brazil)', 'Fixed + Variable', '695 + (0.0015 * cargo_value)']
    for _ in WEIGHT_TIERS:
        formula = '=695+0.0015*$B$4'
        inland_row.append(formula)
    all_data.append(inland_row)
    
    # Brazil Airport Charges
    airport_row = ['Brazil Airport Charges', 'Variable (min)', '0.30/kg, minimum 250']
    for weight in WEIGHT_TIERS:
        formula = f'=MAX(0.30*{weight}, 250)'
        airport_row.append(formula)
    all_data.append(airport_row)
    
    # US Terminal Fee
    terminal_row = ['US Airline Terminal Fee', 'Fixed', '200-225, using midpoint 212.50'] + [212.50] * len(WEIGHT_TIERS)
    all_data.append(terminal_row)
    
    # Import Handling Fee
    handling_row = ['US Import Handling Fee', 'Fixed', 'Per shipment'] + [125.00] * len(WEIGHT_TIERS)
    all_data.append(handling_row)
    
    # US Customs Clearance
    customs_row = ['US Customs Clearance', 'Fixed', 'Base fee'] + [150.00] * len(WEIGHT_TIERS)
    all_data.append(customs_row)
    
    # Invoice Line Items
    line_items_row = ['Invoice Line Items', 'Conditional', 'First 3 free, then $5/line']
    for _ in WEIGHT_TIERS:
        formula = '=MAX(0, ($B$8-3)*5)'
        line_items_row.append(formula)
    all_data.append(line_items_row)
    
    # FDA Processing
    fda_row = ['FDA Processing', 'Conditional', 'If applicable (likely for cacao)']
    for _ in WEIGHT_TIERS:
        formula = '=IF(UPPER($B$6)="YES", 100, 0)'
        fda_row.append(formula)
    all_data.append(fda_row)
    
    # Bond
    bond_row = ['Bond (Single-Entry)', 'Conditional', '6 per 1000 value + duty, min 100']
    for _ in WEIGHT_TIERS:
        formula = '=IF(UPPER($B$7)="YES", MAX(100, 6*($B$4/1000)+($B$4*$B$5/100)), 0)'
        bond_row.append(formula)
    all_data.append(bond_row)
    
    # MPF
    mpf_row = ['MPF (Merchandise Processing Fee)', 'Variable', '0.3464% of value, min 33.58, max 651.50']
    for _ in WEIGHT_TIERS:
        formula = '=MIN(MAX(0.003464*$B$4, 33.58), 651.50)'
        mpf_row.append(formula)
    all_data.append(mpf_row)
    
    # Exam Charges
    exam_row = ['US Customs Exam Charges', 'Conditional', 'Cost + 125 per exam (assume cost=0)']
    for _ in WEIGHT_TIERS:
        formula = '=$B$9*125'
        exam_row.append(formula)
    all_data.append(exam_row)
    
    # Subtotal row
    cost_start_row = len(all_data) - 13  # Start of cost rows
    subtotal_row = ['SUBTOTAL (excluding ad valorem)', '', '']
    for col_idx, weight in enumerate(WEIGHT_TIERS):
        col_letter = chr(68 + col_idx)  # D=68, E=69, etc.
        formula = f'=SUM({col_letter}{cost_start_row+1}:{col_letter}{len(all_data)})'
        subtotal_row.append(formula)
    all_data.append(subtotal_row)
    
    # Ad valorem note
    adval_row = ['Inland Ad Valorem (0.15% of cargo value)', 'Variable', 'Already included in Inland Transport row'] + ['N/A'] * len(WEIGHT_TIERS)
    all_data.append(adval_row)
    
    # Batch update
    worksheet.update('A1', all_data, value_input_option='USER_ENTERED')
    
    # Formatting
    worksheet.format('A1:H1', {
        'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.6},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}}
    })
    
    # Format section headers
    input_header_row = 2
    cost_header_row = 11
    worksheet.format(f'A{input_header_row}', {'textFormat': {'bold': True}})
    worksheet.format(f'A{cost_header_row}', {'textFormat': {'bold': True}})
    
    # Format subtotal row
    subtotal_row_num = len(all_data) - 1
    worksheet.format(f'A{subtotal_row_num}:C{subtotal_row_num}', {'textFormat': {'bold': True}})
    
    # Format numeric columns (D through H for weight tiers)
    for col_idx in range(4, 4 + len(WEIGHT_TIERS)):
        col_letter = chr(64 + col_idx)
        worksheet.format(f'{col_letter}{cost_header_row+1}:{col_letter}{subtotal_row_num}', {
            'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}
        })
    
    # Create named range for air freight rates (for VLOOKUP)
    try:
        # Air rates range: D13:H13 (air freight row)
        spreadsheet.batch_update([{
            'addNamedRange': {
                'namedRange': {
                    'name': 'AirRates',
                    'range': {
                        'sheetId': worksheet.id,
                        'startRowIndex': 12,  # Row 13 (0-indexed)
                        'endRowIndex': 13,
                        'startColumnIndex': 3,  # Column D (0-indexed)
                        'endColumnIndex': 8
                    }
                }
            }
        }])
    except Exception as e:
        print(f"⚠️  Could not create named range: {e}")
    
    print("✅ Cost Breakdown sheet created")


def create_totals_sheet(spreadsheet):
    """Create the Totals by Weight summary sheet."""
    print("📊 Creating Totals by Weight sheet...")
    
    try:
        worksheet = spreadsheet.worksheet("Totals by Weight")
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Totals by Weight", rows=100, cols=15)
    
    # Get subtotal row from Cost Breakdown sheet
    cost_sheet = spreadsheet.worksheet("Cost Breakdown")
    cost_data = cost_sheet.get_all_values()
    subtotal_row = None
    for i, row in enumerate(cost_data, start=1):
        if row and len(row) > 0 and 'SUBTOTAL' in str(row[0]).upper():
            subtotal_row = i
            break
    
    totals_data = []
    totals_data.append(['Weight (kg)', 'Total Cost (USD)', 'Per kg Cost (USD)'])
    
    if subtotal_row:
        for weight_idx, weight in enumerate(WEIGHT_TIERS, start=0):
            col_letter = chr(68 + weight_idx)  # D=68, E=69, etc.
            formula_total = f'=\'Cost Breakdown\'!{col_letter}{subtotal_row}'
            formula_per_kg = f'={col_letter}{weight_idx+2}/{weight}'
            totals_data.append([weight, formula_total, formula_per_kg])
    else:
        for weight in WEIGHT_TIERS:
            totals_data.append([weight, '', ''])
    
    worksheet.update('A1', totals_data, value_input_option='USER_ENTERED')
    
    # Formatting
    worksheet.format('A1:C1', {
        'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.6},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}}
    })
    worksheet.format('B2:C100', {
        'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}
    })
    
    print("✅ Totals by Weight sheet created")


def create_notes_sheet(spreadsheet):
    """Create the Notes & Assumptions sheet."""
    print("📊 Creating Notes & Assumptions sheet...")
    
    try:
        worksheet = spreadsheet.worksheet("Notes & Assumptions")
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Notes & Assumptions", rows=100, cols=10)
    
    notes = [
        ['NOTES ON ESTIMATES'],
        [''],
        ['Ad Valorem/MPF/Bond:'],
        ['These scale with cargo value. For example, for 200 kg at $5/kg = $1,000 value:'],
        ['- Inland ad valorem: +$1.50 (0.15% of $1,000)'],
        ['- MPF: ~$33.58 minimum (0.3464% of $1,000)'],
        ['- Bond: ~$100 minimum (if required)'],
        [''],
        ['Dashboard Interpolation:'],
        ['The Quick Estimate dashboard uses linear interpolation for air freight rates between weight brackets.'],
        ['For example, 400 kg interpolates between 300 kg ($3.40/kg) and 500 kg ($3.30/kg) rates.'],
        ['Verify with provider for accuracy on custom weights.'],
        [''],
        ['Seasonal Note:'],
        ['No data on post-Christmas drop; original query unanswered.'],
        [''],
        ['Ocean Freight:'],
        ['Not quoted (deemed too expensive due to infrastructure/distance).'],
        [''],
        ['Missing Information:'],
        ['- Full local charges to SSA airport (still pending per emails)'],
        ['- Delivery to door pricing (available upon request)'],
        [''],
        ['Product Types:'],
        ['- Cacao beans (1801.00.00)'],
        ['- Cacao nibs (1801.00.00)'],
        ['- Cacao liquor (1801.00.00)'],
        [''],
        ['Pallet Specifications:'],
        ['- Maximum dimensions: 300 x 200 x 160 cm'],
        ['- Maximum weight: 4,000 kgs per pallet'],
        [''],
        ['Contact Information:'],
        ['Company: SeaCoast Logistics (5CL)'],
        ['Contact: Graziela Vedana'],
        ['Email: Graziela@seacoastlogistics.com / graziela@5cl.rs'],
        [''],
        ['Quotation Date:'],
        ['- Air freight rates: November 4, 2025'],
        ['- Inland charges: November 5, 2025'],
    ]
    
    worksheet.update('A1', notes)
    worksheet.format('A1', {'textFormat': {'bold': True, 'fontSize': 14}})
    
    print("✅ Notes & Assumptions sheet created")


def update_hyperlinks(spreadsheet):
    """Update hyperlinks in Quick Estimate dashboard after all sheets are created."""
    try:
        dashboard = spreadsheet.worksheet("Quick Estimate")
        cost_sheet = spreadsheet.worksheet("Cost Breakdown")
        notes_sheet = spreadsheet.worksheet("Notes & Assumptions")
        
        # Update hyperlinks
        cost_link = f'=HYPERLINK("#gid={cost_sheet.id}", "Cost Breakdown")'
        notes_link = f'=HYPERLINK("#gid={notes_sheet.id}", "Notes & Assumptions")'
        
        # Find the row with hyperlinks (should be near the end)
        data = dashboard.get_all_values()
        for i, row in enumerate(data, start=1):
            if row and len(row) > 0:
                if 'View Detailed Breakdown' in str(row[0]):
                    dashboard.update_cell(i, 2, cost_link)
                elif 'View Notes' in str(row[0]):
                    dashboard.update_cell(i, 2, notes_link)
    except Exception as e:
        print(f"⚠️  Could not update hyperlinks: {e}")


def main():
    """Main execution function."""
    print("="*80)
    print("SeaCoast Logistics - Airfreight Costing Sheet Creator")
    print("="*80)
    
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        # Clean up unused sheets first
        cleanup_unused_sheets(spreadsheet)
        time.sleep(1)
        
        # Create all sheets (order matters for hyperlinks)
        create_cost_breakdown_sheet(spreadsheet)
        time.sleep(2)  # Rate limit protection
        
        create_notes_sheet(spreadsheet)
        time.sleep(1)
        
        create_totals_sheet(spreadsheet)
        time.sleep(1)
        
        create_quick_estimate_dashboard(spreadsheet)
        time.sleep(2)
        
        # Update hyperlinks now that all sheets exist
        update_hyperlinks(spreadsheet)
        
        # Final cleanup in case any sheets were created during the process
        cleanup_unused_sheets(spreadsheet)
        
        print("\n✅ All sheets created successfully!")
        print(f"📊 View sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")
        print("\n📋 Sheets created:")
        print("  1. Quick Estimate - Main dashboard with inputs and instant calculations")
        print("  2. Cost Breakdown - Detailed cost components by weight tier")
        print("  3. Totals by Weight - Summary totals and per-kg costs")
        print("  4. Notes & Assumptions - Documentation and notes")
        print("\n💡 Usage:")
        print("  - Open the 'Quick Estimate' sheet")
        print("  - Enter weight in B4 (or select from dropdown)")
        print("  - Adjust other inputs as needed")
        print("  - Total cost updates automatically in B27")
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
