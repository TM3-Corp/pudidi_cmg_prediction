#!/usr/bin/env python3
"""
Test script to debug CMG Programado fetching
Shows exactly what data is being fetched from each page
"""

import requests
import json
from datetime import datetime, timedelta
import pytz
import time
from collections import defaultdict

# API Configuration
SIP_BASE_URL = "https://sipub.api.coordinador.cl:443"
SIP_API_KEY = "e67a45c78b3245b6ab5e8c74e8e529ad"

# PID Node mapping (for programmed data)
PID_NODE_MAP = {
    'BA S/E CHILOE 110KV BP1': 'CHILOE________110',
    'BA S/E CHILOE 220KV BP1': 'CHILOE________220',
    'BA S/E CHONCHI 110KV BP1': 'CHONCHI_______110',
    'BA S/E DALCAHUE 23KV BP1': 'DALCAHUE______023',
    'BA S/E QUELLON 110KV BP1': 'QUELLON_______110',
    'BA S/E QUELLON 13KV BP1': 'QUELLON_______013'
}

def fetch_page_with_retry(url, params, page, max_retries=3):
    """Fetch a single page with retry logic"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                return records, len(records)
            elif response.status_code >= 500:
                wait_time = min(3 * (1.5 ** attempt), 30)
                print(f"      Server error {response.status_code}, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                print(f"      Error {response.status_code} on attempt {attempt+1}")
                time.sleep(2)
        except Exception as e:
            print(f"      Exception on attempt {attempt+1}: {str(e)[:50]}")
            time.sleep(2)
    
    print(f"      Failed after {max_retries} attempts")
    return [], 0

def test_programmed_fetch():
    """Test fetching programmed CMG data"""
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("="*80)
    print(f"🔍 TESTING CMG PROGRAMADO FETCH")
    print(f"📅 Current time: {now.strftime('%Y-%m-%d %H:%M')} Santiago")
    print(f"⏰ Current hour: {now.hour}")
    print("="*80)
    
    # Test fetching for today and tomorrow
    dates_to_test = [
        (now.strftime('%Y-%m-%d'), "Today"),
        ((now + timedelta(days=1)).strftime('%Y-%m-%d'), "Tomorrow"),
        ((now + timedelta(days=2)).strftime('%Y-%m-%d'), "Day After Tomorrow")
    ]
    
    url_pid = f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate"
    
    for date_str, label in dates_to_test:
        print(f"\n📆 Testing {label}: {date_str}")
        print("-"*60)
        
        all_records = []
        node_hours = defaultdict(set)
        page = 1
        consecutive_empty = 0
        records_per_page = 1000
        
        while consecutive_empty < 3 and page <= 50:
            params = {
                'startDate': date_str,
                'endDate': date_str,
                'page': page,
                'limit': records_per_page,
                'user_key': SIP_API_KEY
            }
            
            records, count = fetch_page_with_retry(url_pid, params, page)
            
            if count > 0:
                consecutive_empty = 0
                
                # Analyze records
                page_nodes = set()
                page_hours = set()
                our_records = []
                
                # Show first 3 records for debugging
                if page == 1:
                    print(f"\n  📝 Sample records from page 1:")
                    for i, record in enumerate(records[:3]):
                        print(f"    Record {i+1}:")
                        print(f"      fecha_hora: {record.get('fecha_hora', 'N/A')}")
                        print(f"      hra: {record.get('hra', 'N/A')}")
                        print(f"      nmb_barra_info: {record.get('nmb_barra_info', 'N/A')}")
                        print(f"      cmg_usd_mwh_: {record.get('cmg_usd_mwh_', 'N/A')}")
                
                for record in records:
                    node = record.get('nmb_barra_info')
                    if node in PID_NODE_MAP:
                        our_records.append(record)
                        page_nodes.add(node)
                        
                        # Extract hour
                        hour = record.get('hra')
                        if hour is not None:
                            page_hours.add(hour)
                            node_hours[node].add(hour)
                
                all_records.extend(our_records)
                
                # Show page summary
                print(f"  Page {page:3d}: {count:4d} total records, {len(our_records):3d} for our nodes, {len(page_hours)} unique hours: {sorted(page_hours)}")
                
                # Check if this is the last page
                if count < records_per_page:
                    print(f"  📍 Page {page} is the LAST PAGE ({count} < {records_per_page})")
                    break
            else:
                consecutive_empty += 1
                print(f"  Page {page:3d}: Empty")
                if consecutive_empty >= 3:
                    print(f"  ✅ Found end of data (3 consecutive empty pages)")
                    break
            
            page += 1
        
        # Summary for this date
        print(f"\n  📊 Summary for {label}:")
        print(f"    Total pages fetched: {page}")
        print(f"    Total records for our nodes: {len(all_records)}")
        print(f"    Unique hours found: {sorted(set().union(*node_hours.values()) if node_hours else set())}")
        
        print(f"\n  📊 Coverage by node:")
        for pid_node, cmg_node in PID_NODE_MAP.items():
            hours = sorted(node_hours.get(pid_node, set()))
            coverage = len(hours)
            status = "✅" if coverage == 24 else "⚠️" if coverage > 0 else "❌"
            print(f"    {status} {pid_node}: {coverage}/24 hours")
            if hours and coverage < 24:
                print(f"       Hours: {hours}")
        
        # Check for duplicates
        print(f"\n  🔍 Checking for duplicates:")
        record_keys = []
        for record in all_records:
            key = (record.get('nmb_barra_info'), record.get('hra'))
            record_keys.append(key)
        
        unique_keys = set(record_keys)
        if len(record_keys) != len(unique_keys):
            print(f"    ⚠️ DUPLICATES FOUND: {len(record_keys)} records but only {len(unique_keys)} unique (node, hour) pairs")
            
            # Find which keys are duplicated
            from collections import Counter
            key_counts = Counter(record_keys)
            duplicates = {k: v for k, v in key_counts.items() if v > 1}
            if duplicates:
                print(f"    Duplicated (node, hour) pairs:")
                for (node, hour), count in list(duplicates.items())[:5]:
                    print(f"      ({node}, hour {hour}): {count} times")
        else:
            print(f"    ✅ No duplicates found")

if __name__ == "__main__":
    test_programmed_fetch()