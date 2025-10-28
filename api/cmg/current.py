"""
Main CMG endpoint - Returns cached data immediately
Fast response time (< 100ms) for excellent UX
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
import os
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.utils.cache_manager_readonly import CacheManagerReadOnly as CacheManager

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Return current cached CMG data immediately"""
        
        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=60')  # Client cache for 1 minute
        self.end_headers()
        
        try:
            # Initialize cache manager
            cache_manager = CacheManager()
            
            # Get combined display data
            display_data = cache_manager.get_combined_display_data()
            
            # Add response metadata
            response = {
                'success': True,
                'data': display_data,
                'cache_status': display_data['status']['overall']['status'],
                'needs_update': display_data['status']['overall']['needs_update']
            }
            
            self.wfile.write(json.dumps(response, default=str).encode())
            
        except Exception as e:
            # Error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve cached data',
                'data': {
                    'historical': {'available': False, 'data': []},
                    'programmed': {'available': False, 'data': []}
                }
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_OPTIONS(self):
        """Handle preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()