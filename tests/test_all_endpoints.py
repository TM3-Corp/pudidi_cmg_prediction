"""
Test all CMG endpoints to find which has the most recent 24h data for Chiloé
"""
import requests
from datetime import datetime, timedelta
import pytz

SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Get Santiago time
santiago_tz = pytz.timezone('America/Santiago')
santiago_now = datetime.now(santiago_tz)
print(f"Current Santiago time: {santiago_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print("=" * 60)

# Calculate last 24 hours
end_date = santiago_now
start_date = santiago_now - timedelta(days=1)

endpoints = [
    {
        'name': 'CMG Programado PCP (Day-ahead)',
        'url': f"{SIP_BASE_URL}/cmg-programado-pcp/v4/findByDate",
        'node_field': 'nmb_barra_info',
        'cmg_field': 'cmg_usd_mwh',
        'date_field': 'fecha_hora'
    },
    {
        'name': 'CMG Programado PID (Intraday)',
        'url': f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate",
        'node_field': 'nmb_barra_info',
        'cmg_field': 'cmg_usd_mwh',
        'date_field': 'fecha_hora'
    },
    {
        'name': 'CMG Online',
        'url': f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate",
        'node_field': 'barra_transf',
        'cmg_field': 'cmg_usd_mwh',
        'date_field': 'fecha_hora'
    },
    {
        'name': 'CMG Real',
        'url': f"{SIP_BASE_URL}/costo-marginal-real/v4/findByDate",
        'node_field': 'barra_transf',
        'cmg_field': 'cmg_usd_mwh_',
        'date_field': 'fecha_hora'
    }
]

for endpoint in endpoints:
    print(f"\n{endpoint['name']}")
    print("-" * 40)
    
    # Test with last 2 days to ensure we get data
    params = {
        'startDate': (santiago_now - timedelta(days=2)).strftime('%Y-%m-%d'),
        'endDate': santiago_now.strftime('%Y-%m-%d'),
        'limit': 2000,
        'user_key': SIP_API_KEY
    }
    
    try:
        response = requests.get(endpoint['url'], params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            total = len(data.get('data', []))
            print(f"  Total records: {total}")
            
            if total > 0:
                # Find Chiloé data
                chiloe_data = []
                for item in data['data']:
                    node = item.get(endpoint['node_field'], '')
                    if 'CHILOE' in str(node).upper():
                        chiloe_data.append(item)
                
                if chiloe_data:
                    print(f"  Chiloé records: {len(chiloe_data)}")
                    
                    # Sort by date and show latest
                    sorted_data = sorted(chiloe_data, 
                                       key=lambda x: x.get(endpoint['date_field'], ''))
                    
                    if sorted_data:
                        latest = sorted_data[-1]
                        earliest = sorted_data[0]
                        
                        print(f"  Data range: {earliest[endpoint['date_field']]} to {latest[endpoint['date_field']]}")
                        
                        # Show last 5 hours
                        print(f"  Last 5 records:")
                        for item in sorted_data[-5:]:
                            dt = item[endpoint['date_field']]
                            cmg = item.get(endpoint['cmg_field'], 0)
                            node = item.get(endpoint['node_field'], '')
                            print(f"    {dt}: ${cmg:.2f} at {node}")
                        
                        # Calculate how recent the data is
                        latest_dt_str = latest[endpoint['date_field']]
                        # Parse datetime (handle different formats)
                        if ' ' in latest_dt_str:
                            latest_dt = datetime.strptime(latest_dt_str[:19], '%Y-%m-%d %H:%M:%S')
                        else:
                            latest_dt = datetime.strptime(latest_dt_str[:16], '%Y-%m-%d %H:%M')
                        
                        latest_dt = santiago_tz.localize(latest_dt)
                        hours_ago = (santiago_now - latest_dt).total_seconds() / 3600
                        print(f"  Most recent data: {hours_ago:.1f} hours ago")
                        
                        # Check if we have last 24 hours
                        hours_covered = set()
                        for item in chiloe_data:
                            dt_str = item[endpoint['date_field']]
                            if ' ' in dt_str:
                                dt = datetime.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S')
                            else:
                                dt = datetime.strptime(dt_str[:16], '%Y-%m-%d %H:%M')
                            hours_covered.add(dt.strftime('%Y-%m-%d %H'))
                        
                        print(f"  Hours with data: {len(hours_covered)}")
                        
                else:
                    # Check what nodes exist
                    sample = data['data'][0]
                    print(f"  No Chiloé data found")
                    print(f"  Sample node: {sample.get(endpoint['node_field'], 'N/A')}")
                    
        else:
            print(f"  Error: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "=" * 60)
print("SUMMARY:")
print("For complete last 24 hours data, use CMG Programado PCP or PID")
print("These provide forecast/scheduled data that is available in advance")