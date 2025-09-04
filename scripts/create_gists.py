#!/usr/bin/env python3
"""
Create necessary GitHub Gists for the performance tracking system
This script will create two new gists:
1. Optimization Results Gist
2. Performance Metrics Gist
"""

import requests
import json
import os
from datetime import datetime
import pytz

def create_gist(token, name, description, initial_content):
    """Create a new GitHub Gist"""
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    payload = {
        'description': description,
        'public': True,
        'files': {
            name: {
                'content': json.dumps(initial_content, indent=2)
            }
        }
    }
    
    response = requests.post(
        'https://api.github.com/gists',
        headers=headers,
        json=payload
    )
    
    if response.status_code == 201:
        gist_data = response.json()
        return {
            'success': True,
            'id': gist_data['id'],
            'url': gist_data['html_url'],
            'api_url': gist_data['url']
        }
    else:
        return {
            'success': False,
            'error': response.text,
            'status': response.status_code
        }

def main():
    """Main execution"""
    print("="*60)
    print("GITHUB GIST SETUP FOR PERFORMANCE TRACKING")
    print("="*60)
    
    # Get GitHub token
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("\n⚠️  GITHUB_TOKEN not found in environment variables.")
        print("Please provide your GitHub Personal Access Token.")
        print("You can create one at: https://github.com/settings/tokens")
        print("Required scopes: gist")
        token = input("\nEnter GitHub Token: ").strip()
        
        if not token:
            print("❌ No token provided. Exiting.")
            return 1
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    # 1. Create Optimization Results Gist
    print("\n📊 Creating Optimization Results Gist...")
    
    opt_initial = {
        "_metadata": {
            "created": now.isoformat(),
            "description": "Daily optimization results from CMG Programado forecasts",
            "structure": "One optimization per day, stored at 17:00 Chilean time"
        },
        "example_date": {
            "optimization": {
                "timestamp": now.isoformat(),
                "date": now.strftime('%Y-%m-%d'),
                "hour": 17,
                "parameters": {
                    "horizon": 24,
                    "node": "PMontt220",
                    "p_min": 0.5,
                    "p_max": 3.0,
                    "s0": 25000,
                    "s_min": 1000,
                    "s_max": 50000,
                    "kappa": 0.667,
                    "inflow": 2.5
                },
                "results": {
                    "power_schedule": [1.75] * 24,
                    "revenue": 0,
                    "avg_generation": 1.75,
                    "peak_generation": 1.75,
                    "capacity_factor": 58.3
                }
            },
            "version": 1
        }
    }
    
    opt_result = create_gist(
        token,
        'optimization_results.json',
        'Pudidi CMG - Daily Optimization Results',
        opt_initial
    )
    
    if opt_result['success']:
        print(f"✅ Created Optimization Gist")
        print(f"   ID: {opt_result['id']}")
        print(f"   URL: {opt_result['url']}")
    else:
        print(f"❌ Failed to create Optimization Gist: {opt_result['error']}")
        return 1
    
    # 2. Create Performance Metrics Gist
    print("\n📈 Creating Performance Metrics Gist...")
    
    perf_initial = {
        "_metadata": {
            "created": now.isoformat(),
            "description": "Daily performance metrics comparing optimization strategies",
            "metrics": [
                "stable_generation: Fixed 1.75 MW baseline",
                "optimized: Using CMG Programado forecast",
                "perfect_hindsight: Using actual CMG Online values"
            ]
        },
        "example_date": {
            "date": now.strftime('%Y-%m-%d'),
            "timestamp": now.isoformat(),
            "cmg_online_hours": 24,
            "optimization_available": True,
            "results": {
                "revenues": {
                    "stable": 1000.00,
                    "optimized": 1100.00,
                    "perfect_hindsight": 1200.00
                },
                "metrics": {
                    "improvement_vs_stable": 10.0,
                    "efficiency": 91.7,
                    "gap_to_perfect": 100.00
                }
            },
            "parameters": {
                "p_min": 0.5,
                "p_max": 3.0,
                "s0": 25000,
                "s_min": 1000,
                "s_max": 50000,
                "kappa": 0.667,
                "inflow": 2.5
            }
        }
    }
    
    perf_result = create_gist(
        token,
        'performance_history.json',
        'Pudidi CMG - Daily Performance Metrics',
        perf_initial
    )
    
    if perf_result['success']:
        print(f"✅ Created Performance Gist")
        print(f"   ID: {perf_result['id']}")
        print(f"   URL: {perf_result['url']}")
    else:
        print(f"❌ Failed to create Performance Gist: {perf_result['error']}")
        return 1
    
    # 3. Generate configuration updates
    print("\n📝 Configuration Updates Needed:")
    print("="*60)
    print("Update the following files with the new Gist IDs:\n")
    
    print("1. In api/optimizer.py:")
    print(f"   OPTIMIZATION_GIST_ID = '{opt_result['id']}'")
    
    print("\n2. In scripts/daily_performance_calculation.py:")
    print(f"   OPTIMIZATION_GIST = '{opt_result['id']}'")
    print(f"   PERFORMANCE_GIST = '{perf_result['id']}'")
    
    print("\n3. In api/performance.py (line ~412):")
    print(f"   gist_id = '{opt_result['id']}'")
    
    # 4. Save configuration to file
    config = {
        "optimization_gist": {
            "id": opt_result['id'],
            "url": opt_result['url'],
            "created": now.isoformat()
        },
        "performance_gist": {
            "id": perf_result['id'],
            "url": perf_result['url'],
            "created": now.isoformat()
        },
        "update_instructions": {
            "api/optimizer.py": f"OPTIMIZATION_GIST_ID = '{opt_result['id']}'",
            "scripts/daily_performance_calculation.py": {
                "OPTIMIZATION_GIST": opt_result['id'],
                "PERFORMANCE_GIST": perf_result['id']
            },
            "api/performance.py": f"gist_id = '{opt_result['id']}'"
        }
    }
    
    with open('gist_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\n✅ Configuration saved to gist_config.json")
    print("\n" + "="*60)
    print("🎉 SETUP COMPLETE!")
    print("="*60)
    print("\nNext steps:")
    print("1. Update the files mentioned above with the new Gist IDs")
    print("2. Commit and push the changes")
    print("3. Add GITHUB_TOKEN to your repository secrets")
    print("4. The system will start collecting data automatically")
    
    return 0

if __name__ == "__main__":
    exit(main())