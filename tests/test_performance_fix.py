#!/usr/bin/env python3
"""
Test script to verify Performance API fixes
"""
import json
import sys
import os
from datetime import datetime

# Add API directory to path
sys.path.insert(0, 'api')

def test_data_availability():
    """Test the hour counting fix"""
    print("="*60)
    print("TEST 1: Data Availability Hour Counting")
    print("="*60)
    
    # Read cache directly
    with open('data/cache/cmg_online_historical.json', 'r') as f:
        data = json.load(f)
    
    # Import performance handler
    os.environ['GITHUB_ACTIONS'] = 'false'  # Ensure we're not in CI mode
    
    # Import the methods directly since handler is a BaseHTTPRequestHandler
    from performance import handler
    
    # Create a mock instance with the methods we need
    class MockHandler:
        pass
    
    h = MockHandler()
    # Copy the methods we need
    h.get_data_availability = handler.get_data_availability.__get__(h, MockHandler)
    h.fetch_from_gist = handler.fetch_from_gist.__get__(h, MockHandler)
    h.fetch_programmed_dates_from_gist = handler.fetch_programmed_dates_from_gist.__get__(h, MockHandler)
    
    # Get data availability
    result = h.get_data_availability()
    
    print(f"Available: {result.get('available')}")
    print(f"Total days: {result.get('total_days')}")
    print(f"CMG Online hours: {result.get('total_hours_online', 0)}")
    print(f"CMG Programado hours: {result.get('total_hours_programmed', 0)}")
    print(f"Date range: {result.get('oldest_date')} to {result.get('newest_date')}")
    
    # Verify hour count is correct (should be 75, not 68)
    assert result.get('total_hours_online', 0) == 75, f"Expected 75 hours, got {result.get('total_hours_online', 0)}"
    print("✓ Hour counting fixed!")
    
    return result

def test_efficiency_calculation():
    """Test that efficiency is capped at 100%"""
    print("\n" + "="*60)
    print("TEST 2: Efficiency Calculation Cap")
    print("="*60)
    
    from performance import handler
    
    class MockHandler:
        pass
    
    h = MockHandler()
    h.calculate_performance = handler.calculate_performance.__get__(h, MockHandler)
    h.fetch_optimization_results = handler.fetch_optimization_results.__get__(h, MockHandler)
    h.calculate_price_following_dispatch = handler.calculate_price_following_dispatch.__get__(h, MockHandler)
    
    # Test case: programmed revenue > hindsight revenue (should be capped)
    historical_prices = [100, 120, 80, 110] * 6  # 24 hours
    programmed_prices = [90, 110, 85, 105] * 6   # Different forecast
    
    # Parameters for a simple hydro plant
    p_min, p_max = 1.0, 4.0
    s0, s_min, s_max = 50, 10, 100
    kappa = 1.0
    inflow = 2.0
    horizon = 24
    start_date = "2025-09-01T00:00:00"
    
    try:
        results = h.calculate_performance(
            historical_prices, programmed_prices,
            p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon,
            start_date
        )
        
        efficiency = results['summary']['efficiency']
        print(f"Calculated efficiency: {efficiency}%")
        
        # Check if efficiency is capped
        if efficiency > 100:
            print("✗ Efficiency exceeds 100%! Cap not working.")
            return False
        elif efficiency == 99.9:
            print("✓ Efficiency capped at 99.9% (was >100%)")
            return True
        else:
            print(f"✓ Efficiency within bounds: {efficiency}%")
            return True
            
    except Exception as e:
        print(f"Error testing efficiency: {e}")
        return False

def test_multi_day_data():
    """Test multi-day data fetching"""
    print("\n" + "="*60)
    print("TEST 3: Multi-Day Data Fetching")
    print("="*60)
    
    from performance import handler
    
    class MockHandler:
        pass
    
    h = MockHandler()
    h.fetch_historical_prices = handler.fetch_historical_prices.__get__(h, MockHandler)
    h.fetch_from_gist = handler.fetch_from_gist.__get__(h, MockHandler)
    
    # Test fetching 3 days of data
    start_date = "2025-09-02T00:00:00"
    horizon = 72  # 3 days
    node = "NVA_P.MONTT___220"
    
    historical = h.fetch_historical_prices(start_date, horizon, node)
    
    if historical:
        valid_hours = sum(1 for p in historical if p > 0)
        print(f"Requested: {horizon} hours (3 days)")
        print(f"Retrieved: {len(historical)} hours")
        print(f"Valid data: {valid_hours} hours")
        print(f"Data completeness: {valid_hours/horizon*100:.1f}%")
        
        # Check daily breakdown
        for day in range(3):
            day_start = day * 24
            day_end = (day + 1) * 24
            day_prices = historical[day_start:day_end]
            valid_in_day = sum(1 for p in day_prices if p > 0)
            print(f"  Day {day+1}: {valid_in_day}/24 hours")
        
        if valid_hours > 24:
            print("✓ Multi-day data fetching works!")
            return True
        else:
            print("✗ Multi-day data incomplete")
            return False
    else:
        print("✗ No data retrieved")
        return False

if __name__ == "__main__":
    print("Performance API Fix Verification")
    print("="*60)
    print(f"Timestamp: {datetime.now()}")
    print()
    
    # Run tests
    tests_passed = 0
    tests_total = 3
    
    # Test 1: Hour counting
    try:
        test_data_availability()
        tests_passed += 1
    except Exception as e:
        print(f"✗ Test 1 failed: {e}")
    
    # Test 2: Efficiency cap
    try:
        if test_efficiency_calculation():
            tests_passed += 1
    except Exception as e:
        print(f"✗ Test 2 failed: {e}")
    
    # Test 3: Multi-day data
    try:
        if test_multi_day_data():
            tests_passed += 1
    except Exception as e:
        print(f"✗ Test 3 failed: {e}")
    
    # Summary
    print("\n" + "="*60)
    print(f"RESULTS: {tests_passed}/{tests_total} tests passed")
    print("="*60)
    
    if tests_passed == tests_total:
        print("✅ All fixes verified successfully!")
        exit(0)
    else:
        print("❌ Some tests failed. Please review the output above.")
        exit(1)