#!/usr/bin/env python3
"""
Initialize Cache with First Data Fetch
Run this script to populate initial cache data
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import pytz

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.utils.cache_manager import CacheManager
from api.utils.fetcher_optimized import OptimizedCMGFetcher

def initialize_cache():
    """Initialize cache with complete data fetch"""
    print("="*80)
    print("CMG CACHE INITIALIZATION")
    print("="*80)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    # Initialize components
    cache_manager = CacheManager()
    fetcher = OptimizedCMGFetcher()
    
    print(f"\nStarting at: {now.isoformat()}")
    print("This will take approximately 3-4 minutes for 100% coverage")
    
    # Step 1: Fetch complete historical data (yesterday for full 24h)
    print("\n" + "="*60)
    print("STEP 1: Fetching Historical Data (Last 24 Hours)")
    print("="*60)
    
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"Fetching data for: {yesterday}")
    
    historical_data = fetcher.fetch_historical_cmg(
        date=yesterday,
        target_coverage=1.0,  # 100% coverage
        incremental=False
    )
    
    if historical_data and historical_data.get('data'):
        print(f"\n✅ Success! Fetched {len(historical_data['data'])} historical records")
        print(f"   Fetch time: {historical_data['statistics']['fetch_time_seconds']:.1f} seconds")
        print(f"   Pages fetched: {historical_data['statistics']['pages_fetched']}")
        print(f"   Coverage: {historical_data['statistics']['coverage']*100:.1f}%")
        
        # Also fetch today's data for most recent hours
        today = now.strftime('%Y-%m-%d')
        print(f"\nFetching today's data: {today}")
        
        today_data = fetcher.fetch_historical_cmg(
            date=today,
            target_coverage=0.8,  # 80% is enough for recent
            incremental=False
        )
        
        if today_data and today_data.get('data'):
            print(f"✅ Fetched {len(today_data['data'])} records from today")
            
            # Merge both days
            all_historical = historical_data['data'] + today_data['data']
            merged_historical = cache_manager.merge_historical_data(
                all_historical,
                window_hours=24
            )
        else:
            merged_historical = cache_manager.merge_historical_data(
                historical_data['data'],
                window_hours=24
            )
        
        # Save historical cache
        if cache_manager.write_cache('historical', merged_historical):
            print("✅ Historical cache saved successfully")
        else:
            print("❌ Failed to save historical cache")
            return False
    else:
        print("❌ Failed to fetch historical data")
        return False
    
    # Step 2: Fetch programmed data (next 48 hours)
    print("\n" + "="*60)
    print("STEP 2: Fetching Programmed Data (Next 48 Hours)")
    print("="*60)
    
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"Fetching programmed data starting from: {tomorrow}")
    
    programmed_data = fetcher.fetch_programmed_cmg(
        date=tomorrow,
        hours_ahead=48
    )
    
    if programmed_data and programmed_data.get('data'):
        print(f"\n✅ Success! Fetched {len(programmed_data['data'])} programmed records")
        print(f"   Fetch time: {programmed_data['statistics']['fetch_time_seconds']:.1f} seconds")
        print(f"   Pages fetched: {programmed_data['statistics']['pages_fetched']}")
        print(f"   Hours ahead: {programmed_data['statistics']['hours_ahead']}")
        
        # Save programmed cache
        if cache_manager.write_cache('programmed', programmed_data):
            print("✅ Programmed cache saved successfully")
        else:
            print("❌ Failed to save programmed cache")
            return False
    else:
        print("⚠️ No programmed data available (this is normal if PID is not yet published)")
        # Create empty programmed cache
        empty_programmed = {
            'timestamp': now.isoformat(),
            'data': [],
            'statistics': {
                'hours_ahead': 0,
                'total_records': 0
            }
        }
        cache_manager.write_cache('programmed', empty_programmed)
    
    # Step 3: Create metadata
    print("\n" + "="*60)
    print("STEP 3: Creating Metadata")
    print("="*60)
    
    metadata = {
        'timestamp': now.isoformat(),
        'initialized_at': now.isoformat(),
        'last_update': now.isoformat(),
        'update_type': 'initial',
        'historical_records': len(merged_historical.get('data', [])),
        'programmed_records': len(programmed_data.get('data', [])) if programmed_data else 0,
        'next_update': (now + timedelta(hours=1)).isoformat(),
        'system_version': '2.0.0'
    }
    
    if cache_manager.write_cache('metadata', metadata):
        print("✅ Metadata saved successfully")
    else:
        print("❌ Failed to save metadata")
        return False
    
    # Step 4: Verify cache status
    print("\n" + "="*60)
    print("STEP 4: Verifying Cache Status")
    print("="*60)
    
    status = cache_manager.get_cache_status()
    
    print("\n📊 Cache Status:")
    for cache_type, info in status['caches'].items():
        status_icon = "✅" if info['exists'] else "❌"
        print(f"   {status_icon} {cache_type}: {'Ready' if info['exists'] else 'Missing'}")
        if info['exists']:
            print(f"      Records: {info['records']}")
    
    print(f"\n🎯 Overall Status: {status['overall']['status'].upper()}")
    print(f"   System Ready: {'Yes' if status['overall']['ready'] else 'No'}")
    print(f"   Needs Update: {'Yes' if status['overall']['needs_update'] else 'No'}")
    
    # Final summary
    end_time = datetime.now(santiago_tz)
    duration = (end_time - now).total_seconds()
    
    print("\n" + "="*80)
    print("✅ CACHE INITIALIZATION COMPLETE")
    print(f"Total time: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    print("="*80)
    
    print("\n📋 Next Steps:")
    print("1. Deploy to Vercel: vercel --prod")
    print("2. GitHub Actions will update cache every hour")
    print("3. Visit your site to see the dashboard")
    
    return True

if __name__ == "__main__":
    success = initialize_cache()
    exit(0 if success else 1)