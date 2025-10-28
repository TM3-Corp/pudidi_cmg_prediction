#!/usr/bin/env python3
"""
Test Supabase Connection
========================
Quick test to verify Supabase credentials and connectivity
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from api.utils.supabase_client import SupabaseClient
    
    print("="*60)
    print("TESTING SUPABASE CONNECTION")
    print("="*60)
    
    # Check environment variables
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY')
    
    print(f"\n✅ SUPABASE_URL: {url[:50]}..." if url else "❌ SUPABASE_URL: NOT SET")
    print(f"✅ SUPABASE_SERVICE_KEY: {key[:20]}..." if key else "❌ SUPABASE_SERVICE_KEY: NOT SET")
    
    if not url or not key:
        print("\n❌ Missing environment variables!")
        print("\nSet them with:")
        print("export SUPABASE_URL=https://btyfbrclgmphcjgrvcgd.supabase.co")
        print("export SUPABASE_SERVICE_KEY=your_service_role_key")
        sys.exit(1)
    
    # Initialize client
    print("\n📡 Initializing Supabase client...")
    client = SupabaseClient()
    print("✅ Client initialized")
    
    # Test read access to each table
    print("\n🔍 Testing read access...")
    
    print("  - cmg_online table: ", end="")
    records = client.get_cmg_online(limit=1)
    print(f"✅ ({len(records)} records)" if isinstance(records, list) else "❌ Failed")
    
    print("  - cmg_programado table: ", end="")
    records = client.get_cmg_programado(limit=1)
    print(f"✅ ({len(records)} records)" if isinstance(records, list) else "❌ Failed")
    
    print("  - ml_predictions table: ", end="")
    records = client.get_latest_ml_predictions(limit=1)
    print(f"✅ ({len(records)} records)" if isinstance(records, list) else "❌ Failed")
    
    print("\n" + "="*60)
    print("🎉 CONNECTION TEST SUCCESSFUL!")
    print("="*60)
    print("\nNext step: Run migration script to import data")
    print("  python scripts/migrate_to_supabase.py")
    
except Exception as e:
    print(f"\n❌ Connection test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
