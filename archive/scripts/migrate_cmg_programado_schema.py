#!/usr/bin/env python3
"""
Migrate CMG Programado Table to New Schema
===========================================

Changes:
- datetime → target_datetime
- fetched_at → forecast_datetime
- cmg_programmed → cmg_usd
- Add: forecast_date, forecast_hour, target_date, target_hour columns

Steps:
1. Backup existing data
2. Add new columns
3. Transform data to new format
4. Drop old columns
5. Backfill from Gist (29 days of historical data)
"""

import sys
from pathlib import Path
import json
from datetime import datetime
import pytz

# Add lib path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.utils.supabase_client import SupabaseClient
import requests
import os

def backup_existing_data(supabase):
    """Step 1: Backup existing CMG Programado records"""
    print("\n" + "="*80)
    print("STEP 1: BACKUP EXISTING DATA")
    print("="*80)

    base_url = "https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1"
    api_key = os.environ['SUPABASE_SERVICE_KEY']

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Get ALL existing records (old schema)
    response = requests.get(
        f"{base_url}/cmg_programado",
        params={"limit": 100000},
        headers=headers
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch records: {response.status_code}")
        return None

    records = response.json()
    print(f"✅ Fetched {len(records)} existing records")

    # Save backup
    backup_path = Path('data/backups/cmg_programado_pre_migration.json')
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    with open(backup_path, 'w') as f:
        json.dump({
            'backup_date': datetime.now(pytz.UTC).isoformat(),
            'record_count': len(records),
            'records': records
        }, f, indent=2)

    print(f"✅ Backup saved to {backup_path}")
    return records

def run_sql_migration():
    """Step 2: Run SQL migration to rename/add columns"""
    print("\n" + "="*80)
    print("STEP 2: ALTER TABLE SCHEMA")
    print("="*80)

    migration_sql = """
    -- Add new columns (if they don't exist)
    DO $$
    BEGIN
        -- Add forecast columns
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='cmg_programado' AND column_name='forecast_datetime') THEN
            ALTER TABLE cmg_programado ADD COLUMN forecast_datetime TIMESTAMPTZ;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='cmg_programado' AND column_name='forecast_date') THEN
            ALTER TABLE cmg_programado ADD COLUMN forecast_date DATE;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='cmg_programado' AND column_name='forecast_hour') THEN
            ALTER TABLE cmg_programado ADD COLUMN forecast_hour INTEGER;
        END IF;

        -- Add target columns
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='cmg_programado' AND column_name='target_datetime') THEN
            ALTER TABLE cmg_programado ADD COLUMN target_datetime TIMESTAMPTZ;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='cmg_programado' AND column_name='target_date') THEN
            ALTER TABLE cmg_programado ADD COLUMN target_date DATE;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='cmg_programado' AND column_name='target_hour') THEN
            ALTER TABLE cmg_programado ADD COLUMN target_hour INTEGER;
        END IF;

        -- Add cmg_usd column
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name='cmg_programado' AND column_name='cmg_usd') THEN
            ALTER TABLE cmg_programado ADD COLUMN cmg_usd DECIMAL(10, 2);
        END IF;
    END $$;

    -- Populate new columns from old columns
    UPDATE cmg_programado
    SET
        target_datetime = datetime,
        target_date = date,
        target_hour = hour,
        forecast_datetime = fetched_at,
        forecast_date = DATE(fetched_at),
        forecast_hour = EXTRACT(HOUR FROM fetched_at)::INTEGER,
        cmg_usd = cmg_programmed
    WHERE target_datetime IS NULL;

    -- Drop old constraints first
    DO $$
    BEGIN
        ALTER TABLE cmg_programado DROP CONSTRAINT IF EXISTS unique_cmg_programado_datetime_node;
        ALTER TABLE cmg_programado DROP CONSTRAINT IF EXISTS unique_cmg_prog_forecast_target_node;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END $$;

    -- Add new unique constraint
    ALTER TABLE cmg_programado
    ADD CONSTRAINT unique_cmg_prog_forecast_target_node
    UNIQUE(forecast_datetime, target_datetime, node);

    -- Create indexes
    CREATE INDEX IF NOT EXISTS idx_cmg_prog_forecast_dt ON cmg_programado(forecast_datetime DESC);
    CREATE INDEX IF NOT EXISTS idx_cmg_prog_target_dt ON cmg_programado(target_datetime DESC);
    CREATE INDEX IF NOT EXISTS idx_cmg_prog_target_date ON cmg_programado(target_date);
    """

    print("SQL Migration to run:")
    print(migration_sql)
    print("\n⚠️  You need to run this SQL in Supabase SQL Editor")
    print("   Go to: https://btyfbrclgmphcjgrvcgd.supabase.co/project/_/sql")

    input("\nPress Enter after you've run the SQL migration in Supabase...")

    return True

def verify_migration():
    """Step 3: Verify the migration worked"""
    print("\n" + "="*80)
    print("STEP 3: VERIFY MIGRATION")
    print("="*80)

    base_url = "https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1"
    api_key = os.environ['SUPABASE_SERVICE_KEY']

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Get a sample record
    response = requests.get(
        f"{base_url}/cmg_programado",
        params={"limit": 1, "order": "created_at.desc"},
        headers=headers
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch: {response.status_code}")
        return False

    records = response.json()
    if not records:
        print("⚠️  No records found")
        return False

    sample = records[0]
    print(f"✅ Sample record after migration:")
    print(f"   Columns: {list(sample.keys())}")

    # Check required columns exist
    required = ['forecast_datetime', 'target_datetime', 'cmg_usd',
                'forecast_date', 'target_date', 'forecast_hour', 'target_hour']

    missing = [col for col in required if col not in sample or sample[col] is None]

    if missing:
        print(f"❌ Missing or NULL columns: {missing}")
        return False

    print(f"✅ All required columns present and populated")
    print(f"\n   Sample values:")
    for col in required:
        print(f"   {col}: {sample[col]}")

    return True

def backfill_from_gist():
    """Step 4: Backfill historical data from Gist"""
    print("\n" + "="*80)
    print("STEP 4: BACKFILL FROM GIST")
    print("="*80)

    gist_path = Path('data/cache/cmg_programado_historical.json')
    if not gist_path.exists():
        print(f"⚠️  Gist file not found: {gist_path}")
        return False

    with open(gist_path) as f:
        gist_data = json.load(f)

    print(f"✅ Loaded Gist data")
    print(f"   Date Range: {gist_data['metadata']['oldest_date']} to {gist_data['metadata']['newest_date']}")
    print(f"   Total Days: {gist_data['metadata']['total_days']}")

    # Transform Gist data to Supabase format
    santiago_tz = pytz.timezone('America/Santiago')
    supabase_records = []

    daily_data = gist_data.get('daily_data', {})

    for date, date_data in daily_data.items():
        forecasts_by_hour = date_data.get('cmg_programado_forecasts', {})

        for hour, forecast_snapshot in forecasts_by_hour.items():
            forecast_time_str = forecast_snapshot.get('forecast_time')

            # Parse forecast datetime
            if 'T' in forecast_time_str:
                forecast_dt = datetime.fromisoformat(forecast_time_str.replace('Z', '+00:00'))
            else:
                forecast_dt = datetime.strptime(forecast_time_str, '%Y-%m-%dT%H:%M:%S')
                forecast_dt = santiago_tz.localize(forecast_dt)

            # Get all node forecasts
            forecasts_data = forecast_snapshot.get('forecasts', {})
            for node, node_forecasts in forecasts_data.items():
                for forecast in node_forecasts:
                    target_dt_str = forecast['datetime']

                    # Parse target datetime
                    if 'T' in target_dt_str:
                        target_dt = datetime.fromisoformat(target_dt_str.replace('Z', '+00:00'))
                    else:
                        target_dt = datetime.strptime(target_dt_str, '%Y-%m-%d %H:%M:%S')
                        target_dt = santiago_tz.localize(target_dt)

                    supabase_records.append({
                        'forecast_datetime': forecast_dt.isoformat(),
                        'forecast_date': forecast_dt.strftime('%Y-%m-%d'),
                        'forecast_hour': forecast_dt.hour,
                        'target_datetime': target_dt.isoformat(),
                        'target_date': target_dt.strftime('%Y-%m-%d'),
                        'target_hour': target_dt.hour,
                        'node': node,
                        'cmg_usd': float(forecast['cmg'])
                    })

    print(f"\n✅ Transformed {len(supabase_records)} records from Gist")

    # Insert to Supabase
    supabase = SupabaseClient()

    print(f"\n📤 Inserting records to Supabase...")
    batch_size = 100
    success_count = 0

    for i in range(0, len(supabase_records), batch_size):
        batch = supabase_records[i:i+batch_size]
        try:
            if supabase.insert_cmg_programado_batch(batch):
                success_count += len(batch)
        except Exception as e:
            print(f"⚠️  Batch {i//batch_size + 1} failed: {e}")

    print(f"\n✅ Backfill complete: {success_count} / {len(supabase_records)} records inserted")
    return True

def cleanup_old_columns():
    """Step 5: Optionally drop old columns"""
    print("\n" + "="*80)
    print("STEP 5: CLEANUP OLD COLUMNS (OPTIONAL)")
    print("="*80)

    cleanup_sql = """
    -- Drop old columns (only after verifying migration worked!)
    ALTER TABLE cmg_programado DROP COLUMN IF EXISTS datetime;
    ALTER TABLE cmg_programado DROP COLUMN IF EXISTS date;
    ALTER TABLE cmg_programado DROP COLUMN IF EXISTS hour;
    ALTER TABLE cmg_programado DROP COLUMN IF EXISTS cmg_programmed;
    ALTER TABLE cmg_programado DROP COLUMN IF EXISTS fetched_at;
    """

    print("Cleanup SQL (run this ONLY after verifying data):")
    print(cleanup_sql)
    print("\n⚠️  DO NOT run this yet - verify data first!")

def main():
    print("="*80)
    print("CMG PROGRAMADO SCHEMA MIGRATION")
    print("="*80)
    print("\nThis script will:")
    print("1. Backup existing 696 records")
    print("2. Add new columns to match schema.sql")
    print("3. Transform existing data to new format")
    print("4. Backfill 29 days of historical data from Gist")
    print("5. (Optional) Drop old columns")

    response = input("\nProceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Migration cancelled")
        return

    # Step 1: Backup
    supabase = SupabaseClient()
    backup_records = backup_existing_data(supabase)
    if not backup_records:
        print("❌ Backup failed - aborting")
        return

    # Step 2: Run SQL migration
    if not run_sql_migration():
        print("❌ SQL migration failed - aborting")
        return

    # Step 3: Verify
    if not verify_migration():
        print("❌ Verification failed - check the database!")
        return

    # Step 4: Backfill
    if not backfill_from_gist():
        print("⚠️  Backfill had issues - check logs")

    # Step 5: Cleanup instructions
    cleanup_old_columns()

    print("\n" + "="*80)
    print("MIGRATION COMPLETE!")
    print("="*80)
    print("\nNext steps:")
    print("1. Test the API endpoints")
    print("2. Verify forecast_comparison.html works")
    print("3. Once verified, run the cleanup SQL to drop old columns")

if __name__ == "__main__":
    main()
