#!/usr/bin/env python3
"""
Quick test of the fetch system - fetches just yesterday's data
"""

import sys
from fetch_complete_daily import CompleteDailyFetcher
from datetime import datetime, timedelta
import pytz

def main():
    print("Testing fetch system...")
    
    # Create fetcher
    fetcher = CompleteDailyFetcher()
    
    # Get yesterday's date
    santiago_tz = pytz.timezone('America/Santiago')
    yesterday = (datetime.now(santiago_tz) - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"Fetching data for {yesterday}")
    
    # Fetch yesterday's data
    results = fetcher.fetch_complete_day(yesterday)
    
    print("\n=== RESULTS ===")
    print(f"Success: {results['success']}")
    print(f"CMG Real: {results['cmg_real']['records_found']} records, {results['cmg_real']['hours_covered']}/24 hours")
    print(f"CMG PID: {results['cmg_pid']['records_found']} records, {results['cmg_pid']['hours_covered']}/24 hours")
    print(f"CMG Online: {results['cmg_online']['records_found']} records, {results['cmg_online']['hours_covered']}/24 hours")
    print(f"Total fetch time: {results['total_time_seconds']:.1f} seconds")
    
    # Check database
    import sqlite3
    conn = sqlite3.connect('cmg_data.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT source, COUNT(*) as records, COUNT(DISTINCT hour) as hours
        FROM cmg_data
        WHERE date = ? AND node = ?
        GROUP BY source
    """, (yesterday, 'CHILOE________220'))
    
    print("\n=== DATABASE CHECK ===")
    for row in cursor.fetchall():
        print(f"{row[0]}: {row[1]} records, {row[2]} unique hours")
    
    conn.close()

if __name__ == "__main__":
    main()