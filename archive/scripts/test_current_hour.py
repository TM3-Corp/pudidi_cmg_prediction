#!/usr/bin/env python3
"""
Test script to check current hour data availability
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from utils.fetcher_optimized import OptimizedCMGFetcher

def main():
    """Check what data is available for current hour"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("=" * 60)
    print(f"CURRENT HOUR DATA TEST")
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} (Santiago)")
    print("=" * 60)
    
    fetcher = OptimizedCMGFetcher()
    
    # Test fetching today's data
    today = now.strftime('%Y-%m-%d')
    print(f"\n📅 Testing fetch for today: {today}")
    print(f"Current hour: {now.hour}:00")
    
    # Fetch with extended page range to ensure we get all hours
    print("\nFetching with extended page range...")
    
    # Modify fetcher temporarily to fetch more pages
    original_pages = fetcher.PRIORITY_PAGES.copy()
    
    # Add pages that might contain hours 15-16 (based on pattern analysis)
    # Pages 110-111 had hour 21, pages 138-139 had hour 15
    extended_pages = list(range(1, 150))  # Check all pages up to 150
    
    fetcher.PRIORITY_PAGES = extended_pages
    
    today_data = fetcher.fetch_historical_cmg(
        date=today,
        target_coverage=1.0,
        incremental=False
    )
    
    # Restore original pages
    fetcher.PRIORITY_PAGES = original_pages
    
    if today_data and today_data.get('data'):
        print(f"\n✅ Fetched {len(today_data['data'])} records")
        
        # Analyze hours coverage
        hours_data = {}
        nodes_data = set()
        
        for record in today_data['data']:
            hour = record.get('hour', -1)
            node = record.get('node', 'unknown')
            
            if hour not in hours_data:
                hours_data[hour] = []
            hours_data[hour].append(node)
            nodes_data.add(node)
        
        print(f"\n📊 Data Coverage Analysis:")
        print(f"Hours with data: {sorted(hours_data.keys())}")
        print(f"Nodes with data: {sorted(nodes_data)}")
        
        # Check specific hours
        print(f"\n🔍 Hour-by-hour breakdown:")
        for hour in range(0, now.hour + 1):
            if hour in hours_data:
                nodes_count = len(set(hours_data[hour]))
                print(f"  Hour {hour:02d}:00 - {nodes_count}/6 nodes - {', '.join(sorted(set(hours_data[hour])[:3]))}...")
            else:
                print(f"  Hour {hour:02d}:00 - NO DATA")
        
        # Find missing hours
        expected_hours = set(range(0, now.hour + 1))
        actual_hours = set(h for h in hours_data.keys() if h >= 0)
        missing_hours = expected_hours - actual_hours
        
        if missing_hours:
            print(f"\n⚠️ MISSING HOURS: {sorted(missing_hours)}")
            print("These hours need special handling or might not be available yet")
        else:
            print(f"\n✅ All hours up to {now.hour}:00 are available!")
        
        # Save sample data for inspection
        sample_file = Path("data/cache/test_current_hour.json")
        sample_data = {
            'timestamp': now.isoformat(),
            'current_hour': now.hour,
            'hours_available': sorted(actual_hours),
            'missing_hours': sorted(missing_hours),
            'nodes_available': sorted(nodes_data),
            'sample_records': today_data['data'][:10],  # First 10 records
            'statistics': today_data.get('statistics', {})
        }
        
        with open(sample_file, 'w') as f:
            json.dump(sample_data, f, indent=2, default=str)
        print(f"\n💾 Sample data saved to {sample_file}")
        
    else:
        print("❌ Failed to fetch today's data")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()