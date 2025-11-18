#!/usr/bin/env python3
"""
Test script to debug CMG Online Supabase query
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.utils.supabase_client import SupabaseClient

def main():
    print("="*60)
    print("TESTING CMG ONLINE SUPABASE QUERY")
    print("="*60)

    supabase = SupabaseClient()
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)

    print(f"\n📅 Current time (Santiago): {now}")
    print(f"📅 Current date: {now.date()}")
    print(f"📅 Current hour: {now.hour}")

    # Query last 48 hours (same as API)
    historical_start_date = now.date() - timedelta(days=2)
    end_date = now.date()

    print(f"\n🔍 Querying Supabase:")
    print(f"   Start date: {historical_start_date}")
    print(f"   End date: {end_date}")

    records = supabase.get_cmg_online(
        start_date=str(historical_start_date),
        end_date=str(end_date),
        limit=500
    )

    print(f"\n📊 Query returned {len(records)} records")

    if records:
        print(f"\n✅ Sample records:")
        for i, record in enumerate(records[:5]):
            print(f"   {i+1}. Date: {record['date']}, Hour: {record['hour']}, Node: {record['node']}, CMG: {record['cmg_usd']}")

        # Check date range
        dates = sorted(set(str(r['date']) for r in records))
        print(f"\n📅 Date range in results: {dates[0]} to {dates[-1]}")

        # Check nodes
        nodes = sorted(set(r['node'] for r in records))
        print(f"📍 Nodes in results: {nodes}")

        # Check hours distribution
        hours = sorted(set(r['hour'] for r in records))
        print(f"🕐 Hours in results: {min(hours)} to {max(hours)}")

    else:
        print("\n❌ No records returned")
        print("\n🔍 Trying query without date filter:")

        all_records = supabase.get_cmg_online(limit=10)
        print(f"   Returned {len(all_records)} records")

        if all_records:
            print(f"   Sample: {all_records[0]}")
        else:
            print("   Table appears to be empty")

if __name__ == "__main__":
    main()
