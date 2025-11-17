"""
Historical Comparison API - Returns historical data for forecast accuracy analysis

Returns:
- ML Predictions (historical forecasts)
- CMG Programado (historical programmed values)
- CMG Online (actual values)

All data for the last 30 days for comparison analysis
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
    from lib.utils.supabase_client import SupabaseClient
    USE_SUPABASE = True
except Exception as e:
    print(f"⚠️ Supabase unavailable: {e}")
    USE_SUPABASE = False

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Return historical data for all 3 sources"""

        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=300')  # Cache for 5 minutes
        self.end_headers()

        try:
            if USE_SUPABASE:
                # Initialize Supabase client
                supabase = SupabaseClient()

                # Get date range (last 30 days for historical comparison)
                santiago_tz = pytz.timezone('America/Santiago')
                end_date = datetime.now(santiago_tz).date()
                start_date = end_date - timedelta(days=30)

                # Fetch all data sources
                ml_predictions = supabase.get_ml_predictions(
                    start_date=str(start_date),
                    end_date=str(end_date),
                    limit=10000
                )

                cmg_programado = supabase.get_cmg_programado(
                    start_date=str(start_date),
                    end_date=str(end_date),
                    limit=10000
                )

                cmg_online = supabase.get_cmg_online(
                    start_date=str(start_date),
                    end_date=str(end_date),
                    limit=10000
                )

                # Format data for frontend
                # Group ML predictions by forecast date
                ml_by_forecast = {}
                for pred in ml_predictions:
                    forecast_dt = pred['forecast_datetime']
                    if forecast_dt not in ml_by_forecast:
                        ml_by_forecast[forecast_dt] = []

                    ml_by_forecast[forecast_dt].append({
                        'forecast_datetime': forecast_dt,
                        'target_datetime': pred['target_datetime'],
                        'horizon': pred['horizon'],
                        'predicted_cmg': pred['cmg_predicted'],
                        'prob_zero': pred.get('prob_zero', 0),
                        'threshold': pred.get('threshold', 0.5),
                        'node': pred.get('node', 'PMontt220')
                    })

                # Format CMG Programado
                programado_data = [
                    {
                        'datetime': f"{p['date']} {p['hour']:02d}:00:00",
                        'cmg_programmed': p['cmg_programmed'],
                        'node': p['node']
                    }
                    for p in cmg_programado
                ]

                # Format CMG Online (actual values)
                online_data = [
                    {
                        'datetime': f"{o['date']} {o['hour']:02d}:00:00",
                        'cmg_actual': o['cmg_usd'],
                        'node': o['node']
                    }
                    for o in cmg_online
                ]

                response = {
                    'success': True,
                    'data': {
                        'ml_predictions': ml_by_forecast,
                        'cmg_programado': programado_data,
                        'cmg_online': online_data
                    },
                    'metadata': {
                        'start_date': str(start_date),
                        'end_date': str(end_date),
                        'ml_forecast_count': len(ml_by_forecast),
                        'ml_predictions_count': len(ml_predictions),
                        'programado_count': len(programado_data),
                        'online_count': len(online_data)
                    },
                    'source': 'supabase'
                }

                self.wfile.write(json.dumps(response, default=str).encode())

            else:
                # Supabase not available
                error_response = {
                    'success': False,
                    'error': 'Supabase client not available',
                    'message': 'Historical comparison data temporarily unavailable',
                    'data': {
                        'ml_predictions': {},
                        'cmg_programado': [],
                        'cmg_online': []
                    }
                }
                self.wfile.write(json.dumps(error_response).encode())

        except Exception as e:
            # Error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve historical comparison data',
                'data': {
                    'ml_predictions': {},
                    'cmg_programado': [],
                    'cmg_online': []
                }
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
