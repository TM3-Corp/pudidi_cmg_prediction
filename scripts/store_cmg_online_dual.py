#!/usr/bin/env python3
"""
Store CMG Online to BOTH Gist and Supabase (Dual Write)
=======================================================

This script replaces store_historical.py during the migration period.

Writes to:
1. GitHub Gist (existing, for backward compatibility)
2. Supabase Database (new, production destination)

If Supabase write fails, the script still succeeds on Gist write.
Once Supabase is validated, we'll switch to Supabase-only writes.
"""

import json
import requests
from datetime import datetime, timedelta
import pytz
import os
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.utils.supabase_client import SupabaseClient

# GitHub Gist configuration
GIST_ID = '8d7864eb26acf6e780d3c0f7fed69365'
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GIST_FILENAME = 'cmg_online_historical.json'
ROLLING_WINDOW_DAYS = None  # Keep all data permanently

# Timezone
santiago_tz = pytz.timezone('America/Santiago')


def load_current_cache():
    """Load the current aggregated CMG historical cache"""
    cache_path = Path('data/cache/cmg_historical_latest.json')

    if not cache_path.exists():
        print("⚠️  Cache file not found")
        return None

    with open(cache_path, 'r') as f:
        data = json.load(f)

    return data.get('data', [])


def organize_by_date_for_gist(records):
    """Organize records by date and hour for Gist storage (existing format)"""
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

        # Store the actual values
        organized[date]['cmg_online'][node]['cmg_usd'][hour] = round(record.get('cmg_usd', 0), 2)
        organized[date]['cmg_online'][node]['cmg_real'][hour] = round(record.get('cmg_real', 0), 0)

    return organized


def fetch_existing_gist():
    """Fetch existing historical data from Gist"""
    if not GIST_ID:
        return None

    try:
        url = f'https://api.github.com/gists/{GIST_ID}'
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            gist_data = response.json()

            # Check for truncation
            file_info = gist_data['files'].get(GIST_FILENAME, {})
            is_truncated = file_info.get('truncated', False)

            if is_truncated:
                print("⚠️  Gist file is large, fetching from raw URL...")
                raw_url = file_info.get('raw_url')
                raw_response = requests.get(raw_url)
                if raw_response.status_code == 200:
                    content = raw_response.text
                else:
                    print(f"❌ Failed to fetch raw content: {raw_response.status_code}")
                    return None
            else:
                content = file_info.get('content', '{}')

            return json.loads(content)
    except Exception as e:
        print(f"❌ Error fetching existing Gist: {e}")

    return None


def merge_data_for_gist(existing_data, new_organized):
    """Merge new CMG Online data with existing Gist data"""
    now = datetime.now(santiago_tz)

    if existing_data is None or not isinstance(existing_data, dict):
        existing_data = {
            'metadata': {},
            'daily_data': {}
        }

    # Ensure daily_data exists
    if 'daily_data' not in existing_data:
        existing_data['daily_data'] = {}
    if 'metadata' not in existing_data:
        existing_data['metadata'] = {}

    # Merge new data
    for date, day_data in new_organized.items():
        if date not in existing_data['daily_data']:
            existing_data['daily_data'][date] = {}

        existing_data['daily_data'][date].update(day_data)

    # Update metadata
    existing_data['metadata'].update({
        'last_update': now.isoformat(),
        'structure_version': '3.0',
        'rolling_window_days': ROLLING_WINDOW_DAYS,
        'total_days': len(existing_data['daily_data'])
    })

    if existing_data['daily_data']:
        existing_data['metadata']['oldest_date'] = min(existing_data['daily_data'].keys())
        existing_data['metadata']['newest_date'] = max(existing_data['daily_data'].keys())

    return existing_data


def update_gist(data):
    """Update GitHub Gist with CMG Online data"""
    if not GITHUB_TOKEN or not GIST_ID:
        print("⚠️  Missing GITHUB_TOKEN or GIST_ID")
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
        print("✅ CMG Online Gist updated successfully")
        return True
    else:
        print(f"❌ Error updating Gist: {response.status_code}")
        print(response.text)
        return False


def write_to_supabase(records):
    """Write CMG Online data to Supabase (NEW)"""
    try:
        supabase = SupabaseClient()
    except Exception as e:
        print(f"⚠️  Supabase client not available: {e}")
        print("   Skipping Supabase write")
        return False

    try:
        # Transform records to Supabase format
        rows_to_insert = []

        for record in records:
            # Parse datetime from record
            datetime_str = record.get('datetime')
            if not datetime_str:
                continue

            # Localize to Santiago timezone
            dt = datetime.fromisoformat(datetime_str)
            if dt.tzinfo is None:
                dt = santiago_tz.localize(dt)

            row = {
                'datetime': dt.isoformat(),
                'date': record['date'],
                'hour': record['hour'],
                'node': record['node'],
                'cmg_usd': round(record.get('cmg_usd', 0), 2),
                'source': 'SIP_API_v4'
            }

            rows_to_insert.append(row)

        if not rows_to_insert:
            print("⚠️  No rows to insert to Supabase")
            return False

        # Use SupabaseClient's insert method (handles upsert internally)
        success = supabase.insert_cmg_online_batch(rows_to_insert)

        if success:
            print(f"✅ Supabase write successful: {len(rows_to_insert)} rows")
            return True
        else:
            print("❌ Supabase write failed")
            return False

    except Exception as e:
        print(f"❌ Error writing to Supabase: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*60)
    print("STORING CMG ONLINE (DUAL WRITE: GIST + SUPABASE)")
    print("="*60)

    # Load cache
    records = load_current_cache()
    if not records:
        print("⚠️  No CMG Online data to store")
        return 1

    print(f"✅ Loaded {len(records)} CMG Online records from cache")

    # Show date range
    dates = sorted(set(r['date'] for r in records))
    if dates:
        print(f"   Date range: {dates[0]} to {dates[-1]}")

    # === WRITE TO GIST (existing behavior) ===
    print("\n📤 Writing to GitHub Gist...")
    organized_for_gist = organize_by_date_for_gist(records)
    existing_gist_data = fetch_existing_gist()
    merged_gist_data = merge_data_for_gist(existing_gist_data, organized_for_gist)

    gist_success = update_gist(merged_gist_data)

    # Save local copy
    local_path = Path('data/cache/cmg_online_historical.json')
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, 'w') as f:
        json.dump(merged_gist_data, f, indent=2)
    print(f"💾 Saved local Gist copy to {local_path}")

    # === WRITE TO SUPABASE (new behavior) ===
    print("\n📤 Writing to Supabase...")
    # Filter to last 7 days only to avoid duplicate key errors on old data
    now = datetime.now(santiago_tz)
    seven_days_ago = (now - timedelta(days=7)).date()
    recent_records = [r for r in records if r['date'] >= str(seven_days_ago)]

    print(f"   Filtering to last 7 days: {len(recent_records)}/{len(records)} records")
    if recent_records:
        print(f"   Date range: {min(r['date'] for r in recent_records)} to {max(r['date'] for r in recent_records)}")

    supabase_success = write_to_supabase(recent_records)

    # Summary
    print("\n" + "="*60)
    print("DUAL WRITE SUMMARY")
    print("="*60)
    print(f"Gist write:      {'✅ Success' if gist_success else '❌ Failed'}")
    print(f"Supabase write:  {'✅ Success' if supabase_success else '⚠️  Skipped/Failed'}")
    print("="*60 + "\n")

    # Succeed if at least Gist write worked (fail gracefully on Supabase)
    if gist_success:
        print("✅ CMG Online storage complete (Gist write succeeded)")
        return 0
    else:
        print("❌ CMG Online storage failed (Gist write failed)")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
