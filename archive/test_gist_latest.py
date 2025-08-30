#!/usr/bin/env python3
"""
Test script to verify we're getting the CSV with the furthest future data
"""

import requests
from datetime import datetime
import pytz

def test_gist_selection():
    """Test that we select the CSV with data furthest into the future"""
    
    print("="*80)
    print("🔍 TESTING GIST CSV SELECTION")
    print("="*80)
    
    # Get gist metadata
    gist_api_url = "https://api.github.com/gists/a63a3a10479bafcc29e10aaca627bc73"
    
    print("\n📥 Fetching gist metadata...")
    response = requests.get(gist_api_url, timeout=10)
    if response.status_code != 200:
        print(f"❌ Failed to fetch gist metadata: {response.status_code}")
        return
    
    gist_data = response.json()
    files = gist_data.get('files', {})
    
    print(f"✅ Found {len(files)} files in gist\n")
    
    # Find the CSV with data furthest into the future
    furthest_date = None
    best_file_url = None
    best_filename = None
    file_dates = {}
    
    print("📊 Checking each CSV file:")
    print("-" * 60)
    
    for filename, file_info in files.items():
        if filename.endswith('.csv'):
            raw_url = file_info['raw_url']
            print(f"\n📄 File: {filename}")
            
            # Fetch the CSV
            test_response = requests.get(raw_url, timeout=10)
            if test_response.status_code == 200:
                lines = test_response.text.split('\n')
                
                # Find first and last PMontt220 entries
                first_pmontt_date = None
                last_pmontt_date = None
                pmontt_count = 0
                
                # Find first PMontt220
                for line in lines[1:]:  # Skip header
                    if line and 'PMontt220' in line:
                        parts = line.split(',')
                        if len(parts) >= 3:
                            date_str = parts[0]
                            try:
                                first_pmontt_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
                                break
                            except:
                                pass
                
                # Find last PMontt220 and count total
                for line in reversed(lines):
                    if line and 'PMontt220' in line:
                        pmontt_count = sum(1 for l in lines if 'PMontt220' in l)
                        parts = line.split(',')
                        if len(parts) >= 3:
                            date_str = parts[0]
                            try:
                                last_pmontt_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
                                break
                            except:
                                pass
                
                if first_pmontt_date and last_pmontt_date:
                    print(f"   First PMontt220: {first_pmontt_date.strftime('%Y-%m-%d %H:%M')}")
                    print(f"   Last PMontt220:  {last_pmontt_date.strftime('%Y-%m-%d %H:%M')}")
                    print(f"   Total PMontt220 records: {pmontt_count}")
                    
                    file_dates[filename] = {
                        'first': first_pmontt_date,
                        'last': last_pmontt_date,
                        'count': pmontt_count,
                        'url': raw_url
                    }
                    
                    # Check if this has the furthest future date
                    if furthest_date is None or last_pmontt_date > furthest_date:
                        furthest_date = last_pmontt_date
                        best_file_url = raw_url
                        best_filename = filename
                        print(f"   ⭐ NEW BEST (furthest into future)")
                else:
                    print(f"   ❌ No PMontt220 data found")
            else:
                print(f"   ❌ Failed to fetch: {test_response.status_code}")
    
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    
    if best_filename:
        print(f"\n✅ SELECTED FILE: {best_filename}")
        print(f"   Data goes up to: {furthest_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Total PMontt220 records: {file_dates[best_filename]['count']}")
        
        # Show future hours from now
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        next_hour = now.hour + 1 if now.hour < 23 else 0
        today = now.strftime('%Y-%m-%d')
        
        print(f"\n⏰ Current time: {now.strftime('%Y-%m-%d %H:%M')} Santiago")
        print(f"   Next hour: {next_hour:02d}:00")
        
        # Count future hours in selected file
        response = requests.get(best_file_url, timeout=30)
        if response.status_code == 200:
            lines = response.text.split('\n')
            future_count = 0
            future_hours = set()
            
            for line in lines:
                if line and 'PMontt220' in line:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        date_str = parts[0]
                        try:
                            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
                            date = dt.strftime('%Y-%m-%d')
                            hour = dt.hour
                            
                            # Check if future
                            if (date == today and hour >= next_hour) or date > today:
                                future_count += 1
                                future_hours.add((date, hour))
                        except:
                            pass
            
            print(f"\n🔮 Future data available:")
            print(f"   Total future records: {future_count}")
            print(f"   Unique future hours: {len(future_hours)}")
            
            # Show sample of future hours
            sorted_hours = sorted(future_hours)[:10]
            print(f"   First 10 future hours:")
            for date, hour in sorted_hours:
                print(f"      {date} {hour:02d}:00")
            
            if len(future_hours) > 10:
                print(f"      ... and {len(future_hours) - 10} more")
    else:
        print("❌ No suitable CSV file found")
    
    print("\n" + "="*80)
    print("Comparison of all CSV files:")
    print("-" * 60)
    
    # Sort by last date
    sorted_files = sorted(file_dates.items(), key=lambda x: x[1]['last'], reverse=True)
    
    for i, (filename, info) in enumerate(sorted_files, 1):
        marker = "⭐" if filename == best_filename else "  "
        print(f"{marker} {i}. {filename[:20]}...")
        print(f"      Last date: {info['last'].strftime('%Y-%m-%d %H:%M')}")
        print(f"      Records: {info['count']}")

if __name__ == "__main__":
    test_gist_selection()