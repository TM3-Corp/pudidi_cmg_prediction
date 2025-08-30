#!/usr/bin/env python3
"""
Test fetching multiple pages to find Chiloé data
"""

import requests
import os
from datetime import datetime, timedelta
import pytz

# API configuration
SIP_API_KEY = os.environ.get('SIP_API_KEY', '1a81177c8ff4f69e7dd5bb8c61bc08b4')
CHILOE_NODE = 'CHILOE________220'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

def test_fetch_pages():
    # Use August 1st, 2025 which we know has data
    date_to_fetch = '2025-08-01'
    
    print(f"Testing fetch for {date_to_fetch}")
    print("=" * 60)
    
    # Test CMG Online endpoint
    base_url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    chiloe_records_by_page = {}
    page = 1
    max_pages = 10  # Test first 10 pages quickly
    
    while page <= max_pages:
        params = {
            'startDate': date_to_fetch,
            'endDate': date_to_fetch,
            'page': page,
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        try:
            print(f"\nFetching page {page}...", end="")
            response = requests.get(base_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                total_records = len(data.get('data', []))
                
                # Count Chiloé records
                chiloe_records = []
                for record in data.get('data', []):
                    if record.get('barra_transf') == CHILOE_NODE:
                        chiloe_records.append(record)
                
                if chiloe_records:
                    chiloe_records_by_page[page] = chiloe_records
                    print(f" {total_records} total, {len(chiloe_records)} Chiloé ✓")
                    
                    # Show first Chiloé record
                    first = chiloe_records[0]
                    print(f"    Sample: {first.get('fecha_hora')} - CMG: {first.get('cmg')}")
                else:
                    print(f" {total_records} total, 0 Chiloé")
                
                # Check if last page
                if total_records < 1000:
                    print(f"\nLast page reached at page {page}")
                    break
                    
                page += 1
                
            else:
                print(f" Error {response.status_code}")
                break
                
        except Exception as e:
            print(f" Error: {e}")
            break
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_chiloe = sum(len(records) for records in chiloe_records_by_page.values())
    print(f"Total Chiloé records found: {total_chiloe}")
    print(f"Pages with Chiloé data: {len(chiloe_records_by_page)}")
    
    if chiloe_records_by_page:
        print("\nPages containing Chiloé data:")
        for page, records in sorted(chiloe_records_by_page.items())[:10]:
            print(f"  Page {page}: {len(records)} records")
        
        # Check hour coverage
        all_hours = set()
        for records in chiloe_records_by_page.values():
            for record in records:
                hour = int(record.get('fecha_hora', '')[11:13])
                all_hours.add(hour)
        
        print(f"\nHours covered: {sorted(all_hours)}")
        print(f"Total unique hours: {len(all_hours)}/24")

if __name__ == "__main__":
    test_fetch_pages()