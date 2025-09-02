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
GIST_ID = '8d7864eb26acf6e780d3c0f7fed69365'  # Our public Gist for historical data
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

def load_programmed_cache():
    """Load the current CMG Programado forecast"""
    cache_path = Path('data/cache/cmg_programmed_latest.json')
    
    if not cache_path.exists():
        print("Programmed cache file not found")
        return None
    
    with open(cache_path, 'r') as f:
        data = json.load(f)
    
    return data.get('data', [])

def organize_by_date(records, programmed_records=None):
    """Organize records by date and hour for easier storage"""
    organized = {}
    
    # Process CMG Online (actual) data
    for record in records:
        date = record['date']
        hour = record['hour']
        node = record['node']
        
        if date not in organized:
            organized[date] = {
                'hours': list(range(24)),
                'cmg_online': {},
                'cmg_programado': {}  # Will store what was forecasted for this date
            }
        
        if node not in organized[date]['cmg_online']:
            organized[date]['cmg_online'][node] = {
                'cmg_usd': [None] * 24,
                'cmg_real': [None] * 24
            }
        
        # Store the actual values
        organized[date]['cmg_online'][node]['cmg_usd'][hour] = round(record.get('cmg_usd', 0), 2)
        organized[date]['cmg_online'][node]['cmg_real'][hour] = round(record.get('cmg_real', 0), 0)
    
    # Process CMG Programado (forecast) data if available
    if programmed_records:
        # Map node names (PMontt220 -> NVA_P.MONTT___220)
        node_mapping = {
            'PMontt220': 'NVA_P.MONTT___220',
            'Pidpid110': 'PIDPID________110',
            'Dalcahue110': 'DALCAHUE______110'
        }
        
        for record in programmed_records:
            date = record.get('date')
            hour = record.get('hour')
            orig_node = record.get('node')
            
            # Map the node name
            node = node_mapping.get(orig_node, orig_node)
            
            if date and date in organized:
                if node not in organized[date]['cmg_programado']:
                    organized[date]['cmg_programado'][node] = {
                        'values': [None] * 24
                    }
                
                if hour is not None and hour < 24:
                    organized[date]['cmg_programado'][node]['values'][hour] = round(record.get('cmg_programmed', 0), 2)
    
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
            # If date exists, merge programado data with existing online data
            if date in existing_data['daily_data']:
                # Keep existing CMG Online data if present
                if 'cmg_online' in existing_data['daily_data'][date]:
                    data['cmg_online'] = existing_data['daily_data'][date]['cmg_online']
                # Update with new CMG Programado if available
                if 'cmg_programado' in data and data['cmg_programado']:
                    existing_data['daily_data'][date]['cmg_programado'] = data['cmg_programado']
                else:
                    # Keep existing programado if new doesn't have it
                    if 'cmg_programado' in existing_data['daily_data'][date]:
                        data['cmg_programado'] = existing_data['daily_data'][date]['cmg_programado']
            
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
        'nodes': NODES,
        'structure_version': '2.0'  # New structure with online and programado
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
    print("STORING CMG HISTORICAL DATA (ONLINE + PROGRAMADO)")
    print(f"{'='*60}")
    
    # Load current CMG Online cache
    online_records = load_current_cache()
    if not online_records:
        print("No CMG Online data to store")
        return
    
    print(f"Found {len(online_records)} CMG Online records")
    
    # Load current CMG Programado forecast
    programmed_records = load_programmed_cache()
    if programmed_records:
        print(f"Found {len(programmed_records)} CMG Programado records")
    else:
        print("No CMG Programado data available")
    
    # Organize by date with both online and programado
    organized_data = organize_by_date(online_records, programmed_records)
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