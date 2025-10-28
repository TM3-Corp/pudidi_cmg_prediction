#!/usr/bin/env python3
"""
One-Time Migration Script: Gist → Supabase
===========================================

Migrates existing data from local cache to Supabase database.

This script:
1. Reads data from local cache files
2. Transforms to Supabase schema
3. Batch uploads to Supabase tables

Run once after schema is created.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
import pytz

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from api.utils.supabase_client import SupabaseClient

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
            key = (record['datetime'], record['node'])

            # Skip if we've already seen this datetime+node combination
            if key in seen_keys:
                continue

            seen_keys.add(key)
            supabase_records.append({
                'datetime': record['datetime'],
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
    
    # Insert in batches of 1000
    batch_size = 1000
    total_batches = (len(supabase_records) + batch_size - 1) // batch_size
    
    for i in range(0, len(supabase_records), batch_size):
        batch = supabase_records[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        print(f"📤 Uploading batch {batch_num}/{total_batches} ({len(batch)} records)...")
        success = client.insert_cmg_online_batch(batch)
        
        if not success:
            print(f"❌ Failed to upload batch {batch_num}")
            return False
    
    print(f"✅ Successfully migrated {len(supabase_records)} CMG Online records")
    return True


def migrate_cmg_programado():
    """Migrate CMG Programado forecast data"""
    print("\n" + "="*60)
    print("MIGRATING CMG PROGRAMADO (FORECAST DATA)")
    print("="*60)
    
    cache_file = Path('data/cache/pmontt_programado.json')
    
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
    seen_keys = set()  # Track (datetime, node) pairs

    for record in records:
        try:
            datetime_str = record['datetime']
            node = 'PMontt220'
            key = (datetime_str, node)

            if key in seen_keys:
                continue

            seen_keys.add(key)
            supabase_records.append({
                'datetime': datetime_str,
                'date': record.get('date', datetime_str.split('T')[0]),
                'hour': record.get('hour', int(datetime_str.split('T')[1].split(':')[0])),
                'node': node,
                'cmg_programmed': float(record.get('cmg_programmed', record.get('value', 0))),
                'fetched_at': datetime.now(pytz.UTC).isoformat()
            })
        except Exception as e:
            print(f"⚠️  Skipping invalid record: {e}")
            continue

    print(f"✅ Transformed {len(supabase_records)} unique records (deduped from {len(records)})")
    
    # Batch insert to Supabase
    client = SupabaseClient()
    
    batch_size = 1000
    total_batches = (len(supabase_records) + batch_size - 1) // batch_size
    
    for i in range(0, len(supabase_records), batch_size):
        batch = supabase_records[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        print(f"📤 Uploading batch {batch_num}/{total_batches} ({len(batch)} records)...")
        success = client.insert_cmg_programado_batch(batch)
        
        if not success:
            print(f"❌ Failed to upload batch {batch_num}")
            return False
    
    print(f"✅ Successfully migrated {len(supabase_records)} CMG Programado records")
    return True


def migrate_ml_predictions():
    """Migrate ML predictions"""
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
    
    predictions = cache_data.get('predictions', [])
    metadata = cache_data.get('metadata', {})
    
    print(f"📊 Found {len(predictions)} predictions in latest forecast")
    
    if not predictions:
        print("⚠️  No predictions to migrate")
        return True
    
    # Get forecast creation time
    forecast_time = metadata.get('forecast_created_at', datetime.now(pytz.UTC).isoformat())
    
    # Transform to Supabase schema and deduplicate
    supabase_records = []
    seen_keys = set()  # Track (forecast_datetime, target_datetime) pairs

    for i, pred in enumerate(predictions):
        try:
            target_dt = pred['datetime']
            key = (forecast_time, target_dt)

            if key in seen_keys:
                continue

            seen_keys.add(key)
            supabase_records.append({
                'forecast_datetime': forecast_time,
                'target_datetime': target_dt,
                'horizon': i + 1,  # 1-24
                'cmg_predicted': float(pred['cmg_predicted']),
                'prob_zero': 0.0,  # Not stored in current format
                'threshold': 0.5,
                'model_version': 'v2.0'
            })
        except Exception as e:
            print(f"⚠️  Skipping invalid prediction: {e}")
            continue

    print(f"✅ Transformed {len(supabase_records)} unique predictions (deduped from {len(predictions)})")
    
    # Insert to Supabase
    client = SupabaseClient()
    success = client.insert_ml_predictions_batch(supabase_records)
    
    if success:
        print(f"✅ Successfully migrated {len(supabase_records)} ML predictions")
        return True
    else:
        print(f"❌ Failed to migrate ML predictions")
        return False


def main():
    """Run full migration"""
    print("\n" + "="*60)
    print("SUPABASE MIGRATION - GIST TO POSTGRES")
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
        print("\n⚠️  Some migrations failed - check logs above")
        return 1


if __name__ == "__main__":
    exit(main())
