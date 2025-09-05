#!/usr/bin/env python3
"""
Create a new GitHub Gist specifically for CMG Programado historical storage
This ensures we have a reliable, gap-free storage separate from partner's Gist
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

def create_cmg_programado_gist(token):
    """Create a new Gist for CMG Programado historical data"""
    
    # Load our current CMG Programado data
    local_path = Path('data/cmg_programado_history.json')
    if local_path.exists():
        with open(local_path, 'r') as f:
            data = json.load(f)
        print(f"✅ Loaded local data: {len(data.get('historical_data', {}))} days")
    else:
        print("❌ No local CMG Programado data found")
        return None
    
    # Prepare Gist content
    gist_content = {
        'description': f'CMG Programado Historical Data - Created {datetime.now().strftime("%Y-%m-%d")}',
        'public': True,  # Make it public for easy access
        'files': {
            'cmg_programado_historical.json': {
                'content': json.dumps(data, indent=2, ensure_ascii=False)
            },
            'README.md': {
                'content': f"""# CMG Programado Historical Data

This Gist stores historical CMG Programado (forecast) data for the Chilean electrical system.

## Purpose
- Reliable storage of CMG Programado forecasts
- Preserves all historical data (no gaps or overwrites)
- Used for performance analysis comparing forecasts vs actual values

## Data Structure
```json
{{
  "historical_data": {{
    "YYYY-MM-DD": {{
      "0": {{"value": 123.4, "node": "PMontt220", ...}},
      "1": {{"value": 125.6, "node": "PMontt220", ...}},
      ...
      "23": {{"value": 120.1, "node": "PMontt220", ...}}
    }}
  }},
  "metadata": {{
    "last_update": "ISO timestamp",
    "total_days": N,
    "total_hours": M,
    "node": "PMontt220"
  }}
}}
```

## Coverage
- Node: PMontt220
- Current range: {sorted(data.get('historical_data', {}).keys())[0]} to {sorted(data.get('historical_data', {}).keys())[-1]}
- Total days: {len(data.get('historical_data', {}))}
- Total hours: {sum(len(hours) for hours in data.get('historical_data', {}).values())}

## Update Schedule
- Daily sync from partner's Gist
- Preserves all historical values
- Only updates future forecasts

Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            }
        }
    }
    
    # Create the Gist
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    response = requests.post(
        'https://api.github.com/gists',
        headers=headers,
        json=gist_content
    )
    
    if response.status_code in (200, 201):
        gist_data = response.json()
        gist_id = gist_data['id']
        gist_url = gist_data['html_url']
        
        print("\n✅ CMG Programado Gist created successfully!")
        print(f"   ID: {gist_id}")
        print(f"   URL: {gist_url}")
        
        # Save the Gist ID for future use
        config = {
            'cmg_programado_gist': {
                'id': gist_id,
                'url': gist_url,
                'created_at': datetime.now().isoformat(),
                'description': 'CMG Programado Historical Storage'
            }
        }
        
        config_path = Path('cmg_programado_gist_config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"   Config saved to: {config_path}")
        
        return gist_id
    else:
        print(f"❌ Failed to create Gist: {response.status_code}")
        print(f"   Response: {response.text}")
        return None

def main():
    """Main execution"""
    print("="*60)
    print("CREATE CMG PROGRAMADO GIST")
    print("="*60)
    print("This will create a new GitHub Gist for reliable")
    print("CMG Programado historical data storage")
    print()
    
    # Get GitHub token
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("❌ GITHUB_TOKEN not set")
        print("\nTo create the Gist, run:")
        print("export GITHUB_TOKEN='your_github_token'")
        print("python scripts/create_cmg_programado_gist.py")
        return 1
    
    # Create the Gist
    gist_id = create_cmg_programado_gist(token)
    
    if gist_id:
        print("\n" + "="*60)
        print("NEXT STEPS:")
        print("="*60)
        print(f"1. Your new CMG Programado Gist ID: {gist_id}")
        print("2. Update scripts to use this Gist ID")
        print("3. The workflow will maintain this Gist with no gaps")
        print("\nArchitecture:")
        print("• CMG Online Gist: 8d7864eb26acf6e780d3c0f7fed69365 (yours)")
        print(f"• CMG Programado Gist: {gist_id} (yours - new)")
        print("• Partner's Gist: a63a3a10479bafcc29e10aaca627bc73 (source)")
        return 0
    else:
        return 1

if __name__ == "__main__":
    exit(main())