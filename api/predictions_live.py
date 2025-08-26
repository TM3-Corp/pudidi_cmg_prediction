from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Initialize response data
        predictions = []
        data_source = "Synthetic"
        avg_value = 60.0
        success = False
        
        try:
            import pytz
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
        except:
            now = datetime.now()
        
        # Try to fetch real data
        try:
            import requests
            
            SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
            SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
            CHILOE_NODE = 'CHILOE________220'
            
            url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            params = {
                'startDate': yesterday,
                'endDate': yesterday,
                'page': 1,
                'limit': 100,
                'user_key': SIP_API_KEY
            }
            
            # Quick fetch attempt
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                # Look for Chiloé data
                chiloe_records = [r for r in records if r.get('barra_transf') == CHILOE_NODE]
                
                if chiloe_records:
                    values = [float(r.get('cmg', 60)) for r in chiloe_records]
                    avg_value = sum(values) / len(values)
                    data_source = "SIP API"
                    success = True
                    
                    # Add historical data
                    for record in chiloe_records[:24]:
                        predictions.append({
                            'datetime': record.get('fecha_hora'),
                            'hour': int(record.get('fecha_hora', '00:00')[11:13]),
                            'cmg_actual': float(record.get('cmg', 60)),
                            'is_historical': True
                        })
        except Exception as e:
            # API fetch failed - continue with synthetic
            pass
        
        # Generate future predictions
        for i in range(48):
            future = now + timedelta(hours=i+1)
            hour = future.hour
            
            # Simple hourly pattern
            if 6 <= hour <= 9:  # Morning peak
                multiplier = 1.3
            elif 18 <= hour <= 21:  # Evening peak
                multiplier = 1.4
            elif 0 <= hour <= 5:  # Night low
                multiplier = 0.7
            else:
                multiplier = 1.0
            
            predicted_value = avg_value * multiplier
            
            predictions.append({
                'datetime': future.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': hour,
                'cmg_predicted': round(predicted_value, 2),
                'confidence_lower': round(predicted_value * 0.9, 2),
                'confidence_upper': round(predicted_value * 1.1, 2),
                'is_prediction': True
            })
        
        # Build response
        result = {
            'success': success,
            'location': 'Chiloé 220kV',
            'node': 'CHILOE________220',
            'data_source': data_source,
            'stats': {
                'avg_value': round(avg_value, 2),
                'predictions_count': len(predictions)
            },
            'predictions': predictions[:72]
        }
        
        self.wfile.write(json.dumps(result).encode())
        return
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        return