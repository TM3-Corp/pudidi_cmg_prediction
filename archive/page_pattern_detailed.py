#!/usr/bin/env python3
"""
Enhanced page pattern scanner with detailed output showing exactly what data is found on each page.
"""

import requests
import json
import time
from datetime import datetime
from collections import defaultdict
import sys

# API Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Chiloé nodes to track
CHILOE_NODES = {
    'CMG_REAL': [
        'CHILOE________220',
        'CHILOE________110', 
        'QUELLON_______110',
        'QUELLON_______013',
        'CHONCHI_______110',
        'DALCAHUE______023'
    ],
    'CMG_PID': [
        'BA S/E CHILOE 220KV BP1',
        'BA S/E CHILOE 110KV BP1',
        'BA S/E QUELLON 110KV BP1',
        'BA S/E QUELLON 13KV BP1',
        'BA S/E CHONCHI 110KV BP1',
        'BA S/E DALCAHUE 23KV BP1'
    ]
}

def scan_with_details(endpoint_url, date_str, node_field, target_nodes, max_pages=20):
    """
    Scan endpoint and print detailed information about what's found on each page.
    """
    print(f"\n{'='*80}")
    print(f"DETAILED SCAN - {date_str}")
    print(f"{'='*80}")
    
    all_data = []
    location_summary = defaultdict(lambda: {'pages': set(), 'hours': set(), 'records': []})
    
    for page in range(1, max_pages + 1):
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        try:
            response = requests.get(endpoint_url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                if not records:
                    print(f"\n📄 Page {page}: END OF DATA")
                    break
                
                # Find target nodes in this page
                page_findings = []
                for node in target_nodes:
                    node_records = [r for r in records if r.get(node_field) == node]
                    
                    if node_records:
                        for record in node_records:
                            # Extract timestamp and hour
                            if 'fecha_hora' in record:
                                timestamp = record['fecha_hora']
                                hour = int(timestamp[11:13])
                            elif 'hra' in record:
                                hour = record['hra']
                                timestamp = f"{date_str} {hour:02d}:00"
                            else:
                                hour = '??'
                                timestamp = 'Unknown'
                            
                            # Extract CMG value
                            cmg = record.get('cmg_usd_mwh_', record.get('cmg_usd_mwh', record.get('cmg', 0)))
                            
                            finding = {
                                'location': node[:30],
                                'timestamp': timestamp,
                                'hour': hour,
                                'cmg': cmg
                            }
                            page_findings.append(finding)
                            
                            # Update summary
                            location_summary[node]['pages'].add(page)
                            location_summary[node]['hours'].add(hour)
                            location_summary[node]['records'].append(finding)
                
                # Print page results
                if page_findings:
                    print(f"\n📄 Page {page}: Found {len(page_findings)} records from {len(set(f['location'] for f in page_findings))} locations")
                    
                    # Group by location for cleaner output
                    by_location = defaultdict(list)
                    for f in page_findings:
                        by_location[f['location']].append(f)
                    
                    for location, findings in sorted(by_location.items()):
                        hours = sorted(set(f['hour'] for f in findings))
                        print(f"   🔹 {location}: Hours {hours}")
                        # Show first few records as examples
                        for f in findings[:2]:
                            print(f"      → {f['timestamp']}: ${f['cmg']:.2f}")
                        if len(findings) > 2:
                            print(f"      → ... and {len(findings)-2} more records")
                else:
                    print(f"\n📄 Page {page}: {len(records)} records - NO TARGET LOCATIONS")
                
                # Stop if incomplete page
                if len(records) < 1000:
                    print(f"   (Last page - incomplete with {len(records)} records)")
                    break
                    
            else:
                print(f"\n📄 Page {page}: ERROR {response.status_code}")
                break
                
        except Exception as e:
            print(f"\n📄 Page {page}: ERROR - {str(e)[:50]}")
            break
        
        # Small delay
        time.sleep(0.3)
    
    return location_summary

def analyze_patterns(location_summary):
    """
    Analyze and display patterns found in the scan.
    """
    print(f"\n{'='*80}")
    print("PATTERN ANALYSIS")
    print(f"{'='*80}")
    
    for location, data in sorted(location_summary.items()):
        pages = sorted(data['pages'])
        hours = sorted(data['hours'])
        
        print(f"\n📍 {location}:")
        print(f"   Pages: {pages}")
        print(f"   Hours covered: {hours} ({len(hours)}/24)")
        
        # Check for page pattern
        if len(pages) > 1:
            gaps = [pages[i+1] - pages[i] for i in range(len(pages)-1)]
            if len(set(gaps)) == 1:
                print(f"   ✅ REGULAR PATTERN: Every {gaps[0]} pages")
            elif len(set(gaps)) <= 2:
                print(f"   🔍 Semi-regular: Gaps of {sorted(set(gaps))}")
            else:
                print(f"   ❌ Irregular pattern: Gaps vary {sorted(set(gaps))}")
        
        # Missing hours
        if len(hours) < 24:
            missing = [h for h in range(24) if h not in hours]
            print(f"   ⚠️ Missing hours: {missing}")

def main():
    """
    Run detailed analysis for different endpoints.
    """
    date_to_scan = '2025-08-25'
    
    # Test each endpoint
    endpoints = [
        ('CMG_ONLINE', '/costo-marginal-online/v4/findByDate', 'barra_transf', CHILOE_NODES['CMG_REAL']),
        ('CMG_PID', '/cmg-programado-pid/v4/findByDate', 'nmb_barra_info', CHILOE_NODES['CMG_PID']),
        ('CMG_REAL', '/costo-marginal-real/v4/findByDate', 'barra_transf', CHILOE_NODES['CMG_REAL'])
    ]
    
    all_results = {}
    
    for endpoint_name, endpoint_path, field, nodes in endpoints:
        print(f"\n{'#'*80}")
        print(f"# SCANNING: {endpoint_name}")
        print(f"{'#'*80}")
        
        url = SIP_BASE_URL + endpoint_path
        results = scan_with_details(url, date_to_scan, field, nodes)
        all_results[endpoint_name] = results
        
        if results:
            analyze_patterns(results)
        else:
            print(f"\n⚠️ No data found for {endpoint_name}")
        
        time.sleep(2)  # Rate limiting between endpoints
    
    # Overall summary
    print(f"\n{'='*80}")
    print("OVERALL SUMMARY")
    print(f"{'='*80}")
    
    total_coverage = defaultdict(set)
    for endpoint, locations in all_results.items():
        for location, data in locations.items():
            total_coverage[location].update(data['hours'])
    
    print("\n🎯 Best combined coverage:")
    for location, hours in sorted(total_coverage.items()):
        coverage_pct = len(hours) / 24 * 100
        if 'CHILOE' in location:
            print(f"   {location[:35]:35} : {len(hours):2}/24 hours ({coverage_pct:.0f}%)")
            if len(hours) < 24:
                missing = sorted(set(range(24)) - hours)
                print(f"      Missing: {missing}")
    
    # Export findings
    export_data = {
        'scan_date': date_to_scan,
        'timestamp': datetime.now().isoformat(),
        'endpoints': {}
    }
    
    for endpoint, locations in all_results.items():
        export_data['endpoints'][endpoint] = {}
        for location, data in locations.items():
            export_data['endpoints'][endpoint][location] = {
                'pages': sorted(data['pages']),
                'hours': sorted(data['hours']),
                'record_count': len(data['records'])
            }
    
    with open('detailed_patterns.json', 'w') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"\n✅ Detailed patterns saved to detailed_patterns.json")

if __name__ == "__main__":
    main()