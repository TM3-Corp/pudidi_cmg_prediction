#!/usr/bin/env python3
"""
Complete CMG Online Pipeline:
1. Download CSV from Coordinador
2. Process and filter for specific nodes
3. Upload to Gist
"""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pytz
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from download_cmg_working import run as download_cmg

# Configuration
GIST_ID = "8d7864eb26acf6e780d3c0f7fed69365"
NODES_TO_TRACK = {
    "P.MONTT_______220": "NVA_P.MONTT___220",  # Map CSV name to Gist name
    "PIDPID________110": "PIDPID________110",
    "DALCAHUE______110": "DALCAHUE______110"
}
santiago_tz = pytz.timezone('America/Santiago')


def process_csv_to_gist_format(csv_path):
    """Process downloaded CSV and format for Gist storage"""
    
    print("\n📊 Processing CSV data...")
    
    # Read CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"   Total rows: {len(rows)}")
    
    # Group data by date and hour
    data_by_date_hour = {}
    
    for row in rows:
        # Parse fields
        fecha_minuto = row['fecha_minuto']  # Format: '2025-09-08 00:00'
        barra = row['Barra']
        cmg_str = row['CMg(USD/MWh)']
        
        # Check if this is a node we care about
        if barra not in NODES_TO_TRACK:
            continue
        
        # Parse datetime
        dt = datetime.strptime(fecha_minuto, '%Y-%m-%d %H:%M')
        date_str = dt.strftime('%Y-%m-%d')
        hour = dt.hour
        minute = dt.minute
        
        # Convert CMG value (handle comma as decimal separator)
        cmg_value = float(cmg_str.replace(',', '.'))
        
        # Get the Gist node name
        gist_node_name = NODES_TO_TRACK[barra]
        
        # Initialize data structure
        if date_str not in data_by_date_hour:
            data_by_date_hour[date_str] = {}
        if hour not in data_by_date_hour[date_str]:
            data_by_date_hour[date_str][hour] = {}
        if gist_node_name not in data_by_date_hour[date_str][hour]:
            data_by_date_hour[date_str][hour][gist_node_name] = []
        
        # Add data point (for averaging later if multiple per hour)
        data_by_date_hour[date_str][hour][gist_node_name].append(cmg_value)
    
    print(f"   Filtered to {len(data_by_date_hour)} dates")
    
    # Format for Gist structure
    daily_data = {}
    
    for date_str, hours_data in data_by_date_hour.items():
        # Initialize structure for this date
        daily_data[date_str] = {
            "hours": list(range(24)),  # All hours 0-23
            "cmg_online": {},
            "cmg_programado": {}  # Empty for now, but keeps structure
        }
        
        # Initialize node data arrays
        for node in NODES_TO_TRACK.values():
            daily_data[date_str]["cmg_online"][node] = {
                "cmg_usd": [None] * 24,  # Initialize with None for all hours
                "cmg_real": [None] * 24   # We don't have CLP values from CSV
            }
            daily_data[date_str]["cmg_programado"][node] = {
                "values": [None] * 24
            }
        
        # Fill in the actual data we have
        for hour, nodes_data in hours_data.items():
            for node, values in nodes_data.items():
                # Average if multiple values per hour
                avg_value = sum(values) / len(values)
                daily_data[date_str]["cmg_online"][node]["cmg_usd"][hour] = round(avg_value, 2)
                # Estimate CLP value (using approximate exchange rate of 970)
                daily_data[date_str]["cmg_online"][node]["cmg_real"][hour] = round(avg_value * 970, 0)
    
    # Create complete Gist data structure
    gist_data = {
        "metadata": {
            "last_update": datetime.now(santiago_tz).isoformat(),
            "total_days": len(daily_data),
            "oldest_date": min(daily_data.keys()) if daily_data else "",
            "newest_date": max(daily_data.keys()) if daily_data else "",
            "nodes": list(NODES_TO_TRACK.values()),
            "structure_version": "2.0",
            "source": "csv_download"
        },
        "daily_data": daily_data
    }
    
    return gist_data


def merge_with_existing_gist(new_data, existing_data):
    """Merge new data with existing Gist data"""
    
    print("\n🔄 Merging with existing data...")
    
    # If no existing data, return new data
    if not existing_data:
        return new_data
    
    # Merge daily_data
    merged_daily = existing_data.get("daily_data", {})
    
    for date_str, date_data in new_data["daily_data"].items():
        if date_str not in merged_daily:
            # New date, add it completely
            merged_daily[date_str] = date_data
            print(f"   Added new date: {date_str}")
        else:
            # Date exists, update CMG Online data only
            if "cmg_online" in date_data:
                merged_daily[date_str]["cmg_online"] = date_data["cmg_online"]
                print(f"   Updated CMG Online for: {date_str}")
    
    # Update metadata
    all_dates = sorted(merged_daily.keys())
    new_data["metadata"]["total_days"] = len(all_dates)
    new_data["metadata"]["oldest_date"] = all_dates[0] if all_dates else ""
    new_data["metadata"]["newest_date"] = all_dates[-1] if all_dates else ""
    
    # Keep existing daily data
    new_data["daily_data"] = merged_daily
    
    print(f"   Total dates after merge: {len(all_dates)}")
    
    return new_data


def upload_to_gist(data, token):
    """Upload data to GitHub Gist"""
    
    print("\n📤 Uploading to Gist...")
    
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Prepare the update
    gist_content = {
        'description': f"CMG Online Historical Data - Updated {datetime.now(santiago_tz).strftime('%Y-%m-%d %H:%M')}",
        'files': {
            'cmg_online_historical.json': {
                'content': json.dumps(data, indent=2, ensure_ascii=False)
            }
        }
    }
    
    # Update the Gist
    url = f'https://api.github.com/gists/{GIST_ID}'
    response = requests.patch(url, headers=headers, json=gist_content)
    
    if response.status_code in (200, 201):
        print(f"   ✅ Successfully updated Gist!")
        print(f"   URL: https://gist.github.com/PVSH97/{GIST_ID}")
        return True
    else:
        print(f"   ❌ Failed to update Gist: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return False


async def main():
    """Main pipeline function"""
    
    print("="*60)
    print("CMG ONLINE COMPLETE PIPELINE")
    print("="*60)
    print(f"Timestamp: {datetime.now(santiago_tz)}")
    print()
    
    # Step 1: Download CSV
    print("📥 Step 1: Downloading CMG Online CSV...")
    csv_path = await download_cmg()
    
    if not csv_path:
        print("❌ Failed to download CSV")
        return 1
    
    print(f"   ✅ Downloaded: {csv_path}")
    
    # Step 2: Process CSV to Gist format
    print("\n📊 Step 2: Processing CSV data...")
    new_data = process_csv_to_gist_format(csv_path)
    
    # Show what we processed
    dates = list(new_data["daily_data"].keys())
    print(f"   ✅ Processed {len(dates)} date(s): {', '.join(dates)}")
    
    # Step 3: Fetch existing Gist data
    print("\n📥 Step 3: Fetching existing Gist data...")
    existing_data = None
    
    try:
        response = requests.get(f'https://gist.githubusercontent.com/PVSH97/{GIST_ID}/raw/cmg_online_historical.json')
        if response.status_code == 200:
            existing_data = response.json()
            print(f"   ✅ Fetched existing data with {len(existing_data.get('daily_data', {}))} dates")
    except Exception as e:
        print(f"   ⚠️ Could not fetch existing data: {e}")
    
    # Step 4: Merge data
    if existing_data:
        final_data = merge_with_existing_gist(new_data, existing_data)
    else:
        final_data = new_data
    
    # Step 5: Upload to Gist
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('CMG_GIST_TOKEN')
    
    if not token:
        print("\n⚠️ No GitHub token found. Saving locally instead...")
        
        # Save locally
        local_path = Path("data/cmg_online_from_csv.json")
        local_path.parent.mkdir(exist_ok=True)
        with open(local_path, 'w') as f:
            json.dump(final_data, f, indent=2)
        
        print(f"   💾 Saved locally to: {local_path}")
        print("\n   To upload to Gist, set GITHUB_TOKEN or CMG_GIST_TOKEN environment variable")
    else:
        success = upload_to_gist(final_data, token)
        
        if success:
            print("\n✅ Pipeline completed successfully!")
            print(f"   Data available at: https://gist.github.com/PVSH97/{GIST_ID}")
            
            # Also save locally as backup
            local_path = Path("data/cmg_online_from_csv.json")
            local_path.parent.mkdir(exist_ok=True)
            with open(local_path, 'w') as f:
                json.dump(final_data, f, indent=2)
            print(f"   💾 Backup saved to: {local_path}")
        else:
            print("\n❌ Pipeline failed at Gist upload")
            return 1
    
    # Step 6: Update cache files for the dashboard
    print("\n🔄 Step 6: Updating cache files...")
    cache_path = Path("data/cache/cmg_online_historical.json")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(cache_path, 'w') as f:
        json.dump(final_data, f, indent=2)
    
    print(f"   ✅ Updated cache: {cache_path}")
    
    print("\n" + "="*60)
    print("✅ PIPELINE COMPLETE!")
    print("="*60)
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)