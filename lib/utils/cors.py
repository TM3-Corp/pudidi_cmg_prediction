"""
CORS Utility for API Endpoints
==============================

Provides standardized CORS headers for API responses.
Restricts access to production domain and localhost for development.
"""

import os

# Allowed origins - production domain and localhost for development
ALLOWED_ORIGINS = [
    'https://pudidicmgprediction.vercel.app',
    'https://pudidi-cmg-prediction.vercel.app',
    'http://localhost:3000',
    'http://localhost:5000',
    'http://127.0.0.1:3000',
    'http://127.0.0.1:5000',
]

# Environment override for additional origins
EXTRA_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
ALLOWED_ORIGINS.extend([o.strip() for o in EXTRA_ORIGINS if o.strip()])


def get_cors_origin(request_origin: str = None) -> str:
    """
    Get the CORS origin header value based on the request origin.

    Args:
        request_origin: The Origin header from the request

    Returns:
        The origin to allow, or the first allowed origin if request origin not allowed
    """
    if request_origin and request_origin in ALLOWED_ORIGINS:
        return request_origin
    # Default to production domain
    return ALLOWED_ORIGINS[0]


def add_cors_headers(handler, request_origin: str = None, methods: str = 'GET, OPTIONS'):
    """
    Add CORS headers to response.

    Args:
        handler: HTTP request handler
        request_origin: The Origin header from the request (optional)
        methods: Allowed HTTP methods
    """
    origin = get_cors_origin(request_origin)

    handler.send_header('Access-Control-Allow-Origin', origin)
    handler.send_header('Access-Control-Allow-Methods', methods)
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    handler.send_header('Access-Control-Allow-Credentials', 'true')


def send_cors_preflight(handler, methods: str = 'GET, OPTIONS'):
    """
    Send CORS preflight response.

    Args:
        handler: HTTP request handler
        methods: Allowed HTTP methods
    """
    request_origin = handler.headers.get('Origin', '')

    handler.send_response(200)
    add_cors_headers(handler, request_origin, methods)
    handler.end_headers()
