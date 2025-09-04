#!/usr/bin/env python3
"""
Test all performance tracking systems manually
This allows you to verify everything works before waiting for scheduled runs
"""

import os
import sys
import json
import asyncio
import subprocess
from datetime import datetime
import pytz

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def check_environment():
    """Check environment setup"""
    print_section("ENVIRONMENT CHECK")
    
    # Check for GitHub token
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        print("✅ GITHUB_TOKEN is set")
        # Mask the token for security
        print(f"   Token: {token[:10]}...{token[-4:] if len(token) > 14 else '***'}")
    else:
        print("⚠️  GITHUB_TOKEN not set")
        print("   You can set it with: export GITHUB_TOKEN='your_token_here'")
        print("   Or the scripts will use GitHub Actions token when run in CI")
    
    # Check Python packages
    required_packages = ['requests', 'pytz', 'numpy', 'playwright']
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} is installed")
        except ImportError:
            missing.append(package)
            print(f"❌ {package} is NOT installed")
    
    if missing:
        print(f"\n⚠️  Install missing packages with: pip install {' '.join(missing)}")
        if 'playwright' in missing:
            print("   Also run: playwright install chromium")
    
    return len(missing) == 0

def test_cmg_programado():
    """Test CMG Programado download and storage"""
    print_section("TEST 1: CMG PROGRAMADO STORAGE")
    
    print("This will:")
    print("1. Download current CMG Programado from Coordinador")
    print("2. Preserve any existing historical data")
    print("3. Update the Gist with merged data")
    print()
    
    response = input("Run CMG Programado update? (y/n): ").strip().lower()
    if response != 'y':
        print("⏭️  Skipping CMG Programado test")
        return False
    
    try:
        # Run the CMG Programado update script
        result = subprocess.run(
            ["python", "scripts/update_cmg_programado.py"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("✅ CMG Programado update completed successfully")
            print("\nOutput:")
            print(result.stdout)
            
            # Check the Gist
            print("\n📊 Check the updated Gist at:")
            print("   https://gist.github.com/arbanados/a63a3a10479bafcc29e10aaca627bc73")
            return True
        else:
            print("❌ CMG Programado update failed")
            print("Error:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⏱️ CMG Programado update timed out")
        return False
    except Exception as e:
        print(f"❌ Error running CMG Programado update: {e}")
        return False

def test_optimization():
    """Test optimization and storage"""
    print_section("TEST 2: OPTIMIZATION TRIGGER")
    
    print("This will:")
    print("1. Run optimization with current CMG Programado data")
    print("2. Store results to Gist (creating it if needed)")
    print("3. Show optimization metrics")
    print()
    
    response = input("Run optimization? (y/n): ").strip().lower()
    if response != 'y':
        print("⏭️  Skipping optimization test")
        return False
    
    try:
        # Run the optimization trigger script
        result = subprocess.run(
            ["python", "scripts/trigger_optimization.py"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ Optimization completed successfully")
            print("\nOutput:")
            print(result.stdout)
            
            # Extract Gist ID if it was created
            if "Created new" in result.stdout or "Gist" in result.stdout:
                print("\n📊 Check for optimization results Gist in your account:")
                print("   https://gist.github.com/PVSH97")
            return True
        else:
            print("❌ Optimization failed")
            print("Error:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⏱️ Optimization timed out")
        return False
    except Exception as e:
        print(f"❌ Error running optimization: {e}")
        return False

def test_performance_calculation():
    """Test performance calculation"""
    print_section("TEST 3: PERFORMANCE CALCULATION")
    
    print("This will:")
    print("1. Fetch CMG Online data for today")
    print("2. Fetch optimization results")
    print("3. Calculate performance metrics")
    print("4. Store results to Gist (creating it if needed)")
    print()
    
    response = input("Run performance calculation? (y/n): ").strip().lower()
    if response != 'y':
        print("⏭️  Skipping performance calculation")
        return False
    
    try:
        # Run the performance calculation script
        result = subprocess.run(
            ["python", "scripts/daily_performance_calculation.py"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ Performance calculation completed successfully")
            print("\nOutput:")
            print(result.stdout)
            
            # Extract Gist ID if it was created
            if "Created new" in result.stdout or "Gist" in result.stdout:
                print("\n📊 Check for performance metrics Gist in your account:")
                print("   https://gist.github.com/PVSH97")
            return True
        else:
            print("❌ Performance calculation failed")
            print("Error:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⏱️ Performance calculation timed out")
        return False
    except Exception as e:
        print(f"❌ Error running performance calculation: {e}")
        return False

def test_smart_cache():
    """Test smart CMG Online caching"""
    print_section("TEST 4: SMART CMG ONLINE CACHE")
    
    print("This will:")
    print("1. Check existing cache")
    print("2. Fetch only missing data")
    print("3. Show cache efficiency")
    print()
    
    response = input("Run smart cache update? (y/n): ").strip().lower()
    if response != 'y':
        print("⏭️  Skipping smart cache test")
        return False
    
    try:
        # Run the smart cache update script
        result = subprocess.run(
            ["python", "scripts/smart_cmg_online_update.py"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("✅ Smart cache update completed successfully")
            print("\nOutput:")
            print(result.stdout)
            return True
        else:
            print("❌ Smart cache update failed")
            print("Error:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⏱️ Smart cache update timed out")
        return False
    except Exception as e:
        print(f"❌ Error running smart cache update: {e}")
        return False

def summary(results):
    """Print test summary"""
    print_section("TEST SUMMARY")
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()
    
    if results['env_check']:
        print("✅ Environment is ready")
    else:
        print("⚠️  Environment needs setup")
    
    if results['cmg_programado']:
        print("✅ CMG Programado storage is working")
    else:
        print("⚠️  CMG Programado needs attention")
    
    if results['optimization']:
        print("✅ Optimization system is working")
    else:
        print("⚠️  Optimization needs attention")
    
    if results['performance']:
        print("✅ Performance calculation is working")
    else:
        print("⚠️  Performance calculation needs attention")
    
    if results['smart_cache']:
        print("✅ Smart cache is working")
    else:
        print("⚠️  Smart cache needs attention")
    
    print("\n📊 Check your Gists at: https://gist.github.com/PVSH97")
    print("🔍 Look for:")
    print("   - cmg_programado_historical.json (in arbanados account)")
    print("   - optimization_results.json (will be created)")
    print("   - performance_history.json (will be created)")

def main():
    """Main test execution"""
    print_section("PUDIDI PERFORMANCE TRACKING SYSTEM TEST")
    
    results = {
        'env_check': False,
        'cmg_programado': False,
        'optimization': False,
        'performance': False,
        'smart_cache': False
    }
    
    # Check environment
    results['env_check'] = check_environment()
    
    if not results['env_check']:
        print("\n⚠️  Please fix environment issues before continuing")
        response = input("Continue anyway? (y/n): ").strip().lower()
        if response != 'y':
            return 1
    
    # Run tests
    results['cmg_programado'] = test_cmg_programado()
    results['optimization'] = test_optimization()
    results['performance'] = test_performance_calculation()
    results['smart_cache'] = test_smart_cache()
    
    # Show summary
    summary(results)
    
    return 0

if __name__ == "__main__":
    exit(main())