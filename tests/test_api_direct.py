"""Direct test of the predictions API without HTTP server"""
import sys
from datetime import datetime
import pytz
import json

# Import the handler directly
from api.predictions import handler

# Create a minimal instance for testing
class TestHandler(handler):
    def __init__(self):
        self.path = "/api/predictions?force=true"
        self.responses = []
        self.headers = {}
        self.body = None
        
    def send_response(self, code):
        self.responses.append(code)
        print(f"HTTP Response Code: {code}")
        
    def send_header(self, key, value):
        self.headers[key] = value
        
    def end_headers(self):
        pass
        
    class WFile:
        def __init__(self):
            self.data = []
        def write(self, data):
            self.data.append(data)
    
    def test_fetch(self):
        """Test the fetch_last_24h_cmg method directly"""
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        print(f"\n{'='*60}")
        print(f"DIRECT TEST at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"{'='*60}")
        
        # Test fetching directly
        data = self.fetch_last_24h_cmg()
        
        print(f"\n📊 RESULT:")
        print(f"  Data points fetched: {len(data)}")
        if data:
            print(f"  First: {data[0]}")
            print(f"  Last: {data[-1]}")
        
        return data

# Run the test
if __name__ == "__main__":
    print("Testing predictions API directly...")
    
    h = TestHandler()
    
    # Test direct fetch first
    print("\n1. Testing direct data fetch:")
    data = h.test_fetch()
    
    # Now test full API
    print("\n2. Testing full API endpoint:")
    h.wfile = TestHandler.WFile()
    
    try:
        h.do_GET()
        
        if h.wfile.data:
            result = json.loads(h.wfile.data[0])
            print(f"\n✅ API Success: {result['success']}")
            if 'stats' in result:
                stats = result['stats']
                print(f"\n📈 Statistics:")
                print(f"  Data points: {stats.get('data_points', 0)}")
                print(f"  Source data count: {stats.get('source_data_count', 0)}")
                print(f"  Method: {stats.get('method', 'Unknown')}")
                print(f"  Actual points (24h): {stats.get('actual_points_24h', 0)}")
                print(f"  Missing points: {stats.get('missing_points_24h', 0)}")
            if 'predictions' in result:
                preds = result['predictions']
                historical = [p for p in preds if p.get('is_historical')]
                predicted = [p for p in preds if p.get('is_prediction') or p.get('cmg_predicted')]
                print(f"\n📊 Data breakdown:")
                print(f"  Total items: {len(preds)}")
                print(f"  Historical: {len(historical)}")
                print(f"  Predicted: {len(predicted)}")
        else:
            print("❌ No data returned")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()