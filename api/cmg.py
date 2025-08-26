"""
CMG Predictions API - No pandas, pure Python
Works with minimal dependencies
"""
import json
import requests
from datetime import datetime, timedelta
import math

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

def fetch_recent_cmg(days_back=7):
    """Fetch recent CMG Real data"""
    url = f"{SIP_BASE_URL}/costo-marginal-real/v4/findByDate"
    
    end_date = datetime.utcnow() - timedelta(hours=3)  # Santiago time
    start_date = end_date - timedelta(days=days_back)
    
    all_data = []
    current = start_date
    
    while current <= end_date:
        params = {
            'startDate': current.strftime('%Y-%m-%d'),
            'endDate': current.strftime('%Y-%m-%d'),
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=8)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    for item in data['data']:
                        if item.get('barra_transf') == CHILOE_NODE:
                            all_data.append({
                                'datetime': item['fecha_hora'],
                                'cmg': float(item['cmg_usd_mwh_'])
                            })
        except:
            pass
        
        current += timedelta(days=1)
    
    return all_data

def calculate_hourly_patterns(historical_data):
    """Calculate average CMG by hour"""
    hourly_totals = {}
    hourly_counts = {}
    
    for item in historical_data:
        dt = datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M')
        hour = dt.hour
        
        if hour not in hourly_totals:
            hourly_totals[hour] = 0
            hourly_counts[hour] = 0
        
        hourly_totals[hour] += item['cmg']
        hourly_counts[hour] += 1
    
    hourly_avg = {}
    for hour in hourly_totals:
        hourly_avg[hour] = hourly_totals[hour] / hourly_counts[hour]
    
    return hourly_avg

def generate_predictions(historical_data, hours=48):
    """Generate predictions based on patterns"""
    predictions = []
    
    if historical_data:
        # Calculate patterns
        hourly_patterns = calculate_hourly_patterns(historical_data)
        
        # Get average and recent trend
        total = sum(d['cmg'] for d in historical_data)
        avg_cmg = total / len(historical_data) if historical_data else 80
        
        # Recent trend (last 24 records)
        recent = historical_data[-24:] if len(historical_data) > 24 else historical_data
        recent_avg = sum(d['cmg'] for d in recent) / len(recent) if recent else avg_cmg
        trend = recent_avg / avg_cmg if avg_cmg > 0 else 1.0
        
        # Get last datetime
        last_dt_str = historical_data[-1]['datetime'] if historical_data else None
        if last_dt_str:
            last_dt = datetime.strptime(last_dt_str, '%Y-%m-%d %H:%M')
        else:
            last_dt = datetime.utcnow() - timedelta(hours=3)
    else:
        # Default values if no data
        hourly_patterns = {}
        avg_cmg = 80
        trend = 1.0
        last_dt = datetime.utcnow() - timedelta(hours=3)
    
    # Generate predictions
    for h in range(hours):
        pred_dt = last_dt + timedelta(hours=h+1)
        hour = pred_dt.hour
        
        # Get base value from hourly pattern or use average
        base_value = hourly_patterns.get(hour, avg_cmg)
        
        # Apply trend adjustment
        predicted = base_value * (0.7 + 0.3 * trend)
        
        # Add time-based variation
        hour_factor = 1 + 0.2 * math.sin(2 * math.pi * (hour - 14) / 24)
        predicted *= hour_factor
        
        predictions.append({
            'datetime': pred_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'hour': hour,
            'cmg_predicted': round(predicted, 2),
            'confidence_lower': round(predicted * 0.9, 2),
            'confidence_upper': round(predicted * 1.1, 2)
        })
    
    return predictions

def handler(request, response):
    """Main API handler"""
    try:
        # Fetch recent CMG data
        historical_data = fetch_recent_cmg(days_back=7)
        
        # Generate predictions
        predictions = generate_predictions(historical_data, hours=48)
        
        # Add historical data
        all_results = []
        if historical_data:
            # Add last 24 hours
            for item in historical_data[-24:]:
                dt = datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M')
                all_results.append({
                    'datetime': item['datetime'] + ':00',
                    'hour': dt.hour,
                    'cmg_actual': round(item['cmg'], 2),
                    'is_historical': True
                })
        
        # Add predictions
        all_results.extend(predictions)
        
        # Calculate statistics
        if historical_data:
            last_actual = round(historical_data[-1]['cmg'], 2)
            data_points = len(historical_data)
        else:
            last_actual = None
            data_points = 0
        
        pred_values = [p['cmg_predicted'] for p in predictions]
        avg_24 = sum(pred_values[:24]) / 24 if len(pred_values) >= 24 else 0
        
        stats = {
            'last_actual': last_actual,
            'avg_24h': round(avg_24, 2),
            'max_48h': round(max(pred_values), 2) if pred_values else 0,
            'min_48h': round(min(pred_values), 2) if pred_values else 0,
            'data_points': data_points
        }
        
        result = {
            'success': True,
            'generated_at': datetime.utcnow().isoformat(),
            'location': 'Chiloé 220kV',
            'stats': stats,
            'predictions': all_results
        }
        
    except Exception as e:
        # Fallback with basic predictions
        now = datetime.utcnow() - timedelta(hours=3)
        fallback = []
        
        for h in range(48):
            pred_dt = now + timedelta(hours=h)
            value = 80 + 20 * math.sin(2 * math.pi * pred_dt.hour / 24)
            fallback.append({
                'datetime': pred_dt.strftime('%Y-%m-%d %H:%M:%S'),
                'hour': pred_dt.hour,
                'cmg_predicted': round(value, 2)
            })
        
        result = {
            'success': False,
            'error': str(e),
            'predictions': fallback,
            'stats': {'avg_24h': 80, 'max_48h': 100, 'min_48h': 60}
        }
    
    response.status = 200
    response.headers = {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300'
    }
    response.body = json.dumps(result)
    return response