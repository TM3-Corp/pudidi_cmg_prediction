#!/usr/bin/env python3
"""
Simple Manual Update Script - Run this locally to update cache
"""

import requests
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Priority pages that we know work (from your notebook)
PRIORITY_PAGES = [
    2, 6, 10, 11, 16, 18, 21, 23, 27, 29, 32, 35, 37,  # High value
    3, 4, 7, 14, 19, 20, 24, 26, 28, 31, 33, 36,       # Medium value
    1, 5, 8, 9, 12, 13, 15, 17, 22, 25, 30, 34         # Low value
]

NODES = ['CHILOE________220', 'CHILOE________110', 'QUELLON_______110', 
         'QUELLON_______013', 'CHONCHI_______110', 'DALCAHUE______023']

def fetch_page(url, params, page_num):
    """Fetch a single page"""
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            records = data.get('data', [])
            return records if records else None
        return None
    except Exception as e:
        print(f"   Error on page {page_num}: {e}")
        return None

def main():
    print("\n" + "="*80)
    print("🚀 MANUAL CACHE UPDATE")
    print("="*80)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print(f"📅 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} Santiago")
    print(f"📊 Using 4000 records/page optimization")
    print(f"🎯 Maximum 40 pages (proven to be sufficient)")
    
    # Create cache directory if needed
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Fetch Historical Data
    print(f"\n📦 FETCHING HISTORICAL DATA")
    print("-" * 40)
    
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    today = now.strftime('%Y-%m-%d')
    
    all_historical = []
    
    # Fetch yesterday
    print(f"Fetching {yesterday}...")
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    pages_to_try = PRIORITY_PAGES[:40]  # Max 40 pages
    empty_count = 0
    
    for i, page in enumerate(pages_to_try, 1):
        params = {
            'startDate': yesterday,
            'endDate': yesterday,
            'page': page,
            'limit': 4000,
            'user_key': SIP_API_KEY
        }
        
        records = fetch_page(url, params, page)
        
        if records:
            # Filter for our nodes
            filtered = [r for r in records if r.get('barra_transf') in NODES]
            all_historical.extend(filtered)
            print(f"   Page {page:2d}: {len(records)} records, {len(filtered)} for our nodes")
            empty_count = 0
        else:
            print(f"   Page {page:2d}: Empty")
            empty_count += 1
            if empty_count >= 3:
                print("   Stopping - 3 consecutive empty pages")
                break
        
        # Show progress
        if i % 10 == 0:
            unique_hours = len(set(r.get('hra', -1) for r in all_historical))
            print(f"   Progress: {i} pages, {len(all_historical)} records, {unique_hours} unique hours")
        
        time.sleep(0.2)  # Small delay
    
    # Fetch today (up to current hour)
    print(f"\nFetching {today} (up to hour {now.hour})...")
    
    for i, page in enumerate(pages_to_try[:20], 1):  # Less pages for today
        params = {
            'startDate': today,
            'endDate': today,
            'page': page,
            'limit': 4000,
            'user_key': SIP_API_KEY
        }
        
        records = fetch_page(url, params, page)
        
        if records:
            # Filter for our nodes AND current hours
            filtered = []
            for r in records:
                if r.get('barra_transf') in NODES:
                    if 'hra' in r and r['hra'] <= now.hour:
                        filtered.append(r)
            
            if filtered:
                all_historical.extend(filtered)
                print(f"   Page {page:2d}: {len(filtered)} records for current hours")
        
        time.sleep(0.2)
    
    # Process and save historical data
    print(f"\n📊 Processing historical data...")
    print(f"   Total records: {len(all_historical)}")
    
    # Convert to display format
    historical_display = []
    for record in all_historical:
        try:
            # Parse datetime
            if 'fecha_hora' in record:
                dt_str = record['fecha_hora'][:19]  # Remove timezone
                dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
            else:
                continue
            
            historical_display.append({
                'datetime': dt.strftime('%Y-%m-%d %H:%M'),
                'hour': record.get('hra', dt.hour),
                'cmg_actual': record.get('cmg_usd_mwh_', 0),
                'node': record.get('barra_transf', 'unknown')
            })
        except Exception as e:
            continue
    
    # Remove duplicates
    seen = set()
    unique_historical = []
    for item in historical_display:
        key = (item['datetime'], item['node'])
        if key not in seen:
            seen.add(key)
            unique_historical.append(item)
    
    # Sort by datetime
    unique_historical.sort(key=lambda x: x['datetime'])
    
    # Keep last 24 hours
    cutoff = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
    filtered_historical = [h for h in unique_historical if h['datetime'] >= cutoff]
    
    print(f"   After filtering: {len(filtered_historical)} records")
    
    # Analyze coverage
    unique_hours = len(set(h['hour'] for h in filtered_historical))
    unique_nodes = len(set(h['node'] for h in filtered_historical))
    coverage = (unique_hours / 24) * 100
    
    print(f"   Coverage: {coverage:.1f}% ({unique_hours}/24 hours)")
    print(f"   Nodes: {unique_nodes}/6")
    
    # Save historical cache
    hist_cache = {
        'timestamp': now.isoformat(),
        'data': filtered_historical,
        'statistics': {
            'total_records': len(filtered_historical),
            'coverage_hours': unique_hours,
            'coverage_percentage': coverage,
            'oldest_record': filtered_historical[0]['datetime'] if filtered_historical else None,
            'newest_record': filtered_historical[-1]['datetime'] if filtered_historical else None
        }
    }
    
    cache_file = cache_dir / 'cmg_historical_latest.json'
    with open(cache_file, 'w') as f:
        json.dump(hist_cache, f, indent=2)
    
    print(f"   ✅ Saved to {cache_file}")
    
    # Step 2: Fetch Programmed Data (simplified)
    print(f"\n📦 FETCHING PROGRAMMED DATA")
    print("-" * 40)
    
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    url_prog = f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate"
    
    all_programmed = []
    
    print(f"Fetching programmed for {tomorrow}...")
    
    for page in range(1, 11):  # Just first 10 pages for programmed
        params = {
            'startDate': tomorrow,
            'endDate': tomorrow,
            'page': page,
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        records = fetch_page(url_prog, params, page)
        
        if records:
            print(f"   Page {page}: {len(records)} records")
            all_programmed.extend(records)
        else:
            break
        
        time.sleep(0.2)
    
    # Process programmed data
    if all_programmed:
        prog_display = []
        for record in all_programmed[:100]:  # Limit to first 100
            try:
                prog_display.append({
                    'datetime': f"{tomorrow} {record.get('hra', 0):02d}:00:00",
                    'hour': record.get('hra', 0),
                    'cmg_programmed': record.get('cmg_usd_mwh_', 0),
                    'node': 'CHILOE________110',  # Simplified
                    'pid_node': record.get('nmb_barra_info', ''),
                    'is_programmed': True
                })
            except:
                continue
        
        prog_cache = {
            'timestamp': now.isoformat(),
            'data': prog_display
        }
        
        prog_file = cache_dir / 'cmg_programmed_latest.json'
        with open(prog_file, 'w') as f:
            json.dump(prog_cache, f, indent=2)
        
        print(f"   ✅ Saved {len(prog_display)} programmed records")
    
    # Save metadata
    metadata = {
        'timestamp': now.isoformat(),
        'last_update': now.isoformat()
    }
    
    meta_file = cache_dir / 'metadata.json'
    with open(meta_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n" + "="*80)
    print("✅ MANUAL UPDATE COMPLETE!")
    print("="*80)
    print(f"\nCache files updated in: data/cache/")
    print(f"Now you can commit and push these files to update your dashboard")
    print(f"\nCommands to deploy:")
    print(f"  git add data/cache/")
    print(f"  git commit -m '🔄 Manual cache update - {now.strftime('%Y-%m-%d %H:%M')}'")
    print(f"  git push origin main")

if __name__ == "__main__":
    main()