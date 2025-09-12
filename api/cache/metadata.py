"""
API endpoint to serve cache metadata
"""

from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Serve cache metadata"""
        
        # Set CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        
        # Look for the cache file
        cache_file = 'metadata.json'
        
        # Try different paths
        possible_paths = [
            Path(__file__).parent.parent.parent / 'data' / 'cache' / cache_file,
            Path('data/cache') / cache_file,
            Path('/var/task/data/cache') / cache_file,
            Path('/tmp/data/cache') / cache_file,
            Path('/tmp') / cache_file
        ]
        
        cache_path = None
        for path in possible_paths:
            if path.exists():
                cache_path = path
                break
        
        if cache_path and cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
                
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': f'Error reading cache file: {str(e)}',
                    'path': str(cache_path)
                }).encode())
        else:
            # If file doesn't exist, return empty metadata
            self.end_headers()
            self.wfile.write(json.dumps({
                'last_update': None,
                'error': 'Metadata file not found',
                'searched_paths': [str(p) for p in possible_paths]
            }).encode())
    
    def do_OPTIONS(self):
        """Handle preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()