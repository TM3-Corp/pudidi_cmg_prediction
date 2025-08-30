#!/usr/bin/env python3
"""
Quick update for programmed data only from GitHub Gist
"""

import json
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
from pathlib import Path

def fetch_programmed_from_gist():
    """Fetch PMontt220 programmed data from GitHub Gist"""
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print(f"📌 Fetching PMontt220 programmed data from GitHub Gist at {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Gist with CSV files
    gist_url = "https://gist.github.com/PVSH97/a63a3a10479bafcc29e10aaca627bc73"
    
    try:
        # Get gist metadata
        gist_api_url = "https://api.github.com/gists/a63a3a10479bafcc29e10aaca627bc73"
        response = requests.get(gist_api_url, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch gist metadata: {response.status_code}")
            return None
            
        gist_data = response.json()
        
        # Find CSV files and select the one with latest data
        csv_files = {}
        print("🔍 Checking CSV files in gist...")
        
        for filename, file_info in gist_data['files'].items():
            if filename.endswith('.csv'):
                # Fetch the CSV content
                csv_url = file_info['raw_url']
                csv_response = requests.get(csv_url, timeout=10)
                
                if csv_response.status_code == 200:
                    try:
                        # Parse CSV
                        from io import StringIO
                        df = pd.read_csv(StringIO(csv_response.text))
                        
                        # Check if it has required columns
                        if 'Fecha' in df.columns and 'PMontt220' in df.columns:
                            # Find the last date in this CSV
                            df['datetime'] = pd.to_datetime(df['Fecha'])
                            last_date = df['datetime'].max()
                            
                            csv_files[filename] = {
                                'df': df,
                                'last_date': last_date,
                                'url': csv_url
                            }
                            
                            print(f"   {filename[:12]}... has data until {last_date.strftime('%Y-%m-%d %H:%M')}")
                            
                    except Exception as e:
                        print(f"   ❌ Error parsing {filename}: {str(e)[:50]}")
        
        if not csv_files:
            print("❌ No valid CSV files found in gist")
            return None
        
        # Select CSV with the latest data
        selected_file = max(csv_files.items(), key=lambda x: x[1]['last_date'])
        selected_name, selected_data = selected_file
        
        print(f"✅ Selected CSV with data up to {selected_data['last_date'].strftime('%Y-%m-%d %H:%M')}")
        
        # Process the selected CSV
        df = selected_data['df']
        df['datetime'] = pd.to_datetime(df['Fecha'])
        
        # Filter for future hours only
        future_data = []
        for _, row in df.iterrows():
            dt = row['datetime']
            
            # Skip if not future
            if dt <= now:
                continue
                
            # Add to programmed data
            future_data.append({
                'datetime': dt.strftime('%Y-%m-%dT%H:%M:%S'),
                'date': dt.strftime('%Y-%m-%d'),
                'hour': dt.hour,
                'node': 'PMontt220',
                'cmg_programmed': row['PMontt220']
            })
        
        # Sort by datetime
        future_data.sort(key=lambda x: x['datetime'])
        
        # Limit to next 72 hours
        max_future = now + timedelta(hours=72)
        future_data = [d for d in future_data if datetime.fromisoformat(d['datetime']) <= max_future]
        
        print(f"📊 Found {len(future_data)} future hours of PMontt220 data")
        
        if future_data:
            # Check which hours we have for next 24 hours
            next_24_hours = []
            for i in range(24):
                target_hour = (now + timedelta(hours=i+1)).hour
                if any(d['hour'] == target_hour for d in future_data[:24]):
                    next_24_hours.append(target_hour)
            
            print(f"   Next 24 hours available: {next_24_hours[:10]}{'...' if len(next_24_hours) > 10 else ''}")
        
        return future_data
        
    except Exception as e:
        print(f"❌ Error fetching from gist: {str(e)}")
        return None

def main():
    """Quick update of programmed cache only"""
    
    print("="*80)
    print("QUICK PROGRAMMED DATA UPDATE")
    print("="*80)
    
    # Fetch programmed data
    programmed_data = fetch_programmed_from_gist()
    
    if programmed_data:
        # Save to cache
        cache_dir = Path('data/cache')
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        
        programmed_cache = {
            'timestamp': now.isoformat(),
            'data': programmed_data,
            'statistics': {
                'total_records': len(programmed_data),
                'hours_ahead': min(len(programmed_data), 72),
                'node': 'PMontt220'
            }
        }
        
        cache_file = cache_dir / 'cmg_programmed_latest.json'
        with open(cache_file, 'w') as f:
            json.dump(programmed_cache, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved {len(programmed_data)} programmed records to cache")
        print(f"📊 First 5 prices:")
        for i in range(min(5, len(programmed_data))):
            record = programmed_data[i]
            print(f"   {record['datetime']}: ${record['cmg_programmed']:.2f}/MWh")
    else:
        print("❌ Failed to fetch programmed data")
        return 1
    
    print("="*80)
    print("✅ QUICK UPDATE COMPLETE")
    print("="*80)
    return 0

if __name__ == "__main__":
    exit(main())