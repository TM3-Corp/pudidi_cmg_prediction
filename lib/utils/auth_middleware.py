"""
Supabase Auth Middleware
========================

Verifies JWT tokens from Supabase Auth for API endpoint protection.
Requires SUPABASE_JWT_SECRET environment variable to be set.

Usage in API endpoints:

    from lib.utils.auth_middleware import verify_auth, require_auth

    # Option 1: Verify and get user info
    user, error = verify_auth(self)
    if error:
        return send_auth_error(self, error)

    # Option 2: Simple decorator-style check
    if not require_auth(self):
        return  # Already sent 401 response
"""

import os
import json
from typing import Tuple, Optional, Dict, Any


def get_jwt_secret() -> Optional[str]:
    """Get JWT secret from environment"""
    return os.environ.get('SUPABASE_JWT_SECRET')


def verify_auth(handler) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Verify JWT token from Authorization header.

    Args:
        handler: HTTP request handler with headers attribute

    Returns:
        Tuple of (user_payload, error_message)
        - On success: (user_payload, None)
        - On failure: (None, error_message)
    """
    jwt_secret = get_jwt_secret()

    if not jwt_secret:
        return None, 'Server configuration error: JWT secret not set'

    # Get Authorization header
    auth_header = handler.headers.get('Authorization', '')

    if not auth_header:
        return None, 'Missing Authorization header'

    if not auth_header.startswith('Bearer '):
        return None, 'Invalid Authorization header format. Expected: Bearer <token>'

    token = auth_header[7:]  # Remove 'Bearer ' prefix

    if not token:
        return None, 'Empty token'

    try:
        # Import jwt library
        import jwt

        # Decode and verify the token
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=['HS256'],
            audience='authenticated'
        )

        # Check if token has required fields
        if 'sub' not in payload:
            return None, 'Invalid token: missing user ID'

        return payload, None

    except jwt.ExpiredSignatureError:
        return None, 'Token has expired'
    except jwt.InvalidAudienceError:
        return None, 'Invalid token audience'
    except jwt.InvalidTokenError as e:
        return None, f'Invalid token: {str(e)}'
    except ImportError:
        # PyJWT not installed - fallback to basic validation
        return _verify_token_basic(token, jwt_secret)
    except Exception as e:
        return None, f'Token verification failed: {str(e)}'


def _verify_token_basic(token: str, secret: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Basic token validation without PyJWT library.
    Only verifies structure, not cryptographic signature.
    Use PyJWT for production.
    """
    import base64

    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None, 'Invalid token structure'

        # Decode payload (middle part)
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding

        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)

        # Check expiration
        import time
        exp = payload.get('exp', 0)
        if exp < time.time():
            return None, 'Token has expired'

        # Check audience
        aud = payload.get('aud', '')
        if aud != 'authenticated':
            return None, 'Invalid token audience'

        # Note: This does NOT verify the signature!
        # Install PyJWT for proper verification
        return payload, None

    except Exception as e:
        return None, f'Token parsing failed: {str(e)}'


def require_auth(handler) -> bool:
    """
    Check authentication and send 401 if not authenticated.

    Args:
        handler: HTTP request handler

    Returns:
        True if authenticated, False if not (and 401 response already sent)
    """
    user, error = verify_auth(handler)

    if error:
        send_auth_error(handler, error)
        return False

    # Store user info on handler for later use
    handler.auth_user = user
    return True


def send_auth_error(handler, message: str, status_code: int = 401):
    """
    Send authentication error response.

    Args:
        handler: HTTP request handler
        message: Error message
        status_code: HTTP status code (default 401)
    """
    handler.send_response(status_code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('WWW-Authenticate', 'Bearer')
    handler.end_headers()

    error_response = {
        'success': False,
        'error': 'authentication_required',
        'message': message
    }

    handler.wfile.write(json.dumps(error_response).encode())


def get_user_email(handler) -> Optional[str]:
    """
    Get authenticated user's email.

    Args:
        handler: HTTP request handler (after require_auth)

    Returns:
        User email or None
    """
    if hasattr(handler, 'auth_user') and handler.auth_user:
        return handler.auth_user.get('email')
    return None


def get_user_id(handler) -> Optional[str]:
    """
    Get authenticated user's ID.

    Args:
        handler: HTTP request handler (after require_auth)

    Returns:
        User ID (sub) or None
    """
    if hasattr(handler, 'auth_user') and handler.auth_user:
        return handler.auth_user.get('sub')
    return None
