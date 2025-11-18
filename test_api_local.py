#!/usr/bin/env python3
"""
Test the API logic locally to see actual error
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

sys.path.insert(0, str(Path(__file__).parent))

from lib.utils.supabase_client import SupabaseClient

def main():
    try:
        supabase = SupabaseClient()
        santiago_tz = pytz.timezone('America/Santiago')
        end_date = datetime.now(santiago_tz).date()
        start_date = end_date - timedelta(days=30)

        print(f"📅 Fetching data from {start_date} to {end_date}")

        # Fetch ML predictions
        print("\n🤖 Fetching ML predictions...")
        ml_predictions = supabase.get_ml_predictions(
            start_date=str(start_date),
            end_date=str(end_date),
            limit=10000
        )
        print(f"✅ Got {len(ml_predictions)} ML predictions")

        # Try to process them
        print("\n📊 Processing ML predictions...")
        ml_by_forecast = {}
        for i, pred in enumerate(ml_predictions[:3]):  # Just first 3
            print(f"\n   Record {i+1}:")
            print(f"   Keys: {list(pred.keys())}")

            # Try to calculate forecast_date/hour
            try:
                forecast_dt_utc = datetime.fromisoformat(pred['forecast_datetime'].replace('Z', '+00:00'))
                forecast_dt_santiago = forecast_dt_utc.astimezone(santiago_tz)
                forecast_date = forecast_dt_santiago.date()
                forecast_hour = forecast_dt_santiago.hour
                print(f"   ✅ forecast_datetime: {pred['forecast_datetime']}")
                print(f"   ✅ Santiago time: {forecast_dt_santiago}")
                print(f"   ✅ forecast_date: {forecast_date}")
                print(f"   ✅ forecast_hour: {forecast_hour}")
            except Exception as e:
                print(f"   ❌ Error: {e}")

        # Fetch CMG Programado
        print("\n\n📅 Fetching CMG Programado...")
        cmg_programado = supabase.get_cmg_programado(
            start_date=str(start_date),
            end_date=str(end_date),
            limit=10000
        )
        print(f"✅ Got {len(cmg_programado)} CMG Programado records")

        if cmg_programado:
            print("\n📊 Processing CMG Programado...")
            for i, p in enumerate(cmg_programado[:3]):  # Just first 3
                print(f"\n   Record {i+1}:")
                print(f"   Keys: {list(p.keys())}")

                try:
                    forecast_key = f"{p['forecast_date']} {p['forecast_hour']:02d}:00:00"
                    print(f"   ✅ forecast_key: {forecast_key}")
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    print(f"   Has forecast_date: {'forecast_date' in p}")
                    print(f"   Has forecast_hour: {'forecast_hour' in p}")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
