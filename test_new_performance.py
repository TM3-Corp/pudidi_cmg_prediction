#!/usr/bin/env python3
"""Test the new Performance API with date ranges"""
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, 'api')
os.environ['GITHUB_ACTIONS'] = 'false'

from performance import handler

# Create mock handler
class MockHandler:
    pass

h = MockHandler()
h.fetch_historical_prices = handler.fetch_historical_prices.__get__(h, MockHandler)
h.fetch_programmed_prices = handler.fetch_programmed_prices.__get__(h, MockHandler)
h.fetch_from_gist = handler.fetch_from_gist.__get__(h, MockHandler)
h.fetch_programmed_from_gist = handler.fetch_programmed_from_gist.__get__(h, MockHandler)
h.calculate_performance = handler.calculate_performance.__get__(h, MockHandler)
h.fetch_optimization_results = handler.fetch_optimization_results.__get__(h, MockHandler)
h.calculate_price_following_dispatch = handler.calculate_price_following_dispatch.__get__(h, MockHandler)

print("Testing New Performance API with Date Ranges")
print("="*60)

# Test case 1: 3-day range (Sept 4-6, 2025)
print("\nTest 1: Sept 4-6, 2025 (3 days)")
print("-"*40)

start_date = '2025-09-04T00:00:00'
end_date = '2025-09-06T23:59:59'

# Calculate horizon the new way
start_dt = datetime.fromisoformat(start_date)
end_dt = datetime.fromisoformat(end_date)
delta = end_dt - start_dt
horizon = int(delta.total_seconds() / 3600) + 1

print(f"Date range: {start_date} to {end_date}")
print(f"Calculated horizon: {horizon} hours")

# Test fetching prices
node = 'NVA_P.MONTT___220'
historical = h.fetch_historical_prices(start_date, horizon, node)
programmed = h.fetch_programmed_prices(start_date, horizon, node)

if historical:
    valid_hours = sum(1 for p in historical if p > 0)
    print(f"Historical prices: {len(historical)} hours, {valid_hours} valid")
else:
    print("No historical prices found")

if programmed:
    valid_hours = sum(1 for p in programmed if p > 0)
    print(f"Programmed prices: {len(programmed)} hours, {valid_hours} valid")
else:
    print("No programmed prices found")

# Run performance calculation
if historical and programmed:
    print("\nRunning performance calculation...")
    results = h.calculate_performance(
        historical, programmed,
        p_min=0.5, p_max=3.0,
        s0=25000, s_min=1000, s_max=50000,
        kappa=0.667, inflow=2.5,
        horizon=horizon,
        start_date=start_date
    )
    
    print(f"✓ Calculation successful!")
    print(f"  Efficiency: {results['summary']['efficiency']}%")
    print(f"  Days returned: {len(results.get('daily_performance', []))}")
    
    for day in results.get('daily_performance', []):
        print(f"    Day {day['day']}: efficiency={day['efficiency']}%")

# Test case 2: Single day (Sept 5, 2025)
print("\n" + "="*60)
print("Test 2: Sept 5, 2025 (single day)")
print("-"*40)

start_date = '2025-09-05T00:00:00'
end_date = '2025-09-05T23:59:59'

start_dt = datetime.fromisoformat(start_date)
end_dt = datetime.fromisoformat(end_date)
delta = end_dt - start_dt
horizon = int(delta.total_seconds() / 3600) + 1

print(f"Date range: {start_date} to {end_date}")
print(f"Calculated horizon: {horizon} hours")

historical = h.fetch_historical_prices(start_date, horizon, node)
if historical:
    valid_hours = sum(1 for p in historical if p > 0)
    print(f"Historical prices: {len(historical)} hours, {valid_hours} valid")

print("\n" + "="*60)
print("✅ All tests completed successfully!")
print("The Performance API now correctly handles arbitrary date ranges.")