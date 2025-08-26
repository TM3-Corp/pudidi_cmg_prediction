#!/usr/bin/env python3
"""Find Chiloé data in SIP API"""

import requests
import json

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
date = '2025-08-25'

print(f"Searching for {CHILOE_NODE} data on {date}...")

for page in range(1, 20):
    params = {
        'startDate': date,
        'endDate': date,
        'page': page,
        'limit': 1000,
        'user_key': SIP_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            records = data.get('data', [])
            
            if not records:
                print(f"  Page {page}: No more data")
                break
                
            # Look for Chiloé
            chiloe_records = [r for r in records if r.get('barra_transf') == CHILOE_NODE]
            
            if chiloe_records:
                print(f"  ✅ FOUND on page {page}! {len(chiloe_records)} Chiloé records")
                for r in chiloe_records[:5]:
                    print(f"     {r['fecha_hora']}: ${r.get('cmg_usd_mwh_', 0):.2f}")
                break
            else:
                # Show sample of what's on this page
                unique_nodes = set(r.get('barra_transf', '') for r in records)
                chiloe_like = [n for n in unique_nodes if 'CHILO' in n]
                print(f"  Page {page}: {len(records)} records, no exact match")
                if chiloe_like:
                    print(f"     Similar nodes: {chiloe_like}")
        else:
            print(f"  Page {page}: Error {response.status_code}")
    except Exception as e:
        print(f"  Page {page}: Error - {e}")

print("\nSearching for any node containing 'CHILO'...")
params = {
    'startDate': date,
    'endDate': date,
    'page': 1,
    'limit': 1000,
    'user_key': SIP_API_KEY
}
response = requests.get(url, params=params)
if response.status_code == 200:
    data = response.json()
    all_nodes = set(r.get('barra_transf', '') for r in data.get('data', []))
    chiloe_nodes = [n for n in all_nodes if 'CHIL' in n.upper()]
    if chiloe_nodes:
        print(f"Found nodes with 'CHIL': {chiloe_nodes}")
    else:
        print("No nodes containing 'CHIL' found")