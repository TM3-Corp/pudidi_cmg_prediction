#!/usr/bin/env python3
"""
Verify CMG Programado Schema Migration
=======================================

Run this AFTER running the SQL migration to verify success.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import requests
from lib.utils.supabase_client import SupabaseClient

def test_database_schema():
    """Test 1: Verify new columns exist in database"""
    print("\n" + "="*80)
    print("TEST 1: DATABASE SCHEMA VERIFICATION")
    print("="*80)

    base_url = "https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1"
    api_key = os.environ['SUPABASE_SERVICE_KEY']

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Get a sample record to check columns
    response = requests.get(
        f"{base_url}/cmg_programado",
        params={"limit": 1, "order": "created_at.desc"},
        headers=headers
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

    records = response.json()
    if not records:
        print("❌ No records found in table")
        return False

    sample = records[0]
    print(f"✅ Successfully fetched sample record")
    print(f"   Available columns: {list(sample.keys())}")

    # Check required new columns
    required_columns = [
        'forecast_datetime', 'forecast_date', 'forecast_hour',
        'target_datetime', 'target_date', 'target_hour',
        'cmg_usd', 'node'
    ]

    missing = []
    null_values = []

    for col in required_columns:
        if col not in sample:
            missing.append(col)
        elif sample[col] is None:
            null_values.append(col)

    if missing:
        print(f"❌ Missing columns: {missing}")
        print("   Migration may not have run successfully!")
        return False

    if null_values:
        print(f"⚠️  Columns with NULL values: {null_values}")
        print("   Data transformation may not have completed!")
        return False

    print(f"✅ All required columns present and populated")
    print(f"\n   Sample values:")
    for col in required_columns:
        print(f"      {col}: {sample[col]}")

    return True

def test_supabase_client():
    """Test 2: Verify SupabaseClient can query with new schema"""
    print("\n" + "="*80)
    print("TEST 2: SUPABASE CLIENT QUERY TEST")
    print("="*80)

    try:
        supabase = SupabaseClient()
        print("✅ SupabaseClient initialized")

        # This should work without 400 error now
        prog_records = supabase.get_cmg_programado(limit=10)

        if not prog_records:
            print("⚠️  Query returned 0 records (unexpected)")
            return False

        print(f"✅ Successfully queried {len(prog_records)} records")
        print(f"\n   Sample record:")
        sample = prog_records[0]
        for key in ['forecast_datetime', 'target_datetime', 'node', 'cmg_usd']:
            if key in sample:
                print(f"      {key}: {sample[key]}")

        return True

    except Exception as e:
        print(f"❌ Query failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_record_count():
    """Test 3: Verify record count (should have at least 696 original records)"""
    print("\n" + "="*80)
    print("TEST 3: RECORD COUNT VERIFICATION")
    print("="*80)

    base_url = "https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1"
    api_key = os.environ['SUPABASE_SERVICE_KEY']

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Get count
    response = requests.get(
        f"{base_url}/cmg_programado",
        params={"select": "count"},
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        count = data[0]['count'] if data else 0
        print(f"✅ Total records: {count}")

        if count < 696:
            print(f"⚠️  Expected at least 696 records (original data)")
            print(f"   Only found {count} - some data may be missing!")
            return False

        if count >= 696:
            print(f"✅ Record count looks good (>= 696 original records)")

        return True
    else:
        print(f"❌ Failed to get count: {response.status_code}")
        return False

def test_date_range():
    """Test 4: Check date range of data"""
    print("\n" + "="*80)
    print("TEST 4: DATE RANGE VERIFICATION")
    print("="*80)

    try:
        supabase = SupabaseClient()

        # Get all records (with limit)
        all_records = supabase.get_cmg_programado(limit=50000)

        if not all_records:
            print("❌ No records found")
            return False

        # Get date range
        forecast_dates = sorted(set(
            r['forecast_datetime'].split('T')[0] if 'T' in r['forecast_datetime']
            else r['forecast_datetime'][:10]
            for r in all_records
        ))

        print(f"✅ Found {len(all_records)} total records")
        print(f"   Forecast date range: {forecast_dates[0]} to {forecast_dates[-1]}")
        print(f"   Total unique forecast dates: {len(forecast_dates)}")

        # Count by date
        from collections import defaultdict
        by_date = defaultdict(int)
        for r in all_records:
            date = r['forecast_datetime'].split('T')[0] if 'T' in r['forecast_datetime'] else r['forecast_datetime'][:10]
            by_date[date] += 1

        print(f"\n   Records per date (first 5):")
        for date in forecast_dates[:5]:
            print(f"      {date}: {by_date[date]} records")

        print(f"\n   Records per date (last 5):")
        for date in forecast_dates[-5:]:
            print(f"      {date}: {by_date[date]} records")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_api_endpoint():
    """Test 5: Verify API endpoint works (no 400 error)"""
    print("\n" + "="*80)
    print("TEST 5: API ENDPOINT TEST")
    print("="*80)

    try:
        response = requests.get(
            "https://pudidicmgprediction.vercel.app/api/historical_comparison",
            timeout=30
        )

        print(f"   Status Code: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ API returned error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False

        data = response.json()

        if not data.get('success'):
            print(f"❌ API returned success=false")
            print(f"   Error: {data.get('error')}")
            return False

        metadata = data.get('metadata', {})
        print(f"✅ API endpoint working!")
        print(f"\n   Response metadata:")
        print(f"      ML forecast count: {metadata.get('ml_forecast_count')}")
        print(f"      Programado forecast count: {metadata.get('programado_forecast_count')}")
        print(f"      Programado record count: {metadata.get('programado_count')}")
        print(f"      Online record count: {metadata.get('online_count')}")

        if metadata.get('programado_forecast_count', 0) == 0:
            print(f"\n⚠️  WARNING: No CMG Programado forecasts in API response!")
            print(f"   The backfill script may not have run yet.")
            return False

        return True

    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False

def main():
    print("="*80)
    print("CMG PROGRAMADO MIGRATION VERIFICATION")
    print("="*80)
    print("\nThis script verifies that:")
    print("1. Database schema has new columns (forecast_datetime, target_datetime, etc.)")
    print("2. SupabaseClient can query with new schema (no 400 errors)")
    print("3. Record count is preserved (at least 696 original records)")
    print("4. Date range looks reasonable")
    print("5. API endpoints return data correctly")

    # Check environment variables
    if not os.environ.get('SUPABASE_URL') or not os.environ.get('SUPABASE_SERVICE_KEY'):
        print("\n❌ Missing environment variables!")
        print("   Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        sys.exit(1)

    # Run all tests
    results = {
        "Schema": test_database_schema(),
        "Client Query": test_supabase_client(),
        "Record Count": test_record_count(),
        "Date Range": test_date_range(),
        "API Endpoint": test_api_endpoint()
    }

    # Summary
    print("\n" + "="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)

    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Migration successful!")
        print("\nNext steps:")
        print("1. Run backfill script to add 29 days of historical data")
        print("2. Test forecast_comparison.html frontend")
        print("3. Verify hourly workflows populate data correctly")
    else:
        print("\n⚠️  SOME TESTS FAILED - Check errors above")
        print("\nTroubleshooting:")
        print("1. Verify SQL migration ran successfully in Supabase")
        print("2. Check for error messages in SQL Editor")
        print("3. Try re-running the SQL migration")

    print("\n" + "="*80)

if __name__ == "__main__":
    main()
