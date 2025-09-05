#!/usr/bin/env python3
"""
Store CMG Programado historical data in GitHub Gist
Works with GitHub Actions' automatic GITHUB_TOKEN - no PAT needed!
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

# GitHub configuration - uses automatic token in GitHub Actions
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

# Gist configuration
GIST_ID_FILE = '.cmg_programado_gist_id'
GIST_FILENAME = 'cmg_programado_historical.json'

def load_gist_id():
    """Load existing Gist ID from file"""
    if os.path.exists(GIST_ID_FILE):
        with open(GIST_ID_FILE, 'r') as f:
            return f.read().strip()
    return None

def create_or_update_gist(data):
    """Create or update GitHub Gist with CMG Programado data"""
    
    if not GITHUB_TOKEN:
        print("⚠️  GITHUB_TOKEN not set (normal for local runs)")
        print("   In GitHub Actions, this is provided automatically")
        # Save locally as fallback
        with open('cmg_programado_historical.json', 'w') as f:
            json.dump(data, f, indent=2)
        print(f"   Saved locally to cmg_programado_historical.json")
        return False
    
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Prepare Gist content
    historical = data.get('historical_data', {})
    dates = sorted(historical.keys()) if historical else []
    total_hours = sum(len(hours) for hours in historical.values())
    
    # Create README content
    readme_content = f"""# CMG Programado Historical Data

Reliable storage of CMG Programado (forecast) data with no gaps.

## Coverage
- **Date Range**: {dates[0] if dates else 'N/A'} to {dates[-1] if dates else 'N/A'}
- **Total Days**: {len(dates)}
- **Total Hours**: {total_hours}
- **Node**: PMontt220

## Data Sources
- Primary: Partner's Gist (a63a3a10479bafcc29e10aaca627bc73)
- Storage: This Gist (reliable, no gaps)

## Last Update
- {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

## Available Dates
{chr(10).join(f"- {date}: {len(historical.get(date, {}))} hours" for date in sorted(dates)[:10])}
{"..." if len(dates) > 10 else ""}
"""
    
    gist_content = {
        'files': {
            GIST_FILENAME: {
                'content': json.dumps(data, indent=2)
            },
            'README.md': {
                'content': readme_content
            }
        }
    }
    
    # Check if we have an existing Gist ID
    gist_id = load_gist_id()
    
    if gist_id:
        # Update existing Gist
        print(f"📤 Updating existing CMG Programado Gist: {gist_id}")
        url = f'https://api.github.com/gists/{gist_id}'
        response = requests.patch(url, headers=headers, json=gist_content)
    else:
        # Create new Gist
        print("🆕 Creating new CMG Programado Gist...")
        gist_content['description'] = 'CMG Programado Historical Data - Reliable Storage'
        gist_content['public'] = True
        url = 'https://api.github.com/gists'
        response = requests.post(url, headers=headers, json=gist_content)
        
        if response.status_code == 201:
            new_gist = response.json()
            gist_id = new_gist['id']
            print(f"✅ Created new Gist: {gist_id}")
            print(f"   URL: {new_gist['html_url']}")
            
            # Save the Gist ID for future use
            with open(GIST_ID_FILE, 'w') as f:
                f.write(gist_id)
            print(f"   Saved Gist ID to {GIST_ID_FILE}")
    
    if response.status_code in [200, 201]:
        print("✅ Successfully updated CMG Programado Gist")
        if gist_id:
            print(f"   View at: https://gist.github.com/{gist_id}")
        return True
    else:
        print(f"❌ Error updating Gist: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return False

def main():
    """Main function to store CMG Programado data"""
    print("="*60)
    print("STORE CMG PROGRAMADO IN GITHUB GIST")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load CMG Programado data
    data_path = Path('data/cmg_programado_history.json')
    if not data_path.exists():
        print(f"❌ No CMG Programado data found at {data_path}")
        return 1
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    historical = data.get('historical_data', {})
    print(f"\n📊 Loaded CMG Programado data:")
    print(f"   Days: {len(historical)}")
    print(f"   Hours: {sum(len(hours) for hours in historical.values())}")
    
    # Create or update Gist
    success = create_or_update_gist(data)
    
    print("\n" + "="*60)
    if success:
        print("✅ CMG Programado data stored in Gist!")
        print("\nArchitecture:")
        print("• CMG Online Gist: 8d7864eb26acf6e780d3c0f7fed69365")
        print(f"• CMG Programado Gist: {load_gist_id() or 'Will be created'}")
        print("• Partner's Gist: a63a3a10479bafcc29e10aaca627bc73 (source)")
    else:
        if GITHUB_TOKEN:
            print("❌ Failed to update Gist")
        else:
            print("ℹ️  Run in GitHub Actions for automatic Gist updates")
    
    return 0 if success or not GITHUB_TOKEN else 1

if __name__ == "__main__":
    exit(main())