"""
API endpoint to serve cache files
"""

from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Serve cache files"""
        
        # Parse query parameters
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)
        
        # Get the type parameter
        cache_type = query_params.get('type', [''])[0]
        
        # Map cache type to file
        if cache_type == 'programmed':
            cache_file = 'cmg_programmed_latest.json'
        elif cache_type == 'historical':
            cache_file = 'cmg_historical_latest.json'
        elif cache_type == 'metadata':
            cache_file = 'metadata.json'
        else:
            # Return 404
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Cache file not found'}).encode())
            return
        
        # Try to read the cache file
        cache_path = Path(__file__).parent.parent / 'data' / 'cache' / cache_file
        
        # Try alternative paths
        if not cache_path.exists():
            alt_paths = [
                Path('data/cache') / cache_file,
                Path('/var/task/data/cache') / cache_file,
                Path('/tmp/data/cache') / cache_file
            ]
            for alt in alt_paths:
                if alt.exists():
                    cache_path = alt
                    break
        
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'error': 'Cache file not found',
                'searched': str(cache_path),
                'file': cache_file
            }).encode())