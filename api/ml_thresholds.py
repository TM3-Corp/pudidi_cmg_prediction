"""
ML Thresholds API - View and configure decision thresholds
Allows users to see optimal thresholds and adjust them within safe ranges
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
from pathlib import Path
import urllib.parse

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Get current thresholds configuration"""

        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        try:
            # Load optimal thresholds from training
            optimal_file = Path(__file__).parent.parent / 'models_24h' / 'zero_detection' / 'optimal_thresholds.csv'

            if not optimal_file.exists():
                raise FileNotFoundError("Optimal thresholds not found")

            # Parse CSV
            import csv
            thresholds_data = []

            with open(optimal_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    horizon_str = row['horizon']
                    if horizon_str.startswith('t+'):
                        horizon = int(horizon_str.replace('t+', ''))

                        optimal_threshold = float(row['threshold'])

                        # Calculate safe range (±20% from optimal, constrained to [0.1, 0.9])
                        min_threshold = max(0.1, optimal_threshold * 0.8)
                        max_threshold = min(0.9, optimal_threshold * 1.2)

                        thresholds_data.append({
                            'horizon': horizon,
                            'horizon_label': horizon_str,
                            'optimal_threshold': round(optimal_threshold, 4),
                            'current_threshold': round(optimal_threshold, 4),  # Default to optimal
                            'min_allowed': round(min_threshold, 4),
                            'max_allowed': round(max_threshold, 4),
                            'precision': float(row.get('precision', 0)),
                            'recall': float(row.get('recall', 0)),
                            'f1': float(row.get('f1', 0)),
                            'auc': float(row.get('auc', 0))
                        })

            # Response
            response = {
                'success': True,
                'thresholds': thresholds_data,
                'metadata': {
                    'optimization_method': 'F1-maximization',
                    'training_date': '2025-10-08',
                    'horizons_count': len(thresholds_data),
                    'threshold_range': {
                        'min': round(min([t['optimal_threshold'] for t in thresholds_data]), 4),
                        'max': round(max([t['optimal_threshold'] for t in thresholds_data]), 4)
                    }
                },
                'info': {
                    'description': 'Decision thresholds for zero-CMG classification',
                    'adjustable': True,
                    'safe_range_note': 'Adjustments limited to ±20% from optimal value',
                    'impact': 'Lower threshold = more zero predictions (conservative), Higher threshold = fewer zero predictions (aggressive)'
                }
            }

            self.wfile.write(json.dumps(response, default=str).encode())

        except FileNotFoundError:
            error_response = {
                'success': False,
                'error': 'Thresholds configuration not found',
                'message': 'Optimal thresholds have not been configured yet',
                'thresholds': []
            }
            self.wfile.write(json.dumps(error_response).encode())

        except Exception as e:
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to load thresholds configuration',
                'thresholds': []
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_POST(self):
        """Update threshold configuration (optional - for future use)"""

        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            updates = json.loads(body)

            # For now, return success but don't actually update
            # (Updating would require writing to files, which may have permission issues)
            response = {
                'success': True,
                'message': 'Threshold updates received (currently read-only)',
                'note': 'To apply custom thresholds, contact your system administrator',
                'received': updates
            }

            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to update thresholds'
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
