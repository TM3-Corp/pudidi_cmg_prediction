#!/usr/bin/env python3
"""
Store CMG Programado forecasts to dedicated Gist
Keeps 7-day rolling window of hourly forecasts
"""

import json
import requests
from datetime import datetime, timedelta
import pytz
import os
from pathlib import Path

# Configuration
GIST_ID = 'd68bb21360b1ac549c32a80195f99b09'  # CMG Programado Gist
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('CMG_GIST_TOKEN')
GIST_FILENAME = 'cmg_programado_historical.json'
ROLLING_WINDOW_DAYS = None  # Keep all data permanently

NODE_MAPPING = {
    'PMontt220': 'NVA_P.MONTT___220',
    'Pidpid110': 'PIDPID________110',
    'Dalcahue110': 'DALCAHUE______110'
}

def load_cmg_programado():
    """Load latest CMG Programado forecast"""
    prog_path = Path('data/cache/cmg_programmed_latest.json')
    if not prog_path.exists():
        print("⚠️ CMG Programado not found")
        return None

    with open(prog_path, 'r') as f:
        return json.load(f)

def organize_programado_forecasts(prog_data):
    """
    Organize CMG Programado forecasts by (date, hour)

    NOTE: CMG Programado is a batch download from Coordinador that provides
    complete forecasts for the next 2-3 days. We store ALL hours without
    filtering, as they are all legitimate forecast data.
    """
    if not prog_data or 'data' not in prog_data:
        return {}

    # Get when the forecast was fetched
    fetch_time = datetime.fromisoformat(prog_data['timestamp'])
    santiago_tz = pytz.timezone('America/Santiago')
    fetch_time = fetch_time.astimezone(santiago_tz)

    # Use the hour when forecast was made
    forecast_date = fetch_time.strftime('%Y-%m-%d')
    forecast_hour = fetch_time.hour

    # Organize by node - NO FILTERING needed for CMG Programado batch downloads
    forecasts_by_node = {}

    for record in prog_data['data']:
        node = record['node']
        mapped_node = NODE_MAPPING.get(node, node)

        if mapped_node not in forecasts_by_node:
            forecasts_by_node[mapped_node] = []

        forecasts_by_node[mapped_node].append({
            'datetime': record['datetime'],
            'cmg': round(record['cmg_programmed'], 2)
        })

    return {
        (forecast_date, forecast_hour): {
            'forecast_time': fetch_time.isoformat(),
            'forecasts': forecasts_by_node
        }
    }

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

            # Check if content is truncated (GitHub API has 1MB limit)
            file_info = gist_data['files'].get(GIST_FILENAME, {})
            is_truncated = file_info.get('truncated', False)

            if is_truncated:
                # Fetch from raw_url for large files
                print("⚠️ Gist file is large, fetching from raw URL...")
                raw_url = file_info.get('raw_url')
                raw_response = requests.get(raw_url)
                if raw_response.status_code == 200:
                    content = raw_response.text
                else:
                    print(f"❌ Failed to fetch raw content: {raw_response.status_code}")
                    return None
            else:
                # Get existing data from API response
                content = file_info.get('content', '{}')

            return json.loads(content)
    except Exception as e:
        print(f"Error fetching Gist: {e}")

    return None

def merge_data(existing_data, prog_forecasts):
    """Merge new CMG Programado forecasts with existing data"""
    santiago_tz = pytz.timezone('America/Santiago')
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

    # Add new forecasts
    for (date, hour), forecast_data in prog_forecasts.items():
        # No cutoff_date check - keep all data permanently
        if date not in existing_data['daily_data']:
            existing_data['daily_data'][date] = {'cmg_programado_forecasts': {}}

        if 'cmg_programado_forecasts' not in existing_data['daily_data'][date]:
            existing_data['daily_data'][date]['cmg_programado_forecasts'] = {}

        existing_data['daily_data'][date]['cmg_programado_forecasts'][str(hour)] = forecast_data

    # No rolling window deletion - keep all historical data

    # Update metadata
    existing_data['metadata'].update({
        'last_update': now.isoformat(),
        'structure_version': '3.0',
        'rolling_window_days': ROLLING_WINDOW_DAYS,  # None = permanent storage
        'total_days': len(existing_data['daily_data'])
    })

    if existing_data['daily_data']:
        existing_data['metadata']['oldest_date'] = min(existing_data['daily_data'].keys())
        existing_data['metadata']['newest_date'] = max(existing_data['daily_data'].keys())

    return existing_data

def update_gist(data):
    """Update Gist with CMG Programado forecasts"""
    if not GITHUB_TOKEN or not GIST_ID:
        print("⚠️ Missing GITHUB_TOKEN or GIST_ID")
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
        print("✅ CMG Programado Gist updated successfully")
        return True
    else:
        print(f"❌ Error updating Gist: {response.status_code}")
        print(response.text)
        return False

def main():
    print("\n" + "="*60)
    print("STORING CMG PROGRAMADO TO GIST")
    print("="*60)

    # Load CMG Programado
    prog_data = load_cmg_programado()
    if not prog_data:
        print("⚠️ No CMG Programado to store")
        return

    prog_forecasts = organize_programado_forecasts(prog_data)
    print(f"✅ Loaded CMG Programado: {len(prog_forecasts)} forecast(s)")

    for (date, hour), data in prog_forecasts.items():
        nodes = list(data['forecasts'].keys())
        hours_count = len(data['forecasts'][nodes[0]]) if nodes else 0
        print(f"   - {date} {hour:02d}:00 ({hours_count}-hour forecast for {len(nodes)} nodes)")

    # Fetch existing data
    print("\n📥 Fetching existing Gist data...")
    existing_data = fetch_existing_gist()

    # Merge
    print("🔄 Merging CMG Programado forecasts...")
    merged_data = merge_data(existing_data, prog_forecasts)

    print(f"📊 Total days: {merged_data['metadata']['total_days']}")
    if merged_data['metadata'].get('oldest_date'):
        print(f"📅 Date range: {merged_data['metadata']['oldest_date']} to {merged_data['metadata']['newest_date']}")

    # Update Gist
    print("\n📤 Updating Gist...")
    success = update_gist(merged_data)

    # Save local copy
    local_path = Path('data/cache/cmg_programado_historical.json')
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, 'w') as f:
        json.dump(merged_data, f, indent=2)
    print(f"💾 Saved local copy to {local_path}")

    print("\n" + "="*60)
    print("CMG PROGRAMADO STORAGE COMPLETE")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
