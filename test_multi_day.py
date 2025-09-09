#!/usr/bin/env python3
"""Test multi-day performance calculation"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, 'api')
os.environ['GITHUB_ACTIONS'] = 'false'

# Test the actual calculation
from performance import handler

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

# Test Sept 4-6 period
start_date = '2025-09-04T00:00:00'
horizon = 72  # 3 days
node = 'NVA_P.MONTT___220'

print('Testing 3-day period (Sept 4-6, 2025)')
print('='*60)

# Fetch prices
historical = h.fetch_historical_prices(start_date, horizon, node)
programmed = h.fetch_programmed_prices(start_date, horizon, node)

if historical:
    print(f'Historical prices fetched: {len(historical)} hours')
    for day in range(3):
        day_start = day * 24
        day_end = (day + 1) * 24
        day_prices = historical[day_start:day_end]
        valid = sum(1 for p in day_prices if p > 0)
        print(f'  Day {day+1}: {valid}/24 valid hours, sum=${sum(day_prices):.2f}')
else:
    print('No historical prices found')

if programmed:
    print(f'\nProgrammed prices fetched: {len(programmed)} hours')
    for day in range(3):
        day_start = day * 24
        day_end = (day + 1) * 24
        day_prices = programmed[day_start:day_end] if programmed else []
        valid = sum(1 for p in day_prices if p > 0)
        print(f'  Day {day+1}: {valid}/24 valid hours')
else:
    print('\nNo programmed prices found')

# Now run the actual performance calculation
print('\n' + '='*60)
print('Running performance calculation...')

if historical and programmed:
    # Use realistic hydro parameters
    results = h.calculate_performance(
        historical, programmed,
        p_min=1.0, p_max=4.0,
        s0=50, s_min=10, s_max=100,
        kappa=1.0, inflow=2.0,
        horizon=horizon,
        start_date=start_date
    )
    
    print(f"\nSummary:")
    print(f"  Total horizon: {results['summary']['horizon']} hours")
    print(f"  Revenue stable: ${results['summary']['revenue_stable']}")
    print(f"  Revenue programmed: ${results['summary']['revenue_programmed']}")
    print(f"  Revenue hindsight: ${results['summary']['revenue_hindsight']}")
    print(f"  Efficiency: {results['summary']['efficiency']}%")
    
    print(f"\nDaily Performance (should have 3 days):")
    daily = results.get('daily_performance', [])
    print(f"  Days returned: {len(daily)}")
    
    for day_data in daily:
        print(f"\n  Day {day_data['day']}:")
        print(f"    Revenue stable: ${day_data['revenue_stable']}")
        print(f"    Revenue programmed: ${day_data['revenue_programmed']}")
        print(f"    Revenue hindsight: ${day_data['revenue_hindsight']}")
        print(f"    Efficiency: {day_data['efficiency']}%")
    
    if len(daily) < 3:
        print(f"\n⚠️ PROBLEM: Only {len(daily)} days returned instead of 3!")
        print("This explains why you only see Day 1 in the UI.")
    else:
        print("\n✓ All 3 days are being calculated by the backend.")
        print("The issue might be in the frontend display.")
else:
    print("Cannot run calculation - missing price data")