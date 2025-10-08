"""
ML Thresholds API - Proxy to Railway ML Backend

Lightweight Vercel endpoint that proxies threshold configuration
requests to Railway backend.
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
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        try:
            # Proxy to Railway backend
            import urllib.request

            url = f"{RAILWAY_URL}/api/ml_thresholds"

            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read()
                self.wfile.write(data)

        except Exception as e:
            # Fallback error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to connect to ML threshold service',
                'thresholds': []
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
