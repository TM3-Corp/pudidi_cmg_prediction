"""
ML Forecast API - Returns ML predictions from Supabase

Returns the latest 24-hour forecast from ML predictions table
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
import os
from pathlib import Path

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
        """Return latest ML predictions from Supabase"""

        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=300')  # Cache for 5 minutes
        self.end_headers()

        try:
            if USE_SUPABASE:
                # Fetch latest predictions from Supabase
                supabase = SupabaseClient()
                predictions = supabase.get_latest_ml_predictions(limit=24)

                if predictions:
                    # Format predictions for API response
                    # ml_config.html expects: datetime, predicted_cmg, zero_probability, decision_threshold
                    formatted_predictions = [
                        {
                            'horizon': p['horizon'],
                            'datetime': p['target_datetime'],  # ml_config expects 'datetime'
                            'target_datetime': p['target_datetime'],
                            'predicted_cmg': p['cmg_predicted'],  # ml_config expects 'predicted_cmg'
                            'zero_probability': p.get('prob_zero', 0),  # ml_config expects 'zero_probability'
                            'decision_threshold': p.get('threshold', 0.5)  # ml_config expects 'decision_threshold'
                        }
                        for p in predictions
                    ]

                    response = {
                        'success': True,
                        'predictions': formatted_predictions,
                        'predictions_count': len(formatted_predictions),
                        'forecast_time': predictions[0]['forecast_datetime'],
                        'model_version': predictions[0].get('model_version', 'v2.0'),
                        'status': {
                            'available': True,
                            'last_update': predictions[0]['forecast_datetime']
                        },
                        'source': 'supabase'
                    }
                else:
                    response = {
                        'success': True,
                        'predictions': [],
                        'predictions_count': 0,
                        'status': {
                            'available': False,
                            'last_update': None
                        },
                        'message': 'No ML predictions available yet'
                    }

                self.wfile.write(json.dumps(response, default=str).encode())

            else:
                # Supabase not available
                error_response = {
                    'success': False,
                    'error': 'Supabase client not available',
                    'message': 'ML predictions temporarily unavailable',
                    'predictions': [],
                    'status': {
                        'available': False,
                        'last_update': None
                    }
                }
                self.wfile.write(json.dumps(error_response).encode())

        except Exception as e:
            # Error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve ML predictions',
                'predictions': [],
                'status': {
                    'available': False,
                    'last_update': None
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
