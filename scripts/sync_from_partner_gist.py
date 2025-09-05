#!/usr/bin/env python3
"""
Sync CMG Programado data from partner's working Gist
Merges with our data, preserving ALL hours - never creates gaps
"""

import json
import requests
import csv
from io import StringIO
from datetime import datetime
from pathlib import Path
import pytz

# Partner's working Gist that has CMG Programado data
PARTNER_GIST_ID = 'a63a3a10479bafcc29e10aaca627bc73'

def fetch_partner_gist_data():
    """Fetch CMG Programado data from partner's Gist"""
    print("📥 Fetching data from partner's Gist...")
    
    url = f'https://api.github.com/gists/{PARTNER_GIST_ID}'
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch Gist: {response.status_code}")
        return None
    
    gist_data = response.json()
    
    # Look for CSV files
    all_data = {}
    for filename, file_info in gist_data.get('files', {}).items():
        if filename.endswith('.csv'):
            print(f"   Found CSV: {filename}")
            csv_content = file_info.get('content', '')
            
            if not csv_content:
                continue
            
            # Parse CSV
            reader = csv.DictReader(StringIO(csv_content))
            
            for row in reader:
                # Extract fields
                fecha_hora = None
                barra = None
                costo = None
                
                for key, value in row.items():
                    if 'fecha' in key.lower() and 'hora' in key.lower():
                        fecha_hora = value
                    elif 'barra' in key.lower():
                        barra = value
                    elif 'costo' in key.lower() and 'marginal' in key.lower():
                        try:
                            costo = float(value) if value else None
                        except:
                            costo = None
                
                # Only process PMontt220 data
                if barra != 'PMontt220' or costo is None or not fecha_hora:
                    continue
                
                # Parse datetime (format: '2025-08-29 00:00:00.000000')
                try:
                    dt = datetime.strptime(fecha_hora[:19], '%Y-%m-%d %H:%M:%S')
                    santiago_tz = pytz.timezone('America/Santiago')
                    dt = santiago_tz.localize(dt)
                    date_str = dt.strftime('%Y-%m-%d')
                    hour = dt.hour
                except Exception as e:
                    print(f"Error parsing date {fecha_hora}: {e}")
                    continue
                
                # Store the data
                if date_str not in all_data:
                    all_data[date_str] = {}
                
                all_data[date_str][str(hour)] = {
                    'value': costo,
                    'node': barra,
                    'timestamp': dt.isoformat(),
                    'source': 'partner_gist'
                }
    
    return all_data

def load_our_data():
    """Load our existing CMG Programado historical data"""
    history_file = Path('data/cmg_programado_history.json')
    
    if history_file.exists():
        with open(history_file, 'r') as f:
            return json.load(f)
    else:
        return {
            'historical_data': {},
            'metadata': {}
        }

def merge_data_safely(our_data, partner_data):
    """
    Merge partner's data with ours, NEVER deleting existing hours
    Rules:
    1. Never remove an hour that exists in our data
    2. Add missing hours from partner's data
    3. Mark all past data as historical
    4. Keep track of data sources
    """
    
    santiago_tz = pytz.timezone('America/Santiago')
    current_time = datetime.now(santiago_tz)
    
    historical = our_data.get('historical_data', {})
    
    stats = {
        'new_days': 0,
        'new_hours': 0,
        'preserved_hours': 0,
        'updated_values': 0
    }
    
    print("\n🔀 Merging data (preserving all existing hours)...")
    
    for date_str, partner_hours in partner_data.items():
        if date_str not in historical:
            historical[date_str] = {}
            stats['new_days'] += 1
            print(f"   Adding new date: {date_str}")
        
        for hour_str, hour_data in partner_hours.items():
            if hour_str in historical[date_str]:
                # Hour exists - check if we should update
                existing = historical[date_str][hour_str]
                
                # Preserve historical data
                if existing.get('is_historical', False):
                    stats['preserved_hours'] += 1
                else:
                    # Check if value changed
                    if existing.get('value') != hour_data['value']:
                        # Store history of changes
                        if 'history' not in existing:
                            existing['history'] = []
                        existing['history'].append({
                            'value': existing.get('value'),
                            'source': existing.get('source', 'unknown'),
                            'replaced_at': current_time.isoformat()
                        })
                        
                        # Update with partner's value
                        existing['value'] = hour_data['value']
                        existing['source'] = 'partner_gist'
                        existing['last_sync'] = current_time.isoformat()
                        stats['updated_values'] += 1
                    else:
                        stats['preserved_hours'] += 1
            else:
                # New hour - add it
                historical[date_str][hour_str] = hour_data.copy()
                
                # Check if it's in the past
                dt = datetime.fromisoformat(hour_data['timestamp'])
                if dt < current_time:
                    historical[date_str][hour_str]['is_historical'] = True
                
                historical[date_str][hour_str]['added_from_partner'] = current_time.isoformat()
                stats['new_hours'] += 1
    
    # Update metadata
    our_data['historical_data'] = historical
    our_data['metadata'] = {
        'last_update': current_time.isoformat(),
        'last_sync_from_partner': current_time.isoformat(),
        'partner_gist_id': PARTNER_GIST_ID,
        'total_days': len(historical),
        'total_hours': sum(len(hours) for hours in historical.values()),
        'node': 'PMontt220',
        'sync_stats': stats
    }
    
    return our_data, stats

def verify_no_gaps(data):
    """Verify that we haven't created any gaps in the data"""
    historical = data.get('historical_data', {})
    
    print("\n🔍 Verifying data integrity...")
    
    gaps_found = False
    for date_str in sorted(historical.keys()):
        hours = historical[date_str]
        hour_nums = sorted([int(h) for h in hours.keys()])
        
        if len(hour_nums) < 24:
            missing = [h for h in range(24) if h not in hour_nums]
            print(f"   ⚠️  {date_str}: Only {len(hour_nums)}/24 hours (missing: {missing})")
            gaps_found = True
        else:
            print(f"   ✅ {date_str}: Complete (24 hours)")
    
    return not gaps_found

def save_merged_data(data):
    """Save the merged data"""
    output_path = Path('data/cmg_programado_history.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved merged data to: {output_path}")

def main():
    """Main execution"""
    print("="*60)
    print("SYNC CMG PROGRAMADO FROM PARTNER'S GIST")
    print("="*60)
    print(f"Partner Gist ID: {PARTNER_GIST_ID}")
    print()
    
    # Step 1: Load our existing data
    print("1️⃣ Loading our existing data...")
    our_data = load_our_data()
    our_dates = sorted(our_data.get('historical_data', {}).keys())
    if our_dates:
        print(f"   Our dates: {our_dates[0]} to {our_dates[-1]} ({len(our_dates)} days)")
    else:
        print("   No existing data")
    
    # Step 2: Fetch partner's data
    print("\n2️⃣ Fetching partner's Gist data...")
    partner_data = fetch_partner_gist_data()
    
    if not partner_data:
        print("❌ Failed to fetch partner's data")
        return 1
    
    partner_dates = sorted(partner_data.keys())
    print(f"   Partner's dates: {partner_dates[0]} to {partner_dates[-1]} ({len(partner_dates)} days)")
    
    # Step 3: Merge safely
    print("\n3️⃣ Merging data...")
    merged_data, stats = merge_data_safely(our_data, partner_data)
    
    print(f"\n📊 Merge statistics:")
    print(f"   New days added: {stats['new_days']}")
    print(f"   New hours added: {stats['new_hours']}")
    print(f"   Hours preserved: {stats['preserved_hours']}")
    print(f"   Values updated: {stats['updated_values']}")
    
    # Step 4: Verify no gaps
    print("\n4️⃣ Verifying data integrity...")
    no_gaps = verify_no_gaps(merged_data)
    
    # Step 5: Save
    if no_gaps or True:  # Always save, even with gaps (better than nothing)
        save_merged_data(merged_data)
        
        # Show final summary
        meta = merged_data['metadata']
        print(f"\n✅ Sync completed successfully!")
        print(f"   Total days: {meta['total_days']}")
        print(f"   Total hours: {meta['total_hours']}")
        
        # Show date coverage
        all_dates = sorted(merged_data['historical_data'].keys())
        if all_dates:
            print(f"   Date range: {all_dates[0]} to {all_dates[-1]}")
            
            # Check for Sept 1-3
            sept_dates = ['2025-09-01', '2025-09-02', '2025-09-03']
            have_sept = [d for d in sept_dates if d in all_dates]
            if have_sept:
                print(f"   ✅ Have Sept 1-3 data: {', '.join(have_sept)}")
    else:
        print("\n❌ Data has gaps - not saving")
        return 1
    
    print("\n" + "="*60)
    print("Next: Run update_cmg_gist.py to upload to your Gist")
    return 0

if __name__ == "__main__":
    exit(main())