#!/usr/bin/env python3
"""
Backfill CMG Programado from Gist to Supabase
==============================================

Loads 29 days of historical CMG Programado data from Gist cache
and inserts into Supabase using the NEW schema format.

Run this AFTER the SQL migration has been completed.
"""

import sys
from pathlib import Path
import json
from datetime import datetime
import pytz

# Add lib path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.utils.supabase_client import SupabaseClient
import os

def load_gist_data():
    """Load CMG Programado data from Gist cache"""
    print("\n" + "="*80)
    print("LOADING GIST DATA")
    print("="*80)

    gist_path = Path('data/cache/cmg_programado_historical.json')
    if not gist_path.exists():
        print(f"❌ Gist file not found: {gist_path}")
        print(f"   Run the hourly workflow to download latest Gist data")
        return None

    with open(gist_path) as f:
        gist_data = json.load(f)

    metadata = gist_data.get('metadata', {})
    print(f"✅ Loaded Gist data")
    print(f"   Date Range: {metadata.get('oldest_date')} to {metadata.get('newest_date')}")
    print(f"   Total Days: {metadata.get('total_days')}")
    print(f"   Last Updated: {metadata.get('last_update')}")

    return gist_data

def transform_gist_to_supabase(gist_data):
    """Transform Gist format to Supabase new schema format"""
    print("\n" + "="*80)
    print("TRANSFORMING DATA")
    print("="*80)

    santiago_tz = pytz.timezone('America/Santiago')
    supabase_records = []

    daily_data = gist_data.get('daily_data', {})
    print(f"Processing {len(daily_data)} days of data...")

    for date, date_data in daily_data.items():
        forecasts_by_hour = date_data.get('cmg_programado_forecasts', {})

        for hour, forecast_snapshot in forecasts_by_hour.items():
            forecast_time_str = forecast_snapshot.get('forecast_time')

            if not forecast_time_str:
                continue

            # Parse forecast datetime
            try:
                if 'T' in forecast_time_str:
                    forecast_dt = datetime.fromisoformat(forecast_time_str.replace('Z', '+00:00'))
                else:
                    forecast_dt = datetime.strptime(forecast_time_str, '%Y-%m-%d %H:%M:%S')
                    forecast_dt = santiago_tz.localize(forecast_dt)
            except Exception as e:
                print(f"⚠️  Error parsing forecast_time '{forecast_time_str}': {e}")
                continue

            # Get all node forecasts
            forecasts_data = forecast_snapshot.get('forecasts', {})
            for node, node_forecasts in forecasts_data.items():
                if not isinstance(node_forecasts, list):
                    continue

                for forecast in node_forecasts:
                    target_dt_str = forecast.get('datetime')
                    if not target_dt_str:
                        continue

                    # Parse target datetime
                    try:
                        if 'T' in target_dt_str:
                            target_dt = datetime.fromisoformat(target_dt_str.replace('Z', '+00:00'))
                        else:
                            target_dt = datetime.strptime(target_dt_str, '%Y-%m-%d %H:%M:%S')
                            target_dt = santiago_tz.localize(target_dt)
                    except Exception as e:
                        print(f"⚠️  Error parsing target datetime '{target_dt_str}': {e}")
                        continue

                    # Create Supabase record with NEW schema
                    supabase_records.append({
                        'forecast_datetime': forecast_dt.isoformat(),
                        'forecast_date': forecast_dt.strftime('%Y-%m-%d'),
                        'forecast_hour': forecast_dt.hour,
                        'target_datetime': target_dt.isoformat(),
                        'target_date': target_dt.strftime('%Y-%m-%d'),
                        'target_hour': target_dt.hour,
                        'node': node,
                        'cmg_usd': float(forecast.get('cmg', 0))
                    })

    print(f"✅ Transformed {len(supabase_records)} records from Gist")

    # Show sample
    if supabase_records:
        print(f"\nSample record:")
        sample = supabase_records[0]
        for key in ['forecast_datetime', 'target_datetime', 'node', 'cmg_usd']:
            print(f"   {key}: {sample[key]}")

    return supabase_records

def insert_to_supabase(records):
    """Insert records to Supabase in batches"""
    print("\n" + "="*80)
    print("INSERTING TO SUPABASE")
    print("="*80)

    if not records:
        print("❌ No records to insert")
        return False

    # Check environment variables
    if not os.environ.get('SUPABASE_URL') or not os.environ.get('SUPABASE_SERVICE_KEY'):
        print("❌ Missing environment variables!")
        print("   Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        return False

    supabase = SupabaseClient()

    print(f"📤 Inserting {len(records)} records in batches...")
    batch_size = 100
    success_count = 0
    error_count = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        batch_num = i//batch_size + 1
        total_batches = (len(records) + batch_size - 1) // batch_size

        try:
            if supabase.insert_cmg_programado_batch(batch):
                success_count += len(batch)
                print(f"   Batch {batch_num}/{total_batches}: ✅ {len(batch)} records")
            else:
                error_count += len(batch)
                print(f"   Batch {batch_num}/{total_batches}: ❌ Failed")
        except Exception as e:
            error_count += len(batch)
            print(f"   Batch {batch_num}/{total_batches}: ❌ Error: {e}")

    print(f"\n{'='*80}")
    print(f"BACKFILL COMPLETE")
    print(f"{'='*80}")
    print(f"✅ Successfully inserted: {success_count} records")
    if error_count > 0:
        print(f"❌ Failed: {error_count} records")
    print(f"📊 Success rate: {success_count/len(records)*100:.1f}%")

    return success_count > 0

def verify_backfill():
    """Verify the backfill worked"""
    print("\n" + "="*80)
    print("VERIFYING BACKFILL")
    print("="*80)

    supabase = SupabaseClient()

    # Get total count
    all_records = supabase.get_cmg_programado(limit=100000)
    print(f"✅ Total CMG Programado records in Supabase: {len(all_records)}")

    if all_records:
        # Get date range
        forecast_dates = sorted(set(
            r['forecast_datetime'].split('T')[0]
            for r in all_records
        ))

        print(f"   Forecast date range: {forecast_dates[0]} to {forecast_dates[-1]}")
        print(f"   Total unique forecast dates: {len(forecast_dates)}")

        # Count by date
        from collections import defaultdict
        by_date = defaultdict(int)
        for r in all_records:
            date = r['forecast_datetime'].split('T')[0]
            by_date[date] += 1

        print(f"\n   Records per date (first 5):")
        for date in forecast_dates[:5]:
            print(f"      {date}: {by_date[date]} records")

        print(f"\n   Records per date (last 5):")
        for date in forecast_dates[-5:]:
            print(f"      {date}: {by_date[date]} records")

    return True

def main():
    print("="*80)
    print("BACKFILL CMG PROGRAMADO FROM GIST TO SUPABASE")
    print("="*80)
    print("\nThis script will:")
    print("1. Load 29 days of CMG Programado data from Gist cache")
    print("2. Transform to new Supabase schema format")
    print("3. Insert records in batches (handling duplicates)")
    print("4. Verify the backfill completed successfully")
    print("\nNOTE: The SQL migration must be completed first!")

    # Load Gist data
    gist_data = load_gist_data()
    if not gist_data:
        print("\n❌ Failed to load Gist data")
        return 1

    # Transform to Supabase format
    records = transform_gist_to_supabase(gist_data)
    if not records:
        print("\n❌ No records to insert")
        return 1

    # Insert to Supabase
    if not insert_to_supabase(records):
        print("\n❌ Backfill failed")
        return 1

    # Verify
    verify_backfill()

    print("\n" + "="*80)
    print("✅ BACKFILL SUCCESSFUL!")
    print("="*80)
    print("\nNext steps:")
    print("1. Test forecast_comparison.html with Nov 11-16 dates")
    print("2. Verify API endpoints return complete data")
    print("3. Check that hourly workflows continue to populate data")

    return 0

if __name__ == "__main__":
    sys.exit(main())
