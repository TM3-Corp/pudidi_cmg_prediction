#!/usr/bin/env python3
"""
Merge CMG Programado CSV with historical data
Preserves past values, only updates future forecasts
"""

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import pytz

def parse_csv_file(csv_path):
    """Parse CMG Programado CSV file"""
    print(f"Parsing CSV file: {csv_path}")
    
    data = {}
    santiago_tz = pytz.timezone('America/Santiago')
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        row_count = 0
        
        for row in reader:
            row_count += 1
            
            # Find columns (handle different naming conventions)
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
            
            if not fecha_hora or not barra or costo is None:
                continue
            
            # Parse datetime (format: '2025-08-29 00:00:00.000000')
            try:
                dt = datetime.strptime(fecha_hora[:19], '%Y-%m-%d %H:%M:%S')
                dt = santiago_tz.localize(dt)
                date_str = dt.strftime('%Y-%m-%d')
                hour = dt.hour
            except Exception as e:
                print(f"Error parsing date {fecha_hora}: {e}")
                continue
            
            # Filter for PMontt220 (our main node)
            if barra != 'PMontt220':
                continue
            
            # Store the data
            if date_str not in data:
                data[date_str] = {}
            
            data[date_str][str(hour)] = {
                'value': costo,
                'node': barra,
                'timestamp': dt.isoformat()
            }
    
    print(f"Parsed {row_count} rows, found data for {len(data)} days")
    return data

def load_existing_history(gist_id=None):
    """Load existing historical data from Gist or local file"""
    
    # Try local file first
    local_file = Path('data/cmg_programado_history.json')
    if local_file.exists():
        print(f"Loading existing history from local file: {local_file}")
        with open(local_file, 'r') as f:
            return json.load(f)
    
    # Try to fetch from Gist if ID provided
    if gist_id:
        print(f"Fetching existing history from Gist: {gist_id}")
        import requests
        
        response = requests.get(f'https://api.github.com/gists/{gist_id}')
        if response.status_code == 200:
            gist_data = response.json()
            for filename, file_info in gist_data.get('files', {}).items():
                if filename.endswith('.json'):
                    content = file_info.get('content', '{}')
                    return json.loads(content)
    
    print("No existing history found, starting fresh")
    return {}

def merge_with_history(new_data, existing_data):
    """
    Merge new CSV data with existing historical data
    Rules:
    1. Never overwrite past hours that have already occurred
    2. Update future forecasts
    3. Add new dates that don't exist
    """
    
    santiago_tz = pytz.timezone('America/Santiago')
    current_time = datetime.now(santiago_tz)
    
    # Start with existing data
    merged = existing_data.copy() if existing_data else {}
    
    # Ensure we have the right structure
    if 'historical_data' not in merged:
        merged['historical_data'] = {}
    
    historical = merged['historical_data']
    
    stats = {
        'preserved': 0,
        'updated': 0,
        'added': 0
    }
    
    print(f"\nMerging data (current time: {current_time.strftime('%Y-%m-%d %H:%M')})")
    
    for date_str, hours_data in new_data.items():
        if date_str not in historical:
            historical[date_str] = {}
            print(f"  Adding new date: {date_str}")
        
        for hour_str, hour_data in hours_data.items():
            # Parse the timestamp
            dt = datetime.fromisoformat(hour_data['timestamp'])
            
            # Check if this is a past, current, or future hour
            if dt < current_time:
                # This is a past hour
                if hour_str in historical[date_str] and historical[date_str][hour_str].get('is_historical'):
                    # Already marked as historical, don't overwrite
                    stats['preserved'] += 1
                elif hour_str not in historical[date_str]:
                    # Past hour not in our data, add it as historical
                    historical[date_str][hour_str] = hour_data.copy()
                    historical[date_str][hour_str]['is_historical'] = True
                    historical[date_str][hour_str]['added_at'] = current_time.isoformat()
                    stats['added'] += 1
                else:
                    # Mark existing data as historical
                    historical[date_str][hour_str]['is_historical'] = True
                    stats['preserved'] += 1
            else:
                # This is a future hour, update it
                if hour_str in historical[date_str]:
                    old_value = historical[date_str][hour_str].get('value')
                    new_value = hour_data['value']
                    
                    if old_value != new_value:
                        # Store history of changes
                        if 'history' not in historical[date_str][hour_str]:
                            historical[date_str][hour_str]['history'] = []
                        
                        historical[date_str][hour_str]['history'].append({
                            'value': old_value,
                            'replaced_at': current_time.isoformat()
                        })
                    
                    # Update with new forecast
                    historical[date_str][hour_str].update(hour_data)
                    historical[date_str][hour_str]['last_updated'] = current_time.isoformat()
                    stats['updated'] += 1
                else:
                    # Add new future forecast
                    historical[date_str][hour_str] = hour_data.copy()
                    historical[date_str][hour_str]['last_updated'] = current_time.isoformat()
                    stats['added'] += 1
    
    # Update metadata
    merged['metadata'] = {
        'last_update': current_time.isoformat(),
        'total_days': len(historical),
        'total_hours': sum(len(hours) for hours in historical.values()),
        'node': 'PMontt220',
        'merge_stats': stats
    }
    
    print(f"\nMerge complete:")
    print(f"  Preserved: {stats['preserved']} historical values")
    print(f"  Updated: {stats['updated']} future forecasts")
    print(f"  Added: {stats['added']} new values")
    
    return merged

def save_merged_data(merged_data, output_path='data/cmg_programado_history.json'):
    """Save merged data to JSON file"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Saved merged data to: {output_path}")
    
    # Print summary
    if 'metadata' in merged_data:
        meta = merged_data['metadata']
        print(f"   Total days: {meta.get('total_days', 0)}")
        print(f"   Total hours: {meta.get('total_hours', 0)}")

def main():
    """Main execution"""
    print("="*60)
    print("CMG PROGRAMADO HISTORY MERGER")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 1. Find the CSV file
    csv_path = Path('downloads/costo_marginal_programado.csv')
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        return 1
    
    print(f"✅ Found CSV file: {csv_path}")
    
    # 2. Parse the CSV
    new_data = parse_csv_file(csv_path)
    if not new_data:
        print("❌ No data found in CSV")
        return 1
    
    # 3. Load existing history
    existing_data = load_existing_history()
    
    # 4. Merge with history
    merged_data = merge_with_history(new_data, existing_data)
    
    # 5. Save the merged data
    save_merged_data(merged_data)
    
    # 6. Show sample of data
    print("\nSample of merged data:")
    if 'historical_data' in merged_data:
        for date_str in sorted(list(merged_data['historical_data'].keys()))[-2:]:
            hours = merged_data['historical_data'][date_str]
            print(f"\n  {date_str}:")
            for hour in ['0', '12', '23']:
                if hour in hours:
                    data = hours[hour]
                    historical = " (HISTORICAL)" if data.get('is_historical') else ""
                    print(f"    Hour {hour:2s}: {data.get('value', 'N/A'):6.2f} USD/MWh{historical}")
    
    print("\n" + "="*60)
    print("✅ History merge completed successfully!")
    return 0

if __name__ == "__main__":
    exit(main())