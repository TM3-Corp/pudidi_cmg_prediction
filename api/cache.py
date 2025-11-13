"""
API endpoint to serve cached data from Supabase
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from lib.utils.supabase_client import SupabaseClient
    USE_SUPABASE = True
except Exception as e:
    print(f"⚠️ Supabase unavailable, falling back to cache files: {e}")
    USE_SUPABASE = False

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Serve cache data from Supabase or fallback to files"""

        # Parse query parameters
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        # Get the type parameter
        cache_type = query_params.get('type', [''])[0]

        # CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')

        if not cache_type:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Missing type parameter'}).encode())
            return

        try:
            if USE_SUPABASE:
                # Fetch from Supabase
                supabase = SupabaseClient()
                santiago_tz = pytz.timezone('America/Santiago')
                end_date = datetime.now(santiago_tz).date()
                start_date = end_date - timedelta(days=30)  # Last 30 days

                if cache_type == 'programmed':
                    records = supabase.get_cmg_programado(
                        start_date=str(start_date),
                        end_date=str(end_date),
                        limit=10000
                    )
                    data = supabase.format_cmg_programado_as_cache(records)

                elif cache_type == 'historical':
                    records = supabase.get_cmg_online(
                        start_date=str(start_date),
                        end_date=str(end_date),
                        limit=10000
                    )
                    data = supabase.format_cmg_online_as_cache(records)

                elif cache_type == 'metadata':
                    data = {
                        'timestamp': datetime.now(santiago_tz).isoformat(),
                        'source': 'supabase',
                        'last_update': datetime.now(santiago_tz).isoformat()
                    }

                else:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Unknown cache type'}).encode())
                    return

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data, default=str).encode())

            else:
                # Fallback to cache files
                if cache_type == 'programmed':
                    cache_file = 'cmg_programmed_latest.json'
                elif cache_type == 'historical':
                    cache_file = 'cmg_historical_latest.json'
                elif cache_type == 'metadata':
                    cache_file = 'metadata.json'
                else:
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
                    with open(cache_path, 'r') as f:
                        data = json.load(f)

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())

                else:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Cache file not found',
                        'searched': str(cache_path),
                        'file': cache_file
                    }).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
