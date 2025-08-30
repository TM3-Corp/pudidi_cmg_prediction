#!/usr/bin/env python3
"""Test the main production API locally"""

import sys
import json
from http.server import HTTPServer
from threading import Thread
import requests
import time

sys.path.append('.')
from api.index import handler

def run_server():
    server = HTTPServer(('localhost', 8888), handler)
    server.timeout = 5
    server.handle_request()

# Start server in background
thread = Thread(target=run_server)
thread.start()

# Wait for server to start
time.sleep(1)

try:
    # Make request
    response = requests.get('http://localhost:8888/')
    data = response.json()
    
    print("✅ API Response:")
    print(f"  Status Code: {response.status_code}")
    print(f"  Success: {data.get('success')}")
    print(f"  Data Source: {data.get('data_source')}")
    print(f"  Location: {data.get('location')}")
    print(f"  Node: {data.get('node')}")
    
    stats = data.get('stats', {})
    print(f"\n📊 Stats:")
    print(f"  Average Value: ${stats.get('avg_value')}")
    print(f"  Last Value: ${stats.get('last_value')}")
    print(f"  Total Predictions: {stats.get('predictions_count')}")
    print(f"  Historical Data Points: {stats.get('historical_count')}")
    print(f"  Future Predictions: {stats.get('future_count')}")
    
    fetch_info = data.get('fetch_info', {})
    if fetch_info:
        print(f"\n🔍 Fetch Info:")
        print(f"  Pages Fetched: {fetch_info.get('pages_fetched')}")
        print(f"  Records Found: {fetch_info.get('records_found')}")
        print(f"  Date Fetched: {fetch_info.get('date_fetched')}")
    
    # Show sample predictions
    predictions = data.get('predictions', [])
    if predictions:
        print(f"\n📈 Sample Predictions (showing first 3):")
        for pred in predictions[:3]:
            if pred.get('is_historical'):
                print(f"  [{pred.get('datetime')}] Historical: ${pred.get('cmg_actual')}")
            elif pred.get('is_prediction'):
                print(f"  [{pred.get('datetime')}] Predicted: ${pred.get('cmg_predicted')} [{pred.get('confidence_lower')}-{pred.get('confidence_upper')}]")
    
except Exception as e:
    print(f"❌ Error: {e}")

thread.join()