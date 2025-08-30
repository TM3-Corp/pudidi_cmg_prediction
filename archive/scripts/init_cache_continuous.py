#!/usr/bin/env python3
"""
Enhanced Cache Initialization with Data Continuity
Ensures seamless transition from historical to programmed data
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from utils.fetcher_optimized import OptimizedCMGFetcher
from utils.cache_manager import CacheManager

def main():
    """Initialize cache with continuous data coverage"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("=" * 60)
    print(f"ENHANCED CMG CACHE INITIALIZATION - DATA CONTINUITY")
    print(f"Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')} (Santiago)")
    print("=" * 60)
    
    # Initialize components
    fetcher = OptimizedCMGFetcher()
    cache_manager = CacheManager()
    
    # Step 1: Fetch complete historical data (last 24 hours including current hour)
    print("\nSTEP 1: Fetching Complete Historical Data")
    print("-" * 40)
    
    # Calculate the time window
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    start_time = current_hour - timedelta(hours=24)
    
    print(f"Fetching from: {start_time.strftime('%Y-%m-%d %H:00')}")
    print(f"Fetching to:   {current_hour.strftime('%Y-%m-%d %H:00')}")
    print(f"Current hour:  {now.hour}:00")
    
    all_historical_data = []
    
    # Fetch yesterday's complete data
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"\n📅 Fetching yesterday's data: {yesterday}")
    
    yesterday_data = fetcher.fetch_historical_cmg(
        date=yesterday,
        target_coverage=1.0,  # 100% coverage
        incremental=False
    )
    
    if yesterday_data and yesterday_data.get('data'):
        print(f"✅ Fetched {len(yesterday_data['data'])} records from yesterday")
        all_historical_data.extend(yesterday_data['data'])
        
        # Check what's the latest hour we got
        hours_in_data = set()
        for record in yesterday_data['data']:
            if 'hour' in record:
                hours_in_data.add(record['hour'])
        print(f"   Hours covered: {sorted(hours_in_data)}")
    
    # Fetch today's data up to current hour
    today = now.strftime('%Y-%m-%d')
    print(f"\n📅 Fetching today's data: {today}")
    print(f"   Target: All hours up to {now.hour}:00")
    
    today_data = fetcher.fetch_historical_cmg(
        date=today,
        target_coverage=1.0,  # 100% coverage for today too
        incremental=False
    )
    
    if today_data and today_data.get('data'):
        print(f"✅ Fetched {len(today_data['data'])} records from today")
        
        # Check hours coverage for today
        hours_in_today = set()
        for record in today_data['data']:
            if 'hour' in record:
                hours_in_today.add(record['hour'])
        print(f"   Hours covered today: {sorted(hours_in_today)}")
        
        # Filter to include only up to current hour
        today_filtered = []
        for record in today_data['data']:
            if 'hour' in record and record['hour'] <= now.hour:
                today_filtered.append(record)
        
        print(f"   Filtered to current hour: {len(today_filtered)} records")
        all_historical_data.extend(today_filtered)
    
    # Find the actual last hour in historical data
    last_historical_hour = -1
    last_historical_datetime = None
    
    for record in all_historical_data:
        record_dt = datetime.strptime(record['datetime'], '%Y-%m-%d %H:%M')
        if record_dt > (last_historical_datetime or datetime.min):
            last_historical_datetime = record_dt
            last_historical_hour = record['hour']
    
    print(f"\n📊 Historical Data Summary:")
    print(f"   Total records: {len(all_historical_data)}")
    print(f"   Last data point: {last_historical_datetime.strftime('%Y-%m-%d %H:00') if last_historical_datetime else 'None'}")
    print(f"   Missing hours from current: {now.hour - last_historical_hour if last_historical_hour >= 0 else 'N/A'}")
    
    # Merge and save historical data
    if all_historical_data:
        merged_historical = cache_manager.merge_historical_data(
            all_historical_data,
            window_hours=24
        )
        
        # Add metadata about coverage
        merged_historical['last_hour'] = last_historical_hour
        merged_historical['last_datetime'] = last_historical_datetime.isoformat() if last_historical_datetime else None
        merged_historical['coverage_up_to_hour'] = now.hour
        
        if cache_manager.write_cache('historical', merged_historical):
            print("✅ Historical cache saved with continuity metadata")
        else:
            print("❌ Failed to save historical cache")
            return False
    else:
        print("❌ No historical data fetched")
        return False
    
    # Step 2: Fetch programmed data starting from the next hour after historical
    print("\n" + "=" * 60)
    print("STEP 2: Fetching Programmed Data (Continuous from Historical)")
    print("=" * 60)
    
    # Calculate start time for programmed data
    if last_historical_datetime:
        programmed_start = last_historical_datetime + timedelta(hours=1)
        print(f"Starting programmed data from: {programmed_start.strftime('%Y-%m-%d %H:00')}")
    else:
        # Fallback to next hour
        programmed_start = current_hour + timedelta(hours=1)
        print(f"No historical data found, starting from next hour: {programmed_start.strftime('%Y-%m-%d %H:00')}")
    
    # Fetch programmed data for today (remaining hours)
    today_programmed = []
    if programmed_start.date() == now.date():
        print(f"\n📅 Fetching today's programmed hours...")
        
        today_pid = fetcher.fetch_programmed_cmg(
            date=today,
            hours_ahead=24 - programmed_start.hour
        )
        
        if today_pid and today_pid.get('data'):
            # Filter to only include hours after last historical
            for record in today_pid['data']:
                record_dt = datetime.strptime(record['datetime'], '%Y-%m-%d %H:%M:%S')
                if record_dt >= programmed_start:
                    today_programmed.append(record)
            
            print(f"✅ Fetched {len(today_programmed)} programmed records for today")
    
    # Fetch tomorrow's programmed data
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"\n📅 Fetching tomorrow's programmed data: {tomorrow}")
    
    tomorrow_pid = fetcher.fetch_programmed_cmg(
        date=tomorrow,
        hours_ahead=48
    )
    
    all_programmed_data = today_programmed
    
    if tomorrow_pid and tomorrow_pid.get('data'):
        print(f"✅ Fetched {len(tomorrow_pid['data'])} programmed records for tomorrow")
        all_programmed_data.extend(tomorrow_pid['data'])
    
    # Create final programmed data structure
    if all_programmed_data:
        print(f"\n📊 Programmed Data Summary:")
        print(f"   Total records: {len(all_programmed_data)}")
        
        # Find first and last programmed times
        first_prog = min(all_programmed_data, key=lambda x: x['datetime'])
        last_prog = max(all_programmed_data, key=lambda x: x['datetime'])
        
        print(f"   First hour: {first_prog['datetime']}")
        print(f"   Last hour: {last_prog['datetime']}")
        print(f"   Continuity: {'✅ Seamless' if first_prog['hour'] == (last_historical_hour + 1) % 24 else '⚠️ Gap detected'}")
        
        programmed_result = {
            'timestamp': now.isoformat(),
            'data': all_programmed_data,
            'statistics': {
                'total_records': len(all_programmed_data),
                'first_hour': first_prog['datetime'],
                'last_hour': last_prog['datetime'],
                'continues_from_historical': first_prog['hour'] == (last_historical_hour + 1) % 24
            }
        }
        
        if cache_manager.write_cache('programmed', programmed_result):
            print("✅ Programmed cache saved with continuity")
        else:
            print("❌ Failed to save programmed cache")
            return False
    else:
        print("⚠️ No programmed data available")
    
    # Step 3: Create metadata
    print("\n" + "=" * 60)
    print("STEP 3: Creating Metadata")
    print("=" * 60)
    
    metadata = {
        'timestamp': now.isoformat(),
        'last_update': now.isoformat(),
        'environment': 'production',
        'historical': {
            'last_hour': last_historical_hour,
            'last_datetime': last_historical_datetime.isoformat() if last_historical_datetime else None,
            'records': len(all_historical_data),
            'coverage': 100.0 if last_historical_hour == now.hour else ((last_historical_hour + 1) / (now.hour + 1)) * 100
        },
        'programmed': {
            'first_hour': first_prog['datetime'] if all_programmed_data else None,
            'last_hour': last_prog['datetime'] if all_programmed_data else None,
            'records': len(all_programmed_data),
            'continuous': first_prog['hour'] == (last_historical_hour + 1) % 24 if all_programmed_data else False
        },
        'nodes': list(set(r['node'] for r in all_historical_data if 'node' in r))
    }
    
    if cache_manager.write_cache('metadata', metadata):
        print("✅ Metadata saved")
    
    # Step 4: Verify continuity
    print("\n" + "=" * 60)
    print("CONTINUITY CHECK")
    print("=" * 60)
    
    if last_historical_hour == now.hour:
        print("✅ Historical data is current (includes current hour)")
    else:
        print(f"⚠️ Historical data is {now.hour - last_historical_hour} hours behind")
    
    if all_programmed_data and first_prog['hour'] == (last_historical_hour + 1) % 24:
        print("✅ Programmed data continues seamlessly from historical")
    else:
        print("⚠️ Gap between historical and programmed data")
    
    # Calculate total coverage
    total_hours_covered = len(set(r['hour'] for r in all_historical_data if 'hour' in r))
    expected_hours = 24
    coverage_percent = (total_hours_covered / expected_hours) * 100
    
    print(f"\n📊 Overall Coverage: {coverage_percent:.1f}%")
    print(f"   Historical hours: {total_hours_covered}/24")
    print(f"   Nodes with data: {len(metadata['nodes'])}/6")
    
    print("\n" + "=" * 60)
    print("✅ CACHE INITIALIZATION COMPLETE WITH DATA CONTINUITY")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    import time
    start = time.time()
    success = main()
    elapsed = time.time() - start
    
    print(f"\n⏱️ Total time: {elapsed/60:.1f} minutes")
    sys.exit(0 if success else 1)