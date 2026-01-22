from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from lib.utils.cache_manager_readonly import CacheManagerReadOnly as CacheManager
from lib.utils.cors import add_cors_headers, send_cors_preflight

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Main production endpoint - fetches real CMG data and makes ML predictions"""
        request_origin = self.headers.get('Origin', '')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        add_cors_headers(self, request_origin, 'GET, OPTIONS')
        self.end_headers()
        
        # Initialize response data
        predictions = []
        data_source = "Synthetic (Default)"
        avg_value = 60.0
        last_value = 60.0
        success = False
        fetch_info = {}
        last_updated = None
        
        try:
            import pytz
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
        except Exception:
            now = datetime.now()
        
        # Try to get cached data first
        try:
            cache_manager = CacheManager()
            display_data = cache_manager.get_combined_display_data()
            
            # Get last updated from cache
            if display_data and display_data.get('historical', {}).get('last_updated'):
                last_updated = display_data['historical']['last_updated']
            elif display_data and display_data.get('programmed', {}).get('last_updated'):
                last_updated = display_data['programmed']['last_updated']
        except Exception:
            pass
        
        # Try to fetch real data from SIP API
        try:
            import requests
            import numpy as np
            
            SIP_API_KEY = os.environ.get('SIP_API_KEY')
            if not SIP_API_KEY:
                raise ValueError("SIP_API_KEY environment variable not set")
            SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
            CHILOE_NODE = 'CHILOE________220'
            
            # Fetch yesterday's data (more complete)
            url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            all_chiloe_data = []
            pages_fetched = 0
            max_pages = 10  # Limit for performance
            
            # Start from page 4 where Chiloé data usually is
            start_page = 4
            for page in range(start_page, max_pages + start_page):
                params = {
                    'startDate': yesterday,
                    'endDate': yesterday,
                    'page': page,
                    'limit': 1000,
                    'user_key': SIP_API_KEY
                }
                
                try:
                    response = requests.get(url, params=params, timeout=8)
                    pages_fetched += 1
                    
                    if response.status_code == 200:
                        data = response.json()
                        records = data.get('data', [])
                        
                        # Filter Chiloé records
                        chiloe_records = [r for r in records if r.get('barra_transf') == CHILOE_NODE]
                        all_chiloe_data.extend(chiloe_records)
                        
                        # If we have enough data or reached last page
                        if len(all_chiloe_data) >= 24 or len(records) < 1000:
                            break
                    else:
                        break
                except Exception:
                    break
            
            fetch_info = {
                'pages_fetched': pages_fetched,
                'records_found': len(all_chiloe_data),
                'date_fetched': yesterday
            }
            
            if all_chiloe_data:
                # Sort by time
                all_chiloe_data.sort(key=lambda x: x.get('fecha_hora', ''))
                
                # Extract values for ML (field is cmg_usd_mwh_ not cmg)
                values = [float(r.get('cmg_usd_mwh_', r.get('cmg', 60))) for r in all_chiloe_data]
                hours = [int(r.get('fecha_hora', '00:00')[11:13]) for r in all_chiloe_data]
                
                avg_value = np.mean(values)
                last_value = values[-1] if values else 60
                std_value = np.std(values) if len(values) > 1 else 5
                
                # Learn hourly patterns
                hourly_patterns = {}
                for h, v in zip(hours, values):
                    if h not in hourly_patterns:
                        hourly_patterns[h] = []
                    hourly_patterns[h].append(v)
                
                # Calculate median for each hour
                for h in hourly_patterns:
                    hourly_patterns[h] = np.median(hourly_patterns[h])
                
                data_source = f"SIP API ({len(all_chiloe_data)} records)"
                success = True
                
                # Add historical data (last 24 available)
                for record in all_chiloe_data[-24:]:
                    predictions.append({
                        'datetime': record.get('fecha_hora'),
                        'hour': int(record.get('fecha_hora', '00:00')[11:13]),
                        'cmg_actual': round(float(record.get('cmg_usd_mwh_', record.get('cmg', 60))), 2),
                        'is_historical': True
                    })
                
                # Generate ML-based predictions
                for i in range(48):
                    future_time = now + timedelta(hours=i+1)
                    hour = future_time.hour
                    
                    # Use learned pattern if available
                    if hour in hourly_patterns:
                        base_pred = hourly_patterns[hour]
                    else:
                        # Fallback to time-based pattern
                        if 6 <= hour <= 9:  # Morning peak
                            base_pred = avg_value * 1.2
                        elif 18 <= hour <= 21:  # Evening peak  
                            base_pred = avg_value * 1.3
                        elif 0 <= hour <= 5:  # Night low
                            base_pred = avg_value * 0.75
                        else:
                            base_pred = avg_value
                    
                    # Add some variation based on recent trend
                    if len(values) > 1:
                        trend = (values[-1] - values[0]) / len(values)
                        base_pred += trend * i * 0.1
                    
                    # Add random variation
                    variation = np.random.normal(0, std_value * 0.1)
                    final_pred = max(20, base_pred + variation)  # Ensure positive
                    
                    predictions.append({
                        'datetime': future_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'hour': hour,
                        'cmg_predicted': round(final_pred, 2),
                        'confidence_lower': round(final_pred * 0.9, 2),
                        'confidence_upper': round(final_pred * 1.1, 2),
                        'is_prediction': True
                    })
                    
            else:
                # No real data - use synthetic predictions
                success = False
                data_source = "Synthetic (SIP API unavailable)"
                
        except Exception as e:
            # Fetch failed - use synthetic
            data_source = f"Synthetic (Error: {str(e)[:50]})"
            success = False
        
        # If no real predictions, generate synthetic ones
        if not predictions:
            for i in range(48):
                future_time = now + timedelta(hours=i+1)
                hour = future_time.hour
                
                # Simple time-based pattern
                if 6 <= hour <= 9:
                    pred = 75
                elif 18 <= hour <= 21:
                    pred = 85
                elif 0 <= hour <= 5:
                    pred = 45
                else:
                    pred = 60
                
                predictions.append({
                    'datetime': future_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'hour': hour,
                    'cmg_predicted': float(pred),
                    'confidence_lower': float(pred * 0.9),
                    'confidence_upper': float(pred * 1.1),
                    'is_prediction': True
                })
        
        # Build final response
        result = {
            'success': success,
            'location': 'Chiloé 220kV',
            'node': 'CHILOE________220',
            'data_source': data_source,
            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
            'last_updated': last_updated if last_updated else now.strftime('%Y-%m-%d %H:%M:%S'),
            'stats': {
                'avg_value': round(avg_value, 2),
                'last_value': round(last_value, 2),
                'predictions_count': len(predictions),
                'historical_count': len([p for p in predictions if p.get('is_historical', False)]),
                'future_count': len([p for p in predictions if p.get('is_prediction', False)])
            },
            'fetch_info': fetch_info,
            'predictions': predictions[:72]  # Limit to 72 total
        }
        
        self.wfile.write(json.dumps(result).encode())
        return
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        send_cors_preflight(self, 'GET, OPTIONS')
        return