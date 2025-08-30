#!/usr/bin/env python3
"""
Deployment Verification Script
Checks that all components are ready for Vercel deployment
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import pytz

def check_cache_files():
    """Verify cache files exist and are valid"""
    cache_dir = Path("data/cache")
    required_files = [
        "cmg_historical_latest.json",
        "cmg_programmed_latest.json", 
        "metadata.json"
    ]
    
    print("🔍 Checking cache files...")
    all_good = True
    
    for file in required_files:
        file_path = cache_dir / file
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    records = len(data.get('data', []))
                    print(f"  ✅ {file}: {records} records")
            except Exception as e:
                print(f"  ❌ {file}: Invalid JSON - {e}")
                all_good = False
        else:
            print(f"  ❌ {file}: Missing")
            all_good = False
    
    return all_good

def check_api_endpoints():
    """Verify all API endpoints exist"""
    api_dir = Path("api/cmg")
    required_endpoints = ["current.py", "status.py", "refresh.py"]
    
    print("\n🔍 Checking API endpoints...")
    all_good = True
    
    for endpoint in required_endpoints:
        file_path = api_dir / endpoint
        if file_path.exists():
            # Check if it uses the read-only cache manager
            with open(file_path, 'r') as f:
                content = f.read()
                if "CacheManagerReadOnly" in content:
                    print(f"  ✅ {endpoint}: Uses read-only cache")
                else:
                    print(f"  ⚠️  {endpoint}: May not use read-only cache")
        else:
            print(f"  ❌ {endpoint}: Missing")
            all_good = False
    
    return all_good

def check_frontend():
    """Verify frontend files exist"""
    public_dir = Path("public")
    required_files = ["index_new.html"]
    
    print("\n🔍 Checking frontend...")
    all_good = True
    
    for file in required_files:
        file_path = public_dir / file
        if file_path.exists():
            print(f"  ✅ {file}: Found")
        else:
            print(f"  ❌ {file}: Missing")
            all_good = False
    
    return all_good

def check_vercel_config():
    """Verify Vercel configuration"""
    print("\n🔍 Checking Vercel configuration...")
    
    vercel_json = Path("vercel.json")
    if vercel_json.exists():
        with open(vercel_json, 'r') as f:
            config = json.load(f)
            if "functions" in config:
                print(f"  ✅ vercel.json: Configured with functions")
            else:
                print(f"  ⚠️  vercel.json: No functions configured")
    else:
        print(f"  ❌ vercel.json: Missing")
        return False
    
    return True

def check_github_actions():
    """Check GitHub Actions workflow"""
    workflow_path = Path(".github/workflows/hourly_update.yml")
    
    print("\n🔍 Checking GitHub Actions...")
    if workflow_path.exists():
        print(f"  ✅ hourly_update.yml: Found")
        print(f"     ⏰ Runs every hour at minute 5")
        return True
    else:
        print(f"  ⚠️  hourly_update.yml: Not found (optional)")
        return True

def main():
    """Run all checks"""
    print("=" * 50)
    print("🚀 CMG MONITOR DEPLOYMENT VERIFICATION")
    print("=" * 50)
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    print(f"\n📅 Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')} (Santiago)")
    
    checks = [
        check_cache_files(),
        check_api_endpoints(),
        check_frontend(),
        check_vercel_config(),
        check_github_actions()
    ]
    
    print("\n" + "=" * 50)
    if all(checks):
        print("✅ ALL CHECKS PASSED - Ready to deploy!")
        print("\nNext steps:")
        print("1. git add -A")
        print("2. git commit -m 'Deploy with read-only filesystem support'")
        print("3. git push origin main")
        print("4. npx vercel --prod")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Review issues above")
        print("\nRun 'python scripts/init_cache.py' if cache is missing")
        return 1

if __name__ == "__main__":
    sys.exit(main())