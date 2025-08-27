"""
Refresh endpoint - For Vercel read-only environment
Returns refresh status but actual update happens via GitHub Actions
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.cache_manager_readonly import CacheManagerReadOnly as CacheManager

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Check if refresh is needed (actual refresh happens via GitHub Actions)"""
        
        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
            
            # Initialize cache manager (read-only)
            cache_manager = CacheManager()
            
            # Check cache status
            status = cache_manager.get_cache_status()
            
            # Determine if refresh is needed
            needs_refresh = False
            refresh_reason = []
            
            # Check historical cache
            hist_cache = status['caches'].get('historical', {})
            if not hist_cache.get('exists') or hist_cache.get('age_hours', 24) > 1:
                needs_refresh = True
                refresh_reason.append('historical_stale')
            
            # Check programmed cache
            prog_cache = status['caches'].get('programmed', {})
            if not prog_cache.get('exists') or prog_cache.get('age_hours', 24) > 2:
                needs_refresh = True
                refresh_reason.append('programmed_stale')
            
            # In Vercel, we can't actually refresh - that happens via GitHub Actions
            response = {
                'success': True,
                'needs_refresh': needs_refresh,
                'timestamp': now.isoformat(),
                'reason': refresh_reason,
                'message': 'Refresh happens automatically via GitHub Actions every hour',
                'cache_age': {
                    'historical': hist_cache.get('age_hours', 0),
                    'programmed': prog_cache.get('age_hours', 0)
                },
                'next_update': (now.replace(minute=5, second=0) + timedelta(hours=1)).isoformat() if now.minute > 5 else now.replace(minute=5, second=0).isoformat(),
                'environment': 'read-only (Vercel)'
            }
            
            self.wfile.write(json.dumps(response, default=str).encode())
            
        except Exception as e:
            # Error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to check refresh status',
                'timestamp': datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_OPTIONS(self):
        """Handle preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()