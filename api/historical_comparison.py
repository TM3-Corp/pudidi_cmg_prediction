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
                # FIXED: Group ML predictions by (forecast_date, forecast_hour) in Santiago timezone
                # NOTE: ml_predictions table doesn't have forecast_date/hour columns yet,
                # so we calculate them from forecast_datetime
                ml_by_forecast = {}
                for pred in ml_predictions:
                    # Convert UTC forecast_datetime to Santiago timezone
                    forecast_dt_utc = datetime.fromisoformat(pred['forecast_datetime'].replace('Z', '+00:00'))
                    forecast_dt_santiago = forecast_dt_utc.astimezone(santiago_tz)

                    # Extract date and hour in Santiago timezone
                    forecast_date = forecast_dt_santiago.date()
                    forecast_hour = forecast_dt_santiago.hour

                    # Create composite key: "YYYY-MM-DD HH:00:00"
                    forecast_key = f"{forecast_date} {forecast_hour:02d}:00:00"

                    if forecast_key not in ml_by_forecast:
                        ml_by_forecast[forecast_key] = []

                    ml_by_forecast[forecast_key].append({
                        'forecast_datetime': pred['forecast_datetime'],  # Keep original UTC timestamp
                        'forecast_date': str(forecast_date),
                        'forecast_hour': forecast_hour,
                        'target_datetime': pred['target_datetime'],
                        'horizon': pred['horizon'],
                        'predicted_cmg': pred['cmg_predicted'],
                        'prob_zero': pred.get('prob_zero', 0),
                        'threshold': pred.get('threshold', 0.5),
                        'model_version': pred.get('model_version', 'v2.0')
                    })

                # Format CMG Programado - group by (forecast_date, forecast_hour) in Santiago timezone
                # This ensures all forecasts made in same hour are grouped together
                programado_by_forecast = {}
                for p in cmg_programado:
                    # Create composite key from Santiago timezone columns: "YYYY-MM-DD HH:00:00"
                    forecast_key = f"{p['forecast_date']} {p['forecast_hour']:02d}:00:00"

                    if forecast_key not in programado_by_forecast:
                        programado_by_forecast[forecast_key] = []

                    programado_by_forecast[forecast_key].append({
                        'forecast_datetime': p['forecast_datetime'],  # Keep original UTC timestamp
                        'forecast_date': str(p['forecast_date']),
                        'forecast_hour': p['forecast_hour'],
                        'target_datetime': p['target_datetime'],
                        'cmg_programmed': p['cmg_usd'],  # Schema uses cmg_usd
                        'node': p['node']
                    })

                # For backward compatibility, also provide flat array
                programado_data = []
                for forecast_dt, forecasts in programado_by_forecast.items():
                    programado_data.extend(forecasts)

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
                        'cmg_programado': programado_data,  # Flat array for compatibility
                        'cmg_programado_by_forecast': programado_by_forecast,  # Grouped by forecast_datetime
                        'cmg_online': online_data
                    },
                    'metadata': {
                        'start_date': str(start_date),
                        'end_date': str(end_date),
                        'ml_forecast_count': len(ml_by_forecast),
                        'ml_predictions_count': len(ml_predictions),
                        'programado_forecast_count': len(programado_by_forecast),
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
