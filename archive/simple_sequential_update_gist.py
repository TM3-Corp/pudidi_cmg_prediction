#!/usr/bin/env python3
"""
Simple Sequential Update Script - Using GitHub Gist for Programmed Data
Fetches Historical from API, Programmed from Gist
"""

import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
import csv
from io import StringIO

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
                return records, len(records)
            
            elif response.status_code == 502:
                # Server error - exponential backoff
                wait_time = min(wait_time * 1.5, max_wait)
                print(f"      Page {page_num}: 502 error, attempt {attempt+1}/{max_retries}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            
            elif response.status_code == 429:
                # Rate limited - wait longer
                wait_time = min(wait_time * 2, max_wait)
                print(f"      Page {page_num}: Rate limited, attempt {attempt+1}/{max_retries}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            
            elif response.status_code == 403:
                print(f"      Page {page_num}: 403 Forbidden - API key may be invalid")
                return [], 0
            
            else:
                print(f"      Page {page_num}: Error {response.status_code}, attempt {attempt+1}/{max_retries}")
                time.sleep(3)
        
        except requests.exceptions.Timeout:
            print(f"      Page {page_num}: Timeout, attempt {attempt+1}/{max_retries}")
            time.sleep(5)
        
        except Exception as e:
            print(f"      Page {page_num}: Exception {str(e)[:50]}, attempt {attempt+1}/{max_retries}")
            time.sleep(5)
    
    print(f"      Page {page_num}: Failed after {max_retries} attempts")
    return [], 0

def fetch_all_pages_sequential(url, date_str, node_field, target_nodes, records_per_page=4000, api_name="API"):
    """
    Fetch ALL pages sequentially until we have complete data.
    Keeps going until we find 3 consecutive empty pages.
    """
    all_records = []
    page = 1
    consecutive_empty = 0
    location_hours = defaultdict(set)
    
    print(f"\n   Fetching {api_name} for {date_str}:")
    print(f"   Using {records_per_page} records per page")
    
    while consecutive_empty < 3:
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': records_per_page,
            'user_key': SIP_API_KEY
        }
        
        records, count = fetch_page_with_retry(url, params, page)
        
        if count > 0:
            # Reset empty counter
            consecutive_empty = 0
            
            # Filter for our nodes
            our_records = []
            for record in records:
                node = record.get(node_field, '')
                if node in target_nodes:
                    our_records.append(record)
                    
                    # Track hours we've seen for each location
                    hour = record.get('hora') or record.get('hra', 0)
                    location_hours[node].add(hour)
            
            all_records.extend(our_records)
            
            # Show progress
            unique_hours = set()
            for hours in location_hours.values():
                unique_hours.update(hours)
            
            print(f"      Page {page:3d}: {count:4d} total records, {len(our_records):3d} for our nodes, cumulative hours: {len(unique_hours)}/24")
            
            # Check if this might be the last page
            if count < records_per_page:
                print(f"      Page {page} is the LAST PAGE ({count} < {records_per_page})")
                break  # This was the last page
            
            page += 1
            
            # Safety limit
            if page > 50:
                print(f"      Reached page limit (50)")
                break
        else:
            # Empty page
            consecutive_empty += 1
            print(f"      Page {page:3d}: Empty (consecutive empty: {consecutive_empty})")
            
            if consecutive_empty >= 3:
                print(f"      Found end of data (3 consecutive empty pages)")
                break
            
            page += 1
            
            # Safety limit even for empty pages
            if page > 60:
                print(f"      Reached absolute page limit (60)")
                break
    
    # Show final coverage
    print(f"\n   📊 Coverage summary for {api_name}:")
    for node in sorted(target_nodes):
        hours = sorted(location_hours.get(node, set()))
        coverage = len(hours)
        if coverage == 24:
            print(f"      ✅ {node}: {coverage}/24 hours")
        elif coverage > 0:
            print(f"      ⚠️ {node}: {coverage}/24 hours")
        else:
            print(f"      ❌ {node}: 0/24 hours")
    
    print(f"   Total records retrieved: {len(all_records)}")
    
    return all_records, location_hours

def parse_historical_record(record):
    """Parse a historical CMG record"""
    try:
        # CRITICAL FIX: Use 'hra' field for the actual hour!
        hour = record.get('hra')
        
        # If hra doesn't exist, try parsing from fecha_hora as fallback
        if hour is None:
            fecha_hora = record.get('fecha_hora', '')
            if fecha_hora:
                dt = datetime.fromisoformat(fecha_hora.replace('Z', '+00:00'))
                hour = dt.hour
            else:
                hour = 0
        
        return {
            'datetime': record.get('fecha_hora', ''),
            'date': record.get('fecha_hora', '')[:10],  # Extract date part
            'hour': hour,
            'node': record.get('barra_transf', ''),
            'cmg_real': float(record.get('cmg_pesos_mwh', 0) or 0),
            'cmg_usd': float(record.get('cmg_usd_mwh', 0) or 0)
        }
    except Exception as e:
        print(f"      Warning: Failed to parse record: {e}")
        return None

def fetch_programmed_from_gist(now):
    """Fetch programmed data from GitHub Gist using PMontt220 as proxy"""
    
    print("\n   📌 Using PMontt220 data from GitHub Gist as proxy for all nodes")
    
    all_programmed = []
    
    try:
        # Get gist metadata
        gist_api_url = "https://api.github.com/gists/a63a3a10479bafcc29e10aaca627bc73"
        
        response = requests.get(gist_api_url, timeout=10)
        if response.status_code != 200:
            print(f"   ❌ Failed to fetch gist metadata: {response.status_code}")
            return all_programmed
        
        gist_data = response.json()
        files = gist_data.get('files', {})
        
        # Find the CSV with the most recent data
        latest_date = None
        best_file_url = None
        
        print("   🔍 Checking CSV files in gist...")
        for filename, file_info in files.items():
            if filename.endswith('.csv'):
                raw_url = file_info['raw_url']
                
                # Quick check of dates in file
                test_response = requests.get(raw_url, timeout=10)
                if test_response.status_code == 200:
                    lines = test_response.text.split('\n')[:50]
                    for line in lines[1:]:
                        if line and 'PMontt220' in line:
                            parts = line.split(',')
                            if len(parts) >= 3:
                                date_str = parts[0]
                                try:
                                    date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
                                    if latest_date is None or date > latest_date:
                                        latest_date = date
                                        best_file_url = raw_url
                                except:
                                    pass
                            break
        
        if not best_file_url:
            print("   ❌ No suitable CSV file found in gist")
            return all_programmed
        
        print(f"   ✅ Found CSV with data up to {latest_date.strftime('%Y-%m-%d') if latest_date else 'unknown'}")
        
        # Fetch the full CSV
        response = requests.get(best_file_url, timeout=30)
        if response.status_code != 200:
            print(f"   ❌ Failed to fetch CSV: {response.status_code}")
            return all_programmed
        
        csv_text = response.text
        
        # Parse CSV
        csv_reader = csv.DictReader(StringIO(csv_text))
        
        next_hour = now.hour + 1 if now.hour < 23 else 0
        today = now.strftime('%Y-%m-%d')
        
        pmontt_data = {}  # (date, hour) -> value
        
        for row in csv_reader:
            if row.get('Barra') == 'PMontt220':
                fecha_hora = row.get('Fecha Hora', '')
                cmg = float(row.get('Costo Marginal [USD/MWh]', 0))
                
                try:
                    dt = datetime.strptime(fecha_hora, '%Y-%m-%d %H:%M:%S.%f')
                    date_str = dt.strftime('%Y-%m-%d')
                    hour = dt.hour
                    
                    # Store future data only
                    if (date_str == today and hour >= next_hour) or date_str > today:
                        pmontt_data[(date_str, hour)] = cmg
                except:
                    continue
        
        print(f"   📊 Found PMontt220 data for {len(pmontt_data)} future hours")
        
        # Create synthetic data for all our nodes using PMontt220 values
        for (date_str, hour), cmg_value in sorted(pmontt_data.items()):
            for node in CMG_NODES:
                all_programmed.append({
                    'datetime': f"{date_str}T{hour:02d}:00:00",
                    'date': date_str,
                    'hour': hour,
                    'node': node,
                    'cmg_programmed': cmg_value
                })
        
        print(f"   ✅ Generated {len(all_programmed)} programmed records for all nodes")
        
    except Exception as e:
        print(f"   ❌ Error fetching from gist: {e}")
    
    return all_programmed

def main():
    """Main update function"""
    start_time = time.time()
    
    # Set up timezone
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print(f"\n{'='*80}")
    print(f"SIMPLE SEQUENTIAL CMG DATA UPDATE - WITH GIST PROGRAMMED DATA")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')} Santiago")
    print(f"Strategy: Fetch ALL pages sequentially until we have complete data")
    print(f"Using: 4000 records/page for historical, GitHub Gist for programmed")
    print(f"{'='*80}")
    
    # Set up cache directory
    cache_dir = Path('data/cache')
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # ========== STEP 1: FETCH HISTORICAL DATA ==========
    print(f"\n{'='*80}")
    print("STEP 1: FETCHING HISTORICAL DATA (Past 48 hours)")
    print(f"{'='*80}")
    
    url_online = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    all_historical = []
    
    # We need the last 48 hours of data
    dates_to_fetch = []
    for days_back in range(3):  # Today, yesterday, day before
        date = (now - timedelta(days=days_back)).strftime('%Y-%m-%d')
        dates_to_fetch.append(date)
    
    print(f"📅 Will fetch data for: {', '.join(dates_to_fetch)}")
    
    for date_str in dates_to_fetch:
        records, coverage = fetch_all_pages_sequential(
            url_online, date_str,
            node_field='barra_transf',
            target_nodes=CMG_NODES,
            records_per_page=4000,  # OPTIMIZED VALUE
            api_name=f"CMG Online {date_str}"
        )
        
        # Parse records
        for record in records:
            parsed = parse_historical_record(record)
            if parsed:
                all_historical.append(parsed)
    
    # Sort by datetime
    all_historical.sort(key=lambda x: x['datetime'])
    
    # Calculate coverage
    unique_hours = len(set((r['date'], r['hour']) for r in all_historical))
    expected_hours = 48 * len(CMG_NODES)  # 48 hours * 6 nodes
    actual_records = len(all_historical)
    coverage_pct = (actual_records / expected_hours * 100) if expected_hours > 0 else 0
    
    print(f"\n📊 Historical Data Summary:")
    print(f"   Total records: {len(all_historical)}")
    print(f"   Unique hours: {unique_hours}")
    print(f"   Coverage: {coverage_pct:.1f}% ({actual_records}/{expected_hours} expected records)")
    
    # Save historical cache
    today = now.strftime('%Y-%m-%d')
    hist_cache = {
        'timestamp': now.isoformat(),
        'data': all_historical[-500:],  # Keep last 500 records
        'statistics': {
            'total_records': len(all_historical[-500:]),
            'coverage_percentage': coverage_pct,
            'unique_hours': unique_hours
        }
    }
    
    with open(cache_dir / 'cmg_historical_latest.json', 'w') as f:
        json.dump(hist_cache, f, indent=2)
    print(f"   ✅ Saved historical cache")
    
    # ========== STEP 2: FETCH PROGRAMMED DATA (From GitHub Gist) ==========
    print(f"\n{'='*80}")
    print("STEP 2: FETCHING PROGRAMMED DATA FROM GITHUB GIST")
    print(f"{'='*80}")
    
    all_programmed = fetch_programmed_from_gist(now)
    
    # Sort and save programmed data
    all_programmed.sort(key=lambda x: x['datetime'])
    
    print(f"\n📊 Programmed Data Summary:")
    print(f"   Total records: {len(all_programmed)}")
    print(f"   Note: Using PMontt220 data as proxy for all nodes")
    
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
    print(f"   ✅ Saved metadata")
    
    # Final summary
    duration = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"✅ UPDATE COMPLETE")
    print(f"   Duration: {duration:.1f} seconds")
    print(f"   Historical: {len(all_historical)} records ({coverage_pct:.1f}% coverage)")
    print(f"   Programmed: {len(all_programmed)} records")
    print(f"{'='*80}\n")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Update interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)