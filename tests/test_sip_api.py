"""
Test SIP API directly to debug data fetching
"""
import requests
from datetime import datetime, timedelta

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

def test_cmg_real():
    """Test CMG Real endpoint"""
    url = f"{SIP_BASE_URL}/costo-marginal-real/v4/findByDate"
    
    # Try different date ranges
    end_date = datetime(2025, 8, 25) - timedelta(hours=3)  # Santiago time
    dates_to_try = [
        end_date,  # Today
        end_date - timedelta(days=1),  # Yesterday
        end_date - timedelta(days=2),  # 2 days ago
        datetime(2025, 8, 20),  # Fixed date
        datetime(2025, 8, 15),  # Week ago
        datetime(2025, 7, 25),  # Month ago
        datetime(2024, 8, 25),  # Year ago
    ]
    
    for test_date in dates_to_try:
        params = {
            'startDate': test_date.strftime('%Y-%m-%d'),
            'endDate': test_date.strftime('%Y-%m-%d'),
            'limit': 100,
            'user_key': SIP_API_KEY
        }
        
        print(f"\nTrying date: {test_date.strftime('%Y-%m-%d')}")
        
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
                                   if item.get('barra_transf') == CHILOE_NODE]
                    print(f"  Chiloé records: {len(chiloe_data)}")
                    
                    if chiloe_data:
                        # Show sample
                        sample = chiloe_data[0]
                        print(f"  Sample: {sample['fecha_hora']} - ${sample['cmg_usd_mwh_']:.2f}")
                        return True  # Found data!
                    else:
                        # Show available nodes
                        nodes = list(set(item['barra_transf'] for item in data['data'][:20]))
                        chiloe_nodes = [n for n in nodes if 'CHILOE' in n or 'DALCAHUE' in n]
                        if chiloe_nodes:
                            print(f"  Chiloé-related nodes: {chiloe_nodes}")
                        else:
                            print(f"  Sample nodes: {nodes[:5]}")
            else:
                print(f"  Error response: {response.text[:200]}")
                
        except Exception as e:
            print(f"  Error: {e}")
    
    return False

def test_cmg_programado():
    """Test CMG Programado (PCP) endpoint"""
    url = f"{SIP_BASE_URL}/costos-marginales-promedio/v3/pcp"
    
    print("\n\nTesting CMG Programado (PCP):")
    
    params = {
        'fecha': datetime.now().strftime('%Y-%m-%d'),
        'user_key': SIP_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and data['data']:
                print(f"Found {len(data['data'])} records")
                # Look for Chiloé
                chiloe_data = [item for item in data['data'] 
                               if 'CHILOE' in item.get('barra', '')]
                if chiloe_data:
                    print(f"Chiloé PCP records: {len(chiloe_data)}")
                    print(f"Sample: {chiloe_data[0]}")
                else:
                    nodes = list(set(item.get('barra', '') for item in data['data'][:20]))
                    print(f"Sample nodes: {nodes[:5]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Testing SIP API access...")
    print("=" * 50)
    
    found_data = test_cmg_real()
    
    if not found_data:
        print("\n⚠️  No CMG Real data found for any date tested")
        print("This might mean:")
        print("  1. The API key might need refresh")
        print("  2. The node name might have changed")
        print("  3. Data might not be available for 2025 yet")
    
    test_cmg_programado()