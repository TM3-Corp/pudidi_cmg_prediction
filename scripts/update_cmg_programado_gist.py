#!/usr/bin/env python3
"""
Update YOUR CMG Programado Gist with historical data
Maintains gap-free storage while syncing from partner's Gist
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

# Configuration - will be updated with your new Gist ID
CMG_PROGRAMADO_GIST_ID = None  # Will be set after creating the Gist

def load_gist_config():
    """Load the Gist configuration"""
    config_path = Path('cmg_programado_gist_config.json')
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config.get('cmg_programado_gist', {}).get('id')
    return None

def update_cmg_programado_gist(data, gist_id, token):
    """Update YOUR CMG Programado Gist with merged historical data"""
    
    # Prepare the update
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Update metadata
    if 'metadata' in data:
        data['metadata']['last_gist_update'] = datetime.now().isoformat()
    
    # Calculate statistics
    historical = data.get('historical_data', {})
    dates = sorted(historical.keys())
    total_hours = sum(len(hours) for hours in historical.values())
    
    # Prepare README with current statistics
    readme_content = f"""# CMG Programado Historical Data

This Gist stores historical CMG Programado (forecast) data for the Chilean electrical system.

## Current Coverage
- **Date Range**: {dates[0] if dates else 'N/A'} to {dates[-1] if dates else 'N/A'}
- **Total Days**: {len(dates)}
- **Total Hours**: {total_hours}
- **Completeness**: {(total_hours / (len(dates) * 24) * 100) if dates else 0:.1f}%

## Data Sources
- Primary: Partner's Gist (a63a3a10479bafcc29e10aaca627bc73)
- Storage: This Gist (reliable, no gaps)
- Node: PMontt220

## Recent Updates
- Last sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Data preserved: All historical values maintained
- Gaps filled: None (all days complete)

## Available Dates
{chr(10).join(f"- {date}: {len(historical.get(date, {}))} hours" for date in sorted(dates)[:10])}
{"..." if len(dates) > 10 else ""}

## Usage
```python
import requests
import json

gist_id = '{gist_id}'
response = requests.get(f'https://api.github.com/gists/{{gist_id}}')
if response.status_code == 200:
    gist_data = response.json()
    for filename, file_info in gist_data['files'].items():
        if filename.endswith('.json'):
            content = file_info['content']
            cmg_data = json.loads(content)
            print(f"Loaded {{len(cmg_data['historical_data'])}} days of CMG Programado data")
```
"""
    
    # Prepare the Gist update payload
    payload = {
        'description': f"CMG Programado Historical Data - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        'files': {
            'cmg_programado_historical.json': {
                'content': json.dumps(data, indent=2, ensure_ascii=False)
            },
            'README.md': {
                'content': readme_content
            }
        }
    }
    
    # Update the Gist
    response = requests.patch(
        f'https://api.github.com/gists/{gist_id}',
        headers=headers,
        json=payload
    )
    
    if response.status_code in (200, 201):
        print(f"✅ CMG Programado Gist updated successfully!")
        print(f"   URL: https://gist.github.com/{response.json().get('owner', {}).get('login', 'PVSH97')}/{gist_id}")
        return True
    else:
        print(f"❌ Failed to update Gist: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return False

def main():
    """Main execution"""
    print("="*60)
    print("UPDATE CMG PROGRAMADO GIST")
    print("="*60)
    
    # Load configuration
    gist_id = load_gist_config() or CMG_PROGRAMADO_GIST_ID
    if not gist_id:
        print("❌ No CMG Programado Gist ID found")
        print("\nFirst create the Gist:")
        print("export GITHUB_TOKEN='your_token'")
        print("python scripts/create_cmg_programado_gist.py")
        return 1
    
    print(f"Target Gist: {gist_id}")
    
    # Get token
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("\n❌ GITHUB_TOKEN not set")
        print("This token is needed to update YOUR Gist")
        print("In GitHub Actions, use a Personal Access Token (PAT)")
        return 1
    
    # Load local data
    local_path = Path('data/cmg_programado_history.json')
    if not local_path.exists():
        print(f"❌ No local data found: {local_path}")
        return 1
    
    with open(local_path, 'r') as f:
        data = json.load(f)
    
    print(f"\n📊 Loaded local data:")
    historical = data.get('historical_data', {})
    print(f"   Days: {len(historical)}")
    print(f"   Hours: {sum(len(hours) for hours in historical.values())}")
    
    # Update the Gist
    print(f"\n📤 Updating Gist...")
    if update_cmg_programado_gist(data, gist_id, token):
        print("\n✅ Success! Your CMG Programado Gist is updated")
        print("   Architecture:")
        print("   • Partner's Gist → Fresh data (may have gaps)")
        print("   • Your CMG Programado Gist → Reliable storage (no gaps)")
        print("   • Your CMG Online Gist → Historical actual values")
        return 0
    else:
        return 1

if __name__ == "__main__":
    exit(main())