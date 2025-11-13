"""
Main CMG endpoint - Returns data from Supabase
Fast response time for excellent UX
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

try:
    # Try to import Supabase client
    from lib.utils.supabase_client import SupabaseClient
    USE_SUPABASE = True
except Exception as e:
    print(f"⚠️ Supabase unavailable, falling back to cache: {e}")
    from lib.utils.cache_manager_readonly import CacheManagerReadOnly as CacheManager
    USE_SUPABASE = False

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Return current CMG data from Supabase or cache fallback"""

        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=60')  # Client cache for 1 minute
        self.end_headers()

        try:
            if USE_SUPABASE:
                # Initialize Supabase client (read-only with anon key)
                supabase = SupabaseClient()

                # Get last 7 days of data
                santiago_tz = pytz.timezone('America/Santiago')
                end_date = datetime.now(santiago_tz).date()
                start_date = end_date - timedelta(days=7)

                # Fetch data from Supabase
                cmg_online_records = supabase.get_cmg_online(
                    start_date=str(start_date),
                    end_date=str(end_date),
                    limit=5000
                )

                cmg_programado_records = supabase.get_cmg_programado(
                    start_date=str(start_date),
                    end_date=str(end_date),
                    limit=5000
                )

                # Format as cache structure for API compatibility
                historical_data = supabase.format_cmg_online_as_cache(cmg_online_records)
                programmed_data = supabase.format_cmg_programado_as_cache(cmg_programado_records)

                # Build display data structure
                display_data = {
                    'historical': {
                        'available': len(cmg_online_records) > 0,
                        'data': historical_data
                    },
                    'programmed': {
                        'available': len(cmg_programado_records) > 0,
                        'data': programmed_data
                    },
                    'status': {
                        'overall': {
                            'status': 'operational',
                            'needs_update': False
                        }
                    },
                    'source': 'supabase'
                }

            else:
                # Fallback to cache files
                cache_manager = CacheManager()
                display_data = cache_manager.get_combined_display_data()
                display_data['source'] = 'cache_fallback'

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
                'message': 'Failed to retrieve data',
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