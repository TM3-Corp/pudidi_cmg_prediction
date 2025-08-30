"""
Test CMG Online endpoint to get proper last 24 hours data
"""
import requests
from datetime import datetime, timedelta
import pytz

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

def fetch_cmg_online_last_24h():
    """Fetch CMG Online data for the last 24 hours"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print(f"Current Santiago time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 60)
    
    # CMG Online endpoint
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    all_chiloe_data = []
    
    # Try to get last 3 days to ensure we have data
    for days_back in range(0, 10):
        check_date = now - timedelta(days=days_back)
        
        params = {
            'startDate': check_date.strftime('%Y-%m-%d'),
            'endDate': check_date.strftime('%Y-%m-%d'),
            'limit': 5000,  # Get all nodes for this day
            'user_key': SIP_API_KEY
        }
        
        print(f"\nChecking {check_date.strftime('%Y-%m-%d')}...")
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    # Filter for Chiloé
                    chiloe_records = []
                    for item in data['data']:
                        if item.get('barra_transf') == CHILOE_NODE:
                            chiloe_records.append({
                                'datetime': item['fecha_hora'],
                                'cmg': float(item.get('cmg_usd_mwh', 0) or item.get('cmg_usd_mwh_', 0)),
                                'node': item['barra_transf']
                            })
                    
                    if chiloe_records:
                        print(f"  Found {len(chiloe_records)} Chiloé records")
                        all_chiloe_data.extend(chiloe_records)
                        
                        # Show sample
                        for rec in chiloe_records[:3]:
                            print(f"    {rec['datetime']}: ${rec['cmg']:.2f}")
                    else:
                        print(f"  No Chiloé data (total records: {len(data['data'])})")
                        # Check what nodes exist
                        nodes = list(set(item['barra_transf'] for item in data['data'][:100]))
                        chiloe_related = [n for n in nodes if 'CHILOE' in n]
                        if chiloe_related:
                            print(f"  Found related nodes: {chiloe_related}")
                else:
                    print(f"  No data returned")
            else:
                print(f"  Error: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"  Timeout - trying next date")
        except Exception as e:
            print(f"  Error: {e}")
    
    # Sort all data
    all_chiloe_data.sort(key=lambda x: x['datetime'])
    
    if all_chiloe_data:
        print("\n" + "=" * 60)
        print(f"TOTAL Chiloé records found: {len(all_chiloe_data)}")
        print(f"Date range: {all_chiloe_data[0]['datetime']} to {all_chiloe_data[-1]['datetime']}")
        
        # Get last 24 hours
        cutoff = now - timedelta(hours=24)
        last_24h = [d for d in all_chiloe_data if datetime.strptime(d['datetime'], '%Y-%m-%d %H:%M:%S') > cutoff.replace(tzinfo=None)]
        
        print(f"\nRecords in last 24 hours: {len(last_24h)}")
        if last_24h:
            print("Last 5 records:")
            for rec in last_24h[-5:]:
                print(f"  {rec['datetime']}: ${rec['cmg']:.2f}")
    
    return all_chiloe_data

def fetch_cmg_programado():
    """Test CMG Programado endpoints"""
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("\n" + "=" * 60)
    print("Testing CMG Programado (PCP and PID)")
    print("=" * 60)
    
    for endpoint_name, endpoint_url in [
        ('PCP (Day-ahead)', '/cmg-programado-pcp/v4/findByDate'),
        ('PID (Intraday)', '/cmg-programado-pid/v4/findByDate')
    ]:
        print(f"\n{endpoint_name}:")
        url = f"{SIP_BASE_URL}{endpoint_url}"
        
        params = {
            'startDate': (now - timedelta(days=1)).strftime('%Y-%m-%d'),
            'endDate': (now + timedelta(days=1)).strftime('%Y-%m-%d'),
            'limit': 5000,
            'user_key': SIP_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    # Look for Chiloé
                    chiloe_records = []
                    for item in data['data']:
                        if 'CHILOE' in str(item.get('nmb_barra_info', '')):
                            chiloe_records.append({
                                'datetime': item['fecha_hora'],
                                'cmg': float(item['cmg_usd_mwh']),
                                'node': item['nmb_barra_info']
                            })
                    
                    if chiloe_records:
                        # Sort and show
                        chiloe_records.sort(key=lambda x: x['datetime'])
                        print(f"  Found {len(chiloe_records)} Chiloé records")
                        print(f"  Date range: {chiloe_records[0]['datetime']} to {chiloe_records[-1]['datetime']}")
                        
                        # Show hourly coverage
                        unique_hours = set(r['datetime'][:13] for r in chiloe_records)  # YYYY-MM-DD HH
                        print(f"  Unique hours covered: {len(unique_hours)}")
                        
                        # Show sample
                        print("  Sample records:")
                        for rec in chiloe_records[-5:]:
                            print(f"    {rec['datetime']}: ${rec['cmg']:.2f} at {rec['node']}")
                    else:
                        print(f"  No Chiloé data found (total: {len(data['data'])} records)")
                else:
                    print("  No data returned")
            else:
                print(f"  Error: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    print("Testing SIP API endpoints for Chiloé CMG data")
    print("=" * 60)
    
    # Test CMG Online
    online_data = fetch_cmg_online_last_24h()
    
    # Test CMG Programado
    fetch_cmg_programado()
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    if online_data:
        print(f"✅ Found {len(online_data)} total CMG Online records for Chiloé")
    else:
        print("❌ No CMG Online data found for Chiloé")
    
    print("\nNOTE: CMG Online typically has a delay of several days")
    print("For real-time data, use CMG Programado (PCP/PID)")