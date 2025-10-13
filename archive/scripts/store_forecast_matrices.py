#!/usr/bin/env python3
"""
Store forecast matrices to GitHub Gist for time-travel analysis
Stores 24×24 ML predictions and 24×72 CMG Programado forecasts
"""

import json
import requests
from datetime import datetime, timedelta
import pytz
import os
from pathlib import Path

# GitHub Gist configuration
GIST_ID = '8d7864eb26acf6e780d3c0f7fed69365'
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('CMG_GIST_TOKEN')
GIST_FILENAME = 'cmg_online_historical.json'

# Data configuration
ROLLING_WINDOW_DAYS = 7  # Keep 7 days of hourly forecasts (7×24 = 168 forecast matrices)
NODE_MAPPING = {
    'PMontt220': 'NVA_P.MONTT___220',
    'Pidpid110': 'PIDPID________110',
    'Dalcahue110': 'DALCAHUE______110'
}

def load_ml_predictions():
    """Load latest ML predictions"""
    ml_path = Path('data/ml_predictions/latest.json')

    if not ml_path.exists():
        print("⚠️ ML predictions not found")
        return None

    with open(ml_path, 'r') as f:
        data = json.load(f)

    return data

def load_cmg_programado():
    """Load latest CMG Programado forecasts"""
    prog_path = Path('data/cache/cmg_programmed_latest.json')

    if not prog_path.exists():
        print("⚠️ CMG Programado not found")
        return None

    with open(prog_path, 'r') as f:
        data = json.load(f)

    return data

def organize_ml_forecasts(ml_data):
    """
    Organize ML predictions by forecast hour
    Returns dict keyed by (date, hour) with list of 24 predictions
    """
    if not ml_data or 'forecasts' not in ml_data:
        return {}

    # Parse base datetime to get when forecast was made
    base_dt = datetime.fromisoformat(ml_data['base_datetime'])
    forecast_date = base_dt.strftime('%Y-%m-%d')
    forecast_hour = base_dt.hour

    # Extract compact predictions
    predictions = []
    for forecast in ml_data['forecasts']:
        predictions.append({
            'horizon': forecast['horizon'],
            'target_datetime': forecast['target_datetime'],
            'cmg': forecast['predicted_cmg'],
            'prob_zero': round(forecast['zero_probability'], 4),
            'threshold': round(forecast['decision_threshold'], 4),
            'value_pred': round(forecast.get('value_prediction', 0), 2)
        })

    return {
        (forecast_date, forecast_hour): {
            'forecast_time': ml_data['base_datetime'],
            'generated_at': ml_data['generated_at'],
            'model_version': ml_data.get('model_version', 'unknown'),
            'predictions': predictions
        }
    }

def organize_programado_forecasts(prog_data):
    """
    Organize CMG Programado forecasts by forecast hour
    Returns dict keyed by (date, hour) with FUTURE forecast values only
    (filters out past data to match ML forecast behavior)
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

    # Organize by node, filtering for FUTURE forecasts only
    forecasts_by_node = {}

    # Round fetch_time UP to next hour to ensure we only get future hours
    # Example: if fetch_time is 12:45, we want forecasts from 13:00 onwards
    fetch_hour_ceil = fetch_time.replace(minute=0, second=0, microsecond=0)
    if fetch_time.minute > 0 or fetch_time.second > 0:
        fetch_hour_ceil = fetch_hour_ceil + timedelta(hours=1)

    for record in prog_data['data']:
        # Parse record datetime
        record_time = datetime.fromisoformat(record['datetime']).replace(tzinfo=santiago_tz)

        # ONLY include forecasts for future hours (next hour onwards)
        # This matches ML behavior: forecast made at hour X predicts hour X+1 onwards
        if record_time >= fetch_hour_ceil:
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
    """Fetch existing historical data from Gist"""
    if not GIST_ID or not GITHUB_TOKEN:
        print("⚠️ Gist ID or token not available")
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

def merge_forecast_matrices(existing_data, ml_forecasts, prog_forecasts):
    """
    Merge new forecast matrices with existing data
    Structure: daily_data[date][ml_forecasts][hour] and [cmg_programado_forecasts][hour]
    """
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    cutoff_date = (now - timedelta(days=ROLLING_WINDOW_DAYS)).strftime('%Y-%m-%d')

    if existing_data is None:
        existing_data = {
            'metadata': {},
            'daily_data': {}
        }

    # Ensure structure version
    if 'metadata' not in existing_data:
        existing_data['metadata'] = {}

    # Add ML forecasts
    for (date, hour), forecast_data in ml_forecasts.items():
        if date >= cutoff_date:
            if date not in existing_data['daily_data']:
                existing_data['daily_data'][date] = {
                    'hours': list(range(24)),
                    'cmg_online': {},
                    'cmg_programado': {},
                    'ml_forecasts': {},
                    'cmg_programado_forecasts': {}
                }

            # Ensure v3.0 keys exist (backward compatibility with v2.0 data)
            if 'ml_forecasts' not in existing_data['daily_data'][date]:
                existing_data['daily_data'][date]['ml_forecasts'] = {}
            if 'cmg_programado_forecasts' not in existing_data['daily_data'][date]:
                existing_data['daily_data'][date]['cmg_programado_forecasts'] = {}

            # Add ML forecast for this hour
            existing_data['daily_data'][date]['ml_forecasts'][str(hour)] = forecast_data

    # Add CMG Programado forecasts
    for (date, hour), forecast_data in prog_forecasts.items():
        if date >= cutoff_date:
            if date not in existing_data['daily_data']:
                existing_data['daily_data'][date] = {
                    'hours': list(range(24)),
                    'cmg_online': {},
                    'cmg_programado': {},
                    'ml_forecasts': {},
                    'cmg_programado_forecasts': {}
                }

            # Ensure v3.0 keys exist (backward compatibility with v2.0 data)
            if 'ml_forecasts' not in existing_data['daily_data'][date]:
                existing_data['daily_data'][date]['ml_forecasts'] = {}
            if 'cmg_programado_forecasts' not in existing_data['daily_data'][date]:
                existing_data['daily_data'][date]['cmg_programado_forecasts'] = {}

            # Add Programado forecast for this hour
            existing_data['daily_data'][date]['cmg_programado_forecasts'][str(hour)] = forecast_data

    # Remove old data beyond rolling window
    dates_to_remove = [date for date in existing_data['daily_data'] if date < cutoff_date]
    for date in dates_to_remove:
        del existing_data['daily_data'][date]

    # Update metadata
    existing_data['metadata']['last_update'] = now.isoformat()
    existing_data['metadata']['structure_version'] = '3.0'  # Updated version
    existing_data['metadata']['rolling_window_days'] = ROLLING_WINDOW_DAYS
    existing_data['metadata']['total_days'] = len(existing_data['daily_data'])
    if existing_data['daily_data']:
        existing_data['metadata']['oldest_date'] = min(existing_data['daily_data'].keys())
        existing_data['metadata']['newest_date'] = max(existing_data['daily_data'].keys())

    return existing_data

def update_gist(data):
    """Update GitHub Gist with forecast matrices"""
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN not set, saving locally only")
        local_path = Path('data/cache/forecast_matrices.json')
        with open(local_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Saved locally to {local_path}")
        return

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
        print("✅ Successfully updated GitHub Gist with forecast matrices")
    else:
        print(f"❌ Error updating Gist: {response.status_code}")
        print(response.text)

def main():
    """Main function to store forecast matrices"""
    print(f"\n{'='*60}")
    print("STORING FORECAST MATRICES TO GIST")
    print(f"{'='*60}")

    # Load ML predictions
    ml_data = load_ml_predictions()
    ml_forecasts = {}
    if ml_data:
        ml_forecasts = organize_ml_forecasts(ml_data)
        print(f"✅ Loaded ML predictions: {len(ml_forecasts)} forecast(s)")
        for (date, hour), _ in ml_forecasts.items():
            print(f"   - {date} {hour:02d}:00 (24-hour ML forecast)")
    else:
        print("⚠️ No ML predictions to store")

    # Load CMG Programado
    prog_data = load_cmg_programado()
    prog_forecasts = {}
    if prog_data:
        prog_forecasts = organize_programado_forecasts(prog_data)
        print(f"✅ Loaded CMG Programado: {len(prog_forecasts)} forecast(s)")
        for (date, hour), data in prog_forecasts.items():
            nodes = list(data['forecasts'].keys())
            hours_count = len(data['forecasts'][nodes[0]]) if nodes else 0
            print(f"   - {date} {hour:02d}:00 ({hours_count}-hour forecast for {len(nodes)} nodes)")
    else:
        print("⚠️ No CMG Programado to store")

    if not ml_forecasts and not prog_forecasts:
        print("❌ No forecasts to store, exiting")
        return

    # Fetch existing Gist data
    print("\n📥 Fetching existing Gist data...")
    existing_data = fetch_existing_gist()

    # Merge forecast matrices
    print("🔄 Merging forecast matrices...")
    merged_data = merge_forecast_matrices(existing_data, ml_forecasts, prog_forecasts)

    print(f"📊 Total days in historical data: {merged_data['metadata']['total_days']}")
    print(f"📅 Date range: {merged_data['metadata'].get('oldest_date')} to {merged_data['metadata'].get('newest_date')}")

    # Update Gist
    print("\n📤 Updating Gist...")
    update_gist(merged_data)

    # Also save locally for reference
    local_path = Path('data/cache/cmg_online_historical.json')
    with open(local_path, 'w') as f:
        json.dump(merged_data, f, indent=2)
    print(f"💾 Saved local copy to {local_path}")

    print(f"\n{'='*60}")
    print("FORECAST MATRICES STORAGE COMPLETE")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
