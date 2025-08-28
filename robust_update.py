#!/usr/bin/env python3
"""
Robust Cache Update Script - Handles timeouts and ensures data integrity
Based on the proven optimized_fetch_final.ipynb approach
"""

import requests
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import pytz
import sys

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Priority pages from your working notebook
PRIORITY_PAGES = [
    2, 6, 10, 11, 16, 18, 21, 23, 27, 29, 32, 35, 37,  # High value
    3, 4, 7, 14, 19, 20, 24, 26, 28, 31, 33, 36,       # Medium value  
    1, 5, 8, 9, 12, 13, 15, 17, 22, 25, 30, 34, 38     # Low value + 38
]

# All 6 nodes we need
CMG_NODES = [
    'CHILOE________220', 'CHILOE________110', 
    'QUELLON_______110', 'QUELLON_______013',
    'CHONCHI_______110', 'DALCAHUE______023'
]

# Programmed nodes mapping
PID_NODE_MAPPING = {
    'BA S/E CHILOE 220KV BP1': 'CHILOE________220',
    'BA S/E CHILOE 110KV BP1': 'CHILOE________110',
    'BA S/E QUELLON 110KV BP1': 'QUELLON_______110',
    'BA S/E QUELLON 13KV BP1': 'QUELLON_______013',
    'BA S/E CHONCHI 110KV BP1': 'CHONCHI_______110',
    'BA S/E DALCAHUE 23KV BP1': 'DALCAHUE______023'
}

def fetch_page_with_retry(url, params, page_num, max_retries=3):
    """Fetch a page with retry logic for timeouts"""
    for attempt in range(max_retries):
        try:
            # Increase timeout for retries
            timeout = 30 + (attempt * 10)
            response = requests.get(url, params=params, timeout=timeout)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                return records if records else None
            elif response.status_code == 429:  # Rate limit
                wait_time = min(2 ** attempt, 30)
                print(f"   Page {page_num}: Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                return None
                
        except requests.exceptions.Timeout:
            print(f"   Page {page_num}: Timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
        except Exception as e:
            print(f"   Page {page_num}: Error - {str(e)[:50]}")
            return None
    
    return None

def parse_cmg_record(record):
    """Parse a CMG record to our format"""
    try:
        # Get datetime - handle different formats
        dt_str = None
        if 'fecha_hora' in record:
            dt_str = record['fecha_hora']
        
        if not dt_str:
            return None
        
        # Parse datetime - handle timezone
        if 'T' in dt_str:
            # Remove timezone info if present
            if '+' in dt_str:
                dt_str = dt_str.split('+')[0]
            elif '-' in dt_str[-6:]:
                dt_str = dt_str[:-6]
            
            # Parse the datetime
            if len(dt_str) == 19:  # YYYY-MM-DDTHH:MM:SS
                dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
            else:
                dt = datetime.strptime(dt_str[:19], '%Y-%m-%dT%H:%M:%S')
        else:
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        
        return {
            'datetime': dt.strftime('%Y-%m-%d %H:%M'),
            'hour': record.get('hra', dt.hour),
            'cmg_actual': float(record.get('cmg_usd_mwh_', 0)),
            'node': record.get('barra_transf', 'unknown')
        }
    except Exception as e:
        return None

def parse_programmed_record(record, date_str):
    """Parse a programmed CMG record"""
    try:
        hour = record.get('hra', 0)
        pid_node = record.get('nmb_barra_info', '')
        
        # Map PID node to CMG node
        cmg_node = PID_NODE_MAPPING.get(pid_node, 'CHILOE________110')
        
        return {
            'datetime': f"{date_str} {hour:02d}:00:00",
            'hour': hour,
            'cmg_programmed': float(record.get('cmg_usd_mwh_', 0)),
            'node': cmg_node,
            'pid_node': pid_node,
            'is_programmed': True
        }
    except Exception:
        return None

def main():
    print("\n" + "="*80)
    print("🚀 ROBUST CACHE UPDATE")
    print("="*80)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    start_time = time.time()
    
    print(f"📅 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} Santiago")
    print(f"📊 Using 4000 records/page (proven optimization)")
    print(f"🎯 Target: 100% coverage for all 6 nodes")
    print(f"⏱️ Expected time: 3-5 minutes")
    
    # Create cache directory
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # ========== STEP 1: FETCH HISTORICAL DATA ==========
    print(f"\n{'='*80}")
    print("📦 STEP 1: FETCHING HISTORICAL DATA (Last 24 hours)")
    print("="*80)
    
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    today = now.strftime('%Y-%m-%d')
    
    all_historical = []
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    # Fetch yesterday (complete day)
    print(f"\n📅 Fetching {yesterday} (complete 24 hours)...")
    
    location_data = defaultdict(set)  # Track hours per node
    pages_fetched = 0
    total_records = 0
    empty_count = 0
    
    for page in PRIORITY_PAGES[:40]:  # Max 40 pages
        params = {
            'startDate': yesterday,
            'endDate': yesterday,
            'page': page,
            'limit': 4000,
            'user_key': SIP_API_KEY
        }
        
        records = fetch_page_with_retry(url, params, page)
        
        if records:
            pages_fetched += 1
            total_records += len(records)
            
            # Process records
            node_count = 0
            for record in records:
                if record.get('barra_transf') in CMG_NODES:
                    parsed = parse_cmg_record(record)
                    if parsed:
                        all_historical.append(parsed)
                        location_data[parsed['node']].add(parsed['hour'])
                        node_count += 1
            
            # Check if we got less than 4000 records (last page)
            if len(records) < 4000:
                print(f"   Page {page:2d}: {len(records)} records (LAST PAGE - less than 4000)")
                print(f"   ✅ Found end of data")
                break
            else:
                print(f"   Page {page:2d}: {len(records)} records, {node_count} for our nodes")
            
            empty_count = 0
        else:
            print(f"   Page {page:2d}: Empty/Failed")
            empty_count += 1
            if empty_count >= 3:
                print("   ⚠️ Stopping - 3 consecutive empty pages")
                break
        
        # Progress update
        if pages_fetched % 10 == 0:
            coverage = calculate_coverage(location_data)
            print(f"   📊 Progress: {pages_fetched} pages, {len(all_historical)} records, {coverage:.1f}% coverage")
            
            # Check if we have complete data
            if all(len(hours) == 24 for hours in location_data.values()) and len(location_data) == 6:
                print(f"   ✅ Complete data for all 6 nodes!")
                break
        
        # Small delay to avoid rate limiting
        time.sleep(0.3)
    
    print(f"\n📊 Yesterday's summary:")
    print(f"   Pages fetched: {pages_fetched}")
    print(f"   Total records: {total_records}")
    print(f"   Our nodes records: {len(all_historical)}")
    print(f"   Coverage by node:")
    for node in CMG_NODES:
        hours = location_data.get(node, set())
        print(f"      {node}: {len(hours)}/24 hours")
    
    # Fetch today (up to current hour)
    print(f"\n📅 Fetching {today} (up to hour {now.hour})...")
    
    today_location_data = defaultdict(set)
    
    for page in PRIORITY_PAGES[:30]:  # Less pages for partial day
        params = {
            'startDate': today,
            'endDate': today,
            'page': page,
            'limit': 4000,
            'user_key': SIP_API_KEY
        }
        
        records = fetch_page_with_retry(url, params, page)
        
        if records:
            node_count = 0
            hour_count = 0
            
            for record in records:
                if record.get('barra_transf') in CMG_NODES:
                    parsed = parse_cmg_record(record)
                    if parsed and parsed['hour'] <= now.hour:
                        all_historical.append(parsed)
                        today_location_data[parsed['node']].add(parsed['hour'])
                        node_count += 1
                        hour_count += 1
            
            if node_count > 0:
                print(f"   Page {page:2d}: {node_count} records for hours 0-{now.hour}")
            
            # Check if last page
            if len(records) < 4000:
                print(f"   ✅ Found end of today's data")
                break
        
        time.sleep(0.3)
    
    print(f"\n📊 Today's summary:")
    for node in CMG_NODES:
        hours = today_location_data.get(node, set())
        if hours:
            print(f"   {node}: {len(hours)} hours")
    
    # Process and save historical data
    print(f"\n📊 Processing historical data...")
    print(f"   Total records before dedup: {len(all_historical)}")
    
    # Remove duplicates
    seen = set()
    unique_historical = []
    for item in all_historical:
        key = (item['datetime'], item['node'])
        if key not in seen:
            seen.add(key)
            unique_historical.append(item)
    
    # Sort by datetime
    unique_historical.sort(key=lambda x: x['datetime'])
    
    # Filter to last 24 hours
    cutoff = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
    filtered_historical = [h for h in unique_historical if h['datetime'] >= cutoff]
    
    print(f"   After filtering to 24h window: {len(filtered_historical)} records")
    
    # Calculate final coverage
    final_hours = defaultdict(set)
    for record in filtered_historical:
        final_hours[record['node']].add(record['hour'])
    
    total_coverage = sum(len(hours) for hours in final_hours.values())
    max_coverage = 6 * 24  # 6 nodes * 24 hours
    coverage_pct = (total_coverage / max_coverage) * 100
    
    print(f"   📊 Final coverage: {coverage_pct:.1f}%")
    print(f"   📍 Nodes with data: {len(final_hours)}/6")
    
    # Save historical cache
    hist_cache = {
        'timestamp': now.isoformat(),
        'data': filtered_historical,
        'statistics': {
            'total_records': len(filtered_historical),
            'coverage_hours': len(set(r['hour'] for r in filtered_historical)),
            'coverage_percentage': coverage_pct,
            'oldest_record': filtered_historical[0]['datetime'] if filtered_historical else None,
            'newest_record': filtered_historical[-1]['datetime'] if filtered_historical else None
        }
    }
    
    with open(cache_dir / 'cmg_historical_latest.json', 'w') as f:
        json.dump(hist_cache, f, indent=2)
    
    print(f"   ✅ Saved historical cache")
    
    # ========== STEP 2: FETCH PROGRAMMED DATA ==========
    print(f"\n{'='*80}")
    print("📦 STEP 2: FETCHING PROGRAMMED DATA")
    print("="*80)
    
    all_programmed = []
    url_prog = f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate"
    
    # Try to fetch for next 2 days
    for days_ahead in [0, 1, 2]:  # Today, tomorrow, day after
        target_date = (now + timedelta(days=days_ahead))
        date_str = target_date.strftime('%Y-%m-%d')
        
        print(f"\n📅 Fetching programmed for {date_str}...")
        
        prog_found = False
        for page in range(1, 21):  # Try up to 20 pages
            params = {
                'startDate': date_str,
                'endDate': date_str,
                'page': page,
                'limit': 1000,
                'user_key': SIP_API_KEY
            }
            
            records = fetch_page_with_retry(url_prog, params, page)
            
            if records:
                prog_found = True
                valid_records = 0
                
                for record in records:
                    parsed = parse_programmed_record(record, date_str)
                    if parsed:
                        # Only include future hours
                        record_dt = datetime.strptime(parsed['datetime'], '%Y-%m-%d %H:%M:%S')
                        if record_dt > now:
                            all_programmed.append(parsed)
                            valid_records += 1
                
                print(f"   Page {page:2d}: {len(records)} records, {valid_records} future hours")
                
                # Stop if we found less than limit (last page)
                if len(records) < 1000:
                    break
            else:
                if prog_found:
                    break  # We had data but now empty, so we're done
                elif page > 5:
                    print(f"   No programmed data available for {date_str}")
                    break
            
            time.sleep(0.3)
    
    # Save programmed data
    if all_programmed:
        # Remove duplicates
        seen_prog = set()
        unique_programmed = []
        for item in all_programmed:
            key = (item['datetime'], item['node'])
            if key not in seen_prog:
                seen_prog.add(key)
                unique_programmed.append(item)
        
        unique_programmed.sort(key=lambda x: x['datetime'])
        
        prog_cache = {
            'timestamp': now.isoformat(),
            'data': unique_programmed,
            'statistics': {
                'total_records': len(unique_programmed),
                'hours_ahead': len(set(r['hour'] for r in unique_programmed))
            }
        }
        
        with open(cache_dir / 'cmg_programmed_latest.json', 'w') as f:
            json.dump(prog_cache, f, indent=2)
        
        print(f"\n✅ Saved {len(unique_programmed)} programmed records")
    else:
        print(f"\n⚠️ No programmed data available")
    
    # Save metadata
    metadata = {
        'timestamp': now.isoformat(),
        'last_update': now.isoformat(),
        'update_duration_seconds': time.time() - start_time,
        'historical_records': len(filtered_historical),
        'programmed_records': len(all_programmed) if all_programmed else 0
    }
    
    with open(cache_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    elapsed = time.time() - start_time
    print(f"\n" + "="*80)
    print(f"✅ ROBUST UPDATE COMPLETE in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print("="*80)
    
    print(f"\n📊 Final Summary:")
    print(f"   Historical records: {len(filtered_historical)}")
    print(f"   Programmed records: {len(all_programmed) if all_programmed else 0}")
    print(f"   Coverage: {coverage_pct:.1f}%")
    print(f"   Time taken: {elapsed/60:.1f} minutes")
    
    if elapsed > 300:  # More than 5 minutes
        print(f"\n⚠️ Update took longer than expected")
    
    print(f"\n📦 To deploy:")
    print(f"   git add data/cache/")
    print(f"   git commit -m '🔄 Cache update - {now.strftime('%Y-%m-%d %H:%M')}'")
    print(f"   git push origin main")

def calculate_coverage(location_data):
    """Calculate coverage percentage"""
    if not location_data:
        return 0.0
    total_hours = sum(len(hours) for hours in location_data.values())
    max_hours = 6 * 24  # 6 nodes * 24 hours
    return (total_hours / max_hours) * 100

if __name__ == "__main__":
    main()