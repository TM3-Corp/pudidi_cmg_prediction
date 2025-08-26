#!/usr/bin/env python3
"""
Test the predictions_from_db.py API
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.predictions_from_db import handler
import json
from unittest.mock import Mock

def test_api():
    """Test the API handler"""
    print("Testing predictions_from_db.py API...")
    print("="*60)
    
    # Create a simple mock handler
    class TestHandler:
        def __init__(self):
            self.response_code = None
            self.headers = {}
            self.response_data = []
            
        def send_response(self, code):
            self.response_code = code
            
        def send_header(self, key, value):
            self.headers[key] = value
            
        def end_headers(self):
            pass
            
        class WFile:
            def __init__(self, handler):
                self.handler = handler
            def write(self, data):
                self.handler.response_data.append(data)
        
        def get_database_connection(self):
            import sqlite3
            return sqlite3.connect('cmg_data.db')
        
        def get_latest_cmg_data(self):
            # Use the actual method from handler
            return handler.get_latest_cmg_data(self)
        
        def get_latest_weather_data(self):
            return handler.get_latest_weather_data(self)
        
        def get_data_completeness(self):
            return handler.get_data_completeness(self)
        
        def generate_predictions(self, *args):
            return handler.generate_predictions(self, *args)
        
        def format_historical_display(self, *args):
            return handler.format_historical_display(self, *args)
    
    # Create test handler
    test_handler = TestHandler()
    test_handler.wfile = TestHandler.WFile(test_handler)
    
    # Call the handler's do_GET method
    try:
        handler.do_GET(test_handler)
        
        # Parse response
        if test_handler.response_data:
            response = json.loads(test_handler.response_data[0].decode())
            
            print(f"Success: {response.get('success')}")
            print(f"Location: {response.get('location')}")
            print(f"Node: {response.get('node')}")
            print(f"Data source: {response.get('data_source')}")
            
            stats = response.get('stats', {})
            print("\nStatistics:")
            print(f"  Last actual: {stats.get('last_actual')}")
            print(f"  Data points: {stats.get('data_points')}")
            print(f"  24h average: {stats.get('avg_24h')}")
            print(f"  48h max: {stats.get('max_48h')}")
            print(f"  48h min: {stats.get('min_48h')}")
            print(f"  Method: {stats.get('method')}")
            
            completeness = stats.get('data_completeness', {})
            if completeness:
                print("\nData Completeness:")
                print(f"  Last fetch: {completeness.get('last_fetch_date')}")
                print(f"  Hours covered: {completeness.get('hours_covered')}/24")
                print(f"  Fetch time: {completeness.get('fetch_time')}s")
            
            predictions = response.get('predictions', [])
            print(f"\nTotal predictions: {len(predictions)}")
            
            # Show sample predictions
            if predictions:
                print("\nSample predictions (first 5):")
                for i, pred in enumerate(predictions[:5]):
                    if pred.get('is_historical'):
                        print(f"  {i+1}. {pred['datetime']} - Hour {pred['hour']:2d}: Actual = {pred.get('cmg_actual', 'N/A')}")
                    else:
                        print(f"  {i+1}. {pred['datetime']} - Hour {pred['hour']:2d}: Predicted = {pred.get('cmg_predicted', 'N/A'):.1f}")
            
            print("\n✅ API test successful!")
            
        else:
            print("❌ No response data received")
            
    except Exception as e:
        print(f"❌ Error testing API: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api()