#!/usr/bin/env python3
"""
Capture 5PM CMG Programado Snapshot

This script captures ALL available CMG Programado forecast data at 5PM daily.
Unlike the hourly updates (which overwrite), this stores a timestamped snapshot
for proper forecast validation.

Use case:
- Plant decides generation at 5PM for next 24 hours
- This captures what forecasts were available AT THAT TIME
- Later, compare these snapshots vs actual CMG Online to measure accuracy
- Track how forecast accuracy degrades from t+1 to t+24 hours
"""

import json
import requests
from datetime import datetime
from pathlib import Path
import pytz
import os

# Configuration
santiago_tz = pytz.timezone('America/Santiago')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
SNAPSHOT_GIST_ID = os.environ.get('CMG_SNAPSHOT_GIST_ID', '')  # Will be set after Gist creation

def load_current_forecast():
    """Load the current CMG Programado forecast"""
    cache_path = Path('data/cache/cmg_programmed_latest.json')

    if not cache_path.exists():
        print("❌ No CMG Programado forecast found at data/cache/cmg_programmed_latest.json")
        return None

    with open(cache_path, 'r') as f:
        data = json.load(f)

    return data

def fetch_existing_snapshots():
    """Fetch existing snapshots from Gist"""
    if not SNAPSHOT_GIST_ID or not GITHUB_TOKEN:
        return {'snapshots': {}, 'metadata': {}}

    try:
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        response = requests.get(f'https://api.github.com/gists/{SNAPSHOT_GIST_ID}', headers=headers)

        if response.status_code == 200:
            gist_data = response.json()
            if 'cmg_programado_snapshots.json' in gist_data['files']:
                content = gist_data['files']['cmg_programado_snapshots.json']['content']
                return json.loads(content)

        return {'snapshots': {}, 'metadata': {}}
    except Exception as e:
        print(f"⚠️  Error fetching existing snapshots: {e}")
        return {'snapshots': {}, 'metadata': {}}

def create_snapshot(forecast_data, snapshot_time):
    """Create a snapshot from current forecast data"""
    snapshot = {
        'snapshot_time': snapshot_time.isoformat(),
        'captured_at': snapshot_time.strftime('%Y-%m-%d %H:%M %Z'),
        'forecast_hours': {},
        'metadata': {
            'total_hours': len(forecast_data.get('data', [])),
            'dates': forecast_data.get('metadata', {}).get('dates', []),
            'node': forecast_data.get('metadata', {}).get('node', 'PMontt220'),
            'source': forecast_data.get('source', 'CMG Programado Download')
        }
    }

    # Store all forecast hours from the current data
    for record in forecast_data.get('data', []):
        datetime_key = record['datetime']  # e.g., "2025-10-06T18:00:00"
        snapshot['forecast_hours'][datetime_key] = {
            'date': record['date'],
            'hour': record['hour'],
            'node': record['node'],
            'cmg_programmed': record['cmg_programmed']
        }

    return snapshot

def update_gist(snapshots_data):
    """Update or create the snapshots Gist"""
    if not GITHUB_TOKEN:
        # Save locally only if no GitHub token
        local_file = Path('data/cache/cmg_programado_snapshots.json')
        local_file.parent.mkdir(parents=True, exist_ok=True)
        with open(local_file, 'w') as f:
            json.dump(snapshots_data, f, indent=2)
        print(f"💾 Saved snapshot locally (no GitHub token): {local_file}")
        return True

    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }

    gist_content = {
        'files': {
            'cmg_programado_snapshots.json': {
                'content': json.dumps(snapshots_data, indent=2, ensure_ascii=False)
            }
        }
    }

    if SNAPSHOT_GIST_ID:
        # Update existing Gist
        url = f'https://api.github.com/gists/{SNAPSHOT_GIST_ID}'
        gist_content['description'] = f'CMG Programado 5PM Snapshots - Updated {datetime.now(santiago_tz).strftime("%Y-%m-%d %H:%M")}'
        response = requests.patch(url, headers=headers, json=gist_content)

        if response.status_code == 200:
            print(f"✅ Updated snapshot Gist: {SNAPSHOT_GIST_ID}")
            return True
        else:
            print(f"❌ Failed to update Gist: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    else:
        # Create new Gist
        gist_content['description'] = 'CMG Programado 5PM Daily Snapshots for Forecast Validation'
        gist_content['public'] = True
        url = 'https://api.github.com/gists'
        response = requests.post(url, headers=headers, json=gist_content)

        if response.status_code == 201:
            new_gist = response.json()
            print(f"✅ Created new snapshot Gist: {new_gist['id']}")
            print(f"   URL: {new_gist['html_url']}")
            print(f"   ⚠️  Save this Gist ID as CMG_SNAPSHOT_GIST_ID secret!")

            # Save Gist ID locally
            with open('.cmg_snapshot_gist_id', 'w') as f:
                f.write(new_gist['id'])

            return True
        else:
            print(f"❌ Failed to create Gist: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

def main():
    """Main function"""
    now = datetime.now(santiago_tz)

    print("=" * 60)
    print(f"CMG PROGRAMADO 5PM SNAPSHOT CAPTURE")
    print("=" * 60)
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()

    # Load current forecast
    print("📊 Loading current CMG Programado forecast...")
    forecast_data = load_current_forecast()

    if not forecast_data:
        return 1

    total_hours = len(forecast_data.get('data', []))
    dates = forecast_data.get('metadata', {}).get('dates', [])
    print(f"   Found forecast: {total_hours} hours")
    print(f"   Dates: {dates}")
    print()

    # Create snapshot
    print("📸 Creating snapshot...")
    snapshot_time = now
    snapshot_key = snapshot_time.strftime('%Y-%m-%dT%H:%M:%S')

    snapshot = create_snapshot(forecast_data, snapshot_time)
    print(f"   Snapshot captured: {snapshot['captured_at']}")
    print(f"   Forecast hours: {len(snapshot['forecast_hours'])}")
    print()

    # Fetch existing snapshots
    print("📥 Fetching existing snapshots...")
    snapshots_data = fetch_existing_snapshots()
    existing_count = len(snapshots_data.get('snapshots', {}))
    print(f"   Found {existing_count} existing snapshots")
    print()

    # Add new snapshot
    if 'snapshots' not in snapshots_data:
        snapshots_data['snapshots'] = {}

    snapshots_data['snapshots'][snapshot_key] = snapshot

    # Update metadata
    snapshots_data['metadata'] = {
        'last_snapshot': snapshot_time.isoformat(),
        'last_snapshot_readable': snapshot['captured_at'],
        'total_snapshots': len(snapshots_data['snapshots']),
        'snapshots_list': sorted(snapshots_data['snapshots'].keys()),
        'purpose': '5PM daily snapshots for forecast validation (t+1 to t+24)'
    }

    # Update Gist
    print("📤 Uploading to Gist...")
    success = update_gist(snapshots_data)

    if success:
        print()
        print("=" * 60)
        print("✅ SNAPSHOT CAPTURED SUCCESSFULLY")
        print("=" * 60)
        print(f"Snapshot time: {snapshot['captured_at']}")
        print(f"Total snapshots: {snapshots_data['metadata']['total_snapshots']}")
        print(f"Forecast hours in snapshot: {len(snapshot['forecast_hours'])}")
        print()

        # Show what was captured
        if snapshot['forecast_hours']:
            hours_list = sorted(snapshot['forecast_hours'].keys())
            print(f"Forecast range:")
            print(f"  From: {hours_list[0]}")
            print(f"  To:   {hours_list[-1]}")

            # Calculate horizons
            first_hour = datetime.fromisoformat(hours_list[0])
            if first_hour.tzinfo is None:
                first_hour = santiago_tz.localize(first_hour)

            last_hour = datetime.fromisoformat(hours_list[-1])
            if last_hour.tzinfo is None:
                last_hour = santiago_tz.localize(last_hour)

            t1_delta = (first_hour - snapshot_time).total_seconds() / 3600
            t24_delta = (last_hour - snapshot_time).total_seconds() / 3600

            print(f"  Horizons: t+{t1_delta:.0f}h to t+{t24_delta:.0f}h")

        print()
        return 0
    else:
        print()
        print("=" * 60)
        print("⚠️  SNAPSHOT CAPTURED BUT UPLOAD FAILED")
        print("=" * 60)
        print("Snapshot saved locally, but couldn't update Gist")
        return 1

if __name__ == "__main__":
    exit(main())
