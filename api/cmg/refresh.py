"""
Refresh endpoint - Triggers incremental data update
Only fetches new/missing data to optimize performance
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
from utils.cache_manager import CacheManager
from utils.fetcher_optimized import OptimizedCMGFetcher

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Trigger incremental refresh of CMG data"""
        
        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
            
            # Initialize components
            cache_manager = CacheManager()
            fetcher = OptimizedCMGFetcher()
            
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
            
            if needs_refresh:
                # Perform incremental update
                update_result = fetcher.fetch_incremental_update(last_hours=3)
                
                # Update historical cache
                if update_result['historical']['data']:
                    merged_historical = cache_manager.merge_historical_data(
                        update_result['historical']['data'],
                        window_hours=24
                    )
                    cache_manager.write_cache('historical', merged_historical)
                
                # Update programmed cache
                if update_result['programmed']['data']:
                    cache_manager.write_cache('programmed', update_result['programmed'])
                
                # Update metadata
                metadata = {
                    'timestamp': now.isoformat(),
                    'last_refresh': now.isoformat(),
                    'refresh_reason': refresh_reason,
                    'historical_records': len(update_result['historical']['data']),
                    'programmed_records': len(update_result['programmed']['data'])
                }
                cache_manager.write_cache('metadata', metadata)
                
                response = {
                    'success': True,
                    'refreshed': True,
                    'timestamp': now.isoformat(),
                    'reason': refresh_reason,
                    'statistics': {
                        'historical': update_result['historical']['statistics'],
                        'programmed': update_result['programmed']['statistics']
                    }
                }
            else:
                # No refresh needed
                response = {
                    'success': True,
                    'refreshed': False,
                    'timestamp': now.isoformat(),
                    'message': 'Cache is up to date',
                    'cache_age': {
                        'historical': hist_cache.get('age_hours', 0),
                        'programmed': prog_cache.get('age_hours', 0)
                    }
                }
            
            self.wfile.write(json.dumps(response, default=str).encode())
            
        except Exception as e:
            # Error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to refresh data',
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