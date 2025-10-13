#!/usr/bin/env python3
"""
Store ML predictions to dedicated Gist
Keeps 7-day rolling window of hourly forecasts
"""

import json
import requests
from datetime import datetime, timedelta
import pytz
import os
from pathlib import Path

# Configuration
GIST_ID = '38b3f9b1cdae5362d3676911ab27f606'  # ML Predictions Gist
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('CMG_GIST_TOKEN')
GIST_FILENAME = 'ml_predictions_historical.json'
ROLLING_WINDOW_DAYS = 7

def load_ml_predictions():
    """Load latest ML predictions"""
    ml_path = Path('data/ml_predictions/latest.json')
    if not ml_path.exists():
        print("⚠️ ML predictions not found")
        return None

    with open(ml_path, 'r') as f:
        return json.load(f)

def organize_ml_forecasts(ml_data):
    """Organize ML predictions by (date, hour)"""
    if not ml_data or 'forecasts' not in ml_data:
        return {}

    base_dt = datetime.fromisoformat(ml_data['base_datetime'])
    forecast_date = base_dt.strftime('%Y-%m-%d')
    forecast_hour = base_dt.hour

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

def merge_data(existing_data, ml_forecasts):
    """Merge new ML forecasts with existing data"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    cutoff_date = (now - timedelta(days=ROLLING_WINDOW_DAYS)).strftime('%Y-%m-%d')

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
    for (date, hour), forecast_data in ml_forecasts.items():
        if date >= cutoff_date:
            if date not in existing_data['daily_data']:
                existing_data['daily_data'][date] = {'ml_forecasts': {}}

            if 'ml_forecasts' not in existing_data['daily_data'][date]:
                existing_data['daily_data'][date]['ml_forecasts'] = {}

            existing_data['daily_data'][date]['ml_forecasts'][str(hour)] = forecast_data

    # Remove old data
    dates_to_remove = [d for d in existing_data['daily_data'] if d < cutoff_date]
    for date in dates_to_remove:
        del existing_data['daily_data'][date]

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
    """Update Gist with ML predictions"""
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
        print("✅ ML Predictions Gist updated successfully")
        return True
    else:
        print(f"❌ Error updating Gist: {response.status_code}")
        print(response.text)
        return False

def main():
    print("\n" + "="*60)
    print("STORING ML PREDICTIONS TO GIST")
    print("="*60)

    # Load ML predictions
    ml_data = load_ml_predictions()
    if not ml_data:
        print("⚠️ No ML predictions to store")
        return

    ml_forecasts = organize_ml_forecasts(ml_data)
    print(f"✅ Loaded ML predictions: {len(ml_forecasts)} forecast(s)")

    for (date, hour), _ in ml_forecasts.items():
        print(f"   - {date} {hour:02d}:00 (24-hour ML forecast)")

    # Fetch existing data
    print("\n📥 Fetching existing Gist data...")
    existing_data = fetch_existing_gist()

    # Merge
    print("🔄 Merging ML predictions...")
    merged_data = merge_data(existing_data, ml_forecasts)

    print(f"📊 Total days: {merged_data['metadata']['total_days']}")
    if merged_data['metadata'].get('oldest_date'):
        print(f"📅 Date range: {merged_data['metadata']['oldest_date']} to {merged_data['metadata']['newest_date']}")

    # Update Gist
    print("\n📤 Updating Gist...")
    success = update_gist(merged_data)

    # Save local copy
    local_path = Path('data/cache/ml_predictions_historical.json')
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, 'w') as f:
        json.dump(merged_data, f, indent=2)
    print(f"💾 Saved local copy to {local_path}")

    print("\n" + "="*60)
    print("ML PREDICTIONS STORAGE COMPLETE")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
