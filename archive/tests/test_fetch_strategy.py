"""
Test optimal fetching strategy for Chiloé CMG data
Key findings:
- API returns SPARSE data (only 3-5 records per day, not 24)
- We need to check MULTIPLE pages to get all Chiloé data
- Training with only 24h is insufficient - need more days
"""
import requests
import time
from datetime import datetime, timedelta
import pytz

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

def test_one_day_complete_fetch(date_str):
    """
    Fetch ALL Chiloé data for one day by checking multiple pages
    """
    print(f"\n{'='*60}")
    print(f"COMPLETE FETCH TEST for {date_str}")
    print(f"{'='*60}")
    
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    all_chiloe_data = {}
    
    # First, get total pages with minimal request
    params = {
        'startDate': date_str,
        'endDate': date_str,
        'page': 1,
        'limit': 1,
        'user_key': SIP_API_KEY
    }
    
    try:
        print("Getting total pages...")
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            total_pages = data.get('totalPages', 0)
            total_records = total_pages  # Since limit=1
            print(f"Total pages: {total_pages}")
            print(f"Estimated total records: ~{total_pages}")
        else:
            print(f"Failed to get info: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []
    
    # Strategy: Use larger pages to reduce requests
    limit = 1000  # Get 1000 records per page
    pages_to_check = max(10, total_pages // limit + 1)  # Check enough pages
    
    print(f"\nFetching with limit={limit}, checking {pages_to_check} pages...")
    
    start_time = time.time()
    request_count = 0
    
    for page in range(1, pages_to_check + 1):
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': limit,
            'user_key': SIP_API_KEY
        }
        
        try:
            print(f"  Page {page}/{pages_to_check}...", end='')
            req_start = time.time()
            response = requests.get(url, params=params, timeout=30)
            req_time = time.time() - req_start
            request_count += 1
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                # Count Chiloé records
                chiloe_in_page = 0
                for record in records:
                    if record.get('barra_transf') == CHILOE_NODE:
                        dt_key = record['fecha_hora']
                        all_chiloe_data[dt_key] = {
                            'datetime': dt_key,
                            'hour': int(dt_key[11:13]),
                            'cmg': float(record.get('cmg_usd_mwh_', 0))
                        }
                        chiloe_in_page += 1
                
                print(f" {len(records)} records ({req_time:.1f}s) - {chiloe_in_page} Chiloé")
                
                # If page is incomplete, we're done
                if len(records) < limit:
                    print(f"  Last page reached (incomplete)")
                    break
                    
            elif response.status_code == 429:
                print(f" Rate limited! Waiting...")
                time.sleep(5)
            elif response.status_code in [500, 502, 503]:
                print(f" Server error {response.status_code}")
                time.sleep(2)
            else:
                print(f" Error {response.status_code}")
                break
                
        except requests.exceptions.Timeout:
            print(f" Timeout!")
        except Exception as e:
            print(f" Error: {e}")
    
    elapsed = time.time() - start_time
    
    # Analyze results
    sorted_data = sorted(all_chiloe_data.values(), key=lambda x: x['datetime'])
    
    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Total time: {elapsed:.1f}s")
    print(f"  Requests made: {request_count}")
    print(f"  Chiloé records found: {len(sorted_data)}")
    
    if sorted_data:
        # Check hourly coverage
        hours_covered = set(d['hour'] for d in sorted_data)
        print(f"  Hours covered: {sorted(hours_covered)}")
        print(f"  Coverage: {len(hours_covered)}/24 hours ({len(hours_covered)/24*100:.1f}%)")
        
        # Show sample
        print(f"\n  Sample records:")
        for item in sorted_data[:5]:
            print(f"    {item['datetime']}: ${item['cmg']:.2f}")
    
    return sorted_data

def estimate_full_month_fetch():
    """
    Estimate time and feasibility of fetching 30 days
    """
    print("\n" + "="*60)
    print("ESTIMATING 30-DAY FETCH")
    print("="*60)
    
    # Test one recent day
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    test_date = (now - timedelta(days=5)).strftime('%Y-%m-%d')
    
    print(f"\nTesting with {test_date}...")
    start = time.time()
    data = test_one_day_complete_fetch(test_date)
    elapsed = time.time() - start
    
    if data:
        print(f"\n📊 EXTRAPOLATION:")
        print(f"  One day fetch time: {elapsed:.1f}s")
        print(f"  Records per day: {len(data)}")
        print(f"  Estimated 30-day time: {elapsed * 30:.1f}s ({elapsed * 30 / 60:.1f} minutes)")
        print(f"  Estimated total records: {len(data) * 30}")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        if elapsed * 30 > 300:  # More than 5 minutes
            print("  ❌ Too slow for real-time API")
            print("  ✅ Implement background daily fetch at 3 AM")
            print("  ✅ Cache data in database")
            print("  ✅ Use last cached data + real-time updates")
        else:
            print("  ✅ Feasible for on-demand fetching")
            print("  ✅ Cache for 1 hour to reduce load")
    
    return data

def test_alternative_endpoints():
    """
    Test if PCP/PID endpoints have better Chiloé coverage
    """
    print("\n" + "="*60)
    print("TESTING ALTERNATIVE ENDPOINTS")
    print("="*60)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    date_str = now.strftime('%Y-%m-%d')
    
    endpoints = [
        ('PCP', f"{SIP_BASE_URL}/cmg-programado-pcp/v4/findByDate"),
        ('PID', f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate")
    ]
    
    for name, url in endpoints:
        print(f"\n{name} Endpoint:")
        
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'limit': 5000,
            'user_key': SIP_API_KEY
        }
        
        try:
            start = time.time()
            response = requests.get(url, params=params, timeout=20)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                # Find Chiloé
                chiloe_records = [r for r in records if 'CHILOE' in str(r.get('nmb_barra_info', ''))]
                
                print(f"  Response time: {elapsed:.1f}s")
                print(f"  Total records: {len(records)}")
                print(f"  Chiloé records: {len(chiloe_records)}")
                
                if chiloe_records:
                    # Check hourly coverage
                    hours = set(r['fecha_hora'][11:13] for r in chiloe_records if r.get('fecha_hora'))
                    print(f"  Hours covered: {len(hours)}/24")
                    
                    # Sample
                    for r in chiloe_records[:3]:
                        print(f"    {r['fecha_hora']}: ${r.get('cmg_usd_mwh', 0):.2f}")
            else:
                print(f"  Error: {response.status_code}")
                
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    print("CMG FETCHING STRATEGY TEST")
    print("Testing different approaches to get complete Chiloé data")
    
    # 1. Test complete fetch for one day
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    
    data = test_one_day_complete_fetch(yesterday)
    
    # 2. Estimate full month fetch
    estimate_full_month_fetch()
    
    # 3. Test alternative endpoints
    test_alternative_endpoints()
    
    print("\n" + "="*60)
    print("CONCLUSION:")
    print("Based on the tests, the optimal strategy is determined")
    print("="*60)