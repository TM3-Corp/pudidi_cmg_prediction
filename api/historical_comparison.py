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
import requests

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from lib.utils.supabase_client import SupabaseClient
    USE_SUPABASE = True
except Exception as e:
    print(f"⚠️ Supabase unavailable: {e}")
    USE_SUPABASE = False

def fetch_all_with_pagination(url, params, headers, max_records=50000):
    """
    Fetch all records from Supabase with pagination to bypass 1000-row limit.
    PostgREST has a default max of 1000 rows per request.
    """
    all_records = []
    offset = 0
    batch_size = 1000

    while len(all_records) < max_records:
        # Add pagination params
        paginated_params = params + [("offset", offset), ("limit", batch_size)]

        response = requests.get(url, params=paginated_params, headers=headers)

        if response.status_code != 200:
            break

        batch = response.json()
        if not batch:  # No more records
            break

        all_records.extend(batch)
        offset += batch_size

        # Stop if we got less than batch_size (last page)
        if len(batch) < batch_size:
            break

    return all_records


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """
        Return historical data for forecast comparison.

        Two modes:
        1. Summary mode (no query params): Return available dates/hours only
        2. Detail mode (?date=YYYY-MM-DD&hour=HH): Return full forecast data for specific hour

        This two-stage approach prevents UI blocking from loading 46K+ records upfront.
        """

        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=300')  # Cache for 5 minutes
        self.end_headers()

        try:
            if USE_SUPABASE:
                # Parse query parameters
                from urllib.parse import urlparse, parse_qs
                query_params = parse_qs(urlparse(self.path).query)

                # Check if specific date/hour requested (Detail mode)
                requested_date = query_params.get('date', [None])[0]
                requested_hour = query_params.get('hour', [None])[0]

                # Initialize Supabase client
                supabase = SupabaseClient()
                santiago_tz = pytz.timezone('America/Santiago')

                # SUMMARY MODE: Return available dates/hours only
                if not requested_date or requested_hour is None:
                    end_date = datetime.now(santiago_tz).date()
                    start_date = end_date - timedelta(days=30)

                    # Get unique (forecast_date, forecast_hour) combinations
                    # Use pagination to get ALL records (not limited to 1000)
                    # Even though we only select 2 columns, there can be 46K+ rows
                    ml_summary_url = f"{supabase.base_url}/ml_predictions_santiago"
                    ml_summary_params = [
                        ("forecast_date", f"gte.{start_date}"),
                        ("forecast_date", f"lte.{end_date}"),
                        ("select", "forecast_date,forecast_hour")
                    ]
                    ml_summary = fetch_all_with_pagination(ml_summary_url, ml_summary_params, supabase.headers, max_records=10000)

                    prog_summary_url = f"{supabase.base_url}/cmg_programado_santiago"
                    prog_summary_params = [
                        ("forecast_date", f"gte.{start_date}"),
                        ("forecast_date", f"lte.{end_date}"),
                        ("select", "forecast_date,forecast_hour")
                    ]
                    prog_summary = fetch_all_with_pagination(prog_summary_url, prog_summary_params, supabase.headers, max_records=50000)

                    # Group by (date, hour) to get unique combinations
                    ml_hours = set()
                    for record in ml_summary:
                        ml_hours.add((str(record['forecast_date']), record['forecast_hour']))

                    prog_hours = set()
                    for record in prog_summary:
                        prog_hours.add((str(record['forecast_date']), record['forecast_hour']))

                    # Convert to list of dicts
                    available_hours = []
                    all_hours = ml_hours | prog_hours
                    for date, hour in sorted(all_hours, reverse=True):
                        available_hours.append({
                            'date': date,
                            'hour': hour,
                            'has_ml': (date, hour) in ml_hours,
                            'has_programado': (date, hour) in prog_hours
                        })

                    response = {
                        'success': True,
                        'mode': 'summary',
                        'data': {
                            'available_hours': available_hours
                        },
                        'metadata': {
                            'start_date': str(start_date),
                            'end_date': str(end_date),
                            'total_hours': len(available_hours)
                        }
                    }

                    self.wfile.write(json.dumps(response, default=str).encode())
                    return

                # DETAIL MODE: Return full forecast data for specific date/hour
                requested_hour = int(requested_hour)

                # OPTIMIZED: Query only the specific date/hour requested
                # This reduces data transfer from 46K records to ~96 records
                #
                # IMPORTANT: Use Santiago timezone VIEWS for all queries
                # These views have pre-converted Santiago timezone columns (forecast_date, forecast_hour, etc.)

                # Fetch ML predictions for SPECIFIC date/hour from SANTIAGO VIEW
                url = f"{supabase.base_url}/ml_predictions_santiago"
                ml_params = [
                    ("forecast_date", f"eq.{requested_date}"),
                    ("forecast_hour", f"eq.{requested_hour}"),
                    ("order", "target_datetime.asc")
                ]
                ml_response = requests.get(url, params=ml_params, headers=supabase.headers)
                ml_predictions = ml_response.json() if ml_response.status_code == 200 else []

                # Fetch CMG Programado for SPECIFIC date/hour from SANTIAGO VIEW
                prog_url = f"{supabase.base_url}/cmg_programado_santiago"
                prog_params = [
                    ("forecast_date", f"eq.{requested_date}"),
                    ("forecast_hour", f"eq.{requested_hour}"),
                    ("order", "target_datetime.asc")
                ]
                prog_response = requests.get(prog_url, params=prog_params, headers=supabase.headers)
                cmg_programado = prog_response.json() if prog_response.status_code == 200 else []

                # Fetch CMG Online (actual values) for the target period being forecasted
                # Get the datetime range being forecasted (typically next 24 hours)
                # We'll fetch a bit wider range to ensure coverage
                online_url = f"{supabase.base_url}/cmg_online_santiago"
                online_params = [
                    ("date", f"gte.{requested_date}"),
                    ("date", f"lte.{(datetime.strptime(requested_date, '%Y-%m-%d') + timedelta(days=2)).strftime('%Y-%m-%d')}"),
                    ("order", "datetime.asc"),
                    ("limit", "200")  # Max 2 days * 24 hours * 3 nodes = 144 records
                ]
                online_response = requests.get(online_url, params=online_params, headers=supabase.headers)
                cmg_online = online_response.json() if online_response.status_code == 200 else []

                # Format data for frontend
                # Using Santiago timezone views - forecast_date/forecast_hour are already in Santiago timezone!
                # No conversion needed - much faster for 46K+ records
                ml_by_forecast = {}
                for pred in ml_predictions:
                    # Use pre-converted Santiago timezone columns from the view
                    forecast_key = f"{pred['forecast_date']} {pred['forecast_hour']:02d}:00:00"

                    if forecast_key not in ml_by_forecast:
                        ml_by_forecast[forecast_key] = []

                    ml_by_forecast[forecast_key].append({
                        'forecast_datetime': pred['forecast_datetime'],  # UTC timestamp
                        'forecast_date': str(pred['forecast_date']),
                        'forecast_hour': pred['forecast_hour'],
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
                    'mode': 'detail',
                    'data': {
                        'ml_predictions': ml_by_forecast,
                        'cmg_programado': programado_by_forecast,  # FIXED: Send grouped dict like ML predictions
                        'cmg_programado_by_forecast': programado_by_forecast,  # Grouped by forecast_datetime
                        'cmg_online': online_data
                    },
                    'metadata': {
                        'requested_date': requested_date,
                        'requested_hour': requested_hour,
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
