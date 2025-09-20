#!/usr/bin/env python3
"""
Process CMG Programado data - Extract only PMontt220 values
Updates the Gist with Puerto Montt forecast data
"""

import json
import csv
from pathlib import Path
from datetime import datetime
import pytz
import requests
import os
from typing import Dict, List, Optional

# Configuration
santiago_tz = pytz.timezone('America/Santiago')
GIST_ID = "d68bb21360b1ac549c32a80195f99b09"  # Gist ID for CMG Programado data

def read_latest_csv() -> Optional[Path]:
    """Find the most recent CMG Programado CSV file"""
    downloads_dir = Path("downloads")
    csv_files = list(downloads_dir.glob("cmg_programado_*.csv"))
    
    if not csv_files:
        print("❌ No CMG Programado CSV files found")
        return None
    
    # Get the most recent file
    latest_file = max(csv_files, key=lambda x: x.stat().st_mtime)
    print(f"📄 Found CSV: {latest_file}")
    return latest_file

def extract_pmontt_data(csv_path: Path) -> Dict:
    """Extract PMontt220 data from CSV and format for Gist"""
    
    pmontt_data = {}
    now = datetime.now(santiago_tz)
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Filter only PMontt220 rows
            if row['Barra'] == 'PMontt220':
                # Parse the datetime
                fecha_hora = row['Fecha Hora']
                # Handle the microseconds format
                if '.' in fecha_hora:
                    dt = datetime.strptime(fecha_hora.split('.')[0], '%Y-%m-%d %H:%M:%S')
                else:
                    dt = datetime.strptime(fecha_hora, '%Y-%m-%d %H:%M:%S')
                
                dt = santiago_tz.localize(dt)
                
                # Format date and hour for storage
                date_str = dt.strftime('%Y-%m-%d')
                hour_str = str(dt.hour).zfill(2)
                
                # Store the CMG value
                if date_str not in pmontt_data:
                    pmontt_data[date_str] = {}
                
                pmontt_data[date_str][hour_str] = float(row['Costo Marginal [USD/MWh]'])
    
    print(f"📊 Extracted PMontt220 data for {len(pmontt_data)} dates")
    
    # Show summary
    for date in sorted(pmontt_data.keys()):
        hours = len(pmontt_data[date])
        print(f"  {date}: {hours} hours")
    
    return pmontt_data

def update_gist(pmontt_data: Dict) -> bool:
    """Update the Gist with PMontt220 forecast data"""
    
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("⚠️ No GitHub token found, cannot update Gist")
        return False
    
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # First, get the existing Gist data
    url = f"https://api.github.com/gists/{GIST_ID}"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            gist = response.json()
            
            # Get existing data from cmg_programado_historical.json
            existing_content = gist['files'].get('cmg_programado_historical.json', {}).get('content', '{}')
            existing_data = json.loads(existing_content)
            
            # Initialize historical_data if it doesn't exist
            if 'historical_data' not in existing_data:
                existing_data = {'historical_data': {}}
            
            # Convert PMontt220 data to match the existing format
            # Add new forecast data to historical_data
            for date, hours_data in pmontt_data.items():
                if date not in existing_data['historical_data']:
                    existing_data['historical_data'][date] = {}
                
                # Update each hour with the new forecast
                for hour, value in hours_data.items():
                    hour_int = str(int(hour))  # Convert "00" to "0"
                    existing_data['historical_data'][date][hour_int] = {
                        'value': value,
                        'node': 'PMontt220',
                        'timestamp': f"{date}T{hour}:00:00-03:00",
                        'source': 'CMG Programado',
                        'update_time': datetime.now(santiago_tz).isoformat()
                    }
            
            # Add metadata at the root level
            existing_data['metadata'] = {
                'last_updated': datetime.now(santiago_tz).isoformat(),
                'source': 'CMG Programado - PMontt220',
                'total_hours': sum(len(hours) for hours in pmontt_data.values()),
                'dates_available': list(pmontt_data.keys())
            }
            
            # Update the Gist with the correct file name
            update_data = {
                'files': {
                    'cmg_programado_historical.json': {
                        'content': json.dumps(existing_data, indent=2, ensure_ascii=False)
                    }
                }
            }
            
            response = requests.patch(url, json=update_data, headers=headers)
            
            if response.status_code == 200:
                print(f"✅ Gist updated successfully!")
                print(f"   URL: https://gist.github.com/PVSH97/{GIST_ID}")
                print(f"   Total forecast hours: {sum(len(hours) for hours in pmontt_data.values())}")
                return True
            else:
                print(f"❌ Failed to update Gist: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        else:
            print(f"❌ Failed to fetch Gist: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating Gist: {e}")
        return False

def save_local_cache(pmontt_data: Dict):
    """Save PMontt220 data to local cache files"""
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Save to pmontt_programado.json (for reference)
    cache_file = cache_dir / "pmontt_programado.json"
    cache_data = {
        'forecast_data': pmontt_data,
        'metadata': {
            'last_updated': datetime.now(santiago_tz).isoformat(),
            'source': 'CMG Programado - PMontt220',
            'location': 'Puerto Montt'
        }
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Saved to: {cache_file}")
    
    # IMPORTANT: Also save to cmg_programmed_latest.json for the API
    api_cache_file = cache_dir / "cmg_programmed_latest.json"
    
    # Convert to API format
    api_data = []
    for date, hours_data in pmontt_data.items():
        for hour, value in hours_data.items():
            hour_int = int(hour)
            api_data.append({
                "datetime": f"{date}T{hour}:00:00",
                "date": date,
                "hour": hour_int,
                "node": "PMontt220",
                "cmg_programmed": value
            })
    
    # Sort by datetime
    api_data.sort(key=lambda x: x['datetime'])
    
    api_cache = {
        'timestamp': datetime.now(santiago_tz).isoformat(),
        'data': api_data,
        'source': 'CMG Programado Download',
        'metadata': {
            'total_hours': len(api_data),
            'dates': list(pmontt_data.keys()),
            'node': 'PMontt220'
        }
    }
    
    with open(api_cache_file, 'w', encoding='utf-8') as f:
        json.dump(api_cache, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Saved to: {api_cache_file} (for API)")

def main():
    print("="*60)
    print("PROCESS PMONTT220 CMG PROGRAMADO")
    print("="*60)
    print(f"Time: {datetime.now(santiago_tz)}\n")
    
    # Find the latest CSV
    csv_path = read_latest_csv()
    if not csv_path:
        print("❌ No CSV file to process")
        return 1
    
    # Extract PMontt220 data
    pmontt_data = extract_pmontt_data(csv_path)
    
    if not pmontt_data:
        print("❌ No PMontt220 data found in CSV")
        return 1
    
    # Save to local cache
    save_local_cache(pmontt_data)
    
    # Update Gist
    print("\n📤 Updating Gist...")
    if update_gist(pmontt_data):
        print("\n✅ SUCCESS! PMontt220 forecast data updated")
        print(f"Check: https://pudidicmgprediction.vercel.app/index.html")
        return 0
    else:
        print("\n⚠️ Failed to update Gist, but local cache saved")
        return 1

if __name__ == "__main__":
    exit(main())