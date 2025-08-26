"""
Live API Handler - Fetches real-time data from SIP API and makes predictions
Lightweight version using only numpy for Vercel deployment
"""

import json
import requests
from datetime import datetime, timedelta
import numpy as np
import pytz
import time
import os

# Configuration
SIP_API_KEY = os.environ.get('SIP_API_KEY', '1a81177c8ff4f69e7dd5bb8c61bc08b4')
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

class NumpyMLModel:
    """Lightweight ML model using only numpy"""
    
    def __init__(self):
        self.hourly_patterns = {}
        self.trend = 0
        self.base_value = 60
        
    def fit(self, hours, values):
        """Learn patterns from historical data"""
        if len(values) == 0:
            return
            
        # Calculate base value
        self.base_value = np.mean(values)
        
        # Learn hourly patterns
        for h, v in zip(hours, values):
            if h not in self.hourly_patterns:
                self.hourly_patterns[h] = []
            self.hourly_patterns[h].append(v)
        
        # Calculate average for each hour
        for h in self.hourly_patterns:
            self.hourly_patterns[h] = np.median(self.hourly_patterns[h])
        
        # Calculate trend (simple linear regression with numpy)
        if len(values) > 1:
            x = np.arange(len(values))
            # Simple trend calculation
            self.trend = (values[-1] - values[0]) / len(values) if len(values) > 0 else 0
    
    def predict(self, hour, last_value=None):
        """Make prediction for a specific hour"""
        # Start with base prediction
        if hour in self.hourly_patterns:
            prediction = self.hourly_patterns[hour]
        else:
            # Use sinusoidal pattern for unknown hours
            prediction = self.base_value + 15 * np.sin((hour - 6) * np.pi / 12)
        
        # Adjust based on last known value
        if last_value is not None:
            # Weighted average with last value
            prediction = 0.3 * last_value + 0.7 * prediction
        
        # Add small trend component
        prediction += self.trend * 0.1
        
        # Add small random variation
        prediction += np.random.normal(0, 2)
        
        return max(0, prediction)  # Ensure positive

def fetch_cmg_data_with_retry(date_str, max_retries=3, max_pages=30):
    """
    Fetch CMG data from SIP API with retry logic
    Limited pages for faster response
    """
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    all_data = []
    page = 1
    limit = 1000
    
    while page <= max_pages:
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': limit,
            'user_key': SIP_API_KEY
        }
        
        retries = 0
        while retries < max_retries:
            try:
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    records = data.get('data', [])
                    
                    # Filter for Chiloé node
                    chiloe_records = [r for r in records if r.get('barra_transf') == CHILOE_NODE]
                    all_data.extend(chiloe_records)
                    
                    # If we have enough data, stop
                    if len(all_data) >= 24:
                        return all_data
                    
                    # Check if this is the last page
                    if len(records) < limit:
                        return all_data
                    
                    page += 1
                    break  # Success, move to next page
                    
                elif response.status_code in [429, 500, 502, 503]:
                    # Rate limit or server error - wait and retry
                    wait_time = min(2 ** retries, 8)  # Max 8 seconds
                    time.sleep(wait_time)
                    retries += 1
                else:
                    # Other error
                    return all_data
                    
            except Exception as e:
                retries += 1
                if retries >= max_retries:
                    return all_data
                time.sleep(min(2 ** retries, 8))
    
    return all_data

def handler(request):
    """
    Vercel serverless function handler - Lightweight LIVE API VERSION
    Fetches real-time data from SIP API and makes predictions using numpy only
    """
    
    # Handle CORS
    if request.method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': ''
        }
    
    try:
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        today = now.strftime('%Y-%m-%d')
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Try to fetch CMG data from SIP API
        cmg_data = []
        
        # Try yesterday first (more likely to have complete data)
        yesterday_data = fetch_cmg_data_with_retry(yesterday, max_pages=20)
        if yesterday_data:
            cmg_data.extend(yesterday_data)
        
        # Then try today (might be incomplete)
        today_data = fetch_cmg_data_with_retry(today, max_pages=10)
        if today_data:
            cmg_data.extend(today_data)
        
        # Sort by datetime
        cmg_data.sort(key=lambda x: x['fecha_hora'])
        
        # Remove duplicates
        seen = set()
        unique_data = []
        for d in cmg_data:
            key = d['fecha_hora']
            if key not in seen:
                seen.add(key)
                unique_data.append(d)
        cmg_data = unique_data
        
        if cmg_data:
            # Extract values and hours
            values = [float(d['cmg']) for d in cmg_data]
            hours = [int(d['fecha_hora'][11:13]) for d in cmg_data]
            
            # Calculate statistics
            recent_values = values[-24:] if len(values) >= 24 else values
            stats = {
                'data_points': len(cmg_data),
                'avg_24h': round(np.mean(recent_values), 2),
                'max_48h': round(max(values), 2),
                'min_48h': round(min(values), 2),
                'last_actual': round(values[-1], 2) if values else 0,
                'hours_covered': len(set(d['fecha_hora'][11:13] for d in cmg_data[-24:])),
                'method': 'Live Numpy ML'
            }
            
            # Train lightweight model
            model = NumpyMLModel()
            model.fit(hours, values)
            
            # Generate predictions for next 48 hours
            predictions = []
            last_value = values[-1] if values else 60
            
            for i in range(48):
                future_time = now + timedelta(hours=i+1)
                hour = future_time.hour
                
                # Make prediction
                pred_value = model.predict(hour, last_value)
                
                predictions.append({
                    'datetime': future_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'hour': hour,
                    'cmg_predicted': round(pred_value, 2),
                    'confidence_lower': round(pred_value * 0.9, 2),
                    'confidence_upper': round(pred_value * 1.1, 2),
                    'is_prediction': True
                })
                
                last_value = pred_value  # Use prediction for next iteration
            
            # Add historical data (last 24 hours or available)
            historical = []
            for d in cmg_data[-24:]:
                historical.append({
                    'datetime': d['fecha_hora'],
                    'hour': int(d['fecha_hora'][11:13]),
                    'cmg_actual': round(float(d['cmg']), 2),
                    'is_historical': True
                })
            
            all_predictions = historical + predictions
            
            result = {
                'success': True,
                'location': 'Chiloé 220kV',
                'node': CHILOE_NODE,
                'data_source': 'SIP API Live',
                'fetch_info': {
                    'yesterday_records': len(yesterday_data),
                    'today_records': len(today_data),
                    'total_records': len(cmg_data)
                },
                'stats': stats,
                'predictions': all_predictions[:72]
            }
            
        else:
            # No data fetched - use fallback predictions
            stats = {
                'data_points': 0,
                'avg_24h': 60,
                'max_48h': 80,
                'min_48h': 40,
                'last_actual': 57.15,
                'hours_covered': 0,
                'method': 'Fallback (no data)'
            }
            
            # Generate synthetic predictions
            predictions = []
            for i in range(48):
                future_time = now + timedelta(hours=i+1)
                hour = future_time.hour
                # Simple sinusoidal pattern
                base_value = 60 + 15 * np.sin((hour - 6) * np.pi / 12)
                pred_value = base_value + np.random.normal(0, 3)
                
                predictions.append({
                    'datetime': future_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'hour': hour,
                    'cmg_predicted': round(pred_value, 2),
                    'confidence_lower': round(pred_value * 0.9, 2),
                    'confidence_upper': round(pred_value * 1.1, 2),
                    'is_prediction': True
                })
            
            result = {
                'success': False,
                'location': 'Chiloé 220kV',
                'node': CHILOE_NODE,
                'data_source': 'Fallback',
                'message': 'Could not fetch data from API, using synthetic predictions',
                'stats': stats,
                'predictions': predictions
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Cache-Control': 'max-age=300'  # Cache for 5 minutes
            },
            'body': json.dumps(result)
        }
        
    except Exception as e:
        # Return error but with synthetic data
        error_result = {
            'success': False,
            'error': str(e),
            'location': 'Chiloé 220kV',
            'node': CHILOE_NODE,
            'message': 'Error occurred, showing synthetic data',
            'predictions': []
        }
        
        # Add some synthetic predictions even on error
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        
        for i in range(48):
            future_time = now + timedelta(hours=i+1)
            hour = future_time.hour
            base_value = 60 + 15 * np.sin((hour - 6) * np.pi / 12)
            
            error_result['predictions'].append({
                'datetime': future_time.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': hour,
                'cmg_predicted': round(base_value, 2),
                'is_prediction': True
            })
        
        return {
            'statusCode': 200,  # Return 200 even on error to show data
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(error_result)
        }