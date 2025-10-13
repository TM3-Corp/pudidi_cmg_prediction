#!/usr/bin/env python3
"""
Update the CMG Programado cache file from the history file
This ensures the API always has fresh future data to serve
"""

import json
from datetime import datetime
from pathlib import Path
import pytz

def update_programmed_cache():
    """Update cache/cmg_programmed_latest.json from cmg_programado_history.json"""
    
    # Santiago timezone
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    current_date = now.strftime('%Y-%m-%d')
    current_hour = now.hour
    
    print("="*60)
    print("UPDATE CMG PROGRAMADO CACHE")
    print("="*60)
    print(f"Current time: {now}")
    print(f"Current date: {current_date}")
    print(f"Current hour: {current_hour}")
    print()
    
    # Load the programado history
    history_path = Path('data/cmg_programado_history.json')
    if not history_path.exists():
        print(f"❌ History file not found: {history_path}")
        return 1
    
    with open(history_path, 'r') as f:
        history = json.load(f)
    
    print(f"📊 Loaded history with {len(history.get('historical_data', {}))} dates")
    
    # Create programmed data for cache (only future hours)
    programmed_data = []
    
    # Process historical_data to find future hours
    for date_str, hours_data in history.get('historical_data', {}).items():
        for hour_str, hour_data in hours_data.items():
            hour = int(hour_str)
            
            # Include future hours only
            if date_str > current_date or (date_str == current_date and hour > current_hour):
                programmed_data.append({
                    'datetime': f'{date_str}T{hour:02d}:00:00',
                    'date': date_str,
                    'hour': hour,
                    'node': hour_data.get('node', 'PMontt220'),
                    'cmg_programmed': hour_data.get('value', 0)
                })
    
    # Sort by datetime
    programmed_data.sort(key=lambda x: x['datetime'])
    
    # Create cache data
    cache_data = {
        'timestamp': now.isoformat(),
        'data': programmed_data,
        'statistics': {
            'total_records': len(programmed_data),
            'hours_ahead': len(programmed_data),
            'node': 'PMontt220'
        }
    }
    
    # Save to cache
    cache_path = Path('data/cache/cmg_programmed_latest.json')
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(cache_path, 'w') as f:
        json.dump(cache_data, f, indent=2)
    
    print(f"✅ Updated cache with {len(programmed_data)} future hours")
    if programmed_data:
        print(f"📅 Date range: {programmed_data[0]['date']} to {programmed_data[-1]['date']}")
        print(f"⏰ Hours: {programmed_data[0]['hour']:02d}:00 to {programmed_data[-1]['hour']:02d}:00")
    else:
        print("⚠️ No future data available!")
    
    print(f"💾 Cache saved to: {cache_path}")
    print()
    print("✅ Cache update completed successfully!")
    
    return 0


if __name__ == "__main__":
    exit(update_programmed_cache())