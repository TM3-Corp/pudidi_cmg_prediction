#!/usr/bin/env python3
"""
Test script to fetch ALL CMG Programado data (today + future)
Shows complete page-by-page fetching to understand the data structure
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

def fetch_all_pages(date_str, label):
    """Fetch ALL pages of programmed data for a given date"""
    
    url = f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate"
    all_records = []
    page = 1
    consecutive_empty = 0
    records_per_page = 4000  # Use optimized page size
    
    print(f"\n📆 Fetching {label}: {date_str}")
    print("-"*60)
    
    while consecutive_empty < 3:
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': records_per_page,
            'user_key': SIP_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                if records:
                    consecutive_empty = 0
                    
                    # Filter for our nodes
                    our_records = [r for r in records if r.get('nmb_barra_info') in PID_NODE_MAP]
                    all_records.extend(our_records)
                    
                    # Show progress
                    hours_in_page = sorted(set(r.get('hra', -1) for r in our_records))
                    print(f"  Page {page:3d}: {len(records):4d} total, {len(our_records):3d} our nodes, hours: {hours_in_page}")
                    
                    # Check if last page
                    if len(records) < records_per_page:
                        print(f"  ✅ Last page reached (got {len(records)} < {records_per_page})")
                        break
                else:
                    consecutive_empty += 1
                    print(f"  Page {page:3d}: Empty")
                    if consecutive_empty >= 3:
                        print("  ✅ Found end of data (3 consecutive empty pages)")
                        break
            else:
                print(f"  Page {page:3d}: Error {response.status_code}")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                time.sleep(2)
        
        except Exception as e:
            print(f"  Page {page:3d}: Exception - {str(e)[:50]}")
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            time.sleep(2)
        
        page += 1
        if page > 20:  # Safety limit
            print("  ⚠️ Reached page limit (20)")
            break
    
    return all_records

def main():
    """Main test function"""
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("="*80)
    print(f"🔍 COMPLETE CMG PROGRAMADO FETCH TEST")
    print(f"📅 Current time: {now.strftime('%Y-%m-%d %H:%M')} Santiago")
    print(f"⏰ Current hour: {now.hour}")
    print("="*80)
    
    # Dates to fetch
    dates = [
        (now.strftime('%Y-%m-%d'), "Today"),
        ((now + timedelta(days=1)).strftime('%Y-%m-%d'), "Tomorrow"),
        ((now + timedelta(days=2)).strftime('%Y-%m-%d'), "Day After Tomorrow")
    ]
    
    all_data = []
    
    for date_str, label in dates:
        records = fetch_all_pages(date_str, label)
        
        # Analyze what we got
        if records:
            print(f"\n  📊 Analysis for {label}:")
            
            # Group by node and hour
            node_hours = defaultdict(set)
            for r in records:
                node = r.get('nmb_barra_info')
                hour = r.get('hra')
                if node and hour is not None:
                    node_hours[node].add(hour)
                    all_data.append({
                        'date': date_str,
                        'hour': hour,
                        'node': PID_NODE_MAP.get(node, node),
                        'cmg': r.get('cmg_usd_mwh_', 0)
                    })
            
            # Show coverage
            print(f"    Total records: {len(records)}")
            for pid_node, cmg_node in PID_NODE_MAP.items():
                hours = sorted(node_hours.get(pid_node, set()))
                coverage = len(hours)
                if coverage == 24:
                    print(f"    ✅ {cmg_node}: {coverage}/24 hours")
                elif coverage > 0:
                    print(f"    ⚠️ {cmg_node}: {coverage}/24 hours - {hours}")
                else:
                    print(f"    ❌ {cmg_node}: 0/24 hours")
        else:
            print(f"\n  ❌ No data found for {label}")
    
    # Final summary
    print("\n" + "="*80)
    print("📊 FINAL SUMMARY")
    print("="*80)
    
    if all_data:
        # Group by date and hour
        by_date_hour = defaultdict(list)
        for item in all_data:
            key = (item['date'], item['hour'])
            by_date_hour[key].append(item)
        
        print(f"\nTotal data points collected: {len(all_data)}")
        print(f"Unique (date, hour) combinations: {len(by_date_hour)}")
        
        # Show what hours we have for each date
        by_date = defaultdict(set)
        for (date, hour), items in by_date_hour.items():
            by_date[date].add(hour)
        
        print("\nHours available by date:")
        for date in sorted(by_date.keys()):
            hours = sorted(by_date[date])
            print(f"  {date}: {len(hours)} hours - {hours}")
        
        # Filter for future data only
        next_hour = now.hour + 1 if now.hour < 23 else 0
        today = now.strftime('%Y-%m-%d')
        tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        
        future_data = []
        for item in all_data:
            if (item['date'] == today and item['hour'] >= next_hour) or item['date'] > today:
                future_data.append(item)
        
        print(f"\n🔮 Future data (from hour {next_hour} onwards):")
        print(f"  Total future records: {len(future_data)}")
        
        # Group future by date/hour
        future_by_date = defaultdict(set)
        for item in future_data:
            future_by_date[item['date']].add(item['hour'])
        
        for date in sorted(future_by_date.keys()):
            hours = sorted(future_by_date[date])
            if date == today:
                print(f"  {date} (Today): hours {hours}")
            elif date == tomorrow:
                print(f"  {date} (Tomorrow): hours {hours}")
            else:
                print(f"  {date}: hours {hours}")
    else:
        print("❌ No data collected!")

if __name__ == "__main__":
    main()