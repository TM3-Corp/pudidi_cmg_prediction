#!/usr/bin/env python3
"""
Supabase Client for CMG Prediction System
=========================================

Provides a simple interface for Python scripts to write data to Supabase.

Usage:
    from supabase_client import get_supabase_client

    supabase = get_supabase_client()
    if supabase:
        supabase.table('cmg_online').insert([{...}]).execute()
"""

import os
from typing import Optional
from supabase import create_client, Client

def get_supabase_client() -> Optional[Client]:
    """
    Get authenticated Supabase client using environment variables.

    Looks for:
    - SUPABASE_URL: Your project URL (e.g., https://xxx.supabase.co)
    - SUPABASE_SERVICE_KEY: Service role key (not anon key!)

    Returns:
        Client if credentials are found, None otherwise
    """
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY')

    if not url:
        print("⚠️  SUPABASE_URL not found in environment")
        return None

    if not key:
        print("⚠️  SUPABASE_SERVICE_KEY not found in environment")
        return None

    try:
        client = create_client(url, key)
        return client
    except Exception as e:
        print(f"❌ Error creating Supabase client: {e}")
        return None


def test_connection():
    """Test Supabase connection by counting rows in each table"""
    client = get_supabase_client()

    if not client:
        print("❌ Could not connect to Supabase")
        return False

    print("✅ Supabase client created successfully")
    print(f"   URL: {os.environ.get('SUPABASE_URL')}")

    # Test each table
    tables = ['cmg_online', 'cmg_programado', 'ml_predictions']

    for table in tables:
        try:
            result = client.table(table).select('id', count='exact').limit(0).execute()
            count = result.count if hasattr(result, 'count') else 'unknown'
            print(f"✅ {table}: {count} rows")
        except Exception as e:
            print(f"❌ Error querying {table}: {e}")
            return False

    return True


if __name__ == "__main__":
    # Run connection test if executed directly
    print("="*60)
    print("SUPABASE CONNECTION TEST")
    print("="*60)
    test_connection()
