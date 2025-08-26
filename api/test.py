"""
Ultra-minimal test endpoint for Vercel
"""

def handler(request):
    """Simplest possible handler that works"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': '{"success": true, "message": "API is working!", "predictions": [{"hour": 0, "cmg_predicted": 60.0}]}'
    }