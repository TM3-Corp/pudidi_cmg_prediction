#!/usr/bin/env python3
"""
Fixed Migration Script: Gist Cache → Supabase
==============================================

Migrates existing data from local cache files to Supabase database.
Handles the actual structure of cache files correctly.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
import pytz

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.utils.supabase_client import SupabaseClient

santiago_tz = pytz.timezone('America/Santiago')


def migrate_cmg_online():
    """Migrate CMG Online historical data"""
    print("\n" + "="*60)
    print("MIGRATING CMG ONLINE (HISTORICAL DATA)")
    print("="*60)

    cache_file = Path('data/cache/cmg_historical_latest.json')

    if not cache_file.exists():
        print(f"❌ Cache file not found: {cache_file}")
        return False

    # Load cache
    with open(cache_file, 'r') as f:
        cache_data = json.load(f)

    records = cache_data.get('data', [])
    print(f"📊 Found {len(records)} records in cache")

    if not records:
        print("⚠️  No records to migrate")
        return True

    # Transform to Supabase schema and deduplicate
    supabase_records = []
    seen_keys = set()  # Track (datetime, node) pairs to avoid duplicates

    for record in records:
        try:
            # Parse datetime to ensure proper format
            dt = record['datetime']
            key = (dt, record['node'])

            # Skip if we've already seen this datetime+node combination
            if key in seen_keys:
                continue

            seen_keys.add(key)
            supabase_records.append({
                'datetime': dt,
                'date': record['date'],
                'hour': record['hour'],
                'node': record['node'],
                'cmg_usd': float(record['cmg_usd']),
                'source': 'sip_api'
            })
        except Exception as e:
            print(f"⚠️  Skipping invalid record: {e}")
            continue

    print(f"✅ Transformed {len(supabase_records)} unique records (deduped from {len(records)})")

    # Batch insert to Supabase
    client = SupabaseClient()

    # Insert in batches of 500 (smaller batches to avoid issues)
    batch_size = 500
    total_batches = (len(supabase_records) + batch_size - 1) // batch_size
    successful_batches = 0

    for i in range(0, len(supabase_records), batch_size):
        batch = supabase_records[i:i + batch_size]
        batch_num = i // batch_size + 1

        print(f"📤 Uploading batch {batch_num}/{total_batches} ({len(batch)} records)...")
        success = client.insert_cmg_online_batch(batch)

        if success:
            successful_batches += 1
        else:
            print(f"⚠️  Batch {batch_num} had issues but continuing...")

    print(f"✅ Successfully uploaded {successful_batches}/{total_batches} batches")
    return successful_batches > 0


def migrate_cmg_programado():
    """Migrate CMG Programado historical data from cmg_programado_historical.json"""
    print("\n" + "="*60)
    print("MIGRATING CMG PROGRAMADO (HISTORICAL DATA)")
    print("="*60)

    cache_file = Path('data/cache/cmg_programado_historical.json')

    if not cache_file.exists():
        print(f"❌ Cache file not found: {cache_file}")
        return False

    # Load cache
    with open(cache_file, 'r') as f:
        cache_data = json.load(f)

    historical_data = cache_data.get('historical_data', {})
    print(f"📊 Found historical data for {len(historical_data)} dates")

    if not historical_data:
        print("⚠️  No historical data to migrate")
        return True

    # Transform to Supabase schema
    supabase_records = []
    seen_keys = set()

    for date_str, hours_dict in historical_data.items():
        for hour_str, record in hours_dict.items():
            try:
                timestamp = record['timestamp']
                node = record['node']
                key = (timestamp, node)

                if key in seen_keys:
                    continue

                seen_keys.add(key)

                # Parse date and hour from timestamp
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

                supabase_records.append({
                    'datetime': timestamp,
                    'date': dt.date().isoformat(),
                    'hour': dt.hour,
                    'node': node,
                    'cmg_programmed': float(record['value']),
                    'fetched_at': record.get('update_time', timestamp)
                })
            except Exception as e:
                print(f"⚠️  Skipping invalid record for {date_str} hour {hour_str}: {e}")
                continue

    print(f"✅ Transformed {len(supabase_records)} unique records")

    # Batch insert to Supabase
    client = SupabaseClient()

    batch_size = 500
    total_batches = (len(supabase_records) + batch_size - 1) // batch_size
    successful_batches = 0

    for i in range(0, len(supabase_records), batch_size):
        batch = supabase_records[i:i + batch_size]
        batch_num = i // batch_size + 1

        print(f"📤 Uploading batch {batch_num}/{total_batches} ({len(batch)} records)...")
        success = client.insert_cmg_programado_batch(batch)

        if success:
            successful_batches += 1
        else:
            print(f"⚠️  Batch {batch_num} had issues but continuing...")

    print(f"✅ Successfully uploaded {successful_batches}/{total_batches} batches")
    return successful_batches > 0


def migrate_ml_predictions():
    """Migrate ML predictions from latest.json"""
    print("\n" + "="*60)
    print("MIGRATING ML PREDICTIONS (LATEST FORECAST)")
    print("="*60)

    cache_file = Path('data/ml_predictions/latest.json')

    if not cache_file.exists():
        print(f"❌ Cache file not found: {cache_file}")
        return False

    # Load cache
    with open(cache_file, 'r') as f:
        cache_data = json.load(f)

    forecasts = cache_data.get('forecasts', [])
    metadata = cache_data

    print(f"📊 Found {len(forecasts)} predictions in latest forecast")

    if not forecasts:
        print("⚠️  No predictions to migrate")
        return True

    # Get forecast creation time
    forecast_time = cache_data.get('generated_at', datetime.now(pytz.UTC).isoformat())
    model_version = cache_data.get('model_version', 'gpu_enhanced_v1')

    # Transform to Supabase schema
    supabase_records = []
    seen_keys = set()

    for forecast in forecasts:
        try:
            target_dt = forecast['target_datetime']
            key = (forecast_time, target_dt)

            if key in seen_keys:
                continue

            seen_keys.add(key)

            # Parse target datetime for date/hour extraction
            # Handle format: "2025-11-10 16:00:00" or "2025-11-10 19:27:43 UTC"
            target_dt_clean = target_dt.replace(' UTC', '').strip()
            forecast_time_clean = forecast_time.replace(' UTC', '').strip()

            target_parsed = datetime.strptime(target_dt_clean, '%Y-%m-%d %H:%M:%S')
            forecast_parsed = datetime.strptime(forecast_time_clean, '%Y-%m-%d %H:%M:%S')

            # Make timezone-aware timestamps for Supabase (convert to UTC)
            forecast_dt_aware = pytz.timezone('America/Santiago').localize(forecast_parsed).astimezone(pytz.UTC)
            target_dt_aware = pytz.timezone('America/Santiago').localize(target_parsed).astimezone(pytz.UTC)

            supabase_records.append({
                'forecast_datetime': forecast_dt_aware.isoformat(),
                'target_datetime': target_dt_aware.isoformat(),
                'horizon': forecast['horizon'],
                'cmg_predicted': float(forecast['predicted_cmg']),
                'prob_zero': float(forecast.get('zero_probability', 0.0)),
                'threshold': float(forecast.get('decision_threshold', 0.5)),
                'model_version': model_version
            })
        except Exception as e:
            print(f"⚠️  Skipping invalid prediction: {e}")
            continue

    print(f"✅ Transformed {len(supabase_records)} unique predictions")

    # Insert to Supabase
    client = SupabaseClient()

    batch_size = 500
    total_batches = (len(supabase_records) + batch_size - 1) // batch_size
    successful_batches = 0

    for i in range(0, len(supabase_records), batch_size):
        batch = supabase_records[i:i + batch_size]
        batch_num = i // batch_size + 1

        print(f"📤 Uploading batch {batch_num}/{total_batches} ({len(batch)} records)...")
        success = client.insert_ml_predictions_batch(batch)

        if success:
            successful_batches += 1
        else:
            print(f"⚠️  Batch {batch_num} had issues but continuing...")

    print(f"✅ Successfully uploaded {successful_batches}/{total_batches} batches")
    return successful_batches > 0


def main():
    """Run full migration"""
    print("\n" + "="*60)
    print("SUPABASE MIGRATION - GIST TO POSTGRES (FIXED)")
    print("="*60)
    print(f"Started at: {datetime.now(santiago_tz)}")
    print()

    # Check environment variables
    if not os.environ.get('SUPABASE_URL'):
        print("❌ SUPABASE_URL not set in environment")
        print("   Set it before running migration:")
        print("   export SUPABASE_URL=https://btyfbrclgmphcjgrvcgd.supabase.co")
        return 1

    if not os.environ.get('SUPABASE_SERVICE_KEY'):
        print("❌ SUPABASE_SERVICE_KEY not set in environment")
        print("   Set it before running migration:")
        print("   export SUPABASE_SERVICE_KEY=your_service_role_key")
        return 1

    print("✅ Environment variables configured")

    # Run migrations
    results = {
        'cmg_online': migrate_cmg_online(),
        'cmg_programado': migrate_cmg_programado(),
        'ml_predictions': migrate_ml_predictions()
    }

    # Summary
    print("\n" + "="*60)
    print("MIGRATION SUMMARY")
    print("="*60)

    for table, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{table:20s}: {status}")

    print()
    print(f"Completed at: {datetime.now(santiago_tz)}")

    if all(results.values()):
        print("\n🎉 Migration completed successfully!")
        print("\nNext steps:")
        print("1. Verify data in Supabase dashboard")
        print("2. Update ETL scripts to write to Supabase")
        print("3. Update frontend to read from Supabase")
        return 0
    else:
        print("\n⚠️  Some migrations had issues - check logs above")
        return 1


if __name__ == "__main__":
    exit(main())
