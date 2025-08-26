"""Quick test of the API"""
import sys
import os
import json
from datetime import datetime
import pytz

# Mock the handler class
class TestHandler:
    def __init__(self):
        self.response_code = None
        self.headers = {}
        self.body = None
        
    def send_response(self, code):
        self.response_code = code
        
    def send_header(self, key, value):
        self.headers[key] = value
        
    def end_headers(self):
        pass
        
    class WFile:
        def __init__(self):
            self.data = []
        def write(self, data):
            self.data.append(data)

# Import and test
from api.predictions import handler

# Create instance properly
h = type('TestHandler', (handler,), {})()
h.wfile = TestHandler.WFile()
h.send_response = lambda code: print(f"Response: {code}")
h.send_header = lambda k, v: None
h.end_headers = lambda: None

try:
    h.do_GET()
    
    if h.wfile.data:
        result = json.loads(h.wfile.data[0])
        print(f"Success: {result['success']}")
        if 'stats' in result:
            print(f"Data points: {result['stats'].get('data_points', 0)}")
            print(f"Method: {result['stats'].get('method', 'Unknown')}")
        if 'predictions' in result:
            print(f"Total predictions: {len(result['predictions'])}")
            # Check for historical vs predictions
            historical = [p for p in result['predictions'] if p.get('is_historical')]
            predicted = [p for p in result['predictions'] if p.get('is_prediction') or p.get('cmg_predicted')]
            print(f"Historical points: {len(historical)}")
            print(f"Predicted points: {len(predicted)}")
    else:
        print("No data returned")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()