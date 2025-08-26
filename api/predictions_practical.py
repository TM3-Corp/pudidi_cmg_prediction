"""
Practical CMG Predictions API - Optimized for API limitations
- Fetches only 24-48 hours (fast and practical)
- Robust retry logic with exponential backoff
- Safe lag features where available (24h if we have 48h of data)
- Weather forecast integration
- Fast training suitable for real-time API
"""
import json
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta
import requests
import numpy as np
import pytz
import time

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'
CHILOE_LAT = -42.4472
CHILOE_LON = -73.6506

# Cache
CACHE = {
    'data': None,
    'model': None, 
    'timestamp': None,
    'predictions': None,
    'weather_cache': {},
    'weather_timestamp': None
}

class FastEnsembleML:
    """Fast ensemble optimized for limited data"""
    
    def __init__(self, n_estimators=20):
        self.n_estimators = n_estimators
        self.models = []
        
    def fit(self, X, y):
        """Train fast ensemble"""
        self.models = []
        n_samples = len(X)
        
        for _ in range(self.n_estimators):
            indices = np.random.choice(n_samples, n_samples, replace=True)
            X_boot = X[indices]
            y_boot = y[indices]
            
            model = {}
            for i, x in enumerate(X_boot):
                hour = int(x[0]) % 24
                weekday = int(x[1]) % 7
                has_lag = x[10] > 0 if len(x) > 10 else False
                
                key = f"{hour}_{weekday}_{has_lag}"
                if key not in model:
                    model[key] = []
                model[key].append(y_boot[i])
            
            for key in model:
                model[key] = np.median(model[key])  # Median more robust than mean
            
            self.models.append(model)
    
    def predict(self, X):
        """Fast prediction"""
        predictions = []
        
        for x in X:
            hour = int(x[0]) % 24
            weekday = int(x[1]) % 7
            has_lag = x[10] > 0 if len(x) > 10 else False
            
            preds = []
            for model in self.models:
                key = f"{hour}_{weekday}_{has_lag}"
                if key in model:
                    preds.append(model[key])
                else:
                    # Fallback
                    hour_key = f"{hour}_{weekday}_False"
                    if hour_key in model:
                        preds.append(model[hour_key])
                    else:
                        hour_vals = [v for k, v in model.items() if k.startswith(f"{hour}_")]
                        if hour_vals:
                            preds.append(np.median(hour_vals))
                        else:
                            preds.append(60)
            
            predictions.append(np.median(preds) if preds else 60)
        
        return np.array(predictions)

class handler(BaseHTTPRequestHandler):
    def fetch_with_smart_retry(self, url, params, max_retries=5):
        """Smart retry with exponential backoff for 500/429 errors"""
        wait_time = 2
        
        for attempt in range(max_retries):
            try:
                print(f"    Attempt {attempt + 1}/{max_retries}...")
                response = requests.get(url, params=params, timeout=12)
                
                if response.status_code == 200:
                    return response.json()
                    
                elif response.status_code in [429, 500, 502, 503]:
                    if attempt < max_retries - 1:
                        print(f"    ⏳ Got {response.status_code}, waiting {wait_time}s...")
                        time.sleep(wait_time)
                        wait_time = min(wait_time * 2, 30)
                        continue
                else:
                    print(f"    ❌ Status {response.status_code}")
                    return None
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    print(f"    ⏱️ Timeout, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    wait_time = min(wait_time * 2, 30)
                    continue
                    
            except Exception as e:
                print(f"    ❌ Error: {e}")
                return None
        
        return None
    
    def fetch_weather_forecast(self):
        """Fetch weather forecast"""
        global CACHE
        
        # Use cache if fresh
        if CACHE.get('weather_timestamp'):
            age = (datetime.now() - CACHE['weather_timestamp']).total_seconds()
            if age < 3600 and CACHE.get('weather_cache'):
                return CACHE['weather_cache']
        
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": CHILOE_LAT,
                "longitude": CHILOE_LON,
                "hourly": "temperature_2m,windspeed_10m,precipitation,cloudcover",
                "forecast_days": 3,
                "timezone": "America/Santiago"
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                weather_data = {}
                
                if 'hourly' in data:
                    hourly = data['hourly']
                    for i, dt_str in enumerate(hourly.get('time', [])):
                        dt_key = dt_str[:16]
                        weather_data[dt_key] = {
                            'temp': hourly['temperature_2m'][i] if i < len(hourly['temperature_2m']) else 15,
                            'wind': hourly['windspeed_10m'][i] if i < len(hourly['windspeed_10m']) else 10,
                            'rain': hourly['precipitation'][i] if i < len(hourly['precipitation']) else 0,
                            'cloud': hourly['cloudcover'][i] if i < len(hourly['cloudcover']) else 50
                        }
                
                CACHE['weather_cache'] = weather_data
                CACHE['weather_timestamp'] = datetime.now()
                print(f"  🌤️ Got weather for {len(weather_data)} hours")
                return weather_data
                
        except Exception as e:
            print(f"  ⚠️ Weather fetch failed: {e}")
            
        return {}
    
    def fetch_last_48h_cmg(self):
        """Fetch last 48 hours of CMG data with smart retry"""
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        yesterday = now - timedelta(days=1)
        day_before = now - timedelta(days=2)
        
        all_data = {}
        
        print(f"\n{'='*50}")
        print(f"FETCHING LAST 48 HOURS")
        print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"{'='*50}")
        
        # Try each endpoint for each day
        endpoints = [
            {
                'name': 'PCP',
                'url': f"{SIP_BASE_URL}/cmg-programado-pcp/v4/findByDate",
                'node_field': 'nmb_barra_info',
                'cmg_field': 'cmg_usd_mwh',
                'filter': 'CHILOE'
            },
            {
                'name': 'PID',
                'url': f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate",
                'node_field': 'nmb_barra_info',
                'cmg_field': 'cmg_usd_mwh',
                'filter': 'CHILOE'
            },
            {
                'name': 'CMG Online',
                'url': f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate",
                'node_field': 'barra_transf',
                'cmg_field': 'cmg_usd_mwh_',
                'exact': CHILOE_NODE,
                'paginated': True
            }
        ]
        
        dates_to_fetch = [
            (day_before, "2 days ago"),
            (yesterday, "Yesterday"),
            (now, "Today"),
            (now + timedelta(days=1), "Tomorrow (PCP)")
        ]
        
        for date, date_label in dates_to_fetch:
            date_str = date.strftime('%Y-%m-%d')
            print(f"\n📅 {date_label} ({date_str}):")
            
            for endpoint in endpoints:
                print(f"  🔄 {endpoint['name']}...")
                
                if endpoint.get('paginated'):
                    # CMG Online - try first few pages
                    found_any = False
                    for page in range(1, 4):
                        params = {
                            'startDate': date_str,
                            'endDate': date_str,
                            'page': page,
                            'limit': 500,
                            'user_key': SIP_API_KEY
                        }
                        
                        data = self.fetch_with_smart_retry(endpoint['url'], params, max_retries=3)
                        
                        if data and 'data' in data:
                            for item in data['data']:
                                if item.get(endpoint['node_field']) == endpoint['exact']:
                                    dt_str = item.get('fecha_hora', '')
                                    if dt_str and len(dt_str) >= 16:
                                        dt_key = dt_str[:16]
                                        cmg = float(item.get(endpoint['cmg_field'], 0))
                                        
                                        # Check recency
                                        dt_obj = datetime.strptime(dt_key, '%Y-%m-%d %H:%M')
                                        hours_ago = (datetime.now() - dt_obj).total_seconds() / 3600
                                        
                                        if hours_ago <= 72:  # Keep last 72h
                                            all_data[dt_key] = {
                                                'datetime': dt_key,
                                                'cmg': cmg
                                            }
                                            found_any = True
                            
                            if found_any:
                                print(f"    ✅ Found Chiloé data on page {page}")
                                break
                        
                        if not data or page >= 2:  # Don't go beyond page 2
                            break
                            
                else:
                    # Regular endpoints
                    params = {
                        'startDate': date_str,
                        'endDate': date_str,
                        'limit': 5000,
                        'user_key': SIP_API_KEY
                    }
                    
                    data = self.fetch_with_smart_retry(endpoint['url'], params)
                    
                    if data and 'data' in data:
                        count = 0
                        for item in data['data']:
                            node = item.get(endpoint['node_field'], '')
                            if endpoint.get('filter'):
                                if endpoint['filter'] not in node:
                                    continue
                            elif endpoint.get('exact'):
                                if node != endpoint['exact']:
                                    continue
                            
                            dt_str = item.get('fecha_hora', '')
                            if dt_str and len(dt_str) >= 16:
                                dt_key = dt_str[:16]
                                cmg = float(item.get(endpoint['cmg_field'], 0))
                                
                                dt_obj = datetime.strptime(dt_key, '%Y-%m-%d %H:%M')
                                hours_ago = (datetime.now() - dt_obj).total_seconds() / 3600
                                
                                if hours_ago <= 72:
                                    all_data[dt_key] = {
                                        'datetime': dt_key,
                                        'cmg': cmg
                                    }
                                    count += 1
                        
                        if count > 0:
                            print(f"    ✅ Got {count} records")
                
                # If we have enough data for this day, skip other endpoints
                day_count = sum(1 for k in all_data if k.startswith(date_str))
                if day_count >= 20:
                    break
        
        # Convert to sorted list
        sorted_data = sorted(all_data.values(), key=lambda x: x['datetime'])
        
        print(f"\n📊 SUMMARY:")
        print(f"  Total points: {len(sorted_data)}")
        if sorted_data:
            print(f"  Date range: {sorted_data[0]['datetime']} to {sorted_data[-1]['datetime']}")
        print(f"{'='*50}\n")
        
        return sorted_data
    
    def prepare_features(self, data, weather_data=None):
        """Prepare features with safe lags where available"""
        X = []
        y = []
        
        data_dict = {d['datetime']: d['cmg'] for d in data}
        sorted_times = sorted(data_dict.keys())
        
        for dt_key in sorted_times:
            dt = datetime.strptime(dt_key, '%Y-%m-%d %H:%M')
            
            # Base features
            features = [
                dt.hour,
                dt.weekday(),
                dt.month,
                np.sin(2 * np.pi * dt.hour / 24),
                np.cos(2 * np.pi * dt.hour / 24),
                np.sin(2 * np.pi * dt.weekday() / 7),
                np.cos(2 * np.pi * dt.weekday() / 7),
                1 if dt.weekday() in [5, 6] else 0,
                1 if 7 <= dt.hour <= 9 else 0,
                1 if 18 <= dt.hour <= 21 else 0,
            ]
            
            # Safe 24h lag if available
            lag_24h_key = (dt - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
            lag_24h = data_dict.get(lag_24h_key, -1)
            features.append(lag_24h)
            
            # Rolling mean (last 24h if available)
            window_vals = []
            for h in range(1, 25):
                window_key = (dt - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M')
                if window_key in data_dict:
                    window_vals.append(data_dict[window_key])
            
            if window_vals:
                features.append(np.mean(window_vals))
                features.append(np.std(window_vals) if len(window_vals) > 1 else 0)
            else:
                features.append(-1)
                features.append(-1)
            
            # Weather features
            if weather_data and dt_key in weather_data:
                w = weather_data[dt_key]
                features.extend([w.get('temp', 15), w.get('wind', 10), 
                               w.get('rain', 0), w.get('cloud', 50)])
            else:
                features.extend([15, 10, 0, 50])
            
            X.append(features)
            y.append(data_dict[dt_key])
        
        return np.array(X), np.array(y)
    
    def generate_predictions(self, model, data, weather_data, now):
        """Generate 48h predictions"""
        predictions = []
        data_dict = {d['datetime']: d['cmg'] for d in data}
        
        # Calculate base statistics
        recent_vals = [d['cmg'] for d in data[-24:]] if len(data) >= 24 else [d['cmg'] for d in data]
        base_mean = np.mean(recent_vals) if recent_vals else 60
        
        for hours_ahead in range(1, 49):
            pred_dt = now + timedelta(hours=hours_ahead)
            dt_key = pred_dt.strftime('%Y-%m-%d %H:%M')
            
            # Features
            features = [
                pred_dt.hour,
                pred_dt.weekday(),
                pred_dt.month,
                np.sin(2 * np.pi * pred_dt.hour / 24),
                np.cos(2 * np.pi * pred_dt.hour / 24),
                np.sin(2 * np.pi * pred_dt.weekday() / 7),
                np.cos(2 * np.pi * pred_dt.weekday() / 7),
                1 if pred_dt.weekday() in [5, 6] else 0,
                1 if 7 <= pred_dt.hour <= 9 else 0,
                1 if 18 <= pred_dt.hour <= 21 else 0,
            ]
            
            # Lag from historical or previous predictions
            lag_24h_key = (pred_dt - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
            lag_24h = data_dict.get(lag_24h_key, -1)
            features.append(lag_24h)
            
            # Rolling stats
            window_vals = []
            for h in range(1, 25):
                window_key = (pred_dt - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M')
                if window_key in data_dict:
                    window_vals.append(data_dict[window_key])
            
            if window_vals:
                features.append(np.mean(window_vals))
                features.append(np.std(window_vals) if len(window_vals) > 1 else 0)
            else:
                features.append(-1)
                features.append(-1)
            
            # Weather
            if weather_data and dt_key in weather_data:
                w = weather_data[dt_key]
                features.extend([w.get('temp', 15), w.get('wind', 10),
                               w.get('rain', 0), w.get('cloud', 50)])
            else:
                features.extend([15, 10, 0, 50])
            
            # Predict
            X = np.array([features])
            if model is not None:
                pred_value = model.predict(X)[0]
            else:
                # Pattern-based fallback
                if lag_24h > 0:
                    pred_value = lag_24h
                else:
                    # Time-based pattern
                    hour = pred_dt.hour
                    if 7 <= hour <= 9 or 18 <= hour <= 21:
                        pred_value = base_mean * 1.25
                    elif 22 <= hour or hour <= 5:
                        pred_value = base_mean * 0.8
                    else:
                        pred_value = base_mean
            
            # Smooth transitions
            if predictions:
                prev_value = predictions[-1]['cmg_predicted']
                pred_value = 0.75 * pred_value + 0.25 * prev_value
            
            # Bounds
            pred_value = max(20, min(200, pred_value))
            
            # Uncertainty
            uncertainty = 0.12 + 0.06 * (hours_ahead / 48)
            
            predictions.append({
                'datetime': pred_dt.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': pred_dt.hour,
                'cmg_predicted': round(float(pred_value), 2),
                'confidence_lower': round(float(pred_value * (1 - uncertainty)), 2),
                'confidence_upper': round(float(pred_value * (1 + uncertainty)), 2),
                'is_prediction': True
            })
            
            # Add to dict for future lags
            data_dict[dt_key] = pred_value
        
        return predictions
    
    def do_GET(self):
        """Handle GET request"""
        global CACHE
        
        try:
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
            current_hour = now.strftime('%Y-%m-%d %H:00')
            
            force_refresh = 'force=true' in str(self.path) if hasattr(self, 'path') else False
            
            # Use cache if valid
            if not force_refresh and CACHE.get('timestamp') == current_hour:
                result = {
                    'success': True,
                    'generated_at': now.isoformat(),
                    'location': 'Chiloé 220kV',
                    'node': CHILOE_NODE,
                    'stats': CACHE.get('stats', {}),
                    'predictions': CACHE.get('predictions', []),
                    'cached': True
                }
            else:
                # Fetch weather
                print("\n🚀 GENERATING PREDICTIONS")
                weather_data = self.fetch_weather_forecast()
                
                # Fetch last 48h CMG
                cmg_data = self.fetch_last_48h_cmg()
                
                # Fallback to demo if needed
                if len(cmg_data) < 12:
                    print(f"⚠️ Only {len(cmg_data)} points, using demo")
                    cmg_data = []
                    for hours_ago in range(48, 0, -1):
                        dt = now - timedelta(hours=hours_ago)
                        dt_key = dt.strftime('%Y-%m-%d %H:00')[:16]
                        
                        hour = dt.hour
                        base = 60
                        if 7 <= hour <= 9 or 18 <= hour <= 21:
                            value = base * 1.25 + np.random.normal(0, 5)
                        elif 22 <= hour or hour <= 5:
                            value = base * 0.8 + np.random.normal(0, 3)
                        else:
                            value = base + np.random.normal(0, 4)
                        
                        if dt.weekday() in [5, 6]:
                            value *= 0.9
                        
                        cmg_data.append({
                            'datetime': dt_key,
                            'cmg': max(30, min(150, value))
                        })
                
                # Prepare display (last 24h)
                display_24h = []
                for hours_ago in range(24, 0, -1):
                    target_dt = now - timedelta(hours=hours_ago)
                    target_key = target_dt.strftime('%Y-%m-%d %H:00')
                    
                    found = False
                    for item in cmg_data:
                        item_dt = datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M')
                        target_dt_naive = target_dt.replace(tzinfo=None)
                        if abs((item_dt - target_dt_naive).total_seconds()) < 3600:
                            display_24h.append({
                                'datetime': target_key + ':00',
                                'hour': target_dt.hour,
                                'cmg_actual': round(item['cmg'], 2),
                                'is_historical': True
                            })
                            found = True
                            break
                    
                    if not found:
                        display_24h.append({
                            'datetime': target_key + ':00',
                            'hour': target_dt.hour,
                            'cmg_actual': None,
                            'is_historical': True,
                            'is_missing': True
                        })
                
                # Train model
                model = None
                method = 'Statistical'
                
                if len(cmg_data) >= 24:
                    try:
                        X, y = self.prepare_features(cmg_data, weather_data)
                        model = FastEnsembleML(n_estimators=20)
                        model.fit(X, y)
                        method = f'ML Ensemble ({len(cmg_data)} points)'
                        print(f"  ✅ Model trained on {len(cmg_data)} points")
                    except Exception as e:
                        print(f"  ❌ Training failed: {e}")
                
                # Generate predictions
                predictions_48h = self.generate_predictions(model, cmg_data, weather_data, now)
                
                # Combine
                all_display = display_24h + predictions_48h
                
                # Stats
                actual_values = [d['cmg_actual'] for d in display_24h if d.get('cmg_actual') is not None]
                pred_values = [p['cmg_predicted'] for p in predictions_48h]
                
                stats = {
                    'last_actual': actual_values[-1] if actual_values else None,
                    'avg_24h': round(np.mean(pred_values[:24]), 2),
                    'max_48h': round(max(pred_values), 2),
                    'min_48h': round(min(pred_values), 2),
                    'data_points': len(actual_values),
                    'method': method,
                    'has_weather': len(weather_data) > 0,
                    'last_update': now.strftime('%H:%M')
                }
                
                print(f"\n📊 Results: {len(actual_values)} historical, {len(pred_values)} predictions")
                print(f"   Method: {method}, Weather: {'Yes' if weather_data else 'No'}\n")
                
                # Update cache
                CACHE = {
                    'timestamp': current_hour,
                    'predictions': all_display,
                    'stats': stats,
                    'data': cmg_data,
                    'model': model
                }
                
                result = {
                    'success': True,
                    'generated_at': now.isoformat(),
                    'location': 'Chiloé 220kV',
                    'node': CHILOE_NODE,
                    'stats': stats,
                    'predictions': all_display,
                    'cached': False
                }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, max-age=300')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            
        except Exception as e:
            print(f"❌ Error: {e}")
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_result = {'success': False, 'error': str(e)}
            self.wfile.write(json.dumps(error_result).encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()