#!/usr/bin/env python3
"""
Quick test to verify the hour filtering fix works
"""

from datetime import datetime, timedelta
import pytz

def parse_historical_record_test(fecha_hora, hra):
    """Test version of parse function"""
    dt_str = fecha_hora
    
    # Remove timezone
    if '+' in dt_str:
        dt_str = dt_str.split('+')[0]
    elif '-' in dt_str[-6:] and 'T' in dt_str:
        dt_str = dt_str[:-6]
    
    # Parse datetime
    if 'T' in dt_str:
        dt = datetime.strptime(dt_str[:19], '%Y-%m-%dT%H:%M:%S')
    else:
        dt = datetime.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S')
    
    return {
        'datetime': dt.strftime('%Y-%m-%d %H:%M'),
        'date': dt.strftime('%Y-%m-%d'),
        'hour': hra if hra is not None else dt.hour,
    }

# Test with sample data
santiago_tz = pytz.timezone('America/Santiago')
now = datetime.now(santiago_tz)
yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
today = now.strftime('%Y-%m-%d')

print(f"Current time: {now.strftime('%Y-%m-%d %H:%M')}")
print(f"Current hour: {now.hour}")
print(f"Yesterday: {yesterday}")
print(f"Today: {today}")
print()

# Test cases
test_records = [
    # Yesterday records
    {'fecha_hora': f'{yesterday}T18:00:00', 'hra': 18, 'expected': 'KEEP (yesterday hour 18)'},
    {'fecha_hora': f'{yesterday}T19:00:00', 'hra': 19, 'expected': 'KEEP (yesterday hour 19)'},
    {'fecha_hora': f'{yesterday}T23:00:00', 'hra': 23, 'expected': 'KEEP (yesterday hour 23)'},
    {'fecha_hora': f'{yesterday}T17:00:00', 'hra': 17, 'expected': 'DISCARD (yesterday hour 17 = current hour)'},
    {'fecha_hora': f'{yesterday}T10:00:00', 'hra': 10, 'expected': 'DISCARD (yesterday hour 10 < current)'},
    
    # Today records
    {'fecha_hora': f'{today}T00:00:00', 'hra': 0, 'expected': 'KEEP (today hour 0)'},
    {'fecha_hora': f'{today}T10:00:00', 'hra': 10, 'expected': 'KEEP (today hour 10)'},
    {'fecha_hora': f'{today}T17:00:00', 'hra': 17, 'expected': 'KEEP (today hour 17 = current)'},
    {'fecha_hora': f'{today}T18:00:00', 'hra': 18, 'expected': 'DISCARD (today hour 18 > current)'},
    {'fecha_hora': f'{today}T23:00:00', 'hra': 23, 'expected': 'DISCARD (today hour 23 > current)'},
]

print("Testing hour filtering logic:")
print("-" * 60)

for record in test_records:
    parsed = parse_historical_record_test(record['fecha_hora'], record['hra'])
    
    # Apply filtering logic
    keep = False
    reason = ""
    
    if parsed['date'] == yesterday and parsed['hour'] > now.hour:
        keep = True
        reason = f"Yesterday hour {parsed['hour']} > current {now.hour}"
    elif parsed['date'] == today and parsed['hour'] <= now.hour:
        keep = True
        reason = f"Today hour {parsed['hour']} <= current {now.hour}"
    else:
        reason = f"Filtered out: date={parsed['date']}, hour={parsed['hour']}"
    
    status = "✅ KEEP" if keep else "❌ DISCARD"
    print(f"{status}: {parsed['datetime']} | {reason}")
    print(f"         Expected: {record['expected']}")
    print()

# Summary
hours_from_yesterday = [h for h in range(24) if h > now.hour]
hours_from_today = [h for h in range(24) if h <= now.hour]

print("-" * 60)
print(f"Hours from yesterday ({yesterday}): {hours_from_yesterday}")
print(f"Count: {len(hours_from_yesterday)}")
print()
print(f"Hours from today ({today}): {hours_from_today}")
print(f"Count: {len(hours_from_today)}")
print()
print(f"Total hours: {len(hours_from_yesterday) + len(hours_from_today)} (should be 24)")