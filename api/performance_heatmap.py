"""
Daily Performance Heatmap API
==============================

Returns 24×24 error matrices showing forecast performance for a specific date.

Usage:
    GET /api/performance_heatmap?date=YYYY-MM-DD

Returns:
    - ML predictions error matrix (24 forecast hours × 24 target hours)
    - CMG Programado error matrix (24 forecast hours × 24 target hours)
    - Metrics: total distance, average distance, actuals coverage

Error calculation: forecast - actual (positive = overpredicted, negative = underpredicted)
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add lib path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from lib.utils.supabase_client import SupabaseClient
    import requests
    SUPABASE_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Supabase client not available: {e}")
    SUPABASE_AVAILABLE = False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET request for daily heatmap data"""

        # CORS headers
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

        try:
            if not SUPABASE_AVAILABLE:
                raise Exception('Supabase client not available')

            # Parse query parameters
            from urllib.parse import urlparse, parse_qs
            query_params = parse_qs(urlparse(self.path).query)

            requested_date = query_params.get('date', [None])[0]

            if not requested_date:
                raise ValueError('Missing required parameter: date (format: YYYY-MM-DD)')

            # Validate date format
            try:
                date_obj = datetime.strptime(requested_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError('Invalid date format. Use YYYY-MM-DD')

            # Initialize Supabase client
            supabase = SupabaseClient()
            santiago_tz = pytz.timezone('America/Santiago')

            # Query all ML forecasts for this date (all 24 forecast hours)
            ml_url = f"{supabase.base_url}/ml_predictions_santiago"
            ml_params = [
                ("forecast_date", f"eq.{requested_date}"),
                ("order", "forecast_hour.asc,horizon.asc"),
                ("limit", "1000")  # Max 24 hours × 24 horizons = 576 records
            ]
            ml_response = requests.get(ml_url, params=ml_params, headers=supabase.headers)
            ml_forecasts = ml_response.json() if ml_response.status_code == 200 else []

            # Query all CMG Programado for this date
            prog_url = f"{supabase.base_url}/cmg_programado_santiago"
            prog_params = [
                ("forecast_date", f"eq.{requested_date}"),
                ("order", "forecast_hour.asc,target_datetime.asc"),
                ("limit", "2000")  # Max 24 hours × ~72 horizons, but we'll filter
            ]
            prog_response = requests.get(prog_url, params=prog_params, headers=supabase.headers)
            prog_forecasts = prog_response.json() if prog_response.status_code == 200 else []

            # Filter CMG Programado to only future forecasts (target > forecast)
            # and only first 24 hours of predictions
            prog_filtered = []
            for p in prog_forecasts:
                forecast_dt = datetime.fromisoformat(p['forecast_datetime'].replace('Z', '+00:00'))
                target_dt = datetime.fromisoformat(p['target_datetime'].replace('Z', '+00:00'))

                # Skip backwards forecasts
                if target_dt <= forecast_dt:
                    continue

                # Calculate horizon (hours ahead)
                horizon_hours = int((target_dt - forecast_dt).total_seconds() / 3600)

                # Only keep first 24 hours (matching ML predictions)
                if horizon_hours <= 24:
                    p['horizon'] = horizon_hours
                    prog_filtered.append(p)

            # Query CMG Online (actuals) for this date
            online_url = f"{supabase.base_url}/cmg_online_santiago"
            online_params = [
                ("date", f"eq.{requested_date}"),
                ("order", "hour.asc"),
                ("limit", "100")
            ]
            online_response = requests.get(online_url, params=online_params, headers=supabase.headers)
            cmg_online = online_response.json() if online_response.status_code == 200 else []

            # Build actuals lookup: hour → actual CMG (average across nodes)
            actuals = {}
            for record in cmg_online:
                hour = record['hour']
                cmg = record['cmg_usd']
                if hour not in actuals:
                    actuals[hour] = []
                actuals[hour].append(cmg)

            # Average across nodes
            actuals_avg = {hour: sum(values) / len(values) for hour, values in actuals.items()}

            # Build ML error matrix (24 forecast hours × 24 target hours)
            ml_matrix = [[None for _ in range(24)] for _ in range(24)]
            ml_forecast_count = 0
            ml_total_distance = 0
            ml_error_count = 0

            for forecast in ml_forecasts:
                forecast_hour = forecast['forecast_hour']
                horizon = forecast['horizon']
                predicted_cmg = forecast['cmg_predicted']

                # FIXED: Use target_hour from view (already timezone-corrected)
                # Don't calculate with modulo - that doesn't account for day boundaries
                target_hour = forecast['target_hour']

                # Get actual for target hour
                if target_hour in actuals_avg:
                    actual_cmg = actuals_avg[target_hour]
                    error = predicted_cmg - actual_cmg
                    ml_matrix[forecast_hour][horizon - 1] = error  # horizon 1-24 → index 0-23
                    ml_total_distance += abs(error)
                    ml_error_count += 1

                ml_forecast_count += 1

            # Build CMG Programado error matrix
            prog_matrix = [[None for _ in range(24)] for _ in range(24)]
            prog_forecast_count = 0
            prog_total_distance = 0
            prog_error_count = 0

            for forecast in prog_filtered:
                forecast_hour = forecast['forecast_hour']
                horizon = forecast['horizon']
                predicted_cmg = forecast['cmg_usd']

                # FIXED: Use target_hour from view (already timezone-corrected)
                # Don't calculate with modulo - that doesn't account for day boundaries
                target_hour = forecast['target_hour']

                # Get actual for target hour
                if target_hour in actuals_avg:
                    actual_cmg = actuals_avg[target_hour]
                    error = predicted_cmg - actual_cmg
                    prog_matrix[forecast_hour][horizon - 1] = error
                    prog_total_distance += abs(error)
                    prog_error_count += 1

                prog_forecast_count += 1

            # Calculate averages
            ml_avg_distance = ml_total_distance / ml_error_count if ml_error_count > 0 else 0
            prog_avg_distance = prog_total_distance / prog_error_count if prog_error_count > 0 else 0

            # Response
            response = {
                'success': True,
                'date': requested_date,
                'ml_predictions': {
                    'matrix': ml_matrix,
                    'total_distance': round(ml_total_distance, 2),
                    'average_distance': round(ml_avg_distance, 2),
                    'forecast_count': ml_forecast_count,
                    'error_count': ml_error_count,
                    'actuals_available': len(actuals_avg)
                },
                'cmg_programado': {
                    'matrix': prog_matrix,
                    'total_distance': round(prog_total_distance, 2),
                    'average_distance': round(prog_avg_distance, 2),
                    'forecast_count': prog_forecast_count,
                    'error_count': prog_error_count,
                    'actuals_available': len(actuals_avg)
                },
                'actuals': {
                    'hours_available': list(sorted(actuals_avg.keys())),
                    'count': len(actuals_avg)
                }
            }

            self.wfile.write(json.dumps(response, default=str).encode())

        except Exception as e:
            # Error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate performance heatmap'
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
