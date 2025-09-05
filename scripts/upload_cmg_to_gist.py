#!/usr/bin/env python3
"""
Upload CMG Programado historical data to GitHub Gist
Creates a new Gist if it doesn't exist, or updates existing one
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

# GitHub configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    print("❌ Error: GITHUB_TOKEN not set")
    print("   Set it with: export GITHUB_TOKEN='your_token_here'")
    exit(1)

# Gist configuration
GIST_FILENAME = "cmg_programado_history.json"
GIST_DESCRIPTION = f"CMG Programado Historical Data - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}"

def create_gist(data):
    """Create a new GitHub Gist"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    payload = {
        'description': GIST_DESCRIPTION,
        'public': False,  # Make it private
        'files': {
            GIST_FILENAME: {
                'content': json.dumps(data, indent=2, ensure_ascii=False)
            }
        }
    }
    
    print("📤 Creating new Gist...")
    response = requests.post("https://api.github.com/gists", headers=headers, json=payload)
    
    if response.status_code in (200, 201):
        gist_data = response.json()
        gist_id = gist_data['id']
        gist_url = gist_data['html_url']
        print(f"✅ Gist created successfully!")
        print(f"   ID: {gist_id}")
        print(f"   URL: {gist_url}")
        
        # Save the Gist ID for future reference
        config = {
            'cmg_programado_gist': {
                'id': gist_id,
                'url': gist_url,
                'filename': GIST_FILENAME,
                'created_at': datetime.now().isoformat()
            }
        }
        
        config_path = Path('cmg_gist_config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"   Config saved to: {config_path}")
        
        return gist_id
    else:
        print(f"❌ Failed to create gist: {response.status_code}")
        print(f"   Response: {response.text}")
        return None

def update_gist(gist_id, data):
    """Update existing GitHub Gist"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    payload = {
        'description': GIST_DESCRIPTION,
        'files': {
            GIST_FILENAME: {
                'content': json.dumps(data, indent=2, ensure_ascii=False)
            }
        }
    }
    
    print(f"📤 Updating Gist {gist_id}...")
    response = requests.patch(f"https://api.github.com/gists/{gist_id}", headers=headers, json=payload)
    
    if response.status_code in (200, 201):
        gist_data = response.json()
        print(f"✅ Gist updated successfully!")
        print(f"   URL: {gist_data['html_url']}")
        return True
    else:
        print(f"❌ Failed to update gist: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def main():
    """Main execution"""
    print("="*60)
    print("CMG PROGRAMADO GIST UPLOADER")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Load the historical data
    data_path = Path('data/cmg_programado_history.json')
    if not data_path.exists():
        print(f"❌ Data file not found: {data_path}")
        print("   Run the merger script first: python scripts/merge_cmg_history.py")
        return 1
    
    print(f"📁 Loading data from: {data_path}")
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Show summary
    if 'metadata' in data:
        meta = data['metadata']
        print(f"   Total days: {meta.get('total_days', 0)}")
        print(f"   Total hours: {meta.get('total_hours', 0)}")
        print(f"   Last update: {meta.get('last_update', 'N/A')}")
    print()
    
    # Check if we have an existing Gist ID
    config_path = Path('cmg_gist_config.json')
    gist_id = None
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
            if 'cmg_programado_gist' in config:
                gist_id = config['cmg_programado_gist'].get('id')
                print(f"📌 Found existing Gist ID: {gist_id}")
    
    # Upload to Gist
    if gist_id:
        # Update existing Gist
        success = update_gist(gist_id, data)
    else:
        # Create new Gist
        gist_id = create_gist(data)
        success = gist_id is not None
    
    print()
    print("="*60)
    if success:
        print("✅ CMG Programado data uploaded to Gist successfully!")
        print()
        print("Next steps:")
        print("1. Update API endpoints to use this Gist ID")
        print("2. Test performance comparison with the new data")
        print("3. Schedule automated updates in GitHub Actions")
    else:
        print("❌ Failed to upload data to Gist")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())