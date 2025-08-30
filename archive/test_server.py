#!/usr/bin/env python3
"""
Simple test server for local development
Serves both static files and API endpoints
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import sys
from urllib.parse import urlparse

# Add API directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

# Import the API handlers
from utils.cache_manager_readonly import CacheManagerReadOnly

class TestRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve files from current directory
        super().__init__(*args, directory=os.getcwd(), **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        
        # Handle API endpoints
        if parsed_path.path == '/api/cmg/current':
            self.handle_current()
        elif parsed_path.path == '/api/cmg/status':
            self.handle_status()
        elif parsed_path.path == '/api/cmg/refresh':
            self.handle_refresh()
        # Serve static files
        elif parsed_path.path.startswith('/public/'):
            # Adjust path to serve from public directory
            self.path = parsed_path.path[7:]  # Remove '/public' prefix
            SimpleHTTPRequestHandler.do_GET(self)
        elif parsed_path.path.endswith('.html'):
            # Serve HTML files from public directory
            self.path = f"/public{parsed_path.path}"
            self.path = self.path[7:]  # Remove '/public' prefix  
            SimpleHTTPRequestHandler.do_GET(self)
        else:
            SimpleHTTPRequestHandler.do_GET(self)
    
    def handle_current(self):
        """Handle /api/cmg/current endpoint"""
        try:
            cache_manager = CacheManagerReadOnly()
            display_data = cache_manager.get_combined_display_data()
            
            response = {
                'success': True,
                'data': display_data,
                'cache_status': display_data['status']['overall']['status'],
                'needs_update': display_data['status']['overall']['needs_update']
            }
            
            self.send_json_response(200, response)
        except Exception as e:
            self.send_json_response(500, {
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve cached data'
            })
    
    def handle_status(self):
        """Handle /api/cmg/status endpoint"""
        try:
            cache_manager = CacheManagerReadOnly()
            status = cache_manager.get_cache_status()
            
            response = {
                'success': True,
                'timestamp': status['timestamp'],
                'system': {
                    'status': status['overall']['status'],
                    'ready': status['overall']['ready'],
                    'needs_update': status['overall']['needs_update']
                },
                'caches': status['caches']
            }
            
            self.send_json_response(200, response)
        except Exception as e:
            self.send_json_response(500, {
                'success': False,
                'error': str(e)
            })
    
    def handle_refresh(self):
        """Handle /api/cmg/refresh endpoint"""
        response = {
            'success': True,
            'needs_refresh': False,
            'message': 'Test server - refresh happens via GitHub Actions',
            'environment': 'test'
        }
        self.send_json_response(200, response)
    
    def send_json_response(self, code, data):
        """Send JSON response"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
    
    def end_headers(self):
        """Add CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

def main():
    """Run the test server"""
    port = 3000
    server_address = ('', port)
    
    print(f"🚀 Starting test server on http://localhost:{port}")
    print(f"📊 Dashboard: http://localhost:{port}/public/index_fixed.html")
    print(f"📊 Original: http://localhost:{port}/public/index_new.html")
    print(f"🔌 API Status: http://localhost:{port}/api/cmg/status")
    print("\nPress Ctrl+C to stop the server")
    
    httpd = HTTPServer(server_address, TestRequestHandler)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n✋ Server stopped")
        httpd.shutdown()

if __name__ == '__main__':
    main()