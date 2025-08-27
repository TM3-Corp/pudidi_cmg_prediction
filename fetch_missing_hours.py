#!/usr/bin/env python3
"""
Fetch missing hours from CMG endpoints
Specifically targets the hours that were missed in the initial fetch
"""

import requests
import time
from collections import defaultdict

def fetch_missing_hours(endpoint_name, date_str, missing_hours_by_location, start_page=111):
    """
    Continue fetching from where we left off to get missing hours.
    """
    
    # Configuration
    SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
    SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
    
    endpoint_urls = {
        'CMG_ONLINE': '/costo-marginal-online/v4/findByDate',
        'CMG_PID': '/cmg-programado-pid/v4/findByDate'
    }
    
    url = SIP_BASE_URL + endpoint_urls[endpoint_name]
    node_field = 'barra_transf' if 'ONLINE' in endpoint_name else 'nmb_barra_info'
    
    print(f"\n{'='*80}")
    print(f"FETCHING MISSING HOURS from {endpoint_name}")
    print(f"Starting from page {start_page}")
    print(f"{'='*80}")
    
    # Track what we find
    found_hours = defaultdict(set)
    page = start_page
    max_additional_pages = 100
    consecutive_empty = 0
    
    while page < start_page + max_additional_pages:
        # Check if we've found all missing hours
        all_found = True
        for location, missing in missing_hours_by_location.items():
            if not all(h in found_hours[location] for h in missing):
                all_found = False
                break
        
        if all_found and found_hours:
            print(f"\n✅ All missing hours found!")
            break
        
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        print(f"\nPage {page}: ", end='')
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                if not records:
                    print("END OF DATA")
                    break
                
                # Check for missing hours in this page
                page_findings = defaultdict(list)
                
                for record in records:
                    location = record.get(node_field)
                    
                    # Check if this is one of our locations with missing hours
                    if location in missing_hours_by_location:
                        # Extract hour
                        if 'fecha_hora' in record:
                            hour = int(record['fecha_hora'][11:13])
                        elif 'hra' in record:
                            hour = record['hra']
                        else:
                            continue
                        
                        # Check if this is a missing hour
                        if hour in missing_hours_by_location[location]:
                            page_findings[location].append(hour)
                            found_hours[location].add(hour)
                
                if page_findings:
                    print(f"{len(records)} records | FOUND MISSING HOURS:")
                    for loc, hours in page_findings.items():
                        print(f"   🎯 {loc[:30]}: Hours {sorted(hours)}")
                else:
                    print(f"{len(records)} records | No missing hours found")
                    consecutive_empty += 1
                    
                    if consecutive_empty >= 5:
                        print(f"\n⚠️ No missing hours in last 5 pages, stopping search")
                        break
                
                # Check if partial page
                if len(records) < 1000:
                    print("   (Last page)")
                    break
                
            elif response.status_code == 429:
                print(f"Rate limited, waiting 10s...")
                time.sleep(10)
                continue  # Retry same page
                
            elif response.status_code >= 500:
                print(f"Server error {response.status_code}, waiting 5s...")
                time.sleep(5)
                continue  # Retry same page
                
            else:
                print(f"Error {response.status_code}")
                break
                
        except Exception as e:
            print(f"Error: {str(e)[:50]}")
            time.sleep(5)
            continue  # Retry same page
        
        page += 1
        time.sleep(0.3)  # Be nice to API
    
    # Summary
    print(f"\n{'='*80}")
    print("MISSING HOURS SEARCH RESULTS:")
    print(f"{'='*80}")
    
    for location, missing in missing_hours_by_location.items():
        found = found_hours[location]
        still_missing = [h for h in missing if h not in found]
        
        if found:
            print(f"\n{location}:")
            print(f"  ✅ Found hours: {sorted(found)}")
            if still_missing:
                print(f"  ❌ Still missing: {still_missing}")
        elif location in missing_hours_by_location:
            print(f"\n{location}:")
            print(f"  ❌ No missing hours found, still need: {missing}")
    
    return found_hours


# For use in notebook - define missing hours based on your results
def get_missing_hours_from_results():
    """
    Based on your CMG_ONLINE results, these are the missing hours
    """
    return {
        'CHILOE________220': [9, 15, 21],
        'CHILOE________110': [15, 21],
        'CHONCHI_______110': [16, 20, 22],
        'DALCAHUE______023': [1, 7, 20],
        'QUELLON_______013': [6, 12],
        'QUELLON_______110': [6, 12]
    }


if __name__ == "__main__":
    # Test fetching missing hours
    missing = get_missing_hours_from_results()
    
    # Try to find them starting from page 111
    found = fetch_missing_hours('CMG_ONLINE', '2025-08-25', missing, start_page=111)
    
    print(f"\n🎯 Total hours recovered: {sum(len(h) for h in found.values())}")