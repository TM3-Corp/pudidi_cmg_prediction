#!/usr/bin/env python3
"""
Monitored Cache Update Script - Shows detailed progress
Based on the proven optimized_fetch_final.ipynb approach
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import json
import time
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from utils.fetcher_optimized import OptimizedCMGFetcher
from utils.cache_manager import CacheManager

def print_header(title):
    """Print a formatted header"""
    print(f"\n{'='*80}")
    print(f"🚀 {title}")
    print(f"{'='*80}")

def main():
    """Update cache with detailed monitoring output"""
    start_time = time.time()
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print_header(f"CACHE UPDATE - {now.strftime('%Y-%m-%d %H:%M:%S')} Santiago")
    print(f"📊 Records per page: 4000 (optimized)")
    print(f"🎯 Target: Last 24 hours + next 48 hours programmed")
    print(f"⏱️ Expected time: ~3-4 minutes")
    
    try:
        # Initialize components
        fetcher = OptimizedCMGFetcher()
        cache_manager = CacheManager()
        
        # IMPORTANT: Use only the proven pages (37-40 max needed)
        print(f"\n📋 Using optimized page sequence (max 40 pages)")
        print(f"   Priority pages: {fetcher.PRIORITY_PAGES[:13]}")
        
        # Step 1: Fetch Historical Data (Last 24 hours)
        print_header("STEP 1: FETCHING HISTORICAL DATA (Last 24 hours)")
        
        # Calculate date range
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        today = now.strftime('%Y-%m-%d')
        
        print(f"📅 Yesterday: {yesterday}")
        print(f"📅 Today: {today} (up to hour {now.hour})")
        
        all_historical = []
        
        # Fetch yesterday's data
        print(f"\n📦 Fetching yesterday's complete data...")
        print(f"   Date: {yesterday}")
        print(f"   Target coverage: 100%")
        
        yesterday_start = time.time()
        yesterday_data = fetcher.fetch_historical_cmg(
            date=yesterday,
            target_coverage=1.0,  # 100% coverage
            incremental=False
        )
        yesterday_elapsed = time.time() - yesterday_start
        
        if yesterday_data and yesterday_data.get('data'):
            print(f"   ✅ Fetched {len(yesterday_data['data'])} records in {yesterday_elapsed:.1f}s")
            print(f"   📄 Pages fetched: {yesterday_data['statistics'].get('pages_fetched', 'N/A')}")
            print(f"   📊 Coverage: {yesterday_data['statistics'].get('coverage', 0)*100:.1f}%")
            all_historical.extend(yesterday_data['data'])
            
            # Show node coverage
            nodes_found = set(r['node'] for r in yesterday_data['data'] if 'node' in r)
            print(f"   📍 Nodes found: {len(nodes_found)}/6 - {', '.join(sorted(nodes_found)[:3])}...")
        else:
            print(f"   ❌ Failed to fetch yesterday's data")
        
        # Fetch today's data
        print(f"\n📦 Fetching today's data up to current hour...")
        print(f"   Date: {today}")
        print(f"   Up to hour: {now.hour}:00")
        
        today_start = time.time()
        today_data = fetcher.fetch_historical_cmg(
            date=today,
            target_coverage=0.9,  # 90% is enough for today
            incremental=False
        )
        today_elapsed = time.time() - today_start
        
        if today_data and today_data.get('data'):
            print(f"   ✅ Fetched {len(today_data['data'])} records in {today_elapsed:.1f}s")
            print(f"   📄 Pages fetched: {today_data['statistics'].get('pages_fetched', 'N/A')}")
            
            # Filter to current hour
            filtered_today = []
            hours_found = set()
            for record in today_data['data']:
                if 'hour' in record and record['hour'] <= now.hour:
                    filtered_today.append(record)
                    hours_found.add(record['hour'])
            
            print(f"   📊 Hours found: {sorted(hours_found)}")
            print(f"   📈 Filtered to current hour: {len(filtered_today)} records")
            all_historical.extend(filtered_today)
        else:
            print(f"   ❌ Failed to fetch today's data")
        
        # Merge historical data
        print(f"\n📊 Merging historical data...")
        if all_historical:
            merged_historical = cache_manager.merge_historical_data(
                all_historical,
                window_hours=24
            )
            
            print(f"   Total records after merge: {len(merged_historical['data'])}")
            
            # Analyze coverage
            unique_hours = set(r['hour'] for r in merged_historical['data'] if 'hour' in r)
            unique_nodes = set(r['node'] for r in merged_historical['data'] if 'node' in r)
            coverage_pct = (len(unique_hours) / 24) * 100
            
            print(f"   📊 Coverage: {coverage_pct:.1f}% ({len(unique_hours)}/24 hours)")
            print(f"   📍 Nodes: {len(unique_nodes)}/6")
            
            # Find last data point
            last_hour = max(r['hour'] for r in merged_historical['data'] if 'hour' in r)
            print(f"   ⏰ Last data point: Hour {last_hour}:00")
            
            # Save historical cache
            if cache_manager.write_cache('historical', merged_historical):
                print(f"   ✅ Historical cache saved")
            else:
                print(f"   ❌ Failed to save historical cache")
        else:
            print(f"   ❌ No historical data to merge")
            
        # Step 2: Fetch Programmed Data
        print_header("STEP 2: FETCHING PROGRAMMED DATA (Next 48 hours)")
        
        tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        day_after = (now + timedelta(days=2)).strftime('%Y-%m-%d')
        
        print(f"📅 Tomorrow: {tomorrow}")
        print(f"📅 Day after: {day_after}")
        
        all_programmed = []
        
        # Fetch tomorrow's programmed
        print(f"\n📦 Fetching tomorrow's programmed data...")
        prog_start = time.time()
        tomorrow_prog = fetcher.fetch_programmed_cmg(
            date=tomorrow,
            hours_ahead=24
        )
        prog_elapsed = time.time() - prog_start
        
        if tomorrow_prog and tomorrow_prog.get('data'):
            print(f"   ✅ Fetched {len(tomorrow_prog['data'])} records in {prog_elapsed:.1f}s")
            all_programmed.extend(tomorrow_prog['data'])
        else:
            print(f"   ⚠️ No programmed data for tomorrow (might not be published yet)")
        
        # Fetch day after tomorrow's programmed
        print(f"\n📦 Fetching day after tomorrow's programmed data...")
        prog2_start = time.time()
        day_after_prog = fetcher.fetch_programmed_cmg(
            date=day_after,
            hours_ahead=24
        )
        prog2_elapsed = time.time() - prog2_start
        
        if day_after_prog and day_after_prog.get('data'):
            print(f"   ✅ Fetched {len(day_after_prog['data'])} records in {prog2_elapsed:.1f}s")
            all_programmed.extend(day_after_prog['data'])
        else:
            print(f"   ⚠️ No programmed data for day after tomorrow")
        
        # Save programmed data
        if all_programmed:
            programmed_result = {
                'timestamp': now.isoformat(),
                'data': all_programmed,
                'statistics': {
                    'total_records': len(all_programmed),
                    'hours_ahead': len(set(r['hour'] for r in all_programmed if 'hour' in r))
                }
            }
            
            if cache_manager.write_cache('programmed', programmed_result):
                print(f"   ✅ Programmed cache saved ({len(all_programmed)} records)")
            else:
                print(f"   ❌ Failed to save programmed cache")
        else:
            print(f"   ⚠️ No programmed data available")
        
        # Step 3: Update metadata
        print_header("STEP 3: UPDATING METADATA")
        
        metadata = {
            'timestamp': now.isoformat(),
            'last_update': now.isoformat(),
            'runtime_seconds': time.time() - start_time
        }
        
        if cache_manager.write_cache('metadata', metadata):
            print("✅ Metadata updated")
        else:
            print("❌ Failed to update metadata")
        
        # Final summary
        elapsed_total = time.time() - start_time
        print_header(f"UPDATE COMPLETE in {elapsed_total:.1f} seconds ({elapsed_total/60:.1f} minutes)")
        
        if elapsed_total > 240:  # More than 4 minutes
            print("⚠️ WARNING: Update took longer than expected (>4 minutes)")
            print("   This might indicate an issue with page fetching")
        else:
            print("✅ Update completed within expected time")
            
        # Calculate speedup
        baseline_minutes = 34.5  # Original baseline
        if elapsed_total > 0:
            speedup = (baseline_minutes * 60) / elapsed_total
            print(f"🚀 Speed: {speedup:.1f}x faster than baseline")
        
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ ERROR after {elapsed:.1f} seconds: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting monitored cache update...")
    print("This will show detailed progress like the notebook\n")
    
    success = main()
    
    if success:
        print("\n✅ Cache update completed successfully!")
        print("You can now check the updated data in your dashboard")
    else:
        print("\n❌ Cache update failed. Check the error messages above.")
    
    sys.exit(0 if success else 1)