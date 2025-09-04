#!/usr/bin/env python3
"""
Create all necessary Gists for the performance tracking system
This script creates the Gists and shows their IDs for configuration
"""

import os
import json
import requests
from datetime import datetime
import pytz

def create_or_update_gist(token, gist_id, filename, description, content):
    """Create or update a GitHub Gist"""
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # First check if the gist exists
    if gist_id and gist_id != 'placeholder':
        response = requests.get(f'https://api.github.com/gists/{gist_id}', headers=headers)
        if response.status_code == 200:
            # Update existing gist
            print(f"📝 Updating existing gist {gist_id}")
            payload = {
                'files': {
                    filename: {
                        'content': json.dumps(content, indent=2)
                    }
                }
            }
            response = requests.patch(
                f'https://api.github.com/gists/{gist_id}',
                headers=headers,
                json=payload
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to update: {response.status_code}")
                return None
    
    # Create new gist
    print(f"🆕 Creating new gist: {description}")
    payload = {
        'description': description,
        'public': True,
        'files': {
            filename: {
                'content': json.dumps(content, indent=2)
            }
        }
    }
    
    response = requests.post(
        'https://api.github.com/gists',
        headers=headers,
        json=payload
    )
    
    if response.status_code == 201:
        return response.json()
    else:
        print(f"Failed to create: {response.status_code} - {response.text}")
        return None

def main():
    """Main execution"""
    print("="*60)
    print("CREATING ALL PERFORMANCE TRACKING GISTS")
    print("="*60)
    
    # Get GitHub token
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("❌ GITHUB_TOKEN not found in environment")
        print("   This script must be run in GitHub Actions or with token set")
        return 1
    
    print(f"✅ Using GitHub token: {token[:10]}...{token[-4:]}")
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    created_gists = {}
    
    # 1. Create CMG Programado Gist (our own copy)
    print("\n📊 Creating CMG Programado Gist...")
    cmg_content = {
        "metadata": {
            "created": now.isoformat(),
            "description": "CMG Programado Historical Data",
            "info": "Preserves historical values, updates future forecasts"
        },
        "data": {}
    }
    
    result = create_or_update_gist(
        token,
        None,  # Create new
        'cmg_programado_historical.json',
        'Pudidi CMG Programado Historical Data',
        cmg_content
    )
    
    if result:
        created_gists['cmg_programado'] = {
            'id': result['id'],
            'url': result['html_url']
        }
        print(f"✅ Created: {result['html_url']}")
    else:
        print("❌ Failed to create CMG Programado gist")
    
    # 2. Create Optimization Results Gist
    print("\n🎯 Creating Optimization Results Gist...")
    opt_content = {
        "metadata": {
            "created": now.isoformat(),
            "description": "Daily optimization results"
        }
    }
    
    result = create_or_update_gist(
        token,
        None,  # Create new
        'optimization_results.json',
        'Pudidi Optimization Results',
        opt_content
    )
    
    if result:
        created_gists['optimization'] = {
            'id': result['id'],
            'url': result['html_url']
        }
        print(f"✅ Created: {result['html_url']}")
    else:
        print("❌ Failed to create Optimization gist")
    
    # 3. Create Performance History Gist
    print("\n📈 Creating Performance History Gist...")
    perf_content = {
        "metadata": {
            "created": now.isoformat(),
            "description": "Daily performance metrics"
        }
    }
    
    result = create_or_update_gist(
        token,
        None,  # Create new
        'performance_history.json',
        'Pudidi Performance History',
        perf_content
    )
    
    if result:
        created_gists['performance'] = {
            'id': result['id'],
            'url': result['html_url']
        }
        print(f"✅ Created: {result['html_url']}")
    else:
        print("❌ Failed to create Performance gist")
    
    # Save configuration
    print("\n💾 Saving configuration...")
    config = {
        "created": now.isoformat(),
        "gists": created_gists,
        "update_instructions": {
            "scripts/update_cmg_programado.py": f"GIST_ID = '{created_gists.get('cmg_programado', {}).get('id', 'NOT_CREATED')}'",
            "api/optimizer.py": f"OPTIMIZATION_GIST_ID = '{created_gists.get('optimization', {}).get('id', 'NOT_CREATED')}'",
            "scripts/daily_performance_calculation.py": {
                "OPTIMIZATION_GIST": created_gists.get('optimization', {}).get('id', 'NOT_CREATED'),
                "PERFORMANCE_GIST": created_gists.get('performance', {}).get('id', 'NOT_CREATED')
            },
            "api/performance.py": f"gist_id = '{created_gists.get('optimization', {}).get('id', 'NOT_CREATED')}'"
        }
    }
    
    with open('gist_configuration.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\n" + "="*60)
    print("✅ GIST CREATION COMPLETE!")
    print("="*60)
    print("\n📝 Created Gists:")
    for name, info in created_gists.items():
        print(f"  {name}:")
        print(f"    ID: {info['id']}")
        print(f"    URL: {info['url']}")
    
    print("\n📋 Next Steps:")
    print("1. Update the script files with the new Gist IDs")
    print("2. The configuration has been saved to gist_configuration.json")
    print("3. Check your gists at: https://gist.github.com/PVSH97")
    
    return 0

if __name__ == "__main__":
    exit(main())