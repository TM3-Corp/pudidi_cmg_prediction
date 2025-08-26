"""
Live API Handler - Ultra-safe version for Vercel
"""

def handler(request):
    """
    Vercel serverless function - Cannot crash version
    """
    # Start with a guaranteed working response
    response = {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': ''
    }
    
    # Build predictions in the safest way possible
    predictions_list = []
    
    # Try to do the actual work
    try:
        import json
        from datetime import datetime, timedelta
        
        # Get current time (safest way)
        try:
            import pytz
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
        except:
            now = datetime.now()
        
        # Try to fetch data (but don't let it crash)
        data_source = "Synthetic"
        avg_value = 60.0
        
        try:
            import requests
            import numpy as np
            
            # Only if we can import everything, try to fetch
            SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
            SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
            CHILOE_NODE = 'CHILOE________220'
            
            url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            params = {
                'startDate': yesterday,
                'endDate': yesterday,
                'page': 1,
                'limit': 100,  # Smaller limit
                'user_key': SIP_API_KEY
            }
            
            # Very short timeout
            resp = requests.get(url, params=params, timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                records = data.get('data', [])
                
                # Look for Chiloé data
                for record in records:
                    if record.get('barra_transf') == CHILOE_NODE:
                        avg_value = float(record.get('cmg', 60))
                        data_source = "SIP API"
                        break
        except:
            # Any error in fetching - just use defaults
            pass
        
        # Generate 48 predictions
        for i in range(48):
            future = now + timedelta(hours=i+1)
            hour = future.hour
            
            # Simple pattern
            if 6 <= hour <= 9:
                base = avg_value * 1.3
            elif 18 <= hour <= 21:
                base = avg_value * 1.4
            elif 0 <= hour <= 5:
                base = avg_value * 0.7
            else:
                base = avg_value
            
            predictions_list.append({
                'datetime': future.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': hour,
                'cmg_predicted': round(base, 2),
                'is_prediction': True
            })
        
        # Build final result
        result = {
            'success': True,
            'location': 'Chiloé 220kV',
            'node': 'CHILOE________220',
            'data_source': data_source,
            'stats': {
                'avg_value': round(avg_value, 2),
                'predictions_count': len(predictions_list)
            },
            'predictions': predictions_list
        }
        
        response['body'] = json.dumps(result)
        
    except Exception as e:
        # Ultimate fallback - hardcoded response
        response['body'] = json.dumps({
            'success': False,
            'error': str(e)[:100],  # Limit error message length
            'predictions': [
                {'hour': i, 'cmg_predicted': 60.0}
                for i in range(24)
            ]
        })
    
    return response