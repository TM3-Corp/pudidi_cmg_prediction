#!/usr/bin/env python3
"""
Test script for CMG download with timeout and immediate output
"""
import sys
import asyncio
from scripts.download_cmg_en_linea_final import run, santiago_tz, datetime

async def test_with_timeout():
    """Run download with timeout"""
    print("Starting download test...", flush=True)
    try:
        # Run with 30 second timeout
        result = await asyncio.wait_for(run(), timeout=30)
        if result:
            print(f"\n✅ SUCCESS! Downloaded: {result}", flush=True)
            return True
        else:
            print("\n❌ Download returned None", flush=True)
            return False
    except asyncio.TimeoutError:
        print("\n⏱️ TIMEOUT after 30 seconds", flush=True)
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("="*60, flush=True)
    print("CMG DOWNLOAD QUICK TEST", flush=True)
    print("="*60, flush=True)
    print(f"Time: {datetime.now(santiago_tz)}", flush=True)
    print("", flush=True)
    
    success = asyncio.run(test_with_timeout())
    sys.exit(0 if success else 1)