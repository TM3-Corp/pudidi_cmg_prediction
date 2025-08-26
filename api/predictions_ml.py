"""
CMG Predictions API - Proper ML Implementation
"""
import json
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta
import requests
import numpy as np
import pytz

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

class ProperML:
    """Proper ML model using ensemble approach"""
    
    def __init__(self, n_estimators=50):
        self.n_estimators = n_estimators
        self.models = []
        self.feature_means = None
        self.feature_stds = None
        
    def fit(self, X, y):
        """Train ensemble of models"""
        # Store normalization parameters
        self.feature_means = np.mean(X, axis=0)
        self.feature_stds = np.std(X, axis=0) + 1e-8
        X_norm = (X - self.feature_means) / self.feature_stds
        
        n_samples = len(X)
        self.models = []
        
        for i in range(self.n_estimators):
            # Bootstrap sampling
            indices = np.random.choice(n_samples, n_samples, replace=True)
            X_boot = X_norm[indices]
            y_boot = y[indices]
            
            # Create a gradient boosting-like model
            model = {
                'trees': [],
                'weights': []
            }
            
            residuals = y_boot.copy()
            learning_rate = 0.1
            
            # Build trees sequentially
            for tree_idx in range(10):  # 10 trees per model
                tree = self._build_tree(X_boot, residuals, max_depth=5)
                predictions = self._predict_tree(X_boot, tree)
                
                model['trees'].append(tree)
                model['weights'].append(learning_rate * (0.9 ** tree_idx))
                
                # Update residuals
                residuals = residuals - learning_rate * predictions
                
            self.models.append(model)
    
    def _build_tree(self, X, y, max_depth=5, depth=0):
        """Build a simple decision tree"""
        if depth >= max_depth or len(y) < 10:
            return {'type': 'leaf', 'value': np.mean(y)}
        
        # Find best split
        best_gain = 0
        best_split = None
        
        for feature_idx in range(X.shape[1]):
            # Try different split points
            unique_vals = np.unique(X[:, feature_idx])
            if len(unique_vals) < 2:
                continue
                
            for split_val in unique_vals[:-1]:
                left_mask = X[:, feature_idx] <= split_val
                right_mask = ~left_mask
                
                if np.sum(left_mask) < 5 or np.sum(right_mask) < 5:
                    continue
                
                # Calculate variance reduction
                var_before = np.var(y)
                var_left = np.var(y[left_mask])
                var_right = np.var(y[right_mask])
                
                n_left = np.sum(left_mask)
                n_right = np.sum(right_mask)
                n_total = len(y)
                
                var_after = (n_left/n_total) * var_left + (n_right/n_total) * var_right
                gain = var_before - var_after
                
                if gain > best_gain:
                    best_gain = gain
                    best_split = {
                        'feature': feature_idx,
                        'threshold': split_val,
                        'left_mask': left_mask,
                        'right_mask': right_mask
                    }
        
        if best_split is None:
            return {'type': 'leaf', 'value': np.mean(y)}
        
        # Recursively build subtrees
        return {
            'type': 'split',
            'feature': best_split['feature'],
            'threshold': best_split['threshold'],
            'left': self._build_tree(X[best_split['left_mask']], y[best_split['left_mask']], max_depth, depth+1),
            'right': self._build_tree(X[best_split['right_mask']], y[best_split['right_mask']], max_depth, depth+1)
        }
    
    def _predict_tree(self, X, tree):
        """Make predictions with a single tree"""
        predictions = np.zeros(len(X))
        
        for i, x in enumerate(X):
            node = tree
            while node['type'] != 'leaf':
                if x[node['feature']] <= node['threshold']:
                    node = node['left']
                else:
                    node = node['right']
            predictions[i] = node['value']
        
        return predictions
    
    def predict(self, X):
        """Make ensemble predictions"""
        X_norm = (X - self.feature_means) / self.feature_stds
        
        all_predictions = []
        for model in self.models:
            model_pred = np.zeros(len(X))
            for tree, weight in zip(model['trees'], model['weights']):
                model_pred += weight * self._predict_tree(X_norm, tree)
            all_predictions.append(model_pred)
        
        # Average across all models
        return np.mean(all_predictions, axis=0)

class handler(BaseHTTPRequestHandler):
    def fetch_complete_cmg_data(self):
        """Fetch the most complete CMG data available"""
        santiago_tz = pytz.timezone('America/Santiago')
        santiago_now = datetime.now(santiago_tz)
        
        all_data = {}
        
        # Strategy: Get the most recent available data from each source
        
        # 1. Try CMG Real (most accurate but delayed)
        real_url = f"{SIP_BASE_URL}/costo-marginal-real/v4/findByDate"
        for days_ago in range(7, 14):  # Check 7-14 days ago
            check_date = santiago_now - timedelta(days=days_ago)
            params = {
                'startDate': check_date.strftime('%Y-%m-%d'),
                'endDate': check_date.strftime('%Y-%m-%d'),
                'limit': 3000,
                'user_key': SIP_API_KEY
            }
            
            try:
                response = requests.get(real_url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data and data['data']:
                        for item in data['data']:
                            if item.get('barra_transf') == CHILOE_NODE:
                                dt_key = item['fecha_hora'][:16]
                                all_data[dt_key] = {
                                    'datetime': dt_key,
                                    'cmg': float(item['cmg_usd_mwh_']),
                                    'source': 'real'
                                }
            except:
                pass
        
        # 2. Get CMG Programado for recent/future (both PCP and PID)
        for endpoint, name in [
            ('/cmg-programado-pcp/v4/findByDate', 'pcp'),
            ('/cmg-programado-pid/v4/findByDate', 'pid')
        ]:
            url = f"{SIP_BASE_URL}{endpoint}"
            
            # Get last 7 days to today + 2 days ahead
            params = {
                'startDate': (santiago_now - timedelta(days=7)).strftime('%Y-%m-%d'),
                'endDate': (santiago_now + timedelta(days=2)).strftime('%Y-%m-%d'),
                'limit': 10000,
                'user_key': SIP_API_KEY
            }
            
            try:
                response = requests.get(url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data and data['data']:
                        for item in data['data']:
                            if 'CHILOE' in str(item.get('nmb_barra_info', '')):
                                dt_key = item['fecha_hora'][:16]
                                # PID overwrites PCP, Real overwrites both
                                if dt_key not in all_data or (all_data[dt_key]['source'] == 'pcp' and name == 'pid'):
                                    all_data[dt_key] = {
                                        'datetime': dt_key,
                                        'cmg': float(item['cmg_usd_mwh']),
                                        'source': name
                                    }
            except Exception as e:
                print(f"Error fetching {name}: {e}")
        
        # Sort and return as list
        if all_data:
            sorted_data = sorted(all_data.values(), key=lambda x: x['datetime'])
            # Remove source info for output
            for item in sorted_data:
                del item['source']
            return sorted_data
        
        return []
    
    def prepare_features_with_proper_lags(self, data):
        """Prepare features with proper lag handling"""
        X = []
        y = []
        
        # Sort data by datetime
        data_sorted = sorted(data, key=lambda x: x['datetime'])
        
        # Create datetime index for easier lookup
        dt_to_cmg = {item['datetime']: item['cmg'] for item in data_sorted}
        
        for i, item in enumerate(data_sorted):
            if i < 168:  # Need at least 7 days of history
                continue
                
            dt = datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M')
            
            features = []
            
            # Temporal features with cyclical encoding
            features.extend([
                np.sin(2 * np.pi * dt.hour / 24),
                np.cos(2 * np.pi * dt.hour / 24),
                np.sin(2 * np.pi * dt.weekday() / 7),
                np.cos(2 * np.pi * dt.weekday() / 7),
                np.sin(2 * np.pi * dt.month / 12),
                np.cos(2 * np.pi * dt.month / 12),
            ])
            
            # Raw temporal features for tree models
            features.extend([
                dt.hour,
                dt.weekday(),
                dt.month,
                dt.day,
            ])
            
            # Binary indicators
            features.extend([
                1 if dt.weekday() in [5, 6] else 0,  # Weekend
                1 if 7 <= dt.hour <= 9 else 0,  # Morning peak
                1 if 18 <= dt.hour <= 21 else 0,  # Evening peak
                1 if dt.hour in [0, 1, 2, 3, 4, 5] else 0,  # Night
            ])
            
            # PROPER LAG FEATURES - from 24+ hours ago to avoid leakage
            # These provide context without autocorrelation
            lag_24h = data_sorted[i-24]['cmg'] if i >= 24 else np.nan
            lag_48h = data_sorted[i-48]['cmg'] if i >= 48 else np.nan
            lag_72h = data_sorted[i-72]['cmg'] if i >= 72 else np.nan
            lag_168h = data_sorted[i-168]['cmg'] if i >= 168 else np.nan  # 1 week ago
            
            features.extend([
                lag_24h if not np.isnan(lag_24h) else np.mean([d['cmg'] for d in data_sorted[:i]]),
                lag_48h if not np.isnan(lag_48h) else np.mean([d['cmg'] for d in data_sorted[:i]]),
                lag_72h if not np.isnan(lag_72h) else np.mean([d['cmg'] for d in data_sorted[:i]]),
                lag_168h if not np.isnan(lag_168h) else np.mean([d['cmg'] for d in data_sorted[:i]]),
            ])
            
            # Rolling statistics from 24-48 hours ago
            if i >= 48:
                window_24_48 = [data_sorted[j]['cmg'] for j in range(i-48, i-24)]
                features.extend([
                    np.mean(window_24_48),
                    np.std(window_24_48),
                    np.min(window_24_48),
                    np.max(window_24_48),
                ])
            else:
                features.extend([60, 15, 40, 80])  # Defaults
            
            # Hourly averages from past week (same hour)
            same_hour_values = []
            for days_back in range(1, 8):
                idx = i - (days_back * 24)
                if idx >= 0 and data_sorted[idx]['datetime'][11:13] == item['datetime'][11:13]:
                    same_hour_values.append(data_sorted[idx]['cmg'])
            
            if same_hour_values:
                features.extend([
                    np.mean(same_hour_values),
                    np.std(same_hour_values) if len(same_hour_values) > 1 else 10,
                ])
            else:
                features.extend([60, 15])
            
            X.append(features)
            y.append(item['cmg'])
        
        return np.array(X), np.array(y)
    
    def generate_proper_ml_predictions(self, historical_data):
        """Generate predictions using proper ML"""
        if len(historical_data) < 200:
            return self.fallback_predictions(historical_data)
        
        try:
            # Prepare training data
            X, y = self.prepare_features_with_proper_lags(historical_data)
            
            if len(X) < 100:
                return self.fallback_predictions(historical_data)
            
            # Train model
            model = ProperML(n_estimators=30)
            model.fit(X, y)
            
            # Generate predictions
            predictions = []
            last_dt = datetime.strptime(historical_data[-1]['datetime'], '%Y-%m-%d %H:%M')
            
            # For predictions, we need to construct features carefully
            for h in range(48):
                pred_dt = last_dt + timedelta(hours=h+1)
                
                features = []
                
                # Temporal features
                features.extend([
                    np.sin(2 * np.pi * pred_dt.hour / 24),
                    np.cos(2 * np.pi * pred_dt.hour / 24),
                    np.sin(2 * np.pi * pred_dt.weekday() / 7),
                    np.cos(2 * np.pi * pred_dt.weekday() / 7),
                    np.sin(2 * np.pi * pred_dt.month / 12),
                    np.cos(2 * np.pi * pred_dt.month / 12),
                ])
                
                features.extend([
                    pred_dt.hour,
                    pred_dt.weekday(),
                    pred_dt.month,
                    pred_dt.day,
                ])
                
                features.extend([
                    1 if pred_dt.weekday() in [5, 6] else 0,
                    1 if 7 <= pred_dt.hour <= 9 else 0,
                    1 if 18 <= pred_dt.hour <= 21 else 0,
                    1 if pred_dt.hour in [0, 1, 2, 3, 4, 5] else 0,
                ])
                
                # Use historical lags (we know these)
                if len(historical_data) > 24 + h:
                    features.append(historical_data[-(24-h)]['cmg'])
                else:
                    features.append(np.mean([d['cmg'] for d in historical_data[-48:]]))
                
                if len(historical_data) > 48 + h:
                    features.append(historical_data[-(48-h)]['cmg'])
                else:
                    features.append(np.mean([d['cmg'] for d in historical_data[-72:-24]]))
                
                if len(historical_data) > 72 + h:
                    features.append(historical_data[-(72-h)]['cmg'])
                else:
                    features.append(np.mean([d['cmg'] for d in historical_data[-96:-48]]))
                
                if len(historical_data) > 168 + h:
                    features.append(historical_data[-(168-h)]['cmg'])
                else:
                    features.append(np.mean([d['cmg'] for d in historical_data[-192:-144]]))
                
                # Rolling stats from available history
                recent_data = historical_data[-48:-24] if len(historical_data) > 48 else historical_data[-24:]
                features.extend([
                    np.mean([d['cmg'] for d in recent_data]),
                    np.std([d['cmg'] for d in recent_data]),
                    np.min([d['cmg'] for d in recent_data]),
                    np.max([d['cmg'] for d in recent_data]),
                ])
                
                # Same hour historical average
                same_hour_hist = [d['cmg'] for d in historical_data[-168:] 
                                 if datetime.strptime(d['datetime'], '%Y-%m-%d %H:%M').hour == pred_dt.hour]
                if same_hour_hist:
                    features.extend([np.mean(same_hour_hist), np.std(same_hour_hist)])
                else:
                    features.extend([60, 15])
                
                # Make prediction
                X_pred = np.array([features])
                pred_value = model.predict(X_pred)[0]
                
                # Apply realistic bounds and smoothing
                if h > 0 and predictions:
                    # Smooth with previous prediction
                    prev_pred = predictions[-1]['cmg_predicted']
                    pred_value = 0.7 * pred_value + 0.3 * prev_pred
                
                pred_value = max(20, min(200, pred_value))
                
                # Uncertainty grows with horizon
                uncertainty = 0.15 + 0.10 * (h / 48)
                
                predictions.append({
                    'datetime': pred_dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'hour': pred_dt.hour,
                    'cmg_predicted': round(float(pred_value), 2),
                    'confidence_lower': round(float(pred_value * (1 - uncertainty)), 2),
                    'confidence_upper': round(float(pred_value * (1 + uncertainty)), 2),
                    'method': 'Ensemble ML'
                })
            
            return predictions, 'Ensemble ML Model'
            
        except Exception as e:
            print(f"ML error: {e}")
            return self.fallback_predictions(historical_data)
    
    def fallback_predictions(self, historical_data):
        """Fallback to statistical predictions"""
        predictions = []
        
        if not historical_data:
            historical_data = [{'datetime': '2025-08-25 17:00', 'cmg': 60}]
        
        # Calculate hourly patterns
        hourly_patterns = {}
        for item in historical_data:
            dt = datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M')
            hour = dt.hour
            if hour not in hourly_patterns:
                hourly_patterns[hour] = []
            hourly_patterns[hour].append(item['cmg'])
        
        hourly_avg = {h: np.mean(vals) for h, vals in hourly_patterns.items()}
        hourly_std = {h: np.std(vals) if len(vals) > 1 else 10 for h, vals in hourly_patterns.items()}
        
        # Fill missing hours
        overall_avg = np.mean([item['cmg'] for item in historical_data])
        for h in range(24):
            if h not in hourly_avg:
                # Estimate based on typical patterns
                if 7 <= h <= 9 or 18 <= h <= 21:  # Peak hours
                    hourly_avg[h] = overall_avg * 1.3
                elif 0 <= h <= 5:  # Night
                    hourly_avg[h] = overall_avg * 0.7
                else:
                    hourly_avg[h] = overall_avg
                hourly_std[h] = overall_avg * 0.2
        
        last_dt = datetime.strptime(historical_data[-1]['datetime'], '%Y-%m-%d %H:%M')
        
        for h in range(48):
            pred_dt = last_dt + timedelta(hours=h+1)
            hour = pred_dt.hour
            
            base_value = hourly_avg.get(hour, overall_avg)
            std_value = hourly_std.get(hour, 10)
            
            # Add some realistic variation
            variation = np.random.normal(0, std_value * 0.3)
            pred_value = base_value + variation
            
            # Weekend adjustment
            if pred_dt.weekday() in [5, 6]:
                pred_value *= 0.9
            
            pred_value = max(20, min(200, pred_value))
            
            predictions.append({
                'datetime': pred_dt.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': hour,
                'cmg_predicted': round(float(pred_value), 2),
                'confidence_lower': round(float(pred_value - std_value), 2),
                'confidence_upper': round(float(pred_value + std_value), 2),
                'method': 'Statistical'
            })
        
        return predictions, 'Statistical Patterns'
    
    def do_GET(self):
        """Handle GET request"""
        try:
            # Fetch all available CMG data
            historical_data = self.fetch_complete_cmg_data()
            
            # Get last 24 hours for display
            if historical_data:
                # Sort and get recent data
                sorted_data = sorted(historical_data, key=lambda x: x['datetime'])
                display_historical = sorted_data[-24:] if len(sorted_data) >= 24 else sorted_data
                
                # Format for display
                historical_display = []
                for item in display_historical:
                    dt = datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M')
                    historical_display.append({
                        'datetime': item['datetime'] + ':00',
                        'hour': dt.hour,
                        'cmg_actual': round(item['cmg'], 2),
                        'is_historical': True
                    })
            else:
                historical_display = []
            
            # Generate ML predictions
            predictions, method = self.generate_proper_ml_predictions(historical_data)
            
            # Combine for output
            all_data = historical_display + predictions
            
            # Calculate statistics
            if predictions:
                pred_values = [p['cmg_predicted'] for p in predictions]
                actual_values = [h['cmg_actual'] for h in historical_display] if historical_display else []
                
                stats = {
                    'last_actual': historical_display[-1]['cmg_actual'] if historical_display else None,
                    'avg_24h': round(np.mean(pred_values[:24]), 2),
                    'max_48h': round(max(pred_values), 2),
                    'min_48h': round(min(pred_values), 2),
                    'data_points': len(historical_data),
                    'historical_points': len(historical_display),
                    'method': method
                }
            else:
                stats = {
                    'last_actual': None,
                    'avg_24h': 60,
                    'max_48h': 80,
                    'min_48h': 40,
                    'data_points': 0,
                    'method': 'Default'
                }
            
            result = {
                'success': True,
                'generated_at': datetime.now(pytz.timezone('America/Santiago')).isoformat(),
                'location': 'Chiloé 220kV',
                'node': CHILOE_NODE,
                'stats': stats,
                'predictions': all_data
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, max-age=300')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_result = {
                'success': False,
                'error': str(e),
                'message': 'Error generating predictions'
            }
            self.wfile.write(json.dumps(error_result).encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()