"""
Minimal test endpoint
"""
import json
from datetime import datetime

def handler(request):
    """Test endpoint"""
    result = {
        "status": "ok",
        "message": "API is working!",
        "timestamp": str(datetime.now())
    }
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(result)
    }