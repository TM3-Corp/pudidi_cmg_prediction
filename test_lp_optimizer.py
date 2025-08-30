#!/usr/bin/env python3
"""
Test the Linear Programming optimizer locally
"""

import sys
sys.path.append('api')

from optimizer_lp import optimize_hydro_lp, optimize_hydro_greedy
import json

# Load real prices from cache
with open('data/cache/cmg_programmed_latest.json', 'r') as f:
    cache = json.load(f)

# Extract prices
prices = [record['cmg_programmed'] for record in cache['data'][:24]]

print("="*60)
print("TESTING LINEAR PROGRAMMING OPTIMIZER")
print("="*60)
print(f"Using {len(prices)} real CMG prices from cache")
print(f"Price range: ${min(prices):.2f} - ${max(prices):.2f}/MWh")
print(f"First 5 prices: {prices[:5]}")
print("="*60)

# Test parameters
params = {
    'p_min': 0.5,
    'p_max': 3.0,
    's0': 25000,
    's_min': 1000,
    's_max': 50000,
    'kappa': 0.667,
    'inflow': 1.1,
    'horizon': 24
}

print("\nParameters:")
for k, v in params.items():
    print(f"  {k}: {v}")

print("\n" + "="*60)
print("Running LP optimization...")
print("="*60)

# Run LP optimization
solution_lp = optimize_hydro_lp(
    prices,
    params['p_min'], params['p_max'],
    params['s0'], params['s_min'], params['s_max'],
    params['kappa'], params['inflow'], params['horizon']
)

if solution_lp:
    print("\n✅ LP OPTIMIZATION SUCCESSFUL!")
    print(f"Method: {solution_lp['optimization_method']}")
    print(f"Revenue: ${solution_lp['revenue']:.2f}")
    print(f"Avg Generation: {solution_lp['avg_generation']:.2f} MW")
    print(f"Capacity Factor: {solution_lp['capacity_factor']:.1f}%")
    
    # Show generation pattern
    P = solution_lp['P']
    high_hours = [i for i, p in enumerate(P) if p > 2.5]
    print(f"\nHigh generation hours (>2.5 MW): {high_hours[:10]}{'...' if len(high_hours) > 10 else ''}")
else:
    print("\n❌ LP optimization failed, testing greedy fallback...")
    
    solution_greedy = optimize_hydro_greedy(
        prices,
        params['p_min'], params['p_max'],
        params['s0'], params['s_min'], params['s_max'],
        params['kappa'], params['inflow'], params['horizon']
    )
    
    print(f"\nGreedy Result:")
    print(f"Revenue: ${solution_greedy['revenue']:.2f}")
    print(f"Avg Generation: {solution_greedy['avg_generation']:.2f} MW")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)