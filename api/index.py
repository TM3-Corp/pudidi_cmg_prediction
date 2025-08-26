from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Simple response with predictions
        predictions = []
        now = datetime.now()
        
        for i in range(48):
            future = now + timedelta(hours=i+1)
            predictions.append({
                'datetime': future.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': future.hour,
                'cmg_predicted': 60.0 + (10.0 if 6 <= future.hour <= 21 else -10.0),
                'is_prediction': True
            })
        
        response = {
            'success': True,
            'location': 'Chiloé 220kV',
            'node': 'CHILOE________220',
            'data_source': 'Default',
            'message': 'API is working with basic predictions',
            'predictions': predictions
        }
        
        self.wfile.write(json.dumps(response).encode())
        return