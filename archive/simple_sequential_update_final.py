#!/usr/bin/env python3
"""
Final Simple Sequential Update Script
- Historical: NVA_P.MONTT___220, PIDPID________110, DALCAHUE______110
- Programmed: PMontt220 from GitHub Gist
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
import numpy as np

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Our 3 target nodes for historical data
CMG_NODES = [
    'NVA_P.MONTT___220',
    'PIDPID________110', 
    'DALCAHUE______110'
]

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
        
        # FIXED: The API returns fields with underscores at the end!
        # cmg_clp_kwh_ is in CLP/kWh, need to convert to CLP/MWh (*1000)
        cmg_clp_kwh = float(record.get('cmg_clp_kwh_', 0) or 0)
        cmg_real = cmg_clp_kwh * 1000  # Convert from kWh to MWh
        
        # cmg_usd_mwh_ is already in USD/MWh
        cmg_usd = float(record.get('cmg_usd_mwh_', 0) or 0)
        
        return {
            'datetime': record.get('fecha_hora', ''),
            'date': record.get('fecha_hora', '')[:10],  # Extract date part
            'hour': hour,
            'node': record.get('barra_transf', ''),
            'cmg_real': cmg_real,  # Now in CLP/MWh
            'cmg_usd': cmg_usd      # Already in USD/MWh
        }
    except Exception as e:
        print(f"      Warning: Failed to parse record: {e}")
        return None

def aggregate_hourly_data(records):
    """
    Aggregate multiple sub-hourly data points into hourly averages.
    The API sometimes returns multiple values per hour (15-min intervals).
    """
    # Group by (node, date, hour)
    hourly_groups = defaultdict(list)
    
    for record in records:
        if record and record.get('node') and record.get('hour') is not None:
            key = (record['node'], record['date'], record['hour'])
            hourly_groups[key].append(record)
    
    aggregated = []
    for (node, date, hour), hour_records in hourly_groups.items():
        # Average the CMG values for this hour
        cmg_real_values = [r['cmg_real'] for r in hour_records if r.get('cmg_real') is not None]
        cmg_usd_values = [r['cmg_usd'] for r in hour_records if r.get('cmg_usd') is not None]
        
        if cmg_real_values and cmg_usd_values:
            aggregated.append({
                'datetime': hour_records[0]['datetime'],  # Use first record's datetime
                'date': date,
                'hour': hour,
                'node': node,
                'cmg_real': np.mean(cmg_real_values),
                'cmg_usd': np.mean(cmg_usd_values),
                'data_points': len(hour_records)  # Track how many values were averaged
            })
    
    return aggregated

def fetch_programmed_from_gist(now):
    """Fetch programmed data from GitHub Gist - PMontt220 only"""
    
    print("\n   📌 Fetching PMontt220 programmed data from GitHub Gist")
    
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
        
        # Find the CSV with data furthest into the future
        furthest_date = None
        best_file_url = None
        file_dates = {}
        
        print("   🔍 Checking CSV files in gist...")
        for filename, file_info in files.items():
            if filename.endswith('.csv'):
                raw_url = file_info['raw_url']
                
                # Check the LAST PMontt220 entry to find furthest future date
                test_response = requests.get(raw_url, timeout=10)
                if test_response.status_code == 200:
                    lines = test_response.text.split('\n')
                    last_pmontt_date = None
                    
                    # Search through all lines to find the last PMontt220 entry
                    for line in reversed(lines):
                        if line and 'PMontt220' in line:
                            parts = line.split(',')
                            if len(parts) >= 3:
                                date_str = parts[0]
                                try:
                                    date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
                                    last_pmontt_date = date
                                    break
                                except:
                                    pass
                    
                    if last_pmontt_date:
                        file_dates[filename] = last_pmontt_date
                        print(f"      {filename[:8]}... has data until {last_pmontt_date.strftime('%Y-%m-%d %H:%M')}")
                        if furthest_date is None or last_pmontt_date > furthest_date:
                            furthest_date = last_pmontt_date
                            best_file_url = raw_url
        
        if not best_file_url:
            print("   ❌ No suitable CSV file found in gist")
            return all_programmed
        
        print(f"   ✅ Selected CSV with data up to {furthest_date.strftime('%Y-%m-%d %H:%M') if furthest_date else 'unknown'}")
        
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
        
        pmontt_records = []
        
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
                        pmontt_records.append({
                            'datetime': f"{date_str}T{hour:02d}:00:00",
                            'date': date_str,
                            'hour': hour,
                            'node': 'PMontt220',  # Keep original name from gist
                            'cmg_programmed': cmg
                        })
                except:
                    continue
        
        # Sort by datetime
        pmontt_records.sort(key=lambda x: x['datetime'])
        all_programmed = pmontt_records
        
        print(f"   📊 Found {len(all_programmed)} future hours of PMontt220 data")
        
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
    print(f"FINAL CMG DATA UPDATE")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')} Santiago")
    print(f"Historical nodes: NVA_P.MONTT___220, PIDPID________110, DALCAHUE______110")
    print(f"Programmed node: PMontt220 (from GitHub Gist)")
    print(f"{'='*80}")
    
    # Set up cache directory
    cache_dir = Path('data/cache')
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # ========== STEP 1: FETCH HISTORICAL DATA ==========
    print(f"\n{'='*80}")
    print("STEP 1: FETCHING HISTORICAL DATA (Past 48 hours)")
    print(f"Target nodes: {', '.join(CMG_NODES)}")
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
    expected_hours = 48 * len(CMG_NODES)  # 48 hours * 3 nodes
    actual_records = len(all_historical)
    coverage_pct = (actual_records / expected_hours * 100) if expected_hours > 0 else 0
    
    print(f"\n📊 Historical Data Summary:")
    print(f"   Total records: {len(all_historical)}")
    print(f"   Unique hours: {unique_hours}")
    print(f"   Coverage: {coverage_pct:.1f}% ({actual_records}/{expected_hours} expected records)")
    
    # Show breakdown by node
    node_counts = defaultdict(int)
    for record in all_historical:
        node_counts[record['node']] += 1
    
    print(f"\n   Records by node:")
    for node in CMG_NODES:
        count = node_counts[node]
        print(f"      {node}: {count} records")
    
    # Aggregate sub-hourly data before saving
    print(f"\n   📊 Aggregating sub-hourly data...")
    aggregated_historical = aggregate_hourly_data(all_historical)
    print(f"      Aggregated {len(all_historical)} raw records into {len(aggregated_historical)} hourly averages")
    
    # Check for multiple data points per hour
    multi_point_hours = [r for r in aggregated_historical if r.get('data_points', 1) > 1]
    if multi_point_hours:
        print(f"      Found {len(multi_point_hours)} hours with multiple data points (averaged)")
    
    # ========== STEP 1.5: FILL MISSING CURRENT HOUR FROM GIST ==========
    # Check if we're missing data for the current hour
    current_hour = now.hour
    current_date = now.strftime('%Y-%m-%d')
    
    # Check if NVA_P.MONTT___220 has data for current hour
    has_current_hour = any(
        r['node'] == 'NVA_P.MONTT___220' and 
        r['date'] == current_date and 
        r['hour'] == current_hour 
        for r in aggregated_historical
    )
    
    if not has_current_hour:
        print(f"\n   🔍 Missing current hour data ({current_date} {current_hour:02d}:00)")
        print(f"      Attempting to fill from programmed data (Gist)...")
        
        # Fetch programmed data early to fill the gap
        temp_programmed = fetch_programmed_from_gist(now)
        
        # Look for current hour in programmed data
        for prog_record in temp_programmed:
            if prog_record.get('hour') == current_hour and prog_record.get('date') == current_date:
                # Convert PMontt220 programmed data to fill each historical node
                print(f"      ✅ Found programmed data for {current_hour:02d}:00 - filling gap")
                
                # Add synthetic records for each node using programmed CMG
                for node in CMG_NODES:
                    synthetic_record = {
                        'datetime': f"{current_date} {current_hour:02d}:00",
                        'date': current_date,
                        'hour': current_hour,
                        'node': node,
                        'cmg_real': prog_record['cmg_programmed'] * 1000,  # Convert USD to CLP estimate
                        'cmg_usd': prog_record['cmg_programmed'],
                        'data_points': 1,
                        'source': 'programmed_fill'  # Mark as filled from programmed
                    }
                    aggregated_historical.append(synthetic_record)
                
                # Re-sort after adding new records
                aggregated_historical.sort(key=lambda x: (x['datetime'], x['node']))
                break
        else:
            print(f"      ⚠️ No programmed data available for current hour")
    
    # Save historical cache with aggregated data
    today = now.strftime('%Y-%m-%d')
    hist_cache = {
        'timestamp': now.isoformat(),
        'data': aggregated_historical[-500:],  # Keep last 500 aggregated records
        'statistics': {
            'total_records': len(aggregated_historical[-500:]),
            'raw_records_processed': len(all_historical),
            'coverage_percentage': coverage_pct,
            'unique_hours': unique_hours,
            'nodes': CMG_NODES
        }
    }
    
    with open(cache_dir / 'cmg_historical_latest.json', 'w') as f:
        json.dump(hist_cache, f, indent=2)
    print(f"   ✅ Saved historical cache")
    
    # ========== STEP 2: FETCH PROGRAMMED DATA (From GitHub Gist) ==========
    print(f"\n{'='*80}")
    print("STEP 2: FETCHING PROGRAMMED DATA FROM GITHUB GIST")
    print(f"{'='*80}")
    
    # Check if we already fetched programmed data to fill gaps
    if 'temp_programmed' in locals():
        all_programmed = temp_programmed
        print("   ℹ️ Using previously fetched programmed data")
    else:
        all_programmed = fetch_programmed_from_gist(now)
    
    # Sort and save programmed data
    all_programmed.sort(key=lambda x: x['datetime'])
    
    print(f"\n📊 Programmed Data Summary:")
    print(f"   Total records: {len(all_programmed)}")
    print(f"   Node: PMontt220")
    
    if all_programmed:
        # Show sample of future hours
        future_hours = sorted(set(r['hour'] for r in all_programmed[:24]))
        print(f"   Next 24 hours available: {future_hours}")
        
        prog_cache = {
            'timestamp': now.isoformat(),
            'data': all_programmed[:500],  # Limit to 500 records
            'statistics': {
                'total_records': len(all_programmed[:500]),
                'hours_ahead': len(set(r['hour'] for r in all_programmed[:500])),
                'node': 'PMontt220'
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
        'historical_coverage': coverage_pct,
        'historical_nodes': CMG_NODES,
        'programmed_node': 'PMontt220'
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