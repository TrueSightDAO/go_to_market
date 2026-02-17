#!/usr/bin/env python3
"""
Deep dive into pricing and consignment rejection reasons.

This script extracts detailed information about:
- Pricing-related rejections (markup, wholesale pricing, etc.)
- Consignment-related rejections (setup, process, etc.)
"""

from __future__ import annotations

from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
WORKSHEET_NAME = "Hit List"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheets_client() -> gspread.Client:
    """Get authenticated Google Sheets client."""
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"google_credentials.json not found at {creds_path}. "
            "Please place your service account credentials in the repository root."
        )

    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def fetch_hit_list() -> pd.DataFrame:
    """Fetch the Hit List from Google Sheets."""
    client = get_google_sheets_client()
    worksheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

    print(f"✅ Connected to spreadsheet: {SPREADSHEET_ID}")
    print(f"   Worksheet: {WORKSHEET_NAME}")

    values = worksheet.get_all_values()
    if len(values) < 1:
        raise ValueError("Worksheet is empty.")

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)

    print(f"📊 Retrieved {len(df)} rows with {len(df.columns)} columns.")
    return df


def normalize_text(text: str) -> str:
    """Normalize text for analysis."""
    if pd.isna(text):
        return ""
    return str(text).strip()


def extract_full_notes(row: pd.Series) -> str:
    """Extract all notes from a row, cleaning up encrypted signatures."""
    sales_notes = normalize_text(row.get("Sales Process Notes", ""))
    outcome = normalize_text(row.get("Outcome", ""))
    remarks = normalize_text(row.get("Remarks", ""))
    dapp_remarks = normalize_text(row.get("DApp Remarks", ""))
    
    # Combine all notes
    all_notes = []
    
    if outcome:
        all_notes.append(f"OUTCOME: {outcome}")
    
    if sales_notes:
        # Try to extract meaningful text after signatures
        # Pattern: [timestamp | signature] actual text
        parts = sales_notes.split("]")
        if len(parts) > 1:
            # Take parts after signatures
            meaningful_parts = [p.strip() for p in parts[1:] if p.strip() and len(p.strip()) > 10]
            if meaningful_parts:
                all_notes.append(f"SALES NOTES: {' '.join(meaningful_parts)}")
        else:
            # No signature pattern, use as-is if meaningful
            if len(sales_notes) > 20 and not sales_notes.startswith("MIIBI"):
                all_notes.append(f"SALES NOTES: {sales_notes}")
    
    if remarks:
        all_notes.append(f"REMARKS: {remarks}")
    
    if dapp_remarks:
        all_notes.append(f"DAPP REMARKS: {dapp_remarks}")
    
    return "\n".join(all_notes)


def analyze_pricing_consignment_issues(df: pd.DataFrame) -> dict:
    """Analyze pricing and consignment issues in detail."""
    # Find store name column
    name_col = None
    for col in ["Shop Name", "Store Name", "Name", df.columns[0]]:
        if col in df.columns:
            name_col = col
            break
    
    if name_col is None:
        raise ValueError("Could not find store name column")
    
    pricing_stores = []
    consignment_stores = []
    
    for idx, row in df.iterrows():
        status = normalize_text(row.get("Status", ""))
        store_name = normalize_text(row.get(name_col, ""))
        
        if not store_name:
            continue
        
        # Get all notes
        all_notes = extract_full_notes(row)
        notes_lower = all_notes.lower()
        
        # Check for pricing issues
        pricing_keywords = [
            "price", "pricing", "cost", "expensive", "markup", "margin", 
            "wholesale", "retail", "$", "dollar", "too high", "can't afford",
            "need", "requires", "want", "looking for"
        ]
        
        # Check for consignment issues
        consignment_keywords = [
            "consignment", "consignment-based", "not set up for consignment",
            "don't do consignment", "no consignment", "consignment model",
            "consignment sales", "calculate how many per"
        ]
        
        has_pricing_issue = any(keyword in notes_lower for keyword in pricing_keywords)
        has_consignment_issue = any(keyword in notes_lower for keyword in consignment_keywords)
        
        # Only include if rejected or has clear issue
        if status == "Rejected" or has_pricing_issue or has_consignment_issue:
            store_info = {
                "name": store_name,
                "status": status,
                "city": normalize_text(row.get("City", "")),
                "state": normalize_text(row.get("State", "")),
                "visit_date": normalize_text(row.get("Visit Date", "")),
                "all_notes": all_notes,
                "row": idx + 2,
            }
            
            if has_pricing_issue:
                pricing_stores.append(store_info)
            
            if has_consignment_issue:
                consignment_stores.append(store_info)
    
    return {
        "pricing": pricing_stores,
        "consignment": consignment_stores,
    }


def extract_pricing_details(notes: str) -> dict:
    """Extract specific pricing-related information."""
    notes_lower = notes.lower()
    details = {
        "issue_type": None,
        "specific_mention": None,
        "markup_mentioned": False,
        "wholesale_mentioned": False,
        "retail_mentioned": False,
    }
    
    # Check for specific pricing issues
    if "markup" in notes_lower:
        details["markup_mentioned"] = True
        details["issue_type"] = "Markup"
        # Try to extract context
        import re
        markup_context = re.search(r"markup[^.]{0,100}", notes_lower, re.IGNORECASE)
        if markup_context:
            details["specific_mention"] = markup_context.group(0)[:150]
    
    if "wholesale" in notes_lower:
        details["wholesale_mentioned"] = True
        if not details["issue_type"]:
            details["issue_type"] = "Wholesale Pricing"
    
    if "retail" in notes_lower:
        details["retail_mentioned"] = True
    
    if "too high" in notes_lower or "expensive" in notes_lower:
        if not details["issue_type"]:
            details["issue_type"] = "Price Too High"
    
    if "need" in notes_lower or "want" in notes_lower or "requires" in notes_lower:
        if not details["issue_type"]:
            details["issue_type"] = "Pricing Requirements"
        # Try to extract what they need
        import re
        need_context = re.search(r"(need|want|requires|looking for)[^.]{0,100}", notes_lower, re.IGNORECASE)
        if need_context:
            details["specific_mention"] = need_context.group(0)[:150]
    
    return details


def extract_consignment_details(notes: str) -> dict:
    """Extract specific consignment-related information."""
    notes_lower = notes.lower()
    details = {
        "issue_type": None,
        "specific_mention": None,
        "not_setup": False,
        "process_issue": False,
    }
    
    if "not set up" in notes_lower or "don't do" in notes_lower or "no consignment" in notes_lower:
        details["not_setup"] = True
        details["issue_type"] = "Not Set Up for Consignment"
    
    if "calculate" in notes_lower or "process" in notes_lower:
        details["process_issue"] = True
        if not details["issue_type"]:
            details["issue_type"] = "Consignment Process Issue"
    
    # Try to extract specific context
    import re
    consignment_context = re.search(r"consignment[^.]{0,150}", notes_lower, re.IGNORECASE)
    if consignment_context:
        details["specific_mention"] = consignment_context.group(0)[:200]
    
    return details


def main() -> None:
    """Main function."""
    print("=" * 80)
    print("PRICING & CONSIGNMENT DEEP DIVE")
    print("=" * 80)
    
    try:
        df = fetch_hit_list()
        issues = analyze_pricing_consignment_issues(df)
        
        # Analyze Pricing Issues
        print("\n" + "=" * 80)
        print("PRICING ISSUES ANALYSIS")
        print("=" * 80)
        
        if not issues["pricing"]:
            print("\n✅ No pricing issues found in rejected stores.")
        else:
            print(f"\n📊 Found {len(issues['pricing'])} store(s) with pricing issues:\n")
            
            for i, store in enumerate(issues["pricing"], 1):
                print(f"{i}. {store['name']}")
                if store['city'] or store['state']:
                    location = f"{store['city']}, {store['state']}".strip(", ")
                    print(f"   Location: {location}")
                print(f"   Status: {store['status']}")
                
                # Extract pricing details
                pricing_details = extract_pricing_details(store['all_notes'])
                if pricing_details['issue_type']:
                    print(f"   Issue Type: {pricing_details['issue_type']}")
                if pricing_details['specific_mention']:
                    print(f"   Details: {pricing_details['specific_mention']}")
                
                # Show full notes
                if store['all_notes']:
                    print(f"\n   Full Notes:")
                    for line in store['all_notes'].split('\n'):
                        if line.strip():
                            print(f"      {line[:150]}")
                print()
        
        # Analyze Consignment Issues
        print("=" * 80)
        print("CONSIGNMENT ISSUES ANALYSIS")
        print("=" * 80)
        
        if not issues["consignment"]:
            print("\n✅ No consignment issues found in rejected stores.")
        else:
            print(f"\n📊 Found {len(issues['consignment'])} store(s) with consignment issues:\n")
            
            for i, store in enumerate(issues["consignment"], 1):
                print(f"{i}. {store['name']}")
                if store['city'] or store['state']:
                    location = f"{store['city']}, {store['state']}".strip(", ")
                    print(f"   Location: {location}")
                print(f"   Status: {store['status']}")
                
                # Extract consignment details
                consignment_details = extract_consignment_details(store['all_notes'])
                if consignment_details['issue_type']:
                    print(f"   Issue Type: {consignment_details['issue_type']}")
                if consignment_details['specific_mention']:
                    print(f"   Details: {consignment_details['specific_mention']}")
                
                # Show full notes
                if store['all_notes']:
                    print(f"\n   Full Notes:")
                    for line in store['all_notes'].split('\n'):
                        if line.strip():
                            print(f"      {line[:150]}")
                print()
        
        # Summary & Recommendations
        print("=" * 80)
        print("SUMMARY & RECOMMENDATIONS")
        print("=" * 80)
        
        print(f"\n📈 Findings:")
        print(f"   Pricing Issues: {len(issues['pricing'])} store(s)")
        print(f"   Consignment Issues: {len(issues['consignment'])} store(s)")
        
        print(f"\n💡 Recommendations:")
        
        if issues["pricing"]:
            print(f"\n   PRICING:")
            print(f"   - Lead with flexible pricing options upfront")
            print(f"   - Ask about their markup requirements early in conversation")
            print(f"   - Offer both consignment AND purchase options")
            print(f"   - Be transparent about wholesale pricing structure")
            print(f"   - Consider tiered pricing based on order volume")
        
        if issues["consignment"]:
            print(f"\n   CONSIGNMENT:")
            print(f"   - Lead with PURCHASE option first, mention consignment as alternative")
            print(f"   - For stores not set up for consignment, offer simple purchase model")
            print(f"   - Simplify consignment process/paperwork if offering it")
            print(f"   - Consider hybrid model: purchase with return policy")
        
        print("=" * 80)
        
    except Exception as exc:
        print(f"\n❌ Error analyzing pricing/consignment: {exc}")
        raise


if __name__ == "__main__":
    main()






