"""
Find all Chiloé/Dalcahue related nodes in the API
"""
import requests
from datetime import datetime, timedelta

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

url = f"{SIP_BASE_URL}/costo-marginal-real/v4/findByDate"

# Use a date that we know has data
test_date = datetime(2025, 7, 25)

params = {
    'startDate': test_date.strftime('%Y-%m-%d'),
    'endDate': test_date.strftime('%Y-%m-%d'),
    'limit': 5000,  # Get all records
    'user_key': SIP_API_KEY
}

print(f"Fetching all nodes for {test_date.strftime('%Y-%m-%d')}...")

try:
    response = requests.get(url, params=params, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        if 'data' in data and data['data']:
            # Get all unique nodes
            all_nodes = list(set(item.get('barra_transf', '') for item in data['data']))
            all_nodes.sort()
            
            print(f"\nTotal unique nodes: {len(all_nodes)}")
            
            # Find Chiloé related
            chiloe_keywords = ['CHILOE', 'DALCAHUE', 'CASTRO', 'QUELLON', 'ANCUD', 'CHONCHI']
            related_nodes = []
            
            for node in all_nodes:
                for keyword in chiloe_keywords:
                    if keyword in node.upper():
                        related_nodes.append(node)
                        break
            
            if related_nodes:
                print(f"\nFound {len(related_nodes)} Chiloé-related nodes:")
                for node in related_nodes:
                    # Get sample data for this node
                    node_data = [item for item in data['data'] if item.get('barra_transf') == node]
                    if node_data:
                        sample = node_data[0]
                        print(f"  - {node}: ${sample['cmg_usd_mwh_']:.2f} at {sample['fecha_hora']}")
            else:
                print("\nNo Chiloé-related nodes found")
                print("\nSample of all nodes:")
                for node in all_nodes[:20]:
                    print(f"  - {node}")
                    
            # Also look for nodes with '220' voltage (common for major nodes)
            nodes_220 = [n for n in all_nodes if '220' in n]
            print(f"\n220kV nodes ({len(nodes_220)} total):")
            for node in nodes_220[:10]:
                print(f"  - {node}")
                
except Exception as e:
    print(f"Error: {e}")