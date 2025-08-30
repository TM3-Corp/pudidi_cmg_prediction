"""Test improved API"""
import json
from api.predictions import handler

class TestHandler(handler):
    def __init__(self):
        self.path = "/api/predictions?force=true"
        self.responses = []
        self.headers = {}
        
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

# Run test
print("Testing improved predictions API...")
h = TestHandler()
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
            print(f"  Method: {stats.get('method', 'Unknown')}")
            print(f"  Last actual: ${stats.get('last_actual', 'N/A')}")
            print(f"  Avg next 24h: ${stats.get('avg_24h', 'N/A')}")
            
        if 'predictions' in result:
            preds = result['predictions']
            historical = [p for p in preds if p.get('is_historical')]
            predicted = [p for p in preds if p.get('is_prediction')]
            print(f"\n📊 Data breakdown:")
            print(f"  Historical (last 24h): {len(historical)} points")
            print(f"  Predictions (next 48h): {len(predicted)} points")
            
            # Show sample predictions
            if predicted:
                print(f"\n🔮 First 5 predictions:")
                for p in predicted[:5]:
                    print(f"  {p['datetime']}: ${p['cmg_predicted']}")
                    
    else:
        print("❌ No data returned")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()