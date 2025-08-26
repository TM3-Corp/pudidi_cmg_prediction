"""
Live API Handler - Minimal robust version for Vercel
"""

import json
from datetime import datetime, timedelta

def handler(request):
    """
    Vercel serverless function - Minimal working version
    """
    try:
        # Import inside handler to reduce cold start
        import requests
        import numpy as np
        import pytz
        import os
        
        # Configuration
        SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
        SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
        CHILOE_NODE = 'CHILOE________220'
        
        # Get current time
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        
        # Try to fetch some CMG data
        try:
            url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            params = {
                'startDate': yesterday,
                'endDate': yesterday,
                'page': 1,
                'limit': 1000,
                'user_key': SIP_API_KEY
            }
            
            # Quick fetch with short timeout
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                # Filter for Chiloé
                chiloe_data = [r for r in records if r.get('barra_transf') == CHILOE_NODE]
                
                if chiloe_data:
                    # We have real data!
                    values = [float(r['cmg']) for r in chiloe_data]
                    avg_value = np.mean(values)
                    last_value = values[-1] if values else 60
                    
                    data_source = "SIP API (Real)"
                    success = True
                else:
                    # No Chiloé data in this page
                    avg_value = 60
                    last_value = 60
                    data_source = "Default (No Chiloé data found)"
                    success = False
            else:
                # API error
                avg_value = 60
                last_value = 60
                data_source = f"Default (API returned {response.status_code})"
                success = False
                
        except Exception as api_error:
            # Fetch failed, use defaults
            avg_value = 60
            last_value = 60
            data_source = f"Default (Fetch error)"
            success = False
            chiloe_data = []
        
        # Generate predictions (simple but working)
        predictions = []
        
        # Add any historical data we have
        for i, record in enumerate(chiloe_data[-24:]):
            predictions.append({
                'datetime': record.get('fecha_hora', now.strftime('%Y-%m-%d %H:%M:%S')),
                'cmg_actual': round(float(record.get('cmg', 60)), 2),
                'is_historical': True
            })
        
        # Generate future predictions
        for hour_offset in range(48):
            future_time = now + timedelta(hours=hour_offset + 1)
            hour = future_time.hour
            
            # Simple sinusoidal pattern based on hour
            base = avg_value
            variation = 15 * np.sin((hour - 6) * np.pi / 12)
            predicted = base + variation + np.random.uniform(-5, 5)
            
            predictions.append({
                'datetime': future_time.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': hour,
                'cmg_predicted': round(max(20, predicted), 2),
                'is_prediction': True
            })
        
        # Build response
        result = {
            'success': success,
            'location': 'Chiloé 220kV',
            'node': CHILOE_NODE,
            'data_source': data_source,
            'stats': {
                'avg_value': round(avg_value, 2),
                'last_value': round(last_value, 2),
                'predictions_count': len(predictions)
            },
            'predictions': predictions[:72]
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
        }
        
    except Exception as e:
        # Emergency fallback - return something no matter what
        emergency_response = {
            'success': False,
            'error': str(e),
            'location': 'Chiloé 220kV',
            'predictions': []
        }
        
        # Add some basic predictions even in error
        now = datetime.now()
        for i in range(48):
            future = now + timedelta(hours=i+1)
            emergency_response['predictions'].append({
                'datetime': future.strftime('%Y-%m-%d %H:%M:%S'),
                'cmg_predicted': 60.0,
                'is_prediction': True
            })
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(emergency_response)
        }