#!/usr/bin/env python3
"""
Validate CMG Programado data for performance analysis
Checks data integrity and readiness for comparison
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

def validate_data():
    """Validate the CMG Programado historical data"""
    
    # Load the data
    data_path = Path('data/cmg_programado_history.json')
    if not data_path.exists():
        print("❌ Data file not found")
        return False
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    print("="*60)
    print("CMG PROGRAMADO DATA VALIDATION")
    print("="*60)
    
    # Check structure
    print("\n1. STRUCTURE CHECK:")
    has_metadata = 'metadata' in data
    has_historical = 'historical_data' in data
    print(f"   ✓ Metadata present: {has_metadata}")
    print(f"   ✓ Historical data present: {has_historical}")
    
    if not (has_metadata and has_historical):
        print("   ❌ Missing required structure")
        return False
    
    # Check metadata
    print("\n2. METADATA:")
    meta = data['metadata']
    print(f"   Node: {meta.get('node', 'N/A')}")
    print(f"   Total days: {meta.get('total_days', 0)}")
    print(f"   Total hours: {meta.get('total_hours', 0)}")
    print(f"   Last update: {meta.get('last_update', 'N/A')}")
    
    # Check data coverage
    print("\n3. DATA COVERAGE:")
    historical = data['historical_data']
    dates = sorted(historical.keys())
    print(f"   Date range: {dates[0]} to {dates[-1]}")
    print(f"   Total days: {len(dates)}")
    
    # Check hourly completeness
    print("\n4. HOURLY COMPLETENESS:")
    incomplete_days = []
    for date in dates:
        hours = historical[date]
        if len(hours) < 24:
            incomplete_days.append(f"{date} ({len(hours)} hours)")
    
    if incomplete_days:
        print(f"   ⚠️  Incomplete days found:")
        for day in incomplete_days:
            print(f"      - {day}")
    else:
        print(f"   ✓ All days have 24 hours")
    
    # Check data values
    print("\n5. VALUE ANALYSIS:")
    all_values = []
    zero_count = 0
    for date in historical:
        for hour, hour_data in historical[date].items():
            value = hour_data.get('value')
            if value is not None:
                all_values.append(value)
                if value == 0.0:
                    zero_count += 1
    
    if all_values:
        min_val = min(all_values)
        max_val = max(all_values)
        avg_val = sum(all_values) / len(all_values)
        print(f"   Min value: {min_val:.2f} USD/MWh")
        print(f"   Max value: {max_val:.2f} USD/MWh")
        print(f"   Avg value: {avg_val:.2f} USD/MWh")
        print(f"   Zero values: {zero_count} ({zero_count*100/len(all_values):.1f}%)")
    
    # Check for required fields
    print("\n6. FIELD COMPLETENESS:")
    sample_date = dates[0]
    sample_hour = list(historical[sample_date].keys())[0]
    sample_data = historical[sample_date][sample_hour]
    
    required_fields = ['value', 'node', 'timestamp']
    missing_fields = []
    for field in required_fields:
        if field not in sample_data:
            missing_fields.append(field)
    
    if missing_fields:
        print(f"   ❌ Missing fields: {', '.join(missing_fields)}")
    else:
        print(f"   ✓ All required fields present")
        print(f"   Sample record: {sample_data}")
    
    # Performance analysis readiness
    print("\n7. PERFORMANCE ANALYSIS READINESS:")
    ready_for_analysis = True
    
    # Check if we have at least 24 hours
    if meta.get('total_hours', 0) < 24:
        print("   ❌ Need at least 24 hours of data")
        ready_for_analysis = False
    else:
        print(f"   ✓ Sufficient data ({meta.get('total_hours')} hours)")
    
    # Check if node is PMontt220
    if meta.get('node') != 'PMontt220':
        print(f"   ❌ Wrong node: {meta.get('node')} (expected PMontt220)")
        ready_for_analysis = False
    else:
        print("   ✓ Correct node (PMontt220)")
    
    # Check if values are reasonable
    if all_values and (min_val < 0 or max_val > 1000):
        print(f"   ⚠️  Unusual values detected (min: {min_val}, max: {max_val})")
    else:
        print("   ✓ Values within expected range")
    
    print("\n" + "="*60)
    if ready_for_analysis:
        print("✅ DATA VALIDATED - Ready for performance analysis!")
        print("\nYou can now:")
        print("1. Upload to GitHub Gist for API access")
        print("2. Test performance comparison in Rendimiento view")
        print("3. Schedule automated updates")
    else:
        print("❌ DATA VALIDATION FAILED - Please fix issues above")
    
    return ready_for_analysis

if __name__ == "__main__":
    success = validate_data()
    exit(0 if success else 1)