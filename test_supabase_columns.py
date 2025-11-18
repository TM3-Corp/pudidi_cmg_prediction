#!/usr/bin/env python3
"""
Test what columns are actually returned from Supabase
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from lib.utils.supabase_client import SupabaseClient

def main():
    print("="*60)
    print("TESTING SUPABASE COLUMN NAMES")
    print("="*60)

    supabase = SupabaseClient()

    # Test ML Predictions
    print("\n📊 Testing ml_predictions table...")
    ml_records = supabase.get_ml_predictions(limit=1)

    if ml_records:
        print(f"✅ Got {len(ml_records)} record(s)")
        print(f"\n🔑 Columns returned:")
        for key in sorted(ml_records[0].keys()):
            print(f"   - {key}")

        # Check for forecast_date and forecast_hour
        has_forecast_date = 'forecast_date' in ml_records[0]
        has_forecast_hour = 'forecast_hour' in ml_records[0]

        print(f"\n📅 Has forecast_date: {'✅' if has_forecast_date else '❌'}")
        print(f"🕐 Has forecast_hour: {'✅' if has_forecast_hour else '❌'}")

        if has_forecast_date and has_forecast_hour:
            print(f"\n✅ Sample values:")
            print(f"   forecast_date: {ml_records[0]['forecast_date']}")
            print(f"   forecast_hour: {ml_records[0]['forecast_hour']}")
    else:
        print("❌ No ML predictions found")

    # Test CMG Programado
    print("\n" + "="*60)
    print("📊 Testing cmg_programado table...")
    prog_records = supabase.get_cmg_programado(limit=1, latest_forecast_only=False)

    if prog_records:
        print(f"✅ Got {len(prog_records)} record(s)")
        print(f"\n🔑 Columns returned:")
        for key in sorted(prog_records[0].keys()):
            print(f"   - {key}")

        # Check for forecast_date and forecast_hour
        has_forecast_date = 'forecast_date' in prog_records[0]
        has_forecast_hour = 'forecast_hour' in prog_records[0]

        print(f"\n📅 Has forecast_date: {'✅' if has_forecast_date else '❌'}")
        print(f"🕐 Has forecast_hour: {'✅' if has_forecast_hour else '❌'}")

        if has_forecast_date and has_forecast_hour:
            print(f"\n✅ Sample values:")
            print(f"   forecast_date: {prog_records[0]['forecast_date']}")
            print(f"   forecast_hour: {prog_records[0]['forecast_hour']}")
    else:
        print("❌ No CMG Programado found")

if __name__ == "__main__":
    main()
