#!/usr/bin/env python3
"""
Fetch CMG Programado data from GitHub Gist
Uses PMontt220 as proxy for all nodes since our specific nodes aren't available
"""

import requests
import json
from datetime import datetime, timedelta
import pytz
import csv
from io import StringIO

# Our 6 nodes mapping - we'll use PMontt220 data for all
CMG_NODES = [
    'CHILOE________220', 'CHILOE________110', 
    'QUELLON_______110', 'QUELLON_______013', 
    'CHONCHI_______110', 'DALCAHUE______023'
]

def fetch_gist_data():
    """Fetch the most recent CSV from the gist"""
    
    # Get gist metadata
    gist_api_url = "https://api.github.com/gists/a63a3a10479bafcc29e10aaca627bc73"
    
    try:
        response = requests.get(gist_api_url, timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to fetch gist metadata: {response.status_code}")
            return None
            
        gist_data = response.json()
        files = gist_data.get('files', {})
        
        # Find the CSV with the most recent data
        # We'll check each file to find the one with the latest dates
        latest_date = None
        best_file_url = None
        
        print("🔍 Checking CSV files in gist...")
        for filename, file_info in files.items():
            if filename.endswith('.csv'):
                raw_url = file_info['raw_url']
                
                # Fetch first few lines to check dates
                test_response = requests.get(raw_url, timeout=10)
                if test_response.status_code == 200:
                    lines = test_response.text.split('\n')[:50]  # Check first 50 lines
                    for line in lines[1:]:  # Skip header
                        if line and 'PMontt220' in line:
                            parts = line.split(',')
                            if len(parts) >= 3:
                                date_str = parts[0]
                                try:
                                    date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
                                    if latest_date is None or date > latest_date:
                                        latest_date = date
                                        best_file_url = raw_url
                                except:
                                    pass
                            break
        
        if best_file_url:
            print(f"✅ Found best file with data up to {latest_date}")
            
            # Fetch the full CSV
            response = requests.get(best_file_url, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                print(f"❌ Failed to fetch CSV: {response.status_code}")
                return None
        else:
            print("❌ No suitable CSV file found")
            return None
            
    except Exception as e:
        print(f"❌ Error fetching gist: {e}")
        return None

def parse_gist_csv(csv_text):
    """Parse CSV and extract PMontt220 data"""
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    today = now.strftime('%Y-%m-%d')
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    next_hour = now.hour + 1 if now.hour < 23 else 0
    
    programmed_data = []
    
    # Parse CSV
    csv_reader = csv.DictReader(StringIO(csv_text))
    
    pmontt_data = {}  # date_hour -> value
    
    for row in csv_reader:
        if row.get('Barra') == 'PMontt220':
            fecha_hora = row.get('Fecha Hora', '')
            cmg = float(row.get('Costo Marginal [USD/MWh]', 0))
            
            try:
                dt = datetime.strptime(fecha_hora, '%Y-%m-%d %H:%M:%S.%f')
                date_str = dt.strftime('%Y-%m-%d')
                hour = dt.hour
                
                # Store future data only
                if (date_str == today and hour >= next_hour) or date_str > today:
                    pmontt_data[(date_str, hour)] = cmg
                    
            except Exception as e:
                continue
    
    print(f"\n📊 Found PMontt220 data for {len(pmontt_data)} future hours")
    
    # Create synthetic data for all our nodes using PMontt220 values
    for (date_str, hour), cmg_value in sorted(pmontt_data.items()):
        for node in CMG_NODES:
            programmed_data.append({
                'datetime': f"{date_str}T{hour:02d}:00:00",
                'date': date_str,
                'hour': hour,
                'node': node,
                'cmg_programmed': cmg_value  # Use PMontt220 value for all nodes
            })
    
    # Sort by datetime
    programmed_data.sort(key=lambda x: x['datetime'])
    
    return programmed_data

def main():
    """Main function to test fetching from gist"""
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("="*80)
    print(f"🔍 FETCHING CMG PROGRAMADO FROM GITHUB GIST")
    print(f"📅 Current time: {now.strftime('%Y-%m-%d %H:%M')} Santiago")
    print(f"⏰ Current hour: {now.hour}")
    print(f"📌 Using PMontt220 data as proxy for all nodes")
    print("="*80)
    
    # Fetch CSV from gist
    csv_data = fetch_gist_data()
    
    if csv_data:
        # Parse and process
        programmed_data = parse_gist_csv(csv_data)
        
        print(f"\n✅ Generated {len(programmed_data)} records total")
        
        # Show summary by node
        node_hours = {}
        for record in programmed_data:
            node = record['node']
            if node not in node_hours:
                node_hours[node] = set()
            node_hours[node].add(record['hour'])
        
        print("\n📊 Coverage by node:")
        for node in CMG_NODES:
            hours = sorted(node_hours.get(node, set()))
            print(f"  {node}: {len(hours)} future hours")
            if hours:
                print(f"    Hours: {hours[:10]}{'...' if len(hours) > 10 else ''}")
        
        # Show sample data
        print("\n📝 Sample records:")
        for record in programmed_data[:5]:
            print(f"  {record['date']} {record['hour']:02d}:00 - {record['node']}: ${record['cmg_programmed']:.1f}")
        
        return programmed_data
    else:
        print("❌ Failed to fetch data from gist")
        return []

if __name__ == "__main__":
    data = main()
    
    if data:
        # Save to test file
        output = {
            'timestamp': datetime.now(pytz.timezone('America/Santiago')).isoformat(),
            'data': data,
            'statistics': {
                'total_records': len(data),
                'hours_ahead': len(set(r['hour'] for r in data))
            }
        }
        
        with open('test_programmed_gist.json', 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Saved {len(data)} records to test_programmed_gist.json")