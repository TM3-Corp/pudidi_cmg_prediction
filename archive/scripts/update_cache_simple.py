#!/usr/bin/env python3
"""
Simple and Fast Cache Update Script
Designed for GitHub Actions - completes in under 2 minutes
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import json
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from utils.fetcher_optimized import OptimizedCMGFetcher
from utils.cache_manager import CacheManager

def main():
    """Quick cache update - focus on recent hours only"""
    start_time = time.time()
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("=" * 60)
    print("SIMPLE CACHE UPDATE")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')} (Santiago)")
    print("=" * 60)
    
    # Set a hard timeout of 90 seconds for the entire script
    max_runtime = 90  # seconds
    
    try:
        # Initialize components
        fetcher = OptimizedCMGFetcher()
        cache_manager = CacheManager()
        
        # IMPORTANT: Only use the known good pages, don't extend
        # This ensures fast execution
        fetcher.PRIORITY_PAGES = [
            2, 6, 10, 11, 16, 18, 21, 23, 27, 29, 32, 35, 37,  # High value pages
            3, 4, 7, 14, 19, 20, 24, 26, 28, 31, 33, 36        # Medium value pages
        ]  # Max 25 pages for speed
        
        print("\n📊 STEP 1: Fetch Recent Historical Data")
        print("-" * 40)
        
        # Only fetch last 6 hours for speed
        all_historical = []
        
        # Fetch today's recent hours
        today = now.strftime('%Y-%m-%d')
        print(f"Fetching recent hours for today: {today}")
        
        # Check elapsed time
        if time.time() - start_time > max_runtime:
            print("⚠️ Timeout approaching, skipping to save")
            return save_partial_update(cache_manager, all_historical)
        
        today_data = fetcher.fetch_historical_cmg(
            date=today,
            target_coverage=0.8,  # 80% is enough for updates
            incremental=True,      # Only recent data
            last_hours=6           # Last 6 hours
        )
        
        if today_data and today_data.get('data'):
            all_historical.extend(today_data['data'])
            print(f"✅ Fetched {len(today_data['data'])} records from today")
        
        # Also get some of yesterday for continuity
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        print(f"Fetching recent hours for yesterday: {yesterday}")
        
        # Check elapsed time
        if time.time() - start_time > max_runtime:
            print("⚠️ Timeout approaching, skipping to save")
            return save_partial_update(cache_manager, all_historical)
        
        yesterday_data = fetcher.fetch_historical_cmg(
            date=yesterday,
            target_coverage=0.8,
            incremental=True,
            last_hours=24  # Full day of yesterday
        )
        
        if yesterday_data and yesterday_data.get('data'):
            all_historical.extend(yesterday_data['data'])
            print(f"✅ Fetched {len(yesterday_data['data'])} records from yesterday")
        
        # Merge with existing cache
        print("\n📊 STEP 2: Merge with Existing Cache")
        print("-" * 40)
        
        existing = cache_manager.read_cache('historical')
        if existing and existing.get('data'):
            print(f"Existing cache has {len(existing['data'])} records")
            all_historical.extend(existing['data'])
        
        # Merge and keep last 24 hours
        if all_historical:
            merged = cache_manager.merge_historical_data(
                all_historical,
                window_hours=24
            )
            
            # Save historical cache
            if cache_manager.write_cache('historical', merged):
                print(f"✅ Historical cache updated ({len(merged['data'])} records)")
            else:
                print("❌ Failed to save historical cache")
        
        print("\n📊 STEP 3: Quick Programmed Data Update")
        print("-" * 40)
        
        # Check elapsed time
        if time.time() - start_time > max_runtime:
            print("⚠️ Timeout approaching, skipping programmed data")
            return True
        
        # Only fetch tomorrow's programmed data
        tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        print(f"Fetching programmed data for tomorrow: {tomorrow}")
        
        programmed_data = fetcher.fetch_programmed_cmg(
            date=tomorrow,
            hours_ahead=24  # Just 24 hours ahead
        )
        
        if programmed_data and programmed_data.get('data'):
            print(f"✅ Fetched {len(programmed_data['data'])} programmed records")
            cache_manager.write_cache('programmed', programmed_data)
        else:
            print("⚠️ No programmed data available")
        
        # Update metadata
        metadata = {
            'timestamp': now.isoformat(),
            'last_update': now.isoformat(),
            'update_type': 'incremental',
            'runtime_seconds': time.time() - start_time
        }
        cache_manager.write_cache('metadata', metadata)
        
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"✅ UPDATE COMPLETE in {elapsed:.1f} seconds")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        elapsed = time.time() - start_time
        print(f"Failed after {elapsed:.1f} seconds")
        return False

def save_partial_update(cache_manager, historical_data):
    """Save partial update if timeout is approaching"""
    if historical_data:
        merged = cache_manager.merge_historical_data(
            historical_data,
            window_hours=24
        )
        cache_manager.write_cache('historical', merged)
        print(f"⚠️ Partial update saved ({len(merged['data'])} records)")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)