#!/usr/bin/env python3
"""
Update CMG Programado data to existing GitHub Gist
Uses the same Gist as CMG Online for unified access
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

# GitHub configuration - uses automatic token in GitHub Actions
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GIST_ID = '8d7864eb26acf6e780d3c0f7fed69365'  # Your existing CMG Online Gist

def load_cmg_programado_data():
    """Load the merged CMG Programado historical data"""
    data_path = Path('data/cmg_programado_history.json')
    
    if not data_path.exists():
        print(f"❌ CMG Programado data not found: {data_path}")
        return None
    
    with open(data_path, 'r') as f:
        return json.load(f)

def fetch_existing_gist():
    """Fetch the current Gist content"""
    headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
    
    response = requests.get(f'https://api.github.com/gists/{GIST_ID}', headers=headers)
    
    if response.status_code == 200:
        gist_data = response.json()
        # Find the CMG Online file
        for filename, file_info in gist_data.get('files', {}).items():
            if 'cmg' in filename.lower() and filename.endswith('.json'):
                content = file_info.get('content', '{}')
                return json.loads(content), filename
    
    return {}, 'cmg_historical_data.json'

def merge_programado_with_online(cmg_online, cmg_programado):
    """Merge CMG Programado data into the existing structure"""
    
    # Ensure we have the base structure
    if 'metadata' not in cmg_online:
        cmg_online['metadata'] = {}
    
    if 'daily_data' not in cmg_online:
        cmg_online['daily_data'] = {}
    
    # Add CMG Programado data
    cmg_online['cmg_programado'] = {
        'metadata': cmg_programado.get('metadata', {}),
        'historical_data': cmg_programado.get('historical_data', {})
    }
    
    # Update combined metadata
    cmg_online['metadata']['last_update'] = datetime.now().isoformat()
    cmg_online['metadata']['has_cmg_programado'] = True
    
    # Count CMG Programado stats
    prog_data = cmg_programado.get('historical_data', {})
    cmg_online['metadata']['cmg_programado_days'] = len(prog_data)
    cmg_online['metadata']['cmg_programado_hours'] = sum(
        len(hours) for hours in prog_data.values()
    )
    
    return cmg_online

def update_gist(data, filename):
    """Update the GitHub Gist with merged data"""
    
    if not GITHUB_TOKEN:
        print("⚠️  Warning: GITHUB_TOKEN not set")
        print("   In GitHub Actions, this is provided automatically")
        print("   Locally, set: export GITHUB_TOKEN='your_token_here'")
        return False
    
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Prepare the update payload
    payload = {
        'description': f"CMG Historical Data (Online + Programado) - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        'files': {
            filename: {
                'content': json.dumps(data, indent=2, ensure_ascii=False)
            }
        }
    }
    
    # Update the Gist
    response = requests.patch(
        f'https://api.github.com/gists/{GIST_ID}',
        headers=headers,
        json=payload
    )
    
    if response.status_code in (200, 201):
        print(f"✅ Gist updated successfully!")
        print(f"   URL: https://gist.github.com/PVSH97/{GIST_ID}")
        return True
    else:
        print(f"❌ Failed to update Gist: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return False

def main():
    """Main execution"""
    print("="*60)
    print("CMG PROGRAMADO GIST UPDATER")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Target Gist: {GIST_ID}")
    print()
    
    # Step 1: Load CMG Programado data
    print("1️⃣ Loading CMG Programado data...")
    cmg_programado = load_cmg_programado_data()
    if not cmg_programado:
        return 1
    
    prog_meta = cmg_programado.get('metadata', {})
    print(f"   Days: {prog_meta.get('total_days', 0)}")
    print(f"   Hours: {prog_meta.get('total_hours', 0)}")
    print(f"   Node: {prog_meta.get('node', 'N/A')}")
    print()
    
    # Step 2: Fetch existing Gist (CMG Online)
    print("2️⃣ Fetching existing CMG Online data from Gist...")
    cmg_online, filename = fetch_existing_gist()
    
    if 'daily_data' in cmg_online:
        online_days = len(cmg_online.get('daily_data', {}))
        print(f"   Found {online_days} days of CMG Online data")
    else:
        print("   No existing CMG Online data found (will create new)")
    print()
    
    # Step 3: Merge the data
    print("3️⃣ Merging CMG Programado with CMG Online...")
    merged_data = merge_programado_with_online(cmg_online, cmg_programado)
    
    # Show what we have
    meta = merged_data.get('metadata', {})
    print(f"   Combined dataset:")
    print(f"   - CMG Online days: {len(merged_data.get('daily_data', {}))}")
    print(f"   - CMG Programado days: {meta.get('cmg_programado_days', 0)}")
    print(f"   - CMG Programado hours: {meta.get('cmg_programado_hours', 0)}")
    print()
    
    # Step 4: Update the Gist
    print("4️⃣ Updating GitHub Gist...")
    success = update_gist(merged_data, filename)
    
    print()
    print("="*60)
    if success:
        print("✅ CMG Programado data successfully added to Gist!")
        print()
        print("The Rendimiento view can now:")
        print("• Compare CMG Programado (forecast) vs CMG Online (actual)")
        print("• Calculate optimization performance metrics")
        print("• Show how well predictions matched reality")
    else:
        print("❌ Failed to update Gist")
        if not GITHUB_TOKEN:
            print()
            print("For local testing, set your GitHub token:")
            print("export GITHUB_TOKEN='your_github_token_here'")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())