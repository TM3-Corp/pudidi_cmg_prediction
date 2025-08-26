#!/usr/bin/env python3
"""Test the live API locally"""

import sys
sys.path.append('.')

from api.predictions_live import handler
import json

# Mock request object
class MockRequest:
    pass

# Test the handler
request = MockRequest()
response = handler(request)

print("Status Code:", response['statusCode'])
print("Headers:", response['headers'])
print("\nResponse Body:")

# Parse and pretty print the body
body = json.loads(response['body'])
print(json.dumps(body, indent=2))

# Check key fields
print("\n=== Summary ===")
print(f"Success: {body.get('success')}")
print(f"Data Source: {body.get('data_source')}")
print(f"Predictions Count: {len(body.get('predictions', []))}")
if body.get('stats'):
    print(f"Average Value: {body['stats'].get('avg_value')}")