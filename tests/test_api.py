"""
Test the predictions API locally
"""
import sys
import json
from datetime import datetime
from api.predictions import handler
from http.server import BaseHTTPRequestHandler

class MockRequest(BaseHTTPRequestHandler):
    def __init__(self):
        self.wfile = MockWriter()
        self.rfile = None
        
    def send_response(self, code):
        print(f"Response: {code}")
        
    def send_header(self, key, value):
        print(f"Header: {key}: {value}")
        
    def end_headers(self):
        print("---")

class MockWriter:
    def write(self, data):
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        result = json.loads(data)
        print(json.dumps(result, indent=2))

# Test the handler
print("Testing predictions API...")
h = handler()
h.__class__ = type('TestHandler', (handler,), {})
h.wfile = MockWriter()

# Mock the methods
h.send_response = lambda code: print(f"Response: {code}")
h.send_header = lambda key, value: print(f"Header: {key}: {value}")
h.end_headers = lambda: print("---")

# Call the GET method
h.do_GET()