#!/usr/bin/env python3
"""
Ultra-Optimized Update Script - EXACT NOTEBOOK APPROACH
Achieves 100% coverage in ~3-7 minutes using parallel fetching
"""

import sys
import os
from pathlib import Path
import time
import json
import requests
import concurrent.futures
from datetime import datetime, timedelta
from collections import defaultdict
from threading import Lock
import pytz

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# CMG Online nodes
CMG_NODES = ['CHILOE________220', 'CHILOE________110', 'QUELLON_______110', 
             'QUELLON_______013', 'CHONCHI_______110', 'DALCAHUE______023']

# CMG Programado (PID) nodes
PID_NODES = ['BA S/E CHILOE 220KV BP1', 'BA S/E CHILOE 110KV BP1',
             'BA S/E QUELLON 110KV BP1', 'BA S/E QUELLON 13KV BP1',
             'BA S/E CHONCHI 110KV BP1', 'BA S/E DALCAHUE 23KV BP1']

# Node mapping from PID to CMG format
NODE_MAP = {
    'BA S/E CHILOE 220KV BP1': 'CHILOE________220',
    'BA S/E CHILOE 110KV BP1': 'CHILOE________110',
    'BA S/E QUELLON 110KV BP1': 'QUELLON_______110',
    'BA S/E QUELLON 13KV BP1': 'QUELLON_______013',
    'BA S/E CHONCHI 110KV BP1': 'CHONCHI_______110',
    'BA S/E DALCAHUE 23KV BP1': 'DALCAHUE______023'
}

# Optimized page sequence (proven from notebook)
HIGH_VALUE_PAGES = [2, 6, 10, 11, 16, 18, 21, 23, 27, 29, 32, 35, 37]
MEDIUM_VALUE_PAGES = [3, 4, 7, 14, 19, 20, 24, 26, 28, 31, 33, 36]
LOW_VALUE_PAGES = [1, 5, 8, 9, 12, 13, 15, 17, 22, 25, 30, 34]

def get_optimized_page_sequence(max_pages=40):
    """Generate optimized page sequence"""
    sequence = []
    sequence.extend(HIGH_VALUE_PAGES)
    for p in MEDIUM_VALUE_PAGES:
        if p not in sequence:
            sequence.append(p)
    for p in LOW_VALUE_PAGES:
        if p not in sequence:
            sequence.append(p)
    # Add remaining pages
    for p in range(1, max_pages + 1):
        if p not in sequence:
            sequence.append(p)
    return sequence[:max_pages]

def fetch_page_ultra(url, params, page_num, max_retries=3):
    """Ultra-fast page fetcher with retry logic"""
    wait_time = 1
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                return (records, 'success') if records else (None, 'empty')
            elif response.status_code == 429:
                wait_time = min(wait_time * 2, 10)
                time.sleep(wait_time)
            else:
                return None, 'error'
                
        except Exception:
            time.sleep(wait_time)
    
    return None, 'error'

def fetch_batch_turbo(url, date_str, page_batch, node_field='barra_transf', 
                     target_nodes=None, records_per_page=4000, max_workers=5):
    """Turbo parallel fetcher - 5 concurrent workers"""
    if target_nodes is None:
        target_nodes = CMG_NODES
    
    results_lock = Lock()
    batch_results = {}
    
    def worker(page):
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': records_per_page,
            'user_key': SIP_API_KEY
        }
        
        records, status = fetch_page_ultra(url, params, page)
        
        if status == 'success' and records:
            page_data = defaultdict(set)
            locations_found = set()
            raw_records = []
            
            for record in records:
                node = record.get(node_field)
                if node in target_nodes:
                    raw_records.append(record)  # Store raw record
                    locations_found.add(node)
                    
                    # Extract hour
                    hour = None
                    if 'fecha_hora' in record:
                        try:
                            hour = int(record['fecha_hora'][11:13])
                        except:
                            pass
                    elif 'hra' in record:
                        hour = record['hra']
                    
                    if hour is not None:
                        page_data[node].add(hour)
            
            with results_lock:
                batch_results[page] = {
                    'status': 'success',
                    'records': len(records),
                    'locations': len(locations_found),
                    'data': dict(page_data),
                    'raw_records': raw_records  # Include raw records
                }
                
                if page_data:
                    unique_hours = len(set(h for hours in page_data.values() for h in hours))
                    print(f"    ✅ Page {page:2d}: {len(records)} records, {len(locations_found)} locations, {unique_hours} hours")
                
                # Check if this is the last page
                if len(records) < records_per_page:
                    print(f"    📍 Page {page} is LAST PAGE ({len(records)} < {records_per_page})")
        else:
            with results_lock:
                batch_results[page] = {'status': status, 'records': 0, 'locations': 0}
                if status == 'empty':
                    print(f"    ⚪ Page {page:2d}: Empty")
    
    # Execute parallel fetching
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, page) for page in page_batch]
        concurrent.futures.wait(futures)
    
    return batch_results

def fetch_ultra_optimized(url, date_str, target_coverage=1.0, 
                         node_field='barra_transf', target_nodes=None,
                         records_per_page=4000, use_parallel=True, max_workers=5):
    """
    Ultra-optimized fetching matching the notebook approach.
    Returns tuple: (raw_records, location_coverage_data)
    """
    if target_nodes is None:
        target_nodes = CMG_NODES
    
    print(f"\n{'='*80}")
    print(f"🚀 ULTRA-OPTIMIZED FETCH for {date_str}")
    print(f"📊 Records per page: {records_per_page}")
    print(f"🎯 Target coverage: {target_coverage*100:.0f}%")
    print(f"⚡ Parallel workers: {max_workers if use_parallel else 1}")
    print(f"⏱️ Expected time: ~3-7 minutes for 100% coverage")
    print(f"{'='*80}")
    
    # Storage
    location_data = defaultdict(lambda: {'hours': set(), 'pages': set()})
    all_raw_records = []
    pages_fetched = []
    total_records = 0
    start_time = time.time()
    
    # Get optimized page sequence
    page_sequence = get_optimized_page_sequence(max_pages=40)
    print(f"\n📋 Using optimized sequence: {page_sequence[:13]}...")
    
    # Process in batches of 10 pages
    batch_size = 10
    last_page_found = False
    
    for i in range(0, len(page_sequence), batch_size):
        if last_page_found:
            break
            
        batch = page_sequence[i:i+batch_size]
        
        # Check current coverage
        current_coverage = calculate_coverage(location_data, target_nodes)
        
        if current_coverage >= target_coverage:
            print(f"\n🎉 Target coverage {target_coverage*100:.0f}% achieved!")
            break
        
        batch_num = (i // batch_size) + 1
        print(f"\n📦 Batch {batch_num}: Pages {batch}")
        
        # Parallel fetching
        batch_results = fetch_batch_turbo(
            url, date_str, batch, node_field, target_nodes, 
            records_per_page, max_workers
        )
        
        # Process results
        for page in batch:
            if page not in batch_results:
                continue
                
            result = batch_results[page]
            if result['status'] == 'success':
                pages_fetched.append(page)
                total_records += result.get('records', 0)
                
                # Store raw records
                if 'raw_records' in result:
                    all_raw_records.extend(result['raw_records'])
                
                # Update location data
                for node, hours in result.get('data', {}).items():
                    location_data[node]['hours'].update(hours)
                    location_data[node]['pages'].add(page)
                
                # Check if last page
                if result['records'] < records_per_page:
                    print(f"\n✅ Found last page at page {page} - stopping")
                    last_page_found = True
                    break
        
        # Progress update
        elapsed = time.time() - start_time
        coverage = calculate_coverage(location_data, target_nodes)
        print(f"\n⏱️ Progress: {len(pages_fetched)} pages, {total_records} records in {elapsed:.1f}s")
        print(f"📊 Coverage: {coverage*100:.1f}%")
        
        # Check if all locations have complete data
        complete_count = sum(1 for data in location_data.values() if len(data['hours']) == 24)
        if complete_count == len(target_nodes):
            print(f"\n✅ ALL {complete_count} LOCATIONS HAVE COMPLETE 24-HOUR DATA!")
            break
        
        time.sleep(0.3)  # Small delay between batches
    
    # Final summary
    elapsed = time.time() - start_time
    final_coverage = calculate_coverage(location_data, target_nodes)
    
    print(f"\n{'='*80}")
    print(f"✅ FETCH COMPLETE")
    print(f"⏱️ Time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"📄 Pages fetched: {len(pages_fetched)}")
    print(f"📊 Total records: {total_records}")
    print(f"🎯 Final coverage: {final_coverage*100:.1f}%")
    
    # Calculate speedup
    baseline_minutes = 34.5
    speedup = baseline_minutes / (elapsed/60) if elapsed > 0 else 0
    print(f"🚀 Speed improvement: {speedup:.1f}x faster than baseline!")
    print(f"{'='*80}")
    
    # Coverage report
    print(f"\n📊 COVERAGE BY LOCATION:")
    for node in sorted(target_nodes):
        if node in location_data:
            hours = sorted(location_data[node]['hours'])
            coverage = len(hours) / 24 * 100
            status = "✅" if coverage == 100 else "⚠️" if coverage >= 75 else "❌"
            print(f"{status} {node:30}: {len(hours)}/24 ({coverage:.0f}%)")
        else:
            print(f"❌ {node:30}: NO DATA")
    
    return all_raw_records, location_data

def calculate_coverage(location_data, target_nodes):
    """Calculate coverage percentage"""
    if not location_data:
        return 0.0
    total_hours = sum(len(data['hours']) for data in location_data.values())
    max_hours = len(target_nodes) * 24
    return total_hours / max_hours if max_hours > 0 else 0.0

def parse_cmg_record(record):
    """Parse CMG Online record to display format"""
    try:
        dt_str = record.get('fecha_hora', '')
        if not dt_str:
            return None
        
        # Remove timezone if present
        if '+' in dt_str:
            dt_str = dt_str.split('+')[0]
        elif '-' in dt_str[-6:] and 'T' in dt_str:
            dt_str = dt_str[:-6]
        
        # Parse datetime
        if 'T' in dt_str:
            dt = datetime.strptime(dt_str[:19], '%Y-%m-%dT%H:%M:%S')
        else:
            dt = datetime.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S')
        
        return {
            'datetime': dt.strftime('%Y-%m-%d %H:%M'),
            'hour': record.get('hra', dt.hour),
            'cmg_actual': float(record.get('cmg_usd_mwh_', 0)),
            'node': record.get('barra_transf', 'unknown')
        }
    except Exception as e:
        return None

def parse_programmed_record(record, date_str):
    """Parse CMG Programado record to display format"""
    try:
        hour = record.get('hra', 0)
        pid_node = record.get('nmb_barra_info', '')
        
        # Map PID node to CMG node
        node = NODE_MAP.get(pid_node, 'CHILOE________110')
        
        return {
            'datetime': f"{date_str} {hour:02d}:00",
            'hour': hour,
            'cmg_programmed': float(record.get('cmg_usd_mwh_', 0)),
            'node': node,
            'pid_node': pid_node,
            'is_programmed': True
        }
    except:
        return None

def main():
    """Main update function using ultra-optimization"""
    print("\n" + "="*80)
    print("🚀 ULTRA-OPTIMIZED CACHE UPDATE (Fixed Version)")
    print("="*80)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    start_time = time.time()
    
    print(f"📅 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} Santiago")
    print(f"🎯 Goal: 100% coverage in <7 minutes")
    
    # Create cache directory
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # URLs
    url_online = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    url_pid = f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate"
    
    # ========== FETCH HISTORICAL DATA ==========
    all_historical = []
    
    # Fetch yesterday (complete 24 hours)
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"\n📅 Fetching yesterday: {yesterday}")
    
    yesterday_records, _ = fetch_ultra_optimized(
        url_online, yesterday, 
        target_coverage=1.0,  # 100% coverage
        node_field='barra_transf',
        target_nodes=CMG_NODES,
        records_per_page=4000,
        use_parallel=True,
        max_workers=5
    )
    
    # Process yesterday's records
    for record in yesterday_records:
        parsed = parse_cmg_record(record)
        if parsed:
            all_historical.append(parsed)
    
    # Fetch today (up to current hour)
    today = now.strftime('%Y-%m-%d')
    print(f"\n📅 Fetching today: {today} (up to hour {now.hour})")
    
    today_records, _ = fetch_ultra_optimized(
        url_online, today,
        target_coverage=0.9,  # 90% is enough for partial day
        node_field='barra_transf',
        target_nodes=CMG_NODES,
        records_per_page=4000,
        use_parallel=True,
        max_workers=5
    )
    
    # Process today's records (filter to current hour)
    for record in today_records:
        parsed = parse_cmg_record(record)
        if parsed and parsed['hour'] <= now.hour:
            all_historical.append(parsed)
    
    # Process historical data
    print(f"\n📊 Processing historical data...")
    print(f"   Total parsed records: {len(all_historical)}")
    
    # Remove duplicates
    seen = set()
    unique_historical = []
    for item in all_historical:
        key = (item['datetime'], item['node'])
        if key not in seen:
            seen.add(key)
            unique_historical.append(item)
    
    print(f"   After removing duplicates: {len(unique_historical)}")
    
    # Sort by datetime
    unique_historical.sort(key=lambda x: x['datetime'])
    
    # Keep a rolling 24-hour window
    # We want data from yesterday at current hour to now
    cutoff_str = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:00')
    filtered_historical = [h for h in unique_historical if h['datetime'] >= cutoff_str]
    
    print(f"   After 24-hour filter: {len(filtered_historical)}")
    
    # Calculate coverage
    node_hours = defaultdict(set)
    for record in filtered_historical:
        node_hours[record['node']].add(record['hour'])
    
    total_coverage = sum(len(hours) for hours in node_hours.values())
    coverage_pct = (total_coverage / (6 * 24)) * 100 if filtered_historical else 0
    
    print(f"   📊 Final coverage: {coverage_pct:.1f}%")
    print(f"   📍 Nodes with data: {len(node_hours)}/6")
    
    if coverage_pct > 0:
        # Show coverage by node
        for node in CMG_NODES:
            hours = node_hours.get(node, set())
            print(f"      {node}: {len(hours)}/24 hours")
    
    # Save historical cache
    hist_cache = {
        'timestamp': now.isoformat(),
        'data': filtered_historical,
        'statistics': {
            'total_records': len(filtered_historical),
            'coverage_hours': len(set(r['hour'] for r in filtered_historical)) if filtered_historical else 0,
            'coverage_percentage': coverage_pct,
            'oldest_record': filtered_historical[0]['datetime'] if filtered_historical else None,
            'newest_record': filtered_historical[-1]['datetime'] if filtered_historical else None,
            'nodes_with_data': list(node_hours.keys())
        }
    }
    
    with open(cache_dir / 'cmg_historical_latest.json', 'w') as f:
        json.dump(hist_cache, f, indent=2)
    print(f"   ✅ Saved historical cache")
    
    # ========== FETCH PROGRAMMED DATA ==========
    print(f"\n📅 Fetching programmed data (future hours)...")
    
    all_programmed = []
    
    # First, try to get remaining hours of today from programmed
    print(f"   Checking for today's future hours (after hour {now.hour})...")
    today_prog_records, _ = fetch_ultra_optimized(
        url_pid, today,
        target_coverage=0.5,  # Just need some data
        node_field='nmb_barra_info',
        target_nodes=PID_NODES,
        records_per_page=1000,
        use_parallel=True,
        max_workers=3
    )
    
    # Process today's future hours
    today_future_count = 0
    for record in today_prog_records:
        hour = record.get('hra', 0)
        if hour > now.hour:  # Only future hours
            parsed = parse_programmed_record(record, today)
            if parsed:
                all_programmed.append(parsed)
                today_future_count += 1
    
    if today_future_count > 0:
        print(f"   ✅ Found {today_future_count} records for today's future hours")
    
    # Fetch tomorrow's programmed
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"   Fetching tomorrow's programmed: {tomorrow}")
    
    tomorrow_records, _ = fetch_ultra_optimized(
        url_pid, tomorrow,
        target_coverage=0.8,  # 80% coverage for programmed
        node_field='nmb_barra_info',
        target_nodes=PID_NODES,
        records_per_page=1000,
        use_parallel=True,
        max_workers=3
    )
    
    # Process tomorrow's records
    for record in tomorrow_records[:500]:  # Limit to 500 records
        parsed = parse_programmed_record(record, tomorrow)
        if parsed:
            all_programmed.append(parsed)
    
    print(f"   ✅ Total programmed records: {len(all_programmed)}")
    
    # Optionally fetch day after tomorrow if needed
    if len(all_programmed) < 50:  # If we don't have enough programmed data
        day_after = (now + timedelta(days=2)).strftime('%Y-%m-%d')
        print(f"   Fetching day after tomorrow: {day_after}")
        
        day_after_records, _ = fetch_ultra_optimized(
            url_pid, day_after,
            target_coverage=0.5,
            node_field='nmb_barra_info',
            target_nodes=PID_NODES,
            records_per_page=1000,
            use_parallel=False,
            max_workers=1
        )
        
        for record in day_after_records[:200]:
            parsed = parse_programmed_record(record, day_after)
            if parsed:
                all_programmed.append(parsed)
    
    # Save programmed cache
    if all_programmed:
        # Sort by datetime and limit
        all_programmed.sort(key=lambda x: x['datetime'])
        limited_programmed = all_programmed[:200]  # Limit to 200 records
        
        prog_cache = {
            'timestamp': now.isoformat(),
            'data': limited_programmed,
            'statistics': {
                'total_records': len(limited_programmed),
                'hours_ahead': len(set(r['hour'] for r in limited_programmed))
            }
        }
        
        with open(cache_dir / 'cmg_programmed_latest.json', 'w') as f:
            json.dump(prog_cache, f, indent=2)
        print(f"   ✅ Saved programmed cache ({len(limited_programmed)} records)")
    
    # Save metadata
    metadata = {
        'timestamp': now.isoformat(),
        'last_update': now.isoformat(),
        'update_duration_seconds': time.time() - start_time,
        'historical_coverage': coverage_pct,
        'nodes_with_data': list(node_hours.keys())
    }
    
    with open(cache_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Final summary
    elapsed = time.time() - start_time
    print(f"\n" + "="*80)
    print(f"✅ ULTRA-UPDATE COMPLETE")
    print(f"⏱️ Total time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"📊 Historical coverage: {coverage_pct:.1f}%")
    print(f"🚀 Speed: {(34.5*60/elapsed):.1f}x faster than baseline")
    print("="*80)
    
    if coverage_pct < 100:
        print(f"\n⚠️ Coverage is {coverage_pct:.1f}%, not 100%")
        print("Missing data for:")
        for node in CMG_NODES:
            hours = node_hours.get(node, set())
            if len(hours) < 24:
                missing = set(range(24)) - hours
                missing_list = sorted(list(missing))[:10]
                print(f"   {node}: Missing hours {missing_list}...")
    
    print(f"\n📦 Deploy with:")
    print(f"   git add data/cache/")
    print(f"   git commit -m '🔄 Ultra cache update - {coverage_pct:.0f}% coverage'")
    print(f"   git push origin main")
    
    return coverage_pct >= 90  # Success if >= 90% coverage

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)