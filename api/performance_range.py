"""
Range Performance Analysis API - Dual-Dimension Metrics
========================================================

Returns forecast performance metrics across a date range with two analytical perspectives:
1. Temporal Dimension: Average distance by day (identifies outlier days)
2. Structural Dimension: Average distance by horizon (shows forecast degradation)

Usage:
    GET /api/performance_range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

Returns:
    - metrics_by_day: Daily average distances for ML and CMG Programado
    - metrics_by_horizon: Horizon-based average distances (t+1 to t+24)
    - summary: Best/worst days, degradation rates, overall statistics
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

# Add lib path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from lib.utils.supabase_client import SupabaseClient
    from lib.utils.cors import add_cors_headers, send_cors_preflight
    import requests
    SUPABASE_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Supabase client not available: {e}")
    SUPABASE_AVAILABLE = False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET request for range performance analysis"""

        # CORS headers
        request_origin = self.headers.get('Origin', '')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        add_cors_headers(self, request_origin, 'GET, OPTIONS')
        self.end_headers()

        try:
            if not SUPABASE_AVAILABLE:
                raise Exception('Supabase client not available')

            # Parse query parameters
            from urllib.parse import urlparse, parse_qs
            query_params = parse_qs(urlparse(self.path).query)

            start_date_str = query_params.get('start_date', [None])[0]
            end_date_str = query_params.get('end_date', [None])[0]

            if not start_date_str or not end_date_str:
                raise ValueError('Missing required parameters: start_date and end_date (format: YYYY-MM-DD)')

            # Validate date format
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError('Invalid date format. Use YYYY-MM-DD')

            if end_date < start_date:
                raise ValueError('end_date must be >= start_date')

            # Initialize Supabase client
            supabase = SupabaseClient()
            santiago_tz = pytz.timezone('America/Santiago')

            # Calculate number of days
            num_days = (end_date - start_date).days + 1

            # IMPORTANT: To capture all forecasts that TARGET our date range,
            # we need to query forecasts from (start_date - 1 day) because:
            # - A forecast made on Day N with horizon t+24 targets Day N+1
            # - So to get all forecasts targeting start_date, we need Day (start_date - 1)
            forecast_query_start = start_date - timedelta(days=1)

            # Query ML forecasts - BATCH QUERY with date range filter
            ml_url = f"{supabase.base_url}/ml_predictions_santiago"
            ml_forecasts = []

            # Use PostgREST range filter for batch query
            forecast_start_str = forecast_query_start.strftime('%Y-%m-%d')
            end_date_str_query = end_date.strftime('%Y-%m-%d')

            ml_params = [
                ("forecast_date", f"gte.{forecast_start_str}"),
                ("forecast_date", f"lte.{end_date_str_query}"),
                ("order", "forecast_date.asc,forecast_hour.asc,horizon.asc"),
            ]
            # IMPORTANT: Use Range header to bypass Supabase's default 1000-row limit
            ml_headers = supabase.headers.copy()
            ml_headers['Range'] = '0-49999'  # Request up to 50,000 rows
            ml_headers['Range-Unit'] = 'items'
            ml_response = requests.get(ml_url, params=ml_params, headers=ml_headers)
            if ml_response.status_code in [200, 206]:  # 206 = Partial Content (Range response)
                ml_forecasts = ml_response.json()

            # Query CMG Programado - BATCH QUERY with date range filter
            prog_url = f"{supabase.base_url}/cmg_programado_santiago"
            prog_forecasts = []

            prog_params = [
                ("forecast_date", f"gte.{forecast_start_str}"),
                ("forecast_date", f"lte.{end_date_str_query}"),
                ("order", "forecast_date.asc,forecast_hour.asc,target_datetime.asc"),
            ]
            # IMPORTANT: Use Range header to bypass Supabase's default 1000-row limit
            prog_headers = supabase.headers.copy()
            prog_headers['Range'] = '0-99999'  # Request up to 100,000 rows
            prog_headers['Range-Unit'] = 'items'
            prog_response = requests.get(prog_url, params=prog_params, headers=prog_headers)
            if prog_response.status_code in [200, 206]:  # 206 = Partial Content (Range response)
                prog_forecasts = prog_response.json()

            # Filter CMG Programado to only future forecasts and first 24 hours
            prog_filtered = []
            for p in prog_forecasts:
                forecast_dt = datetime.fromisoformat(p['forecast_datetime'].replace('Z', '+00:00'))
                target_dt = datetime.fromisoformat(p['target_datetime'].replace('Z', '+00:00'))

                # Skip backwards forecasts
                if target_dt <= forecast_dt:
                    continue

                # Calculate horizon
                horizon_hours = int((target_dt - forecast_dt).total_seconds() / 3600)

                # Only keep first 24 hours
                if horizon_hours <= 24:
                    p['horizon'] = horizon_hours
                    p['target_date'] = target_dt.astimezone(santiago_tz).strftime('%Y-%m-%d')
                    p['target_hour'] = target_dt.astimezone(santiago_tz).hour
                    prog_filtered.append(p)

            # Add target_date and target_hour to ML forecasts
            for ml in ml_forecasts:
                forecast_date = ml['forecast_date']
                forecast_hour = ml['forecast_hour']
                horizon = ml['horizon']

                # Calculate target datetime
                forecast_dt = santiago_tz.localize(datetime.strptime(f"{forecast_date} {forecast_hour:02d}:00", "%Y-%m-%d %H:%M"))
                target_dt = forecast_dt + timedelta(hours=horizon)

                ml['target_date'] = target_dt.strftime('%Y-%m-%d')
                ml['target_hour'] = target_dt.hour

            # Query CMG Online (actuals) - BATCH QUERY with date range filter
            online_url = f"{supabase.base_url}/cmg_online_santiago"
            cmg_online = []

            online_params = [
                ("date", f"gte.{start_date_str}"),
                ("date", f"lte.{end_date_str}"),
                ("order", "date.asc,hour.asc"),
            ]
            # IMPORTANT: Use Range header to bypass Supabase's default 1000-row limit
            online_headers = supabase.headers.copy()
            online_headers['Range'] = '0-9999'  # Request up to 10,000 rows
            online_headers['Range-Unit'] = 'items'
            online_response = requests.get(online_url, params=online_params, headers=online_headers)
            if online_response.status_code in [200, 206]:  # 206 = Partial Content (Range response)
                cmg_online = online_response.json()

            # Build actuals lookup: (date, hour) → actual CMG (average across nodes)
            actuals_raw = defaultdict(list)
            for record in cmg_online:
                date = record['date']
                hour = record['hour']
                cmg = record['cmg_usd']
                actuals_raw[(date, hour)].append(cmg)

            # Average across nodes
            actuals = {key: sum(values) / len(values) for key, values in actuals_raw.items()}

            # =========================================
            # TEMPORAL DIMENSION: Metrics by Day
            # =========================================

            # Track daily errors: date → list of absolute errors
            ml_daily_errors = defaultdict(list)
            prog_daily_errors = defaultdict(list)

            # ML predictions by day
            for forecast in ml_forecasts:
                target_date = forecast['target_date']
                target_hour = forecast['target_hour']
                predicted = forecast['cmg_predicted']

                if (target_date, target_hour) in actuals:
                    actual = actuals[(target_date, target_hour)]
                    error = abs(predicted - actual)
                    ml_daily_errors[target_date].append(error)

            # CMG Programado by day
            for forecast in prog_filtered:
                target_date = forecast['target_date']
                target_hour = forecast['target_hour']
                predicted = forecast['cmg_usd']

                if (target_date, target_hour) in actuals:
                    actual = actuals[(target_date, target_hour)]
                    error = abs(predicted - actual)
                    prog_daily_errors[target_date].append(error)

            # Calculate daily averages
            metrics_by_day = []
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')

                ml_errors = ml_daily_errors.get(date_str, [])
                prog_errors = prog_daily_errors.get(date_str, [])

                ml_avg = sum(ml_errors) / len(ml_errors) if ml_errors else None
                prog_avg = sum(prog_errors) / len(prog_errors) if prog_errors else None

                metrics_by_day.append({
                    'date': date_str,
                    'ml_avg_distance': round(ml_avg, 2) if ml_avg is not None else None,
                    'ml_count': len(ml_errors),
                    'prog_avg_distance': round(prog_avg, 2) if prog_avg is not None else None,
                    'prog_count': len(prog_errors)
                })

                current_date += timedelta(days=1)

            # =========================================
            # STRUCTURAL DIMENSION: Metrics by Horizon
            # =========================================
            # NOTE: For horizon metrics, we filter by FORECAST date (not target date)
            # This answers: "How did predictions MADE during these days perform?"
            # This is different from temporal dimension which filters by TARGET date.

            # Track horizon errors: horizon → list of absolute errors
            ml_horizon_errors = defaultdict(list)
            prog_horizon_errors = defaultdict(list)

            # ML predictions by horizon - ONLY forecasts MADE during the selected range
            for forecast in ml_forecasts:
                # Filter: only include forecasts where forecast_date is in user's range
                forecast_date = datetime.strptime(forecast['forecast_date'], '%Y-%m-%d').date()
                if forecast_date < start_date or forecast_date > end_date:
                    continue  # Skip forecasts made outside the selected range

                horizon = forecast['horizon']
                target_date = forecast['target_date']
                target_hour = forecast['target_hour']
                predicted = forecast['cmg_predicted']

                if (target_date, target_hour) in actuals:
                    actual = actuals[(target_date, target_hour)]
                    error = abs(predicted - actual)
                    ml_horizon_errors[horizon].append(error)

            # CMG Programado by horizon - ONLY forecasts MADE during the selected range
            for forecast in prog_filtered:
                # Filter: only include forecasts where forecast_date is in user's range
                forecast_dt = datetime.fromisoformat(forecast['forecast_datetime'].replace('Z', '+00:00'))
                forecast_date = forecast_dt.astimezone(santiago_tz).date()
                if forecast_date < start_date or forecast_date > end_date:
                    continue  # Skip forecasts made outside the selected range

                horizon = forecast['horizon']
                target_date = forecast['target_date']
                target_hour = forecast['target_hour']
                predicted = forecast['cmg_usd']

                if (target_date, target_hour) in actuals:
                    actual = actuals[(target_date, target_hour)]
                    error = abs(predicted - actual)
                    prog_horizon_errors[horizon].append(error)

            # Calculate horizon averages (1-24)
            ml_by_horizon = []
            prog_by_horizon = []

            for horizon in range(1, 25):
                ml_errors = ml_horizon_errors.get(horizon, [])
                prog_errors = prog_horizon_errors.get(horizon, [])

                ml_avg = sum(ml_errors) / len(ml_errors) if ml_errors else None
                prog_avg = sum(prog_errors) / len(prog_errors) if prog_errors else None

                if ml_avg is not None:
                    ml_by_horizon.append({
                        'horizon': horizon,
                        'avg_distance': round(ml_avg, 2),
                        'count': len(ml_errors)
                    })

                if prog_avg is not None:
                    prog_by_horizon.append({
                        'horizon': horizon,
                        'avg_distance': round(prog_avg, 2),
                        'count': len(prog_errors)
                    })

            # =========================================
            # SUMMARY STATISTICS
            # =========================================

            # Temporal summary: Best/worst days
            ml_days_with_data = [d for d in metrics_by_day if d['ml_avg_distance'] is not None]
            prog_days_with_data = [d for d in metrics_by_day if d['prog_avg_distance'] is not None]

            ml_best_day = min(ml_days_with_data, key=lambda x: x['ml_avg_distance']) if ml_days_with_data else None
            ml_worst_day = max(ml_days_with_data, key=lambda x: x['ml_avg_distance']) if ml_days_with_data else None

            prog_best_day = min(prog_days_with_data, key=lambda x: x['prog_avg_distance']) if prog_days_with_data else None
            prog_worst_day = max(prog_days_with_data, key=lambda x: x['prog_avg_distance']) if prog_days_with_data else None

            # Calculate overall average across all days
            all_ml_daily = [d['ml_avg_distance'] for d in ml_days_with_data]
            all_prog_daily = [d['prog_avg_distance'] for d in prog_days_with_data]

            ml_overall_avg = sum(all_ml_daily) / len(all_ml_daily) if all_ml_daily else None
            prog_overall_avg = sum(all_prog_daily) / len(all_prog_daily) if all_prog_daily else None

            # Structural summary: Degradation rate (slope from t+1 to t+24)
            # Simple linear degradation: (avg_t24 - avg_t1) / 23
            ml_degradation_rate = None
            prog_degradation_rate = None

            if len(ml_by_horizon) >= 2:
                ml_t1 = next((h['avg_distance'] for h in ml_by_horizon if h['horizon'] == 1), None)
                ml_t24 = next((h['avg_distance'] for h in ml_by_horizon if h['horizon'] == 24), None)
                if ml_t1 is not None and ml_t24 is not None:
                    ml_degradation_rate = round((ml_t24 - ml_t1) / 23, 2)

            if len(prog_by_horizon) >= 2:
                prog_t1 = next((h['avg_distance'] for h in prog_by_horizon if h['horizon'] == 1), None)
                prog_t24 = next((h['avg_distance'] for h in prog_by_horizon if h['horizon'] == 24), None)
                if prog_t1 is not None and prog_t24 is not None:
                    prog_degradation_rate = round((prog_t24 - prog_t1) / 23, 2)

            # Response
            response = {
                'success': True,
                'date_range': {
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'num_days': num_days
                },
                'metrics_by_day': metrics_by_day,
                'metrics_by_horizon': {
                    'ml': ml_by_horizon,
                    'prog': prog_by_horizon
                },
                'summary': {
                    'temporal': {
                        'ml': {
                            'best_day': ml_best_day,
                            'worst_day': ml_worst_day,
                            'overall_avg': round(ml_overall_avg, 2) if ml_overall_avg is not None else None,
                            'days_with_data': len(ml_days_with_data)
                        },
                        'prog': {
                            'best_day': prog_best_day,
                            'worst_day': prog_worst_day,
                            'overall_avg': round(prog_overall_avg, 2) if prog_overall_avg is not None else None,
                            'days_with_data': len(prog_days_with_data)
                        }
                    },
                    'structural': {
                        'ml': {
                            'degradation_rate': ml_degradation_rate,
                            'horizons_available': len(ml_by_horizon)
                        },
                        'prog': {
                            'degradation_rate': prog_degradation_rate,
                            'horizons_available': len(prog_by_horizon)
                        }
                    }
                },
                'data_coverage': {
                    'ml_forecasts': len(ml_forecasts),
                    'prog_forecasts': len(prog_filtered),
                    'prog_raw': len(prog_forecasts),
                    'actuals_hours': len(actuals)
                }
            }

            self.wfile.write(json.dumps(response, default=str).encode())

        except Exception as e:
            # Error response
            import traceback
            error_response = {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'message': 'Failed to generate range performance analysis'
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        send_cors_preflight(self, 'GET, OPTIONS')
