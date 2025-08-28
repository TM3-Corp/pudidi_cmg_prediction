#!/usr/bin/env python3
"""
Simple Sequential Update Script - 100% Data Integrity Focus
Fetches ALL pages sequentially until we have complete data
Priority: Data integrity over speed
"""

import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import pytz

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Our 6 nodes we care about
CMG_NODES = [
    'CHILOE________220', 'CHILOE________110', 
    'QUELLON_______110', 'QUELLON_______013', 
    'CHONCHI_______110', 'DALCAHUE______023'
]

# Programmed node names (different format in PID API)
PID_NODE_MAP = {
    'BA S/E CHILOE 220KV BP1': 'CHILOE________220',
    'BA S/E CHILOE 110KV BP1': 'CHILOE________110',
    'BA S/E QUELLON 110KV BP1': 'QUELLON_______110',
    'BA S/E QUELLON 13KV BP1': 'QUELLON_______013',
    'BA S/E CHONCHI 110KV BP1': 'CHONCHI_______110',
    'BA S/E DALCAHUE 23KV BP1': 'DALCAHUE______023'
}

def fetch_page_with_retry(url, params, page_num, max_retries=10, max_wait=60):
    """
    Fetch a single page with aggressive retry logic.
    Will wait up to max_wait seconds between retries if needed.
    """
    wait_time = 2  # Start with 2 seconds
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                if records:
                    return records, len(records)
                else:
                    return [], 0  # Empty page
                    
            elif response.status_code == 429:  # Rate limited
                wait_time = min(wait_time * 2, max_wait)
                print(f"      Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                
            elif response.status_code >= 500:  # Server error
                wait_time = min(wait_time * 1.5, max_wait)
                print(f"      Server error {response.status_code}, waiting {wait_time}s...")
                time.sleep(wait_time)
                
            else:
                print(f"      Error {response.status_code} on attempt {attempt+1}")
                time.sleep(wait_time)
                
        except requests.exceptions.Timeout:
            print(f"      Timeout on attempt {attempt+1}, waiting {wait_time}s...")
            time.sleep(wait_time)
            
        except Exception as e:
            print(f"      Exception on attempt {attempt+1}: {str(e)[:50]}")
            time.sleep(wait_time)
    
    print(f"      Failed after {max_retries} attempts")
    return [], 0

def fetch_all_pages_parallel(url, date_str, node_field='barra_transf', 
                            target_nodes=None, records_per_page=4000,
                            api_name="CMG Online", use_parallel=True, max_workers=5):
    """
    Fetch ALL pages sequentially until we find the last page.
    Returns all records for our target nodes.
    """
    if target_nodes is None:
        target_nodes = CMG_NODES
    
    print(f"\n{'='*80}")
    print(f"📊 Fetching {api_name} for {date_str}")
    print(f"📦 Records per page: {records_per_page}")
    print(f"🎯 Target nodes: {len(target_nodes)}")
    print(f"⏱️ Will fetch ALL pages until complete")
    print(f"{'='*80}")
    
    all_records = []
    node_hours = defaultdict(set)
    page = 1
    consecutive_empty = 0
    last_page_found = False
    start_time = time.time()
    
    while not last_page_found and page <= 200:  # Safety limit of 200 pages
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': records_per_page,
            'user_key': SIP_API_KEY
        }
        
        # Fetch page with retry
        records, count = fetch_page_with_retry(url, params, page)
        
        if count > 0:
            consecutive_empty = 0
            
            # Filter for our nodes
            our_records = []
            page_nodes = set()
            page_hours = set()
            
            for record in records:
                node = record.get(node_field)
                if node in target_nodes:
                    our_records.append(record)
                    page_nodes.add(node)
                    
                    # Extract hour
                    hour = None
                    if 'fecha_hora' in record:
                        try:
                            hour = int(record['fecha_hora'][11:13])
                        except:
                            pass
                    elif 'hra' in record:
                        hour = record.get('hra')
                    
                    if hour is not None:
                        page_hours.add(hour)
                        node_hours[node].add(hour)
            
            all_records.extend(our_records)
            
            # Print page summary
            total_hours = sum(len(hours) for hours in node_hours.values())
            coverage = (total_hours / (len(target_nodes) * 24)) * 100
            
            print(f"   Page {page:3d}: {count:4d} records, {len(our_records):3d} for our nodes, "
                  f"{len(page_nodes)} nodes, {len(page_hours)} unique hours | "
                  f"Total coverage: {coverage:.1f}%")
            
            # Check if this is the last page (less than full page)
            if count < records_per_page:
                print(f"   📍 Page {page} is the LAST PAGE ({count} < {records_per_page})")
                last_page_found = True
                
        else:
            consecutive_empty += 1
            print(f"   Page {page:3d}: Empty")
            
            # If we get 3 consecutive empty pages, we're done
            if consecutive_empty >= 3:
                print(f"   ✅ Found end of data (3 consecutive empty pages)")
                last_page_found = True
        
        page += 1
        
        # Small delay between pages to be nice to the API
        time.sleep(0.5)
    
    # Final summary
    elapsed = time.time() - start_time
    unique_hours_global = set()
    for node in node_hours:
        unique_hours_global.update(node_hours[node])
    
    print(f"\n📊 FETCH COMPLETE:")
    print(f"   ⏱️ Time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"   📄 Pages fetched: {page-1}")
    print(f"   📦 Total records for our nodes: {len(all_records)}")
    print(f"   📍 Unique hours found: {len(unique_hours_global)}")
    
    # Coverage by node
    print(f"\n📊 Coverage by node:")
    for node in sorted(target_nodes):
        hours = sorted(node_hours.get(node, set()))
        coverage = len(hours) / 24 * 100
        status = "✅" if coverage == 100 else "⚠️" if coverage >= 75 else "❌"
        print(f"   {status} {node}: {len(hours)}/24 hours ({coverage:.0f}%)")
    
    return all_records, node_hours

def parse_historical_record(record):
    """Parse historical CMG record"""
    try:
        dt_str = record.get('fecha_hora', '')
        if not dt_str:
            return None
        
        # Remove timezone
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
            'date': dt.strftime('%Y-%m-%d'),  # Add date for filtering
            'hour': record.get('hra', dt.hour),
            'cmg_actual': float(record.get('cmg_usd_mwh_', 0)),
            'node': record.get('barra_transf', 'unknown')
        }
    except:
        return None

def parse_programmed_record(record, date_str):
    """Parse programmed CMG record"""
    try:
        hour = record.get('hra', 0)
        pid_node = record.get('nmb_barra_info', '')
        
        # Map to our node format
        node = PID_NODE_MAP.get(pid_node)
        if not node:
            # Skip unknown nodes - the programmed API doesn't have all nodes
            return None
        
        return {
            'datetime': f"{date_str} {hour:02d}:00",
            'date': date_str,  # Add date for consistency
            'hour': hour,
            'cmg_programmed': float(record.get('cmg_usd_mwh_', 0)),
            'node': node,
            'pid_node': pid_node,  # Keep original name for debugging
            'is_programmed': True
        }
    except:
        return None

def main():
    """Main update function"""
    print("\n" + "="*80)
    print("🚀 SIMPLE SEQUENTIAL CACHE UPDATE")
    print("   Priority: 100% Data Integrity")
    print("   Method: Sequential fetch of ALL pages")
    print("="*80)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    start_time = time.time()
    
    print(f"\n📅 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} Santiago")
    print(f"⏰ Current hour: {now.hour}:00")
    
    # Create cache directory
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # ========== STEP 1: FETCH HISTORICAL DATA (Last 24 hours) ==========
    print(f"\n{'='*80}")
    print("STEP 1: FETCHING HISTORICAL DATA (Last 24 hours)")
    print(f"{'='*80}")
    
    url_online = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    # We need data from yesterday at current hour to today at current hour
    # This gives us a rolling 24-hour window
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    today = now.strftime('%Y-%m-%d')
    
    # We want exactly 24 hours of data:
    # From yesterday at (current_hour + 1) to today at current_hour
    # Example: if now is 17:00, we want yesterday 18:00 to today 17:00
    print(f"\n📅 Target window: {yesterday} {(now.hour+1):02d}:00 to {today} {now.hour:02d}:00")
    print(f"   This gives us exactly the last 24 hours of data")
    print(f"   Yesterday hours needed: {now.hour+1}-23 ({23-now.hour} hours)")
    print(f"   Today hours needed: 0-{now.hour} ({now.hour+1} hours)")
    print(f"   Total: {23-now.hour + now.hour+1} = 24 hours")
    
    all_historical = []
    
    # Fetch yesterday's data
    print(f"\n📦 Fetching yesterday: {yesterday}")
    yesterday_records, yesterday_coverage = fetch_all_pages_parallel(
        url_online, yesterday, 
        node_field='barra_transf',
        target_nodes=CMG_NODES,
        records_per_page=4000,
        api_name="CMG Online (Yesterday)",
        use_parallel=True,
        max_workers=5
    )
    
    # Parse yesterday's records
    yesterday_count = 0
    for record in yesterday_records:
        parsed = parse_historical_record(record)
        if parsed:
            # For yesterday: keep records from yesterday with hours > current hour
            # Example: if now is 2025-08-28 17:00, keep yesterday's hours 18-23
            if parsed['date'] == yesterday and parsed['hour'] > now.hour:
                all_historical.append(parsed)
                yesterday_count += 1
    
    if yesterday_count == 0 and len(yesterday_records) > 0:
        # Debug: Check why no records were kept
        sample = yesterday_records[0] if yesterday_records else None
        if sample:
            print(f"   ⚠️ Debug: Sample record fecha_hora: {sample.get('fecha_hora', 'N/A')}")
    
    print(f"   ✅ Kept {yesterday_count} records from yesterday (hours {now.hour+1}-23)")
    
    # Fetch today's data
    print(f"\n📦 Fetching today: {today}")
    today_records, today_coverage = fetch_all_pages_parallel(
        url_online, today,
        node_field='barra_transf',
        target_nodes=CMG_NODES,
        records_per_page=4000,
        api_name="CMG Online (Today)",
        use_parallel=True,
        max_workers=5
    )
    
    # Parse today's records
    today_count = 0
    for record in today_records:
        parsed = parse_historical_record(record)
        if parsed:
            # For today: keep records from today with hours <= current hour
            # Example: if now is 2025-08-28 17:00, keep today's hours 0-17
            if parsed['date'] == today and parsed['hour'] <= now.hour:
                all_historical.append(parsed)
                today_count += 1
    
    if today_count == 0 and len(today_records) > 0:
        # Debug: Check why no records were kept
        sample = today_records[0] if today_records else None
        if sample:
            print(f"   ⚠️ Debug: Sample record fecha_hora: {sample.get('fecha_hora', 'N/A')}")
    
    print(f"   ✅ Kept {today_count} records from today (hours 0-{now.hour})")
    
    # Remove duplicates and sort
    seen = set()
    unique_historical = []
    for item in all_historical:
        key = (item['datetime'], item['node'])
        if key not in seen:
            seen.add(key)
            unique_historical.append(item)
    
    unique_historical.sort(key=lambda x: x['datetime'])
    
    # Calculate final coverage
    node_hours = defaultdict(set)
    for record in unique_historical:
        node_hours[record['node']].add(record['hour'])
    
    total_hours = sum(len(hours) for hours in node_hours.values())
    coverage_pct = (total_hours / (6 * 24)) * 100 if unique_historical else 0
    
    print(f"\n📊 Historical Data Summary:")
    print(f"   Total records: {len(unique_historical)}")
    print(f"   Coverage: {coverage_pct:.1f}%")
    print(f"   Nodes with data: {len(node_hours)}/6")
    
    # Save historical cache
    hist_cache = {
        'timestamp': now.isoformat(),
        'data': unique_historical,
        'statistics': {
            'total_records': len(unique_historical),
            'coverage_percentage': coverage_pct,
            'oldest_record': unique_historical[0]['datetime'] if unique_historical else None,
            'newest_record': unique_historical[-1]['datetime'] if unique_historical else None,
            'nodes_with_data': list(node_hours.keys())
        }
    }
    
    with open(cache_dir / 'cmg_historical_latest.json', 'w') as f:
        json.dump(hist_cache, f, indent=2)
    print(f"   ✅ Saved historical cache")
    
    # ========== STEP 2: FETCH PROGRAMMED DATA (Future hours) ==========
    print(f"\n{'='*80}")
    print("STEP 2: FETCHING PROGRAMMED DATA (Future hours)")
    print(f"{'='*80}")
    
    url_pid = f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate"
    
    all_programmed = []
    
    # First, get remaining hours of today (from hour 16 onwards in your example)
    next_hour = now.hour + 1
    if next_hour < 24:
        print(f"\n📦 Fetching today's future hours (from {next_hour:02d}:00 onwards)")
        
        today_prog_records, _ = fetch_all_pages_parallel(
            url_pid, today,
            node_field='nmb_barra_info',
            target_nodes=list(PID_NODE_MAP.keys()),
            records_per_page=1000,  # PID uses 1000
            api_name="CMG Programado (Today Future)",
            use_parallel=False  # Programmed data is smaller, sequential is fine
        )
        
        # Parse and filter for future hours only
        for record in today_prog_records:
            hour = record.get('hra', 0)
            if hour >= next_hour:
                parsed = parse_programmed_record(record, today)
                if parsed:
                    all_programmed.append(parsed)
        
        print(f"   ✅ Found {len(all_programmed)} future records for today")
    
    # Fetch tomorrow's programmed data
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"\n📦 Fetching tomorrow's programmed: {tomorrow}")
    
    tomorrow_records, _ = fetch_all_pages_parallel(
        url_pid, tomorrow,
        node_field='nmb_barra_info',
        target_nodes=list(PID_NODE_MAP.keys()),
        records_per_page=1000,
        api_name="CMG Programado (Tomorrow)",
        use_parallel=False  # Programmed data is smaller, sequential is fine
    )
    
    # Parse tomorrow's records
    tomorrow_count = 0
    for record in tomorrow_records:
        parsed = parse_programmed_record(record, tomorrow)
        if parsed:
            all_programmed.append(parsed)
            tomorrow_count += 1
    
    print(f"   ✅ Found {tomorrow_count} records for tomorrow")
    
    # If we want even more future data, fetch day after tomorrow
    if len(all_programmed) < 100:
        day_after = (now + timedelta(days=2)).strftime('%Y-%m-%d')
        print(f"\n📦 Fetching day after tomorrow: {day_after}")
        
        day_after_records, _ = fetch_all_pages_parallel(
            url_pid, day_after,
            node_field='nmb_barra_info',
            target_nodes=list(PID_NODE_MAP.keys()),
            records_per_page=1000,
            api_name="CMG Programado (Day After)",
            use_parallel=False  # Programmed data is smaller, sequential is fine
        )
        
        for record in day_after_records:
            parsed = parse_programmed_record(record, day_after)
            if parsed:
                all_programmed.append(parsed)
    
    # Sort and save programmed data
    all_programmed.sort(key=lambda x: x['datetime'])
    
    print(f"\n📊 Programmed Data Summary:")
    print(f"   Total records: {len(all_programmed)}")
    print(f"   Note: CMG Programado only has data for some nodes (typically CHILOE 110KV and CHONCHI 110KV)")
    print(f"   This is normal - not all nodes have programmed data available")
    
    if all_programmed:
        prog_cache = {
            'timestamp': now.isoformat(),
            'data': all_programmed[:500],  # Limit to 500 records
            'statistics': {
                'total_records': len(all_programmed[:500]),
                'hours_ahead': len(set(r['hour'] for r in all_programmed[:500]))
            }
        }
        
        with open(cache_dir / 'cmg_programmed_latest.json', 'w') as f:
            json.dump(prog_cache, f, indent=2)
        print(f"   ✅ Saved programmed cache")
    
    # Save metadata
    metadata = {
        'timestamp': now.isoformat(),
        'last_update': now.isoformat(),
        'update_duration_seconds': time.time() - start_time,
        'historical_coverage': coverage_pct
    }
    
    with open(cache_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # ========== FINAL SUMMARY ==========
    elapsed = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"✅ UPDATE COMPLETE")
    print(f"⏱️ Total time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"📊 Historical coverage: {coverage_pct:.1f}%")
    print(f"📈 Programmed records: {len(all_programmed)}")
    print(f"{'='*80}")
    
    if coverage_pct < 100:
        print(f"\n⚠️ Historical coverage is {coverage_pct:.1f}%, not 100%")
        print("Check the detailed logs above to see which hours are missing")
    else:
        print(f"\n✅ Perfect 100% coverage achieved for historical data!")
    
    if len(all_programmed) > 0:
        print(f"\n✅ Programmed data available for future predictions")
    else:
        print(f"\n⚠️ No programmed data available (this may be normal depending on time of day)")
    
    print(f"\n📦 To deploy:")
    print(f"   git add data/cache/")
    print(f"   git commit -m '🔄 Cache update - {coverage_pct:.0f}% coverage'")
    print(f"   git push origin main")
    
    # Return success if we have good coverage
    return coverage_pct >= 80

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)