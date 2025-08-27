#!/usr/bin/env python3
"""
System Health Check Script
Tests all API endpoints and verifies system is operational
Can be used locally or against deployed Vercel app
"""

import requests
import json
import sys
from datetime import datetime
import pytz
from typing import Dict, Tuple
import argparse

def test_endpoint(base_url: str, endpoint: str) -> Tuple[bool, Dict]:
    """Test a single endpoint"""
    url = f"{base_url}/api/cmg/{endpoint}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return response.status_code == 200 and data.get('success', False), data
    except Exception as e:
        return False, {"error": str(e)}

def check_status(base_url: str) -> bool:
    """Check system status endpoint"""
    print("\n📊 Testing /api/cmg/status...")
    success, data = test_endpoint(base_url, "status")
    
    if success:
        system = data.get('system', {})
        caches = data.get('caches', {})
        
        print(f"  ✅ Status: {system.get('status', 'unknown')}")
        print(f"  📈 System ready: {system.get('ready', False)}")
        print(f"  🔄 Needs update: {system.get('needs_update', False)}")
        
        # Check cache ages
        hist = caches.get('historical', {})
        prog = caches.get('programmed', {})
        
        print(f"\n  📁 Historical Cache:")
        print(f"     - Exists: {hist.get('exists', False)}")
        print(f"     - Age: {hist.get('age_display', 'unknown')}")
        print(f"     - Records: {hist.get('records', 0)}")
        
        print(f"\n  📁 Programmed Cache:")
        print(f"     - Exists: {prog.get('exists', False)}")
        print(f"     - Age: {prog.get('age_display', 'unknown')}")
        print(f"     - Records: {prog.get('records', 0)}")
        
        return True
    else:
        print(f"  ❌ Failed: {data.get('error', 'Unknown error')}")
        return False

def check_current(base_url: str) -> bool:
    """Check current data endpoint"""
    print("\n📊 Testing /api/cmg/current...")
    success, data = test_endpoint(base_url, "current")
    
    if success:
        cmg_data = data.get('data', {})
        hist = cmg_data.get('historical', {})
        prog = cmg_data.get('programmed', {})
        
        print(f"  ✅ Data retrieved successfully")
        print(f"  📈 Historical records: {len(hist.get('data', []))}")
        print(f"  📈 Programmed records: {len(prog.get('data', []))}")
        print(f"  🎯 Coverage: {hist.get('coverage', 0):.1f}%")
        
        # Show sample data
        if hist.get('data'):
            latest = hist['data'][-1]
            print(f"\n  📍 Latest Historical Data:")
            print(f"     - Time: {latest.get('hora', 'N/A')}")
            chiloe_value = latest.get('CHILOE________220', {}).get('cmg', 'N/A')
            if isinstance(chiloe_value, (int, float)):
                print(f"     - CHILOE_220: ${chiloe_value:.2f}")
            else:
                print(f"     - CHILOE_220: {chiloe_value}")
        
        return True
    else:
        print(f"  ❌ Failed: {data.get('error', 'Unknown error')}")
        return False

def check_refresh(base_url: str) -> bool:
    """Check refresh endpoint"""
    print("\n📊 Testing /api/cmg/refresh...")
    success, data = test_endpoint(base_url, "refresh")
    
    if success:
        print(f"  ✅ Refresh endpoint operational")
        print(f"  🔄 Needs refresh: {data.get('needs_refresh', False)}")
        
        if data.get('reason'):
            print(f"  📝 Reason: {', '.join(data['reason'])}")
        
        print(f"  ⏰ Next update: {data.get('next_update', 'N/A')}")
        print(f"  🌍 Environment: {data.get('environment', 'unknown')}")
        
        return True
    else:
        print(f"  ❌ Failed: {data.get('error', 'Unknown error')}")
        return False

def check_frontend(base_url: str) -> bool:
    """Check if frontend is accessible"""
    print("\n📊 Testing Frontend...")
    
    # Test new dashboard
    try:
        response = requests.get(f"{base_url}/index_new.html", timeout=10)
        if response.status_code == 200:
            print(f"  ✅ Dashboard accessible at /index_new.html")
            print(f"  📏 Page size: {len(response.content) / 1024:.1f} KB")
            return True
        else:
            print(f"  ❌ Dashboard returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Failed to access dashboard: {e}")
        return False

def main():
    """Run all health checks"""
    parser = argparse.ArgumentParser(description='Check CMG Monitor system health')
    parser.add_argument('--url', default='http://localhost:3000', 
                       help='Base URL (default: http://localhost:3000)')
    parser.add_argument('--deployed', action='store_true',
                       help='Use this flag when testing deployed Vercel app')
    args = parser.parse_args()
    
    base_url = args.url.rstrip('/')
    
    print("=" * 60)
    print("🏥 CMG MONITOR SYSTEM HEALTH CHECK")
    print("=" * 60)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    print(f"\n📅 Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')} (Santiago)")
    print(f"🌐 Testing: {base_url}")
    print(f"🚀 Environment: {'Production (Vercel)' if args.deployed else 'Local Development'}")
    
    # Run all checks
    checks = [
        check_status(base_url),
        check_current(base_url),
        check_refresh(base_url),
        check_frontend(base_url)
    ]
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    
    passed = sum(checks)
    total = len(checks)
    
    if all(checks):
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        print("\n🎉 System is fully operational!")
        
        if args.deployed:
            print("\n📊 Your dashboard is live at:")
            print(f"   {base_url}/index_new.html")
        
        return 0
    else:
        print(f"⚠️  SOME CHECKS FAILED ({passed}/{total})")
        print("\n🔧 Review the errors above and:")
        print("  1. Check if cache files exist")
        print("  2. Verify API endpoints are using CacheManagerReadOnly")
        print("  3. Run 'python scripts/init_cache.py' if needed")
        print("  4. Check Vercel logs for deployment errors")
        return 1

if __name__ == "__main__":
    sys.exit(main())