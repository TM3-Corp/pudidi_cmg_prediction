"""
Test CMG Online endpoint for recent data
"""
import requests
from datetime import datetime, timedelta

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

def test_cmg_online():
    """Test CMG Online endpoint"""
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    # Try recent dates
    end_date = datetime.now() - timedelta(hours=3)  # Santiago time
    dates_to_try = [
        (end_date - timedelta(days=1), end_date),  # Last 24 hours
        (end_date - timedelta(days=2), end_date - timedelta(days=1)),  # Previous day
        (datetime(2025, 8, 24), datetime(2025, 8, 25)),  # Specific dates
        (datetime(2025, 8, 20), datetime(2025, 8, 21)),
    ]
    
    for start_date, end_date in dates_to_try:
        params = {
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d'),
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        print(f"\nTrying CMG Online: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        try:
            response = requests.get(url, params=params, timeout=10)
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                total_records = len(data.get('data', []))
                print(f"  Total records: {total_records}")
                
                if total_records > 0:
                    # Check for Chiloé data
                    chiloe_data = [item for item in data['data'] 
                                   if item.get('barra_transf') == CHILOE_NODE or 
                                   item.get('barra') == CHILOE_NODE]
                    print(f"  Chiloé records: {len(chiloe_data)}")
                    
                    if chiloe_data:
                        # Show recent data
                        recent = sorted(chiloe_data, key=lambda x: x.get('fecha_hora', ''))[-5:]
                        for item in recent:
                            cmg_field = 'cmg_usd_mwh' if 'cmg_usd_mwh' in item else 'cmg_usd_mwh_'
                            if cmg_field in item:
                                print(f"    {item.get('fecha_hora')}: ${item[cmg_field]:.2f}")
                        return True
                    else:
                        # Check field names
                        sample = data['data'][0]
                        print(f"  Sample fields: {list(sample.keys())[:10]}")
                        
        except Exception as e:
            print(f"  Error: {e}")
    
    return False

def test_cmg_programado_pcp():
    """Test CMG Programado PCP endpoint"""
    url = f"{SIP_BASE_URL}/cmg-programado-pcp/v4/findByDate"
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=1)
    
    params = {
        'startDate': start_date.strftime('%Y-%m-%d'),
        'endDate': end_date.strftime('%Y-%m-%d'),
        'limit': 1000,
        'user_key': SIP_API_KEY
    }
    
    print(f"\n\nTrying CMG Programado PCP: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            total_records = len(data.get('data', []))
            print(f"  Total records: {total_records}")
            
            if total_records > 0:
                # Check for Chiloé
                sample = data['data'][0]
                print(f"  Sample fields: {list(sample.keys())}")
                
                chiloe_data = [item for item in data['data'] 
                               if CHILOE_NODE in str(item.get('barra_transf', '')) or
                               CHILOE_NODE in str(item.get('barra', ''))]
                
                if chiloe_data:
                    print(f"  Chiloé PCP records: {len(chiloe_data)}")
                    for item in chiloe_data[:3]:
                        print(f"    {item}")
                        
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    print("Testing CMG Online and Programado endpoints...")
    print("=" * 50)
    
    found_online = test_cmg_online()
    test_cmg_programado_pcp()
    
    if found_online:
        print("\n✅ Found CMG Online data!")
    else:
        print("\n⚠️ No recent CMG Online data found")