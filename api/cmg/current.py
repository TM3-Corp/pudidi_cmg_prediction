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

# Node name mapping: Supabase storage format → Frontend display format
# Reverse of NODE_MAPPING in scripts/store_cmg_programado.py
NODE_DB_TO_FRONTEND = {
    'NVA_P.MONTT___220': 'PMontt220',
    'PIDPID________110': 'Pidpid110',
    'DALCAHUE______110': 'Dalcahue110'
}

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

                # Get current time in Santiago
                santiago_tz = pytz.timezone('America/Santiago')
                now = datetime.now(santiago_tz)
                current_date = now.date()
                current_hour = now.hour

                # CMG Online: Query last 7 days, then filter to 48 hours in memory
                # (Broader query to ensure we don't miss data due to timezone/boundary issues)
                historical_start_date = current_date - timedelta(days=7)
                cmg_online_records = supabase.get_cmg_online(
                    start_date=str(historical_start_date),
                    end_date=str(current_date),
                    limit=1000
                )

                # CMG Programado: From current hour onwards (future data only)
                # Fetch from today up to 3 days ahead
                programmed_end_date = current_date + timedelta(days=3)
                cmg_programado_records = supabase.get_cmg_programado(
                    start_date=str(current_date),
                    end_date=str(programmed_end_date),
                    limit=200
                )

                # Convert to flat array format for frontend compatibility
                # Frontend expects array of {date, hour, node, cmg_usd, datetime}
                historical_data = []
                for record in cmg_online_records:
                    record_datetime = datetime.strptime(f"{record['date']} {record['hour']:02d}:00:00", '%Y-%m-%d %H:%M:%S')
                    record_datetime = santiago_tz.localize(record_datetime)

                    # Only include PAST data from last 48 hours (not future data)
                    hours_ago = (now - record_datetime).total_seconds() / 3600
                    if 0 <= hours_ago <= 48:  # Must be in the past AND within 48 hours
                        historical_data.append({
                            'date': str(record['date']),
                            'hour': record['hour'],
                            'node': record['node'],
                            'cmg_usd': float(record['cmg_usd']),
                            'datetime': f"{record['date']} {record['hour']:02d}:00:00"
                        })

                programmed_data = []
                for record in cmg_programado_records:
                    # FIXED: Use correct schema column names (target_date, target_hour, cmg_usd)
                    record_datetime = datetime.strptime(f"{record['target_date']} {record['target_hour']:02d}:00:00", '%Y-%m-%d %H:%M:%S')
                    record_datetime = santiago_tz.localize(record_datetime)

                    # Only include FUTURE data (from next hour onwards)
                    if record_datetime > now:
                        # Transform node name from DB format to frontend format
                        db_node = record['node']
                        frontend_node = NODE_DB_TO_FRONTEND.get(db_node, db_node)

                        programmed_data.append({
                            'date': str(record['target_date']),
                            'hour': record['target_hour'],
                            'node': frontend_node,  # Use transformed node name
                            'cmg_programmed': float(record['cmg_usd']),  # Schema uses cmg_usd
                            'datetime': f"{record['target_date']} {record['target_hour']:02d}:00:00"
                        })

                # Get last update time from most recent historical data
                last_updated = historical_data[0]['datetime'] if historical_data else now.isoformat()

                # Build display data structure
                display_data = {
                    'historical': {
                        'available': len(historical_data) > 0,
                        'data': historical_data,
                        'coverage': min((len(historical_data) / 24) * 100, 100) if historical_data else 0,
                        'last_updated': last_updated  # FIXED: Add last_updated field for frontend status display
                    },
                    'programmed': {
                        'available': len(programmed_data) > 0,
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