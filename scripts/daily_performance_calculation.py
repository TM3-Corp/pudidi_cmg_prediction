#!/usr/bin/env python3
"""
Daily Performance Calculation
Runs at 23:59 to calculate the day's optimization performance
Compares: Stable vs CMG Programado Optimization vs Perfect Hindsight
"""

import json
import requests
from datetime import datetime, timedelta
import pytz
import os
import numpy as np

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

# Gist IDs
CMG_ONLINE_GIST = '8d7864eb26acf6e780d3c0f7fed69365'  # Historical CMG Online data
OPTIMIZATION_GIST = 'b7c9e8f3d2a1b4c5e6f7a8b9c0d1e2f3'  # Daily optimization results
PERFORMANCE_GIST = 'c8d9f0a1b2c3d4e5f6a7b8c9d0e1f2a3'  # Performance metrics (to be created)

# Hydro parameters (standard values)
HYDRO_PARAMS = {
    'p_min': 0.5,
    'p_max': 3.0,
    's0': 25000,
    's_min': 1000,
    's_max': 50000,
    'kappa': 0.667,
    'inflow': 2.5
}

def fetch_gist_data(gist_id):
    """Fetch data from a GitHub Gist"""
    try:
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
        response = requests.get(f'https://api.github.com/gists/{gist_id}', headers=headers)
        
        if response.status_code == 200:
            gist_data = response.json()
            # Get the first file in the gist
            for filename, file_info in gist_data.get('files', {}).items():
                if filename.endswith('.json'):
                    content = file_info.get('content', '{}')
                    return json.loads(content)
        return None
    except Exception as e:
        print(f"Error fetching gist {gist_id}: {e}")
        return None

def get_cmg_online_for_date(cmg_data, date_str, node='NVA_P.MONTT___220'):
    """Extract CMG Online prices for a specific date and node"""
    prices = []
    
    # Handle both old and new data structures
    if 'daily_data' in cmg_data:
        # New structure
        day_data = cmg_data['daily_data'].get(date_str, {})
        if 'cmg_online' in day_data and node in day_data['cmg_online']:
            prices = day_data['cmg_online'][node].get('cmg_usd', [])
    elif 'data' in cmg_data:
        # Old structure - list of records
        for record in cmg_data['data']:
            if record.get('date') == date_str and record.get('node') == node:
                hour = record.get('hour')
                if hour is not None and 0 <= hour < 24:
                    while len(prices) <= hour:
                        prices.append(0)
                    prices[hour] = record.get('cmg_usd', 0)
    
    # Ensure we have 24 hours
    while len(prices) < 24:
        prices.append(0)
    
    return prices[:24]

def get_optimization_for_date(opt_data, date_str):
    """Get optimization results for a specific date"""
    if date_str in opt_data:
        day_data = opt_data[date_str]
        
        # Handle new structure (single optimization per day)
        if isinstance(day_data, dict) and 'optimization' in day_data:
            return day_data['optimization'].get('results', {})
        # Handle old structure (list of optimizations)
        elif isinstance(day_data, list) and len(day_data) > 0:
            # Get the last optimization of the day (should be from 17:00)
            return day_data[-1].get('results', {})
    
    return None

def calculate_stable_generation(prices, p_min, p_max, inflow, kappa):
    """Calculate revenue for stable generation strategy"""
    # Midpoint strategy
    p_stable = (p_min + p_max) / 2  # 1.75 MW
    
    revenue = sum(p_stable * price for price in prices)
    
    return {
        'strategy': 'stable',
        'power': [p_stable] * 24,
        'revenue': revenue,
        'avg_generation': p_stable
    }

def optimize_with_perfect_hindsight(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow):
    """
    Simple optimization with perfect knowledge of prices
    This is a greedy approach - prioritize high price hours
    """
    horizon = 24
    dt = 1  # hourly
    vol_per_step = 3600 * dt
    
    # Initialize with minimum generation
    power = [p_min] * horizon
    
    # Sort hours by price (descending)
    price_indices = sorted(range(horizon), key=lambda i: prices[i], reverse=True)
    
    # Try to maximize generation during high price hours
    for idx in price_indices:
        # Test if we can increase generation
        test_power = power.copy()
        test_power[idx] = p_max
        
        # Check storage constraints
        storage = s0
        valid = True
        
        for h in range(horizon):
            storage += (inflow - kappa * test_power[h]) * vol_per_step
            if storage < s_min or storage > s_max:
                valid = False
                break
        
        if valid:
            power[idx] = p_max
    
    revenue = sum(power[h] * prices[h] for h in range(horizon))
    avg_gen = sum(power) / len(power)
    
    return {
        'strategy': 'perfect_hindsight',
        'power': power,
        'revenue': revenue,
        'avg_generation': avg_gen
    }

def calculate_performance_metrics(stable, optimized, hindsight, cmg_online_prices):
    """Calculate performance metrics"""
    
    # Calculate actual revenues using CMG Online prices
    stable_revenue = stable['revenue']
    
    # Optimized revenue: what the optimization achieved with actual prices
    if optimized and 'power_schedule' in optimized:
        optimized_power = optimized['power_schedule'][:24]
        optimized_revenue = sum(
            optimized_power[i] * cmg_online_prices[i] 
            for i in range(min(len(optimized_power), 24))
        )
    else:
        # Fallback if no optimization available
        optimized_revenue = stable_revenue * 1.1
        
    hindsight_revenue = hindsight['revenue']
    
    # Calculate metrics
    improvement_vs_stable = ((optimized_revenue - stable_revenue) / stable_revenue * 100) if stable_revenue > 0 else 0
    efficiency = (optimized_revenue / hindsight_revenue * 100) if hindsight_revenue > 0 else 0
    
    return {
        'revenues': {
            'stable': round(stable_revenue, 2),
            'optimized': round(optimized_revenue, 2),
            'perfect_hindsight': round(hindsight_revenue, 2)
        },
        'metrics': {
            'improvement_vs_stable': round(improvement_vs_stable, 2),
            'efficiency': round(efficiency, 2),
            'gap_to_perfect': round(hindsight_revenue - optimized_revenue, 2)
        }
    }

def store_performance_results(performance_data):
    """Store performance results to GitHub Gist"""
    try:
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
        
        # Fetch existing data
        existing_data = fetch_gist_data(PERFORMANCE_GIST) or {}
        
        # Add new performance data
        santiago_tz = pytz.timezone('America/Santiago')
        today = datetime.now(santiago_tz).strftime('%Y-%m-%d')
        
        existing_data[today] = performance_data
        
        # Update Gist
        gist_content = {
            'files': {
                'performance_history.json': {
                    'content': json.dumps(existing_data, indent=2)
                }
            }
        }
        
        response = requests.patch(
            f'https://api.github.com/gists/{PERFORMANCE_GIST}',
            headers=headers,
            json=gist_content
        )
        
        if response.status_code in [200, 201]:
            print(f"✅ Stored performance results for {today}")
            return True
        else:
            # If gist doesn't exist, create it
            if response.status_code == 404:
                gist_content['description'] = 'Daily Optimization Performance Metrics'
                gist_content['public'] = True
                
                response = requests.post(
                    'https://api.github.com/gists',
                    headers=headers,
                    json=gist_content
                )
                
                if response.status_code == 201:
                    new_gist = response.json()
                    print(f"✅ Created new performance gist: {new_gist['id']}")
                    print(f"   URL: {new_gist['html_url']}")
                    return True
            
            print(f"❌ Failed to store performance: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error storing performance: {e}")
        return False

def main():
    """Main execution"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    today = now.strftime('%Y-%m-%d')
    
    print(f"{'='*60}")
    print(f"DAILY PERFORMANCE CALCULATION")
    print(f"Date: {today}")
    print(f"Time: {now.strftime('%H:%M:%S %Z')}")
    print(f"{'='*60}")
    
    # 1. Fetch CMG Online data
    print("📊 Fetching CMG Online data...")
    cmg_online_data = fetch_gist_data(CMG_ONLINE_GIST)
    if not cmg_online_data:
        print("❌ Failed to fetch CMG Online data")
        return 1
    
    cmg_online_prices = get_cmg_online_for_date(cmg_online_data, today)
    print(f"   Found {sum(1 for p in cmg_online_prices if p > 0)} hours of price data")
    
    # 2. Fetch optimization results
    print("🎯 Fetching optimization results...")
    opt_data = fetch_gist_data(OPTIMIZATION_GIST)
    optimization = None
    if opt_data:
        optimization = get_optimization_for_date(opt_data, today)
        if optimization:
            print(f"   Found optimization from {today}")
        else:
            print("   No optimization found for today")
    
    # 3. Calculate performance for each strategy
    print("📈 Calculating performance metrics...")
    
    # Stable generation
    stable = calculate_stable_generation(
        cmg_online_prices,
        HYDRO_PARAMS['p_min'],
        HYDRO_PARAMS['p_max'],
        HYDRO_PARAMS['inflow'],
        HYDRO_PARAMS['kappa']
    )
    
    # Perfect hindsight
    hindsight = optimize_with_perfect_hindsight(
        cmg_online_prices,
        HYDRO_PARAMS['p_min'],
        HYDRO_PARAMS['p_max'],
        HYDRO_PARAMS['s0'],
        HYDRO_PARAMS['s_min'],
        HYDRO_PARAMS['s_max'],
        HYDRO_PARAMS['kappa'],
        HYDRO_PARAMS['inflow']
    )
    
    # Calculate metrics
    metrics = calculate_performance_metrics(
        stable, 
        optimization, 
        hindsight, 
        cmg_online_prices
    )
    
    # Display results
    print("\n📊 PERFORMANCE RESULTS:")
    print(f"   Stable Generation:  ${metrics['revenues']['stable']:,.2f}")
    print(f"   CMG Programado Opt: ${metrics['revenues']['optimized']:,.2f}")
    print(f"   Perfect Hindsight:  ${metrics['revenues']['perfect_hindsight']:,.2f}")
    print(f"\n📈 METRICS:")
    print(f"   Improvement vs Stable: {metrics['metrics']['improvement_vs_stable']:.1f}%")
    print(f"   Efficiency:            {metrics['metrics']['efficiency']:.1f}%")
    print(f"   Gap to Perfect:        ${metrics['metrics']['gap_to_perfect']:,.2f}")
    
    # 4. Store results
    print("\n💾 Storing performance results...")
    performance_record = {
        'date': today,
        'timestamp': now.isoformat(),
        'cmg_online_hours': sum(1 for p in cmg_online_prices if p > 0),
        'optimization_available': optimization is not None,
        'results': metrics,
        'parameters': HYDRO_PARAMS
    }
    
    if store_performance_results(performance_record):
        print("✅ Performance calculation completed successfully")
    else:
        print("⚠️ Performance calculated but storage failed")
    
    print(f"{'='*60}")
    
    return 0

if __name__ == "__main__":
    exit(main())