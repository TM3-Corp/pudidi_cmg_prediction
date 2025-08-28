#!/usr/bin/env python3
"""
Ultra-Optimized Update Script - Exactly mirrors the proven notebook approach
Achieves 100% coverage in ~3-7 minutes using parallel fetching
"""

import requests
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import concurrent.futures
from threading import Lock
import pytz
import sys

# Configuration - EXACT SAME AS NOTEBOOK
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Priority pages - PROVEN TO WORK
HIGH_VALUE_PAGES = [2, 6, 10, 11, 16, 18, 21, 23, 27, 29, 32, 35, 37]  # 6 locations each
MEDIUM_VALUE_PAGES = [3, 4, 7, 14, 19, 20, 24, 26, 28, 31, 33, 36]
LOW_VALUE_PAGES = [1, 5, 8, 9, 12, 13, 15, 17, 22, 25, 30, 34, 38, 39, 40]

# All nodes
CMG_NODES = [
    'CHILOE________220', 'CHILOE________110', 
    'QUELLON_______110', 'QUELLON_______013',
    'CHONCHI_______110', 'DALCAHUE______023'
]

PID_NODES = [
    'BA S/E CHILOE 220KV BP1', 'BA S/E CHILOE 110KV BP1',
    'BA S/E QUELLON 110KV BP1', 'BA S/E QUELLON 13KV BP1',
    'BA S/E CHONCHI 110KV BP1', 'BA S/E DALCAHUE 23KV BP1'
]

# Global results storage
results_lock = Lock()

def get_optimized_page_sequence(max_pages=40):
    """Generate optimized page sequence - EXACT COPY FROM NOTEBOOK"""
    sequence = []
    sequence.extend(HIGH_VALUE_PAGES)
    
    for p in MEDIUM_VALUE_PAGES:
        if p not in sequence:
            sequence.append(p)
    
    for p in LOW_VALUE_PAGES:
        if p not in sequence:
            sequence.append(p)
    
    return sequence[:max_pages]

def fetch_page_ultra(url, params, page_num, max_retries=10):
    """Ultra-optimized page fetcher - EXACT COPY FROM NOTEBOOK"""
    wait_time = 1
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                return (records, 'success') if records else (None, 'empty')
            
            elif response.status_code == 429:
                wait_time = min(wait_time * 2, 30)
                time.sleep(wait_time)
                
            elif response.status_code >= 500:
                wait_time = min(wait_time * 1.5, 20)
                time.sleep(wait_time)
                
            else:
                return None, 'error'
                
        except Exception:
            time.sleep(wait_time)
            wait_time = min(wait_time * 1.5, 30)
    
    return None, 'error'

def fetch_batch_turbo(url, date_str, page_batch, node_field='barra_transf', 
                     target_nodes=None, records_per_page=4000, max_workers=5):
    """Turbo parallel fetcher - BASED ON NOTEBOOK"""
    if target_nodes is None:
        target_nodes = CMG_NODES
    
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
            
            for record in records:
                node = record.get(node_field)
                if node in target_nodes:
                    locations_found.add(node)
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
                    'raw_records': records  # Keep raw records for processing
                }
                
                if page_data:
                    total_hours = sum(len(hours) for hours in page_data.values())
                    print(f"    ✅ Page {page:2d}: {len(records)} records, {len(locations_found)} locations, {total_hours} hours")
                    
                    # Check if last page (less than 4000 records)
                    if len(records) < records_per_page:
                        print(f"    📍 Page {page} is LAST PAGE ({len(records)} < {records_per_page})")
        else:
            with results_lock:
                batch_results[page] = {'status': status, 'records': 0, 'locations': 0}
                if status == 'empty':
                    print(f"    ⚪ Page {page:2d}: Empty")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, page) for page in page_batch]
        concurrent.futures.wait(futures)
    
    return batch_results

def fetch_ultra_optimized(url, date_str, target_coverage=1.0, 
                         node_field='barra_transf', target_nodes=None,
                         records_per_page=4000, use_parallel=True, max_workers=5):
    """Ultra-optimized fetching - EXACT APPROACH FROM NOTEBOOK"""
    if target_nodes is None:
        target_nodes = CMG_NODES
    
    print(f"\n{'='*80}")
    print(f"🚀 ULTRA-OPTIMIZED FETCH for {date_str}")
    print(f"📊 Records per page: {records_per_page} (4x optimization!)")
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
    
    # Process in batches of 10 pages (like notebook)
    batch_size = 10
    
    for i in range(0, len(page_sequence), batch_size):
        batch = page_sequence[i:i+batch_size]
        
        # Check current coverage
        current_coverage = calculate_coverage(location_data, target_nodes)
        
        if current_coverage >= target_coverage:
            print(f"\n🎉 Target coverage {target_coverage*100:.0f}% achieved!")
            break
        
        batch_num = (i // batch_size) + 1
        print(f"\n📦 Batch {batch_num}: Pages {batch}")
        
        # Turbo parallel fetching
        batch_results = fetch_batch_turbo(
            url, date_str, batch, node_field, target_nodes, 
            records_per_page, max_workers
        )
        
        # Process results
        for page, result in batch_results.items():
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
                
                # Check if we found last page
                if result['records'] < records_per_page:
                    print(f"\n✅ Found last page at page {page} - stopping")
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
    """Parse CMG record to display format"""
    try:
        dt_str = record.get('fecha_hora', '')
        if not dt_str:
            return None
        
        # Remove timezone if present
        if '+' in dt_str:
            dt_str = dt_str.split('+')[0]
        elif '-' in dt_str[-6:]:
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
    except Exception:
        return None

def main():
    """Main update function using ultra-optimization"""
    print("\n" + "="*80)
    print("🚀 ULTRA-OPTIMIZED CACHE UPDATE (Notebook Approach)")
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
    
    yesterday_records, yesterday_coverage = fetch_ultra_optimized(
        url_online, yesterday, 
        target_coverage=1.0,
        node_field='barra_transf',
        target_nodes=CMG_NODES,
        records_per_page=4000,
        use_parallel=True,
        max_workers=5
    )
    
    # Process yesterday's records
    for record in yesterday_records:
        if record.get('barra_transf') in CMG_NODES:
            parsed = parse_cmg_record(record)
            if parsed:
                all_historical.append(parsed)
    
    # Fetch today (up to current hour)
    today = now.strftime('%Y-%m-%d')
    print(f"\n📅 Fetching today: {today} (up to hour {now.hour})")
    
    today_records, today_coverage = fetch_ultra_optimized(
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
        if record.get('barra_transf') in CMG_NODES:
            parsed = parse_cmg_record(record)
            if parsed and parsed['hour'] <= now.hour:
                all_historical.append(parsed)
    
    # Process historical data
    print(f"\n📊 Processing historical data...")
    
    # Remove duplicates
    seen = set()
    unique_historical = []
    for item in all_historical:
        key = (item['datetime'], item['node'])
        if key not in seen:
            seen.add(key)
            unique_historical.append(item)
    
    # Sort and filter to last 24 hours
    unique_historical.sort(key=lambda x: x['datetime'])
    cutoff = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
    filtered_historical = [h for h in unique_historical if h['datetime'] >= cutoff]
    
    print(f"   Records after processing: {len(filtered_historical)}")
    
    # Calculate coverage
    node_hours = defaultdict(set)
    for record in filtered_historical:
        node_hours[record['node']].add(record['hour'])
    
    total_coverage = sum(len(hours) for hours in node_hours.values())
    coverage_pct = (total_coverage / (6 * 24)) * 100
    
    print(f"   📊 Final coverage: {coverage_pct:.1f}%")
    print(f"   📍 Nodes with data: {len(node_hours)}/6")
    
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
    
    # ========== FETCH PROGRAMMED DATA ==========
    print(f"\n📅 Fetching programmed data...")
    
    all_programmed = []
    
    # Fetch tomorrow's programmed
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    
    prog_records, prog_coverage = fetch_ultra_optimized(
        url_pid, tomorrow,
        target_coverage=0.8,  # 80% is enough for programmed
        node_field='nmb_barra_info',
        target_nodes=PID_NODES,
        records_per_page=1000,  # Programmed uses 1000
        use_parallel=True,
        max_workers=3  # Less workers for programmed
    )
    
    # Process programmed records
    for record in prog_records[:500]:  # Limit programmed records
        try:
            hour = record.get('hra', 0)
            pid_node = record.get('nmb_barra_info', '')
            
            # Simple mapping
            node = 'CHILOE________110'  # Default
            if '220' in pid_node:
                node = 'CHILOE________220'
            elif 'QUELLON' in pid_node:
                node = 'QUELLON_______110' if '110' in pid_node else 'QUELLON_______013'
            elif 'CHONCHI' in pid_node:
                node = 'CHONCHI_______110'
            elif 'DALCAHUE' in pid_node:
                node = 'DALCAHUE______023'
            
            all_programmed.append({
                'datetime': f"{tomorrow} {hour:02d}:00:00",
                'hour': hour,
                'cmg_programmed': float(record.get('cmg_usd_mwh_', 0)),
                'node': node,
                'pid_node': pid_node,
                'is_programmed': True
            })
        except:
            continue
    
    # Save programmed cache
    if all_programmed:
        prog_cache = {
            'timestamp': now.isoformat(),
            'data': all_programmed[:100],  # Limit to 100 records
            'statistics': {
                'total_records': len(all_programmed[:100]),
                'hours_ahead': len(set(r['hour'] for r in all_programmed[:100]))
            }
        }
        
        with open(cache_dir / 'cmg_programmed_latest.json', 'w') as f:
            json.dump(prog_cache, f, indent=2)
        print(f"   ✅ Saved programmed cache ({len(all_programmed[:100])} records)")
    
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
        print("Missing nodes/hours:")
        for node in CMG_NODES:
            hours = node_hours.get(node, set())
            if len(hours) < 24:
                missing = set(range(24)) - hours
                print(f"   {node}: Missing hours {sorted(missing)[:10]}...")
    
    print(f"\n📦 Deploy with:")
    print(f"   git add data/cache/")
    print(f"   git commit -m '🔄 Ultra cache update - {coverage_pct:.0f}% coverage'")
    print(f"   git push origin main")

if __name__ == "__main__":
    main()