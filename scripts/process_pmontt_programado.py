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
GIST_ID = "03ad6c3b2a0cc887df39f13e3cb27231"  # Your Gist ID for CMG predictions

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
        print("⚠️ No GitHub token found, trying without auth")
        headers = {'Accept': 'application/vnd.github.v3+json'}
    else:
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
            
            # Get existing data
            existing_content = gist['files'].get('cmg_predictions.json', {}).get('content', '{}')
            existing_data = json.loads(existing_content)
            
            # Merge with new PMontt220 data
            if 'forecast_data' not in existing_data:
                existing_data['forecast_data'] = {}
            
            # Update forecast_data with PMontt220 values
            existing_data['forecast_data'] = pmontt_data
            
            # Update metadata
            existing_data['metadata'] = {
                'last_updated': datetime.now(santiago_tz).isoformat(),
                'source': 'CMG Programado - PMontt220',
                'update_frequency': 'hourly',
                'location': 'Puerto Montt (PMontt220)'
            }
            
            # Calculate available hours
            total_hours = sum(len(hours) for hours in pmontt_data.values())
            existing_data['summary'] = {
                'total_forecast_hours': total_hours,
                'dates_available': list(pmontt_data.keys()),
                'last_update': datetime.now(santiago_tz).strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Update the Gist
            update_data = {
                'files': {
                    'cmg_predictions.json': {
                        'content': json.dumps(existing_data, indent=2, ensure_ascii=False)
                    }
                }
            }
            
            response = requests.patch(url, json=update_data, headers=headers)
            
            if response.status_code == 200:
                print(f"✅ Gist updated successfully!")
                print(f"   URL: https://gist.github.com/pmorenoz/{GIST_ID}")
                print(f"   Total forecast hours: {total_hours}")
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
    """Save PMontt220 data to local cache"""
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    print(f"💾 Saved to local cache: {cache_file}")

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