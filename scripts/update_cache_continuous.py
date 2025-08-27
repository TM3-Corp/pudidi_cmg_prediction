#!/usr/bin/env python3
"""
Update Cache with Data Continuity
Ensures seamless transition between historical and programmed data
Used by GitHub Actions for hourly updates
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
from utils.cache_manager import CacheManager

class ContinuousCacheUpdater:
    """Updater that ensures data continuity"""
    
    def __init__(self):
        self.fetcher = OptimizedCMGFetcher()
        self.cache_manager = CacheManager()
        self.santiago_tz = pytz.timezone('America/Santiago')
        self.now = datetime.now(self.santiago_tz)
        
        # Extend priority pages to ensure we get hours 15-16
        # Based on analysis: hour 15 at pages 138-139, hour 21 at pages 110-111
        additional_pages = list(range(100, 150))  # Add pages 100-150
        self.fetcher.PRIORITY_PAGES = self.fetcher.PRIORITY_PAGES + additional_pages
    
    def get_current_cache_status(self):
        """Get current cache status and last data points"""
        historical = self.cache_manager.read_cache('historical')
        programmed = self.cache_manager.read_cache('programmed')
        
        last_historical_dt = None
        last_historical_hour = -1
        
        if historical and historical.get('data'):
            for record in historical['data']:
                record_dt = datetime.strptime(record['datetime'], '%Y-%m-%d %H:%M')
                if record_dt > (last_historical_dt or datetime.min):
                    last_historical_dt = record_dt
                    last_historical_hour = record['hour']
        
        first_programmed_dt = None
        if programmed and programmed.get('data'):
            first_record = min(programmed['data'], key=lambda x: x['datetime'])
            first_programmed_dt = datetime.strptime(first_record['datetime'], '%Y-%m-%d %H:%M:%S')
        
        return {
            'last_historical': last_historical_dt,
            'last_historical_hour': last_historical_hour,
            'first_programmed': first_programmed_dt,
            'has_gap': False
        }
    
    def update_historical(self):
        """Update historical data ensuring we get up to current hour"""
        print("\n📊 UPDATING HISTORICAL DATA")
        print("-" * 40)
        
        current_hour = self.now.replace(minute=0, second=0, microsecond=0)
        
        # Get last 3 hours to ensure continuity
        all_historical = []
        hours_needed = []
        
        # Check what hours we need
        for h in range(max(0, self.now.hour - 2), self.now.hour + 1):
            hours_needed.append(h)
        
        print(f"Target hours: {hours_needed}")
        print(f"Current hour: {self.now.hour}:00")
        
        # Fetch today's data with full coverage
        today = self.now.strftime('%Y-%m-%d')
        print(f"Fetching today's data: {today}")
        
        today_data = self.fetcher.fetch_historical_cmg(
            date=today,
            target_coverage=1.0,  # Always aim for 100%
            incremental=False  # Get all data
        )
        
        if today_data and today_data.get('data'):
            print(f"✅ Fetched {len(today_data['data'])} records from today")
            
            # Analyze coverage
            hours_found = set()
            for record in today_data['data']:
                if record.get('hour', -1) in hours_needed:
                    all_historical.append(record)
                    hours_found.add(record['hour'])
            
            missing_hours = set(hours_needed) - hours_found
            
            if missing_hours:
                print(f"⚠️ Missing hours: {sorted(missing_hours)}")
                print("Attempting to fetch with extended page range...")
                
                # Try fetching with extended range
                original_pages = self.fetcher.PRIORITY_PAGES.copy()
                self.fetcher.PRIORITY_PAGES = list(range(1, 150))
                
                extended_data = self.fetcher.fetch_historical_cmg(
                    date=today,
                    target_coverage=1.0,
                    incremental=False
                )
                
                self.fetcher.PRIORITY_PAGES = original_pages
                
                if extended_data and extended_data.get('data'):
                    for record in extended_data['data']:
                        if record.get('hour', -1) in missing_hours:
                            all_historical.append(record)
                            hours_found.add(record['hour'])
            
            print(f"📈 Hours covered: {sorted(hours_found)}")
        
        # Also get yesterday's data for 24-hour window
        yesterday = (self.now - timedelta(days=1)).strftime('%Y-%m-%d')
        print(f"\nFetching yesterday's data: {yesterday}")
        
        yesterday_data = self.fetcher.fetch_historical_cmg(
            date=yesterday,
            target_coverage=1.0,
            incremental=False
        )
        
        if yesterday_data and yesterday_data.get('data'):
            all_historical.extend(yesterday_data['data'])
            print(f"✅ Added {len(yesterday_data['data'])} records from yesterday")
        
        # Merge and save
        if all_historical:
            merged = self.cache_manager.merge_historical_data(
                all_historical,
                window_hours=24
            )
            
            # Add continuity metadata
            last_dt = None
            last_hour = -1
            for record in merged['data']:
                record_dt = datetime.strptime(record['datetime'], '%Y-%m-%d %H:%M')
                if record_dt > (last_dt or datetime.min):
                    last_dt = record_dt
                    last_hour = record['hour']
            
            merged['continuity'] = {
                'last_datetime': last_dt.isoformat() if last_dt else None,
                'last_hour': last_hour,
                'current_hour': self.now.hour,
                'is_current': last_hour == self.now.hour
            }
            
            self.cache_manager.write_cache('historical', merged)
            print(f"✅ Historical cache updated (last hour: {last_hour}:00)")
            return last_dt, last_hour
        
        return None, -1
    
    def update_programmed(self, last_historical_dt, last_historical_hour):
        """Update programmed data starting from next hour after historical"""
        print("\n📊 UPDATING PROGRAMMED DATA")
        print("-" * 40)
        
        if last_historical_dt:
            start_dt = last_historical_dt + timedelta(hours=1)
            print(f"Starting from: {start_dt.strftime('%Y-%m-%d %H:00')}")
        else:
            start_dt = self.now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            print(f"No historical data, starting from: {start_dt.strftime('%Y-%m-%d %H:00')}")
        
        all_programmed = []
        
        # Fetch remaining hours of today
        if start_dt.date() == self.now.date():
            today = self.now.strftime('%Y-%m-%d')
            remaining_hours = 24 - start_dt.hour
            
            print(f"Fetching {remaining_hours} remaining hours for today")
            
            today_pid = self.fetcher.fetch_programmed_cmg(
                date=today,
                hours_ahead=remaining_hours
            )
            
            if today_pid and today_pid.get('data'):
                for record in today_pid['data']:
                    record_dt = datetime.strptime(record['datetime'], '%Y-%m-%d %H:%M:%S')
                    if record_dt >= start_dt:
                        all_programmed.append(record)
                
                print(f"✅ Got {len(all_programmed)} programmed records for today")
        
        # Fetch tomorrow and day after
        for days_ahead in [1, 2]:
            future_date = (self.now + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
            print(f"Fetching programmed data for {future_date}")
            
            future_pid = self.fetcher.fetch_programmed_cmg(
                date=future_date,
                hours_ahead=24
            )
            
            if future_pid and future_pid.get('data'):
                all_programmed.extend(future_pid['data'])
                print(f"✅ Added {len(future_pid['data'])} records")
        
        # Save programmed data
        if all_programmed:
            first_prog = min(all_programmed, key=lambda x: x['datetime'])
            last_prog = max(all_programmed, key=lambda x: x['datetime'])
            
            programmed_result = {
                'timestamp': self.now.isoformat(),
                'data': all_programmed,
                'statistics': {
                    'total_records': len(all_programmed),
                    'first_hour': first_prog['datetime'],
                    'last_hour': last_prog['datetime'],
                    'hours_ahead': len(set(r['hour'] for r in all_programmed)),
                    'continues_from_historical': True
                },
                'continuity': {
                    'follows_historical': True,
                    'start_hour': first_prog['hour'],
                    'expected_start': (last_historical_hour + 1) % 24,
                    'is_continuous': first_prog['hour'] == (last_historical_hour + 1) % 24
                }
            }
            
            self.cache_manager.write_cache('programmed', programmed_result)
            print(f"✅ Programmed cache updated ({len(all_programmed)} records)")
            
            return programmed_result['continuity']['is_continuous']
        
        return False
    
    def run(self):
        """Run the complete update process"""
        print("=" * 60)
        print("CONTINUOUS CACHE UPDATE")
        print(f"Time: {self.now.strftime('%Y-%m-%d %H:%M:%S')} (Santiago)")
        print("=" * 60)
        
        # Get current status
        status = self.get_current_cache_status()
        print(f"\n📍 Current Status:")
        print(f"   Last historical: {status['last_historical'].strftime('%Y-%m-%d %H:00') if status['last_historical'] else 'None'}")
        print(f"   First programmed: {status['first_programmed'].strftime('%Y-%m-%d %H:00') if status['first_programmed'] else 'None'}")
        
        # Update historical
        last_hist_dt, last_hist_hour = self.update_historical()
        
        # Update programmed
        is_continuous = self.update_programmed(last_hist_dt, last_hist_hour)
        
        # Update metadata
        print("\n📊 UPDATING METADATA")
        print("-" * 40)
        
        # Calculate coverage
        historical_cache = self.cache_manager.read_cache('historical')
        nodes_with_data = set()
        hours_with_data = set()
        
        if historical_cache and historical_cache.get('data'):
            for record in historical_cache['data']:
                nodes_with_data.add(record.get('node'))
                hours_with_data.add(record.get('hour'))
        
        coverage = (len(hours_with_data) / 24) * 100 if hours_with_data else 0
        
        metadata = {
            'timestamp': self.now.isoformat(),
            'last_update': self.now.isoformat(),
            'coverage': {
                'percentage': coverage,
                'hours_covered': len(hours_with_data),
                'nodes_covered': len(nodes_with_data),
                'is_continuous': is_continuous,
                'last_historical_hour': last_hist_hour,
                'current_hour': self.now.hour
            }
        }
        
        self.cache_manager.write_cache('metadata', metadata)
        print("✅ Metadata updated")
        
        # Final summary
        print("\n" + "=" * 60)
        print("UPDATE COMPLETE")
        print("=" * 60)
        print(f"✅ Coverage: {coverage:.1f}%")
        print(f"✅ Nodes: {len(nodes_with_data)}/6")
        print(f"✅ Continuity: {'Yes' if is_continuous else 'No'}")
        
        if last_hist_hour < self.now.hour:
            print(f"⚠️ Historical data is {self.now.hour - last_hist_hour} hours behind")
        else:
            print(f"✅ Historical data is current")

def main():
    updater = ContinuousCacheUpdater()
    updater.run()

if __name__ == "__main__":
    main()