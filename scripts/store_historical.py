#!/usr/bin/env python3
"""
Store historical CMG Online data to GitHub Gist
Maintains a rolling window of historical data for performance comparison
"""

import json
import requests
from datetime import datetime, timedelta
import pytz
import os
from pathlib import Path

# GitHub Gist configuration
GIST_ID = None  # Will be set after creating the Gist
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')  # Set in GitHub Actions secrets
GIST_FILENAME = 'cmg_online_historical.json'

# Data configuration
ROLLING_WINDOW_DAYS = 30  # Keep 30 days of historical data
NODES = ['NVA_P.MONTT___220', 'PIDPID________110', 'DALCAHUE______110']

def load_current_cache():
    """Load the current aggregated CMG historical cache"""
    cache_path = Path('data/cache/cmg_historical_latest.json')
    
    if not cache_path.exists():
        print("Cache file not found")
        return None
    
    with open(cache_path, 'r') as f:
        data = json.load(f)
    
    return data.get('data', [])

def organize_by_date(records):
    """Organize records by date and hour for easier storage"""
    organized = {}
    
    for record in records:
        date = record['date']
        hour = record['hour']
        node = record['node']
        
        if date not in organized:
            organized[date] = {
                'hours': list(range(24)),
                'data': {}
            }
        
        if node not in organized[date]['data']:
            organized[date]['data'][node] = {
                'cmg_usd': [None] * 24,
                'cmg_real': [None] * 24
            }
        
        # Store the values at the correct hour index
        organized[date]['data'][node]['cmg_usd'][hour] = round(record.get('cmg_usd', 0), 2)
        organized[date]['data'][node]['cmg_real'][hour] = round(record.get('cmg_real', 0), 0)
    
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
            if GIST_FILENAME in gist_data['files']:
                content = gist_data['files'][GIST_FILENAME]['content']
                return json.loads(content)
    except Exception as e:
        print(f"Error fetching existing Gist: {e}")
    
    return None

def merge_historical_data(existing_data, new_data):
    """Merge new data with existing, maintaining rolling window"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    cutoff_date = (now - timedelta(days=ROLLING_WINDOW_DAYS)).strftime('%Y-%m-%d')
    
    if existing_data is None:
        existing_data = {
            'metadata': {},
            'daily_data': {}
        }
    
    # Merge new data
    for date, data in new_data.items():
        if date >= cutoff_date:
            existing_data['daily_data'][date] = data
    
    # Remove old data beyond rolling window
    dates_to_remove = [date for date in existing_data['daily_data'] if date < cutoff_date]
    for date in dates_to_remove:
        del existing_data['daily_data'][date]
    
    # Update metadata
    existing_data['metadata'] = {
        'last_update': now.isoformat(),
        'total_days': len(existing_data['daily_data']),
        'oldest_date': min(existing_data['daily_data'].keys()) if existing_data['daily_data'] else None,
        'newest_date': max(existing_data['daily_data'].keys()) if existing_data['daily_data'] else None,
        'nodes': NODES
    }
    
    return existing_data

def update_gist(data):
    """Update or create GitHub Gist with historical data"""
    if not GITHUB_TOKEN:
        print("Warning: GITHUB_TOKEN not set, saving locally only")
        with open('cmg_online_historical.json', 'w') as f:
            json.dump(data, f, indent=2)
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
    
    if GIST_ID:
        # Update existing Gist
        url = f'https://api.github.com/gists/{GIST_ID}'
        response = requests.patch(url, headers=headers, json=gist_content)
    else:
        # Create new Gist
        gist_content['description'] = 'CMG Online Historical Data for Performance Analysis'
        gist_content['public'] = True
        url = 'https://api.github.com/gists'
        response = requests.post(url, headers=headers, json=gist_content)
        
        if response.status_code == 201:
            new_gist = response.json()
            print(f"Created new Gist: {new_gist['id']}")
            print(f"URL: {new_gist['html_url']}")
            # Save the Gist ID for future use
            with open('.gist_id', 'w') as f:
                f.write(new_gist['id'])
    
    if response.status_code in [200, 201]:
        print("Successfully updated GitHub Gist")
    else:
        print(f"Error updating Gist: {response.status_code}")
        print(response.text)

def main():
    """Main function to store historical data"""
    print(f"\n{'='*60}")
    print("STORING CMG ONLINE HISTORICAL DATA")
    print(f"{'='*60}")
    
    # Load current cache
    records = load_current_cache()
    if not records:
        print("No data to store")
        return
    
    print(f"Found {len(records)} records in cache")
    
    # Organize by date
    organized_data = organize_by_date(records)
    print(f"Organized into {len(organized_data)} days")
    
    # Fetch existing Gist data
    existing_data = fetch_existing_gist()
    
    # Merge with existing data
    merged_data = merge_historical_data(existing_data, organized_data)
    print(f"Total days in historical data: {merged_data['metadata']['total_days']}")
    
    # Update Gist
    update_gist(merged_data)
    
    # Also save locally for reference
    with open('data/cache/cmg_online_historical.json', 'w') as f:
        json.dump(merged_data, f, indent=2)
    print("Saved local copy to data/cache/cmg_online_historical.json")

if __name__ == "__main__":
    # Load Gist ID if it exists
    if os.path.exists('.gist_id'):
        with open('.gist_id', 'r') as f:
            GIST_ID = f.read().strip()
    
    main()