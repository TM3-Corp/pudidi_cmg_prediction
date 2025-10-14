#!/usr/bin/env python3
"""
Migrate historical CMG Online data (Sep 2-12) from local cache to Gist
Phase 1 of Historical Data Migration
"""

import json
import requests
from datetime import datetime, timedelta
import pytz
import os
from pathlib import Path
from collections import defaultdict

# Configuration
GIST_ID = '8d7864eb26acf6e780d3c0f7fed69365'  # CMG Online Gist
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('CMG_GIST_TOKEN')
GIST_FILENAME = 'cmg_online_historical.json'

# Target dates for backfill (Sep 2-12, 2025)
BACKFILL_START = '2025-09-02'
BACKFILL_END = '2025-09-12'

NODES = ['NVA_P.MONTT___220', 'PIDPID________110', 'DALCAHUE______110']

def load_local_cache():
    """Load CMG historical cache from local file"""
    cache_path = Path('data/cache/cmg_historical_latest.json')

    if not cache_path.exists():
        print("❌ Local cache not found!")
        return None

    with open(cache_path, 'r') as f:
        data = json.load(f)

    return data.get('data', [])

def extract_backfill_data(records, start_date, end_date):
    """Extract records for backfill date range"""
    backfill_records = []

    for record in records:
        if start_date <= record['date'] <= end_date:
            backfill_records.append(record)

    print(f"📊 Found {len(backfill_records)} records for {start_date} to {end_date}")

    # Group by date
    by_date = defaultdict(list)
    for rec in backfill_records:
        by_date[rec['date']].append(rec)

    for date in sorted(by_date.keys()):
        records_count = len(by_date[date])
        hours_covered = len(set(r['hour'] for r in by_date[date]))
        print(f"   {date}: {records_count} records, {hours_covered} hours")

    return backfill_records

def transform_to_gist_format(records):
    """Transform cache records to Gist daily_data format"""
    organized = {}

    for record in records:
        date = record['date']
        hour = record['hour']
        node = record['node']

        if date not in organized:
            organized[date] = {
                'hours': list(range(24)),
                'cmg_online': {}
            }

        if node not in organized[date]['cmg_online']:
            organized[date]['cmg_online'][node] = {
                'cmg_usd': [None] * 24,
                'cmg_real': [None] * 24
            }

        # Store values
        organized[date]['cmg_online'][node]['cmg_usd'][hour] = round(record.get('cmg_usd', 0), 2)
        organized[date]['cmg_online'][node]['cmg_real'][hour] = round(record.get('cmg_real', 0), 0)

    return organized

def fetch_existing_gist():
    """Fetch existing data from Gist"""
    if not GIST_ID or not GITHUB_TOKEN:
        print("⚠️ Missing GIST_ID or GITHUB_TOKEN")
        return None

    try:
        url = f'https://api.github.com/gists/{GIST_ID}'
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            gist_data = response.json()
            if GIST_FILENAME in gist_data['files']:
                content = gist_data['files'][GIST_FILENAME]['content']
                return json.loads(content)
    except Exception as e:
        print(f"Error fetching Gist: {e}")

    return None

def merge_data(existing_data, backfill_data):
    """Merge backfill data with existing Gist data"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)

    if existing_data is None:
        existing_data = {
            'metadata': {},
            'daily_data': {}
        }

    if 'daily_data' not in existing_data:
        existing_data['daily_data'] = {}

    # Merge backfill data (DON'T overwrite existing dates)
    merged_count = 0
    skipped_count = 0

    for date, day_data in backfill_data.items():
        if date in existing_data['daily_data']:
            # Date already exists - don't overwrite
            print(f"   ⏭️  {date}: Already exists, skipping")
            skipped_count += 1
        else:
            # New date - add it
            existing_data['daily_data'][date] = day_data
            print(f"   ✅ {date}: Added to Gist")
            merged_count += 1

    # Update metadata
    if existing_data['daily_data']:
        dates = sorted(existing_data['daily_data'].keys())
        existing_data['metadata'] = {
            'last_update': now.isoformat(),
            'structure_version': '3.0',
            'total_days': len(existing_data['daily_data']),
            'oldest_date': dates[0],
            'newest_date': dates[-1],
            'nodes': NODES,
            'migration_note': 'Backfilled Sep 2-12 from local cache on ' + now.strftime('%Y-%m-%d')
        }

    print(f"\n📊 Merge summary:")
    print(f"   Added: {merged_count} days")
    print(f"   Skipped (already exist): {skipped_count} days")

    return existing_data, merged_count

def validate_data(data, start_date, end_date):
    """Validate merged data integrity"""
    print(f"\n🔍 Validating data...")

    if 'daily_data' not in data:
        print("❌ No daily_data found!")
        return False

    # Check date range
    dates = sorted(data['daily_data'].keys())
    print(f"✅ Date range: {dates[0]} to {dates[-1]}")
    print(f"✅ Total days: {len(dates)}")

    # Check backfill dates
    backfill_dates = [d for d in dates if start_date <= d <= end_date]
    print(f"✅ Backfilled dates: {len(backfill_dates)} ({start_date} to {end_date})")

    # Check hour completeness for backfill dates
    incomplete_dates = []
    for date in backfill_dates[:5]:  # Check first 5
        day_data = data['daily_data'][date]
        if 'cmg_online' in day_data:
            for node in NODES:
                if node in day_data['cmg_online']:
                    cmg_usd = day_data['cmg_online'][node].get('cmg_usd', [])
                    non_null = sum(1 for v in cmg_usd if v is not None and v > 0)
                    if non_null < 20:  # Less than 20 hours
                        incomplete_dates.append(f"{date} {node}: {non_null}/24h")

    if incomplete_dates:
        print(f"⚠️  Some dates have incomplete hours:")
        for incomplete in incomplete_dates[:3]:
            print(f"     {incomplete}")
    else:
        print(f"✅ Backfill dates have good hour coverage")

    return True

def update_gist(data):
    """Update Gist with merged data"""
    if not GITHUB_TOKEN or not GIST_ID:
        print("⚠️ Missing GITHUB_TOKEN or GIST_ID")
        print("   Saving to local file only")

        # Save locally for testing
        local_file = Path('data/backups/cmg_online_merged.json')
        local_file.parent.mkdir(parents=True, exist_ok=True)
        with open(local_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"💾 Saved to {local_file}")
        return False

    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }

    gist_content = {
        'files': {
            GIST_FILENAME: {
                'content': json.dumps(data, indent=2)
            }
        }
    }

    url = f'https://api.github.com/gists/{GIST_ID}'
    response = requests.patch(url, headers=headers, json=gist_content)

    if response.status_code == 200:
        print("✅ CMG Online Gist updated successfully!")
        return True
    else:
        print(f"❌ Error updating Gist: {response.status_code}")
        print(response.text)
        return False

def main():
    print("="*60)
    print("MIGRATE CMG ONLINE BACKFILL (SEP 2-12)")
    print("="*60)
    print()

    # Load local cache
    print("📂 Loading local cache...")
    records = load_local_cache()
    if not records:
        return 1

    print(f"✅ Loaded {len(records)} total records")
    print()

    # Extract backfill date range
    print(f"🔍 Extracting data for {BACKFILL_START} to {BACKFILL_END}...")
    backfill_records = extract_backfill_data(records, BACKFILL_START, BACKFILL_END)

    if not backfill_records:
        print("❌ No records found in backfill range!")
        return 1

    print()

    # Transform to Gist format
    print("🔄 Transforming to Gist format...")
    backfill_data = transform_to_gist_format(backfill_records)
    print(f"✅ Organized {len(backfill_data)} days")
    print()

    # Fetch existing Gist
    print("📥 Fetching existing Gist data...")
    existing_data = fetch_existing_gist()

    if existing_data:
        existing_dates = len(existing_data.get('daily_data', {}))
        print(f"✅ Existing Gist has {existing_dates} days")
    else:
        print("⚠️ No existing data, will create new structure")

    print()

    # Merge
    print("🔄 Merging data...")
    merged_data, added_count = merge_data(existing_data, backfill_data)
    print()

    # Validate
    if not validate_data(merged_data, BACKFILL_START, BACKFILL_END):
        print("❌ Validation failed!")
        return 1

    print()

    # Update Gist
    print("📤 Updating Gist...")
    if update_gist(merged_data):
        print()
        print("="*60)
        print("✅ MIGRATION COMPLETE!")
        print(f"   Added {added_count} days to CMG Online Gist")
        print(f"   Total days now: {len(merged_data['daily_data'])}")
        print("="*60)
        return 0
    else:
        print()
        print("="*60)
        print("⚠️ MIGRATION SAVED LOCALLY ONLY")
        print("   Set GITHUB_TOKEN to update Gist")
        print("="*60)
        return 1

if __name__ == "__main__":
    exit(main())
