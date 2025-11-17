"""
Debug endpoint to test Supabase queries directly
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from lib.utils.supabase_client import SupabaseClient
    USE_SUPABASE = True
except Exception as e:
    USE_SUPABASE = False
    error_msg = str(e)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Test Supabase queries"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        result = {
            "supabase_available": USE_SUPABASE,
            "tests": []
        }

        if not USE_SUPABASE:
            result["error"] = error_msg
            self.wfile.write(json.dumps(result).encode())
            return

        try:
            supabase = SupabaseClient()
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)

            # Test 1: Query without any filters
            test1_records = supabase.get_cmg_online(limit=5)
            result["tests"].append({
                "name": "Query with no filters (limit 5)",
                "count": len(test1_records),
                "sample": test1_records[:2] if test1_records else []
            })

            # Test 2: Query with start_date only
            start_date = str(now.date() - timedelta(days=7))
            test2_records = supabase.get_cmg_online(start_date=start_date, limit=5)
            result["tests"].append({
                "name": f"Query with start_date={start_date} (limit 5)",
                "count": len(test2_records),
                "sample": test2_records[:2] if test2_records else []
            })

            # Test 3: Query with both start_date and end_date
            end_date = str(now.date())
            test3_records = supabase.get_cmg_online(
                start_date=start_date,
                end_date=end_date,
                limit=5
            )
            result["tests"].append({
                "name": f"Query with start_date={start_date}, end_date={end_date} (limit 5)",
                "count": len(test3_records),
                "sample": test3_records[:2] if test3_records else []
            })

            # Test 4: Check CMG Programado for comparison
            test4_records = supabase.get_cmg_programado(limit=5)
            result["tests"].append({
                "name": "CMG Programado query (limit 5)",
                "count": len(test4_records),
                "sample": test4_records[:2] if test4_records else []
            })

            result["success"] = True
            result["current_time"] = now.isoformat()

        except Exception as e:
            result["error"] = str(e)
            import traceback
            result["traceback"] = traceback.format_exc()

        self.wfile.write(json.dumps(result, default=str, indent=2).encode())
