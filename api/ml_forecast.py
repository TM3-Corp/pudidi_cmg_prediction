"""
ML Forecast API - Proxy to Railway ML Backend

Lightweight Vercel endpoint that proxies requests to Railway
where the heavy ML models and processing run.
"""

from http.server import BaseHTTPRequestHandler
import json
import os

# Railway backend URL (set as environment variable in Vercel)
RAILWAY_URL = os.environ.get('RAILWAY_ML_URL', 'http://localhost:8000')

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Proxy request to Railway ML backend"""

        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=300')  # Cache for 5 minutes
        self.end_headers()

        try:
            # Proxy to Railway backend
            import urllib.request

            url = f"{RAILWAY_URL}/api/ml_forecast"

            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read()
                self.wfile.write(data)

        except Exception as e:
            # Fallback error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to connect to ML prediction service',
                'predictions': [],
                'status': {
                    'available': False,
                    'last_update': None
                }
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
