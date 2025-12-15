#!/usr/bin/env python3
"""
Analyze rejection reasons from the Holistic Wellness Hit List.

This script examines stores with "Rejected" status and extracts:
- Store information
- Rejection reasons from notes/remarks
- Common patterns in rejections
"""

from __future__ import annotations

from pathlib import Path
from collections import Counter

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


def extract_rejection_reasons(df: pd.DataFrame) -> list[dict]:
    """Extract rejection information from stores with Rejected status."""
    # Find store name column
    name_col = None
    for col in ["Shop Name", "Store Name", "Name", df.columns[0]]:
        if col in df.columns:
            name_col = col
            break
    
    if name_col is None:
        raise ValueError("Could not find store name column")
    
    rejected_stores = []
    
    for idx, row in df.iterrows():
        status = normalize_text(row.get("Status", ""))
        if status != "Rejected":
            continue
        
        store_name = normalize_text(row.get(name_col, ""))
        if not store_name:
            continue
        
        # Collect all relevant notes/remarks
        sales_notes = normalize_text(row.get("Sales Process Notes", ""))
        outcome = normalize_text(row.get("Outcome", ""))
        remarks = normalize_text(row.get("Remarks", ""))
        dapp_remarks = normalize_text(row.get("DApp Remarks", ""))
        visit_date = normalize_text(row.get("Visit Date", ""))
        city = normalize_text(row.get("City", ""))
        state = normalize_text(row.get("State", ""))
        
        # Combine all notes
        all_notes = " | ".join(filter(None, [
            sales_notes,
            outcome,
            remarks,
            dapp_remarks,
        ]))
        
        rejected_stores.append({
            "name": store_name,
            "city": city,
            "state": state,
            "visit_date": visit_date,
            "sales_notes": sales_notes,
            "outcome": outcome,
            "remarks": remarks,
            "dapp_remarks": dapp_remarks,
            "all_notes": all_notes,
            "row": idx + 2,
        })
    
    return rejected_stores


def extract_rejection_reason(store: dict) -> str:
    """Extract the primary rejection reason from store data."""
    # Priority: Outcome field first, then parse notes
    outcome = store.get("outcome", "").lower()
    sales_notes = store.get("sales_notes", "").lower()
    
    # Check Outcome field first (most reliable)
    if outcome:
        # Remove "rejected -" prefix if present
        outcome_clean = outcome.replace("rejected -", "").strip()
        if outcome_clean:
            return outcome_clean
    
    # Try to extract from sales notes (skip encrypted signatures)
    if sales_notes:
        # Look for text after timestamps/signatures
        # Common pattern: [timestamp | signature] actual text
        parts = sales_notes.split("]")
        if len(parts) > 1:
            # Take the last part (after all signatures)
            last_part = parts[-1].strip()
            if last_part and len(last_part) > 10:  # Meaningful text
                return last_part
    
    return "No reason provided"


def analyze_rejection_patterns(rejected_stores: list[dict]) -> dict:
    """Analyze common patterns in rejections."""
    patterns = {
        "pricing": [],
        "not_interested": [],
        "no_space": [],
        "wrong_fit": [],
        "consignment_issue": [],
        "product_awareness": [],
        "timing": [],
        "other": [],
    }
    
    # Extract reasons and categorize
    for store in rejected_stores:
        reason = extract_rejection_reason(store)
        reason_lower = reason.lower()
        
        # Store the extracted reason
        store["extracted_reason"] = reason
        
        # Categorize based on keywords
        if any(word in reason_lower for word in ["price", "cost", "expensive", "markup", "margin", "wholesale", "$", "dollar"]):
            patterns["pricing"].append({"name": store["name"], "reason": reason})
        elif any(word in reason_lower for word in ["consignment", "consignment-based", "not set up for consignment"]):
            patterns["consignment_issue"].append({"name": store["name"], "reason": reason})
        elif any(word in reason_lower for word in ["no space", "no room", "full", "no shelf", "doesn't have the space", "don't have space"]):
            patterns["no_space"].append({"name": store["name"], "reason": reason})
        elif any(word in reason_lower for word in ["not aligned", "theme", "doesn't fit", "not right", "different", "not what we", "not our"]):
            patterns["wrong_fit"].append({"name": store["name"], "reason": reason})
        elif any(word in reason_lower for word in ["don't know", "doesn't know", "what it is", "how it taste", "unfamiliar"]):
            patterns["product_awareness"].append({"name": store["name"], "reason": reason})
        elif any(word in reason_lower for word in ["not interested", "don't want", "no interest", "decline"]):
            patterns["not_interested"].append({"name": store["name"], "reason": reason})
        elif any(word in reason_lower for word in ["later", "not now", "maybe later", "future", "timing", "not ready"]):
            patterns["timing"].append({"name": store["name"], "reason": reason})
        else:
            patterns["other"].append({"name": store["name"], "reason": reason})
    
    return patterns


def main() -> None:
    """Main function."""
    print("=" * 80)
    print("REJECTION ANALYSIS")
    print("=" * 80)
    
    try:
        df = fetch_hit_list()
        rejected_stores = extract_rejection_reasons(df)
        
        if not rejected_stores:
            print("\n✅ No rejected stores found in the Hit List.")
            return
        
        print(f"\n📋 Found {len(rejected_stores)} rejected stores:")
        print("=" * 80)
        
        # Display detailed information for each rejected store
        for i, store in enumerate(rejected_stores, 1):
            print(f"\n{i}. {store['name']}")
            if store['city'] or store['state']:
                location = f"{store['city']}, {store['state']}".strip(", ")
                print(f"   Location: {location}")
            if store['visit_date']:
                print(f"   Visit Date: {store['visit_date']}")
            
            # Extract and show primary rejection reason
            reason = extract_rejection_reason(store)
            print(f"   Reason: {reason}")
            
            # Show outcome if different from extracted reason
            if store['outcome'] and store['outcome'].lower() not in reason.lower():
                print(f"   Outcome: {store['outcome']}")
        
        # Analyze patterns
        print("\n" + "=" * 80)
        print("REJECTION PATTERN ANALYSIS")
        print("=" * 80)
        
        patterns = analyze_rejection_patterns(rejected_stores)
        
        print(f"\n📊 Categorized Rejections:")
        print(f"   Pricing Issues: {len(patterns['pricing'])}")
        if patterns['pricing']:
            for item in patterns['pricing']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        print(f"\n   Consignment Issues: {len(patterns['consignment_issue'])}")
        if patterns['consignment_issue']:
            for item in patterns['consignment_issue']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        print(f"\n   No Space/Inventory: {len(patterns['no_space'])}")
        if patterns['no_space']:
            for item in patterns['no_space']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        print(f"\n   Wrong Fit/Theme: {len(patterns['wrong_fit'])}")
        if patterns['wrong_fit']:
            for item in patterns['wrong_fit']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        print(f"\n   Product Awareness: {len(patterns['product_awareness'])}")
        if patterns['product_awareness']:
            for item in patterns['product_awareness']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        print(f"\n   Not Interested: {len(patterns['not_interested'])}")
        if patterns['not_interested']:
            for item in patterns['not_interested']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        print(f"\n   Timing Issues: {len(patterns['timing'])}")
        if patterns['timing']:
            for item in patterns['timing']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        print(f"\n   Other/Unclear: {len(patterns['other'])}")
        if patterns['other']:
            for item in patterns['other']:
                print(f"      - {item['name']}: {item['reason'][:100]}")
        
        # Summary statistics
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total Rejected Stores: {len(rejected_stores)}")
        print(f"Stores with Notes: {sum(1 for s in rejected_stores if s['all_notes'])}")
        print(f"Stores without Notes: {sum(1 for s in rejected_stores if not s['all_notes'])}")
        
        # Most common rejection reason
        category_counts = {k: len(v) for k, v in patterns.items() if len(v) > 0}
        if category_counts:
            top_reason = max(category_counts.items(), key=lambda x: x[1])
            print(f"\nMost Common Reason: {top_reason[0].replace('_', ' ').title()} ({top_reason[1]} stores)")
            
            # Show actionable insights
            print(f"\n💡 Key Insights:")
            if patterns['pricing']:
                print(f"   - {len(patterns['pricing'])} store(s) rejected due to pricing - consider flexible pricing options")
            if patterns['consignment_issue']:
                print(f"   - {len(patterns['consignment_issue'])} store(s) not set up for consignment - offer purchase option upfront")
            if patterns['no_space']:
                print(f"   - {len(patterns['no_space'])} store(s) have no space - follow up when inventory changes")
            if patterns['product_awareness']:
                print(f"   - {len(patterns['product_awareness'])} store(s) don't know the product - bring samples on visits")
            if patterns['wrong_fit']:
                print(f"   - {len(patterns['wrong_fit'])} store(s) wrong fit - improve pre-visit research/targeting")
        
        print("=" * 80)
        
    except Exception as exc:
        print(f"\n❌ Error analyzing rejections: {exc}")
        raise


if __name__ == "__main__":
    main()

