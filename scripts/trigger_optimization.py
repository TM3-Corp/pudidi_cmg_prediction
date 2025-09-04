#!/usr/bin/env python3
"""
Trigger optimization and store results for testing
Can be run manually or scheduled to run at specific times (e.g., 17:00 daily)
"""

import requests
import json
from datetime import datetime
import pytz

def trigger_optimization():
    """Trigger optimization through the API"""
    
    # API endpoint (adjust for local or deployed version)
    api_url = "https://pudidicmgprediction.vercel.app/api/optimizer"
    
    # Optimization parameters
    params = {
        "horizon": 24,
        "node": "PMontt220",
        "p_min": 0.5,
        "p_max": 3.0,
        "s0": 25000,
        "s_min": 1000,
        "s_max": 50000,
        "kappa": 0.667,
        "inflow": 2.5
    }
    
    try:
        print(f"🚀 Triggering optimization at {datetime.now()}")
        print(f"   Parameters: {json.dumps(params, indent=2)}")
        
        # Send POST request
        response = requests.post(api_url, json=params, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('success'):
                solution = result.get('solution', {})
                print("✅ Optimization successful!")
                print(f"   Revenue: ${solution.get('revenue', 0):.2f}")
                print(f"   Avg Generation: {solution.get('avg_generation', 0):.2f} MW")
                print(f"   Capacity Factor: {solution.get('capacity_factor', 0):.1f}%")
                print("   Results have been automatically stored to Gist")
                return True
            else:
                print(f"❌ Optimization failed: {result.get('error')}")
                return False
        else:
            print(f"❌ API request failed: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ Error triggering optimization: {e}")
        return False

def main():
    """Main execution"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print(f"{'='*60}")
    print(f"CMG PROGRAMADO OPTIMIZATION TRIGGER")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"{'='*60}")
    
    success = trigger_optimization()
    
    if success:
        print("\n✅ Optimization completed and stored successfully")
    else:
        print("\n❌ Optimization failed")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())