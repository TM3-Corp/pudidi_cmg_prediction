#!/usr/bin/env python3
"""
Cleanup script to remove t+0 values from CMG Programado historical data
This fixes forecasts that were stored before the timezone bug fix
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

def cleanup_t0_forecasts(data):
    """Remove t+0 values from forecasts"""
    santiago_tz = pytz.timezone('America/Santiago')
    cleaned_count = 0
    removed_count = 0

    if not data or 'daily_data' not in data:
        print("No data to clean")
        return data, 0, 0

    for date, day_data in data['daily_data'].items():
        if 'cmg_programado_forecasts' not in day_data:
            continue

        forecasts = day_data['cmg_programado_forecasts']
        hours_to_remove = []

        for hour_str, forecast_data in forecasts.items():
            if 'forecast_time' not in forecast_data or 'forecasts' not in forecast_data:
                continue

            # Parse forecast time
            forecast_time = datetime.fromisoformat(forecast_data['forecast_time'])
            forecast_hour = forecast_time.hour

            # Calculate t+1 start time
            fetch_hour_floor = forecast_time.replace(minute=0, second=0, microsecond=0)
            fetch_hour_next = fetch_hour_floor + timedelta(hours=1)

            # Check each node's forecasts
            for node, forecasts_list in forecast_data['forecasts'].items():
                if not forecasts_list:
                    continue

                # Get first forecast datetime
                first_forecast_dt_str = forecasts_list[0]['datetime']
                first_forecast_dt = datetime.fromisoformat(first_forecast_dt_str)
                first_forecast_dt = santiago_tz.localize(first_forecast_dt)

                # Check if starts at t+0 (BUG!)
                if first_forecast_dt == fetch_hour_floor:
                    print(f"❌ {date} {hour_str}:00 - Forecast starts at t+0 ({first_forecast_dt_str})")
                    print(f"   Expected t+1: {fetch_hour_next}")
                    print(f"   Removing first forecast...")

                    # Remove t+0 forecast (first item)
                    forecasts_list.pop(0)
                    removed_count += 1
                    cleaned_count += 1

                    if not forecasts_list:
                        print(f"   No forecasts left after cleanup, marking hour for removal")
                        hours_to_remove.append((date, hour_str))

        # Remove empty hours
        for date_key, hour_key in hours_to_remove:
            if date_key == date:
                del forecasts[hour_key]
                print(f"   Removed empty hour {date} {hour_key}:00")

    return data, cleaned_count, removed_count

def update_gist(data):
    """Update Gist with cleaned data"""
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
        print("✅ Gist updated successfully")
        return True
    else:
        print(f"❌ Error updating Gist: {response.status_code}")
        print(response.text)
        return False

def main():
    print("\n" + "="*60)
    print("CLEANUP T+0 FORECASTS FROM CMG PROGRAMADO")
    print("="*60)

    # Fetch existing data
    print("\n📥 Fetching existing Gist data...")
    data = fetch_existing_gist()

    if not data:
        print("❌ Could not fetch Gist data")
        return 1

    print(f"✅ Loaded data with {len(data.get('daily_data', {}))} days")

    # Cleanup
    print("\n🔧 Cleaning up t+0 forecasts...")
    cleaned_data, cleaned_count, removed_count = cleanup_t0_forecasts(data)

    if cleaned_count == 0:
        print("✅ No t+0 forecasts found - data is clean!")
        return 0

    print(f"\n📊 Summary:")
    print(f"   - Forecasts cleaned: {cleaned_count}")
    print(f"   - T+0 values removed: {removed_count}")

    # Update Gist
    print("\n📤 Updating Gist...")
    success = update_gist(cleaned_data)

    # Save local copy
    local_path = Path('data/cache/cmg_programado_historical.json')
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, 'w') as f:
        json.dump(cleaned_data, f, indent=2)
    print(f"💾 Saved local copy to {local_path}")

    print("\n" + "="*60)
    if success:
        print("✅ CLEANUP COMPLETE")
    else:
        print("⚠️ CLEANUP FAILED TO UPDATE GIST")
    print("="*60 + "\n")

    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
