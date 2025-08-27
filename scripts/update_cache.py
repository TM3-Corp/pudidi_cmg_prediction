#!/usr/bin/env python3
"""
Cache Update Script for GitHub Actions
Runs hourly to fetch new CMG data and update cache files
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

def main():
    """Main update function"""
    print("="*80)
    print(f"CMG Cache Update - {datetime.now().isoformat()}")
    print("="*80)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    # Initialize components
    cache_manager = CacheManager()
    fetcher = OptimizedCMGFetcher()
    
    # Check current cache status
    print("\n📊 Checking cache status...")
    status = cache_manager.get_cache_status()
    
    print(f"Historical cache: {'Exists' if status['caches'].get('historical', {}).get('exists') else 'Not found'}")
    print(f"Programmed cache: {'Exists' if status['caches'].get('programmed', {}).get('exists') else 'Not found'}")
    
    # Determine update strategy
    hist_age = status['caches'].get('historical', {}).get('age_hours', 999)
    prog_age = status['caches'].get('programmed', {}).get('age_hours', 999)
    
    update_historical = hist_age > 0.5  # Update if older than 30 minutes
    update_programmed = prog_age > 1  # Update if older than 1 hour
    
    updates_made = False
    
    # Update historical data
    if update_historical:
        print(f"\n📈 Updating historical data (age: {hist_age:.1f} hours)...")
        
        # Determine fetch strategy
        if hist_age > 24:
            # Full fetch if very old or missing
            print("  Performing full fetch (cache very old)...")
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            historical_data = fetcher.fetch_historical_cmg(
                date=yesterday,
                target_coverage=1.0,
                incremental=False
            )
        else:
            # Incremental fetch for recent updates
            print("  Performing incremental fetch...")
            today = now.strftime('%Y-%m-%d')
            historical_data = fetcher.fetch_historical_cmg(
                date=today,
                target_coverage=0.9,
                incremental=True,
                last_hours=3
            )
        
        if historical_data and historical_data.get('data'):
            print(f"  ✅ Fetched {len(historical_data['data'])} historical records")
            
            # Merge with existing cache
            merged_data = cache_manager.merge_historical_data(
                historical_data['data'],
                window_hours=24
            )
            
            # Save to cache
            if cache_manager.write_cache('historical', merged_data):
                print(f"  ✅ Historical cache updated successfully")
                updates_made = True
            else:
                print(f"  ❌ Failed to write historical cache")
        else:
            print(f"  ⚠️ No historical data fetched")
    else:
        print(f"\n✓ Historical data is fresh (age: {hist_age:.1f} hours)")
    
    # Update programmed data
    if update_programmed:
        print(f"\n📊 Updating programmed data (age: {prog_age:.1f} hours)...")
        
        # Fetch next 48 hours of programmed data
        tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        programmed_data = fetcher.fetch_programmed_cmg(
            date=tomorrow,
            hours_ahead=48
        )
        
        if programmed_data and programmed_data.get('data'):
            print(f"  ✅ Fetched {len(programmed_data['data'])} programmed records")
            
            # Save to cache
            if cache_manager.write_cache('programmed', programmed_data):
                print(f"  ✅ Programmed cache updated successfully")
                updates_made = True
            else:
                print(f"  ❌ Failed to write programmed cache")
        else:
            print(f"  ⚠️ No programmed data fetched")
    else:
        print(f"\n✓ Programmed data is fresh (age: {prog_age:.1f} hours)")
    
    # Update metadata
    if updates_made:
        metadata = {
            'timestamp': now.isoformat(),
            'last_update': now.isoformat(),
            'update_type': 'full' if hist_age > 24 else 'incremental',
            'historical_updated': update_historical,
            'programmed_updated': update_programmed,
            'next_update': (now + timedelta(hours=1)).isoformat()
        }
        cache_manager.write_cache('metadata', metadata)
        print(f"\n✅ Metadata updated")
    
    # Cleanup old hourly caches
    print(f"\n🧹 Cleaning up old caches...")
    removed = cache_manager.cleanup_old_caches(days=7)
    if removed > 0:
        print(f"  Removed {removed} old cache files")
    
    # Final status
    print("\n" + "="*80)
    if updates_made:
        print("✅ CACHE UPDATE COMPLETE - Changes made")
    else:
        print("✓ CACHE UPDATE COMPLETE - No changes needed")
    print("="*80)
    
    # Return exit code
    return 0 if not updates_made or updates_made else 0

if __name__ == "__main__":
    exit(main())