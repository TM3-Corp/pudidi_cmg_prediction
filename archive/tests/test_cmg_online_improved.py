"""Test improved CMG Online fetching with pagination"""
import requests
from datetime import datetime, timedelta
import pytz

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

def test_cmg_online_pagination():
    """Test CMG Online with smart pagination"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print(f"Testing CMG Online at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("="*60)
    
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    # Test for today
    date_str = now.strftime('%Y-%m-%d')
    print(f"\nSearching for Chiloé data on {date_str}...")
    
    found_chiloe = False
    chiloe_data = []
    
    # Search up to 10 pages
    for page in range(1, 11):
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        print(f"\nFetching page {page}...")
        
        try:
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                total_pages = data.get('totalPages', 0)
                
                if page == 1:
                    print(f"  Total pages available: {total_pages}")
                    print(f"  Total records: ~{total_pages * 1000}")
                
                if 'data' in data and data['data']:
                    # Check for Chiloé
                    for item in data['data']:
                        if item.get('barra_transf') == CHILOE_NODE:
                            found_chiloe = True
                            chiloe_data.append({
                                'datetime': item['fecha_hora'],
                                'cmg': float(item.get('cmg_usd_mwh_', 0)),
                                'node': item['barra_transf']
                            })
                    
                    # Show some sample nodes from this page
                    sample_nodes = list(set(item['barra_transf'] for item in data['data'][:10]))
                    print(f"  Sample nodes on page {page}: {sample_nodes[:3]}")
                    
                    if found_chiloe:
                        print(f"\n✅ FOUND CHILOÉ DATA on page {page}!")
                        print(f"  Found {len(chiloe_data)} Chiloé records")
                        break
                else:
                    print(f"  No data on page {page}")
                    break
            else:
                print(f"  Error: HTTP {response.status_code}")
                break
                
        except Exception as e:
            print(f"  Error on page {page}: {e}")
            break
    
    if not found_chiloe:
        print(f"\n❌ Chiloé node not found in first {page} pages")
        print("Searching for nodes with 'CHILOE' in name...")
        
        # Try page 1 again and look for any Chiloé-related nodes
        params['page'] = 1
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    all_nodes = list(set(item['barra_transf'] for item in data['data']))
                    chiloe_related = [n for n in all_nodes if 'CHILOE' in n]
                    if chiloe_related:
                        print(f"Found related nodes: {chiloe_related}")
        except:
            pass
    
    # Show results
    if chiloe_data:
        chiloe_data.sort(key=lambda x: x['datetime'])
        print("\n" + "="*60)
        print(f"CHILOÉ DATA SUMMARY:")
        print(f"  Total records: {len(chiloe_data)}")
        print(f"  Time range: {chiloe_data[0]['datetime']} to {chiloe_data[-1]['datetime']}")
        print(f"\n  Last 5 records:")
        for rec in chiloe_data[-5:]:
            print(f"    {rec['datetime']}: ${rec['cmg']:.2f}")
    
    return chiloe_data

if __name__ == "__main__":
    test_cmg_online_pagination()