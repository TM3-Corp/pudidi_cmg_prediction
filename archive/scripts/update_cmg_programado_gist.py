#!/usr/bin/env python3
"""
Update YOUR CMG Programado Gist with historical data
Gist ID: d68bb21360b1ac549c32a80195f99b09
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

# Your CMG Programado Gist ID
CMG_PROGRAMADO_GIST_ID = 'd68bb21360b1ac549c32a80195f99b09'
GIST_FILENAME = 'cmg_programado_historical.json'

def update_gist(data, token):
    """Update your CMG Programado Gist"""
    
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Update metadata
    if 'metadata' in data:
        data['metadata']['last_update'] = datetime.now().isoformat()
        data['metadata']['update_source'] = 'GitHub Actions'
    
    # Prepare the update
    gist_content = {
        'description': f"CMG Programado Historical Data - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        'files': {
            GIST_FILENAME: {
                'content': json.dumps(data, indent=2, ensure_ascii=False)
            }
        }
    }
    
    # Update the Gist
    url = f'https://api.github.com/gists/{CMG_PROGRAMADO_GIST_ID}'
    response = requests.patch(url, headers=headers, json=gist_content)
    
    if response.status_code in (200, 201):
        print(f"✅ Successfully updated CMG Programado Gist!")
        print(f"   URL: https://gist.github.com/PVSH97/{CMG_PROGRAMADO_GIST_ID}")
        return True
    else:
        print(f"❌ Failed to update Gist: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return False

def main():
    """Main function"""
    print("="*60)
    print("UPDATE CMG PROGRAMADO GIST")
    print("="*60)
    print(f"Target Gist: {CMG_PROGRAMADO_GIST_ID}")
    print()
    
    # Load local data
    data_path = Path('data/cmg_programado_history.json')
    if not data_path.exists():
        print(f"❌ No local data found at {data_path}")
        return 1
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Show statistics
    historical = data.get('historical_data', {})
    dates = sorted(historical.keys())
    total_hours = sum(len(hours) for hours in historical.values())
    
    print(f"📊 Local data statistics:")
    print(f"   Date range: {dates[0] if dates else 'N/A'} to {dates[-1] if dates else 'N/A'}")
    print(f"   Total days: {len(dates)}")
    print(f"   Total hours: {total_hours}")
    print()
    
    # Get token (required for updating Gists)
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("⚠️  GITHUB_TOKEN not set")
        print("   This is required to update the Gist")
        print("   In GitHub Actions, you need a PAT with gist scope")
        print("   Add it as CMG_GIST_TOKEN secret in your repository")
        return 1
    
    # Update the Gist
    print("📤 Updating Gist...")
    if update_gist(data, token):
        print("\n✅ Success!")
        print("\nYour 3-Gist Architecture:")
        print("• CMG Online: https://gist.github.com/PVSH97/8d7864eb26acf6e780d3c0f7fed69365")
        print(f"• CMG Programado: https://gist.github.com/PVSH97/{CMG_PROGRAMADO_GIST_ID}")
        print("• Partner's source: https://gist.github.com/arbanados/a63a3a10479bafcc29e10aaca627bc73")
        return 0
    else:
        return 1

if __name__ == "__main__":
    exit(main())