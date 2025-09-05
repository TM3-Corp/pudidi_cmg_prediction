#!/usr/bin/env python3
"""
Update all script files with new Gist IDs from configuration
"""

import json
import re
import os

def update_file(filepath, pattern, replacement):
    """Update a file with regex replacement"""
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    new_content = re.sub(pattern, replacement, content)
    
    if content != new_content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        return True
    return False

def main():
    """Main execution"""
    # Read configuration
    if not os.path.exists('gist_configuration.json'):
        print("❌ Configuration file not found")
        return 1
    
    with open('gist_configuration.json', 'r') as f:
        config = json.load(f)
    
    gists = config.get('gists', {})
    
    print("📝 Updating scripts with new Gist IDs...")
    
    # Update CMG Programado script
    if 'cmg_programado' in gists:
        gist_id = gists['cmg_programado']['id']
        print(f"\n1. CMG Programado Gist ID: {gist_id}")
        
        if update_file(
            'scripts/update_cmg_programado.py',
            r'GIST_ID = ["\']\w+["\']',
            f'GIST_ID = "{gist_id}"'
        ):
            print("   ✅ Updated scripts/update_cmg_programado.py")
        else:
            print("   ℹ️ No changes needed")
    
    # Update optimizer
    if 'optimization' in gists:
        gist_id = gists['optimization']['id']
        print(f"\n2. Optimization Gist ID: {gist_id}")
        
        if update_file(
            'api/optimizer.py',
            r'OPTIMIZATION_GIST_ID = ["\']\w+["\']',
            f'OPTIMIZATION_GIST_ID = "{gist_id}"'
        ):
            print("   ✅ Updated api/optimizer.py")
        else:
            print("   ℹ️ No changes needed")
    
    # Update performance calculator
    if 'optimization' in gists and 'performance' in gists:
        opt_id = gists['optimization']['id']
        perf_id = gists['performance']['id']
        print(f"\n3. Performance Calculator:")
        print(f"   Optimization ID: {opt_id}")
        print(f"   Performance ID: {perf_id}")
        
        updated = False
        if update_file(
            'scripts/daily_performance_calculation.py',
            r'OPTIMIZATION_GIST = ["\']\w+["\']',
            f'OPTIMIZATION_GIST = "{opt_id}"'
        ):
            updated = True
        
        if update_file(
            'scripts/daily_performance_calculation.py',
            r'PERFORMANCE_GIST = ["\']\w+["\']',
            f'PERFORMANCE_GIST = "{perf_id}"'
        ):
            updated = True
        
        if updated:
            print("   ✅ Updated scripts/daily_performance_calculation.py")
        else:
            print("   ℹ️ No changes needed")
    
    # Update performance.py
    if 'optimization' in gists:
        gist_id = gists['optimization']['id']
        print(f"\n4. Performance API:")
        
        if update_file(
            'api/performance.py',
            r'gist_id = ["\']\w+["\']',
            f'gist_id = "{gist_id}"'
        ):
            print("   ✅ Updated api/performance.py")
        else:
            print("   ℹ️ No changes needed")
    
    print("\n✅ All scripts updated successfully!")
    return 0

if __name__ == "__main__":
    exit(main())