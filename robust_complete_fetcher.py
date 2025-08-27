#!/usr/bin/env python3
"""
Robust Complete Fetcher - Handles all edge cases properly
=========================================================
- Distinguishes between "no more data" vs "temporary failure"
- Never gives up on a page in the middle of fetching
- Handles 429/500 errors with infinite patience
- Fetches until truly complete or confirmed end of data
"""

import requests
import time
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, Set, Tuple, Optional

# Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

# Node definitions
CHILOE_NODES = {
    'CMG': [
        'CHILOE________220', 'CHILOE________110',
        'QUELLON_______110', 'QUELLON_______013',
        'CHONCHI_______110', 'DALCAHUE______023'
    ],
    'PID': [
        'BA S/E CHILOE 220KV BP1', 'BA S/E CHILOE 110KV BP1',
        'BA S/E QUELLON 110KV BP1', 'BA S/E QUELLON 13KV BP1',
        'BA S/E CHONCHI 110KV BP1', 'BA S/E DALCAHUE 23KV BP1'
    ]
}

class RobustFetcher:
    """
    Fetcher that never gives up until it gets complete data or confirms end of data.
    """
    
    def __init__(self, records_per_page=1000):
        self.records_per_page = records_per_page
        self.session = requests.Session()
        
    def fetch_single_page(self, url: str, params: dict, page: int) -> Tuple[Optional[list], str]:
        """
        Fetch a single page with INFINITE retry for temporary errors.
        Returns: (records, status) where status is one of:
        - 'success': Got data
        - 'empty': Successful request but no data (end of pages)
        - 'error': Permanent error (bad request, auth issues)
        """
        
        attempt = 0
        wait_time = 2
        max_wait = 120
        
        while True:  # Keep trying forever for temporary errors
            attempt += 1
            
            try:
                response = self.session.get(url, params=params, timeout=45)
                
                # SUCCESS - Got data
                if response.status_code == 200:
                    data = response.json()
                    records = data.get('data', [])
                    
                    if records:
                        return records, 'success'
                    else:
                        # Empty response - this is the end of data
                        return [], 'empty'
                
                # RATE LIMIT - Always retry
                elif response.status_code == 429:
                    wait_time = min(wait_time * 2, max_wait)
                    print(f"       Rate limit on page {page}. Waiting {wait_time}s (attempt {attempt})...")
                    time.sleep(wait_time)
                    continue
                
                # SERVER ERROR - Always retry
                elif response.status_code >= 500:
                    wait_time = min(wait_time * 1.5, 60)
                    print(f"       Server error {response.status_code} on page {page}. Waiting {wait_time}s (attempt {attempt})...")
                    time.sleep(wait_time)
                    continue
                
                # CLIENT ERROR - These are permanent
                elif response.status_code >= 400:
                    print(f"       Client error {response.status_code} on page {page} - stopping")
                    return None, 'error'
                
                # UNKNOWN STATUS
                else:
                    print(f"       Unknown status {response.status_code} on page {page}. Retrying...")
                    time.sleep(wait_time)
                    continue
                    
            except requests.exceptions.Timeout:
                wait_time = min(wait_time * 1.5, 60)
                print(f"       Timeout on page {page}. Waiting {wait_time}s (attempt {attempt})...")
                time.sleep(wait_time)
                continue
                
            except requests.exceptions.ConnectionError:
                wait_time = min(wait_time * 2, max_wait)
                print(f"       Connection error on page {page}. Waiting {wait_time}s (attempt {attempt})...")
                time.sleep(wait_time)
                continue
                
            except Exception as e:
                print(f"       Unexpected error on page {page}: {str(e)[:100]}")
                time.sleep(wait_time)
                continue
    
    def fetch_complete_endpoint(self, endpoint_name: str, date_str: str, max_pages: int = 500):
        """
        Fetch ALL data from an endpoint until truly complete or confirmed end.
        Never gives up on a page unless it's truly the end.
        """
        
        # Setup endpoint configuration
        endpoints = {
            'CMG_ONLINE': {
                'url': '/costo-marginal-online/v4/findByDate',
                'field': 'barra_transf',
                'nodes': CHILOE_NODES['CMG']
            },
            'CMG_PID': {
                'url': '/cmg-programado-pid/v4/findByDate',
                'field': 'nmb_barra_info', 
                'nodes': CHILOE_NODES['PID']
            },
            'CMG_REAL': {
                'url': '/costo-marginal-real/v4/findByDate',
                'field': 'barra_transf',
                'nodes': CHILOE_NODES['CMG']
            }
        }
        
        config = endpoints[endpoint_name]
        url = SIP_BASE_URL + config['url']
        node_field = config['field']
        target_nodes = config['nodes']
        
        print(f"\n{'='*80}")
        print(f"ROBUST FETCH: {endpoint_name} for {date_str}")
        print(f"Records per page: {self.records_per_page}")
        print(f"Target nodes: {len(target_nodes)}")
        print(f"{'='*80}")
        
        # Storage
        all_data = defaultdict(lambda: {'pages': set(), 'hours': set(), 'records': []})
        pages_fetched = []
        total_records = 0
        start_time = time.time()
        
        page = 1
        consecutive_empty = 0
        
        while page <= max_pages:
            params = {
                'startDate': date_str,
                'endDate': date_str,
                'page': page,
                'limit': self.records_per_page,
                'user_key': SIP_API_KEY
            }
            
            print(f"\n📄 Page {page:3d}: ", end='')
            
            # Fetch with infinite retry for temporary errors
            records, status = self.fetch_single_page(url, params, page)
            
            # Handle based on status
            if status == 'success':
                pages_fetched.append(page)
                total_records += len(records)
                consecutive_empty = 0
                
                # Process records
                findings = defaultdict(set)
                
                for record in records:
                    node = record.get(node_field)
                    if node in target_nodes:
                        # Extract hour
                        hour = None
                        if 'fecha_hora' in record:
                            hour = int(record['fecha_hora'][11:13])
                        elif 'hra' in record:
                            hour = record['hra']
                        
                        if hour is not None:
                            findings[node].add(hour)
                            all_data[node]['pages'].add(page)
                            all_data[node]['hours'].add(hour)
                            all_data[node]['records'].append({
                                'page': page,
                                'hour': hour,
                                'timestamp': record.get('fecha_hora', f"{date_str} {hour:02d}:00")
                            })
                
                # Print findings
                if findings:
                    print(f"{len(records):4d} records | Found {sum(len(h) for h in findings.values())} target hours")
                    for node, hours in sorted(findings.items())[:3]:  # Show first 3
                        print(f"   🔹 {node[:25]:25} : Hours {sorted(hours)[:10]}{'...' if len(hours) > 10 else ''}")
                    if len(findings) > 3:
                        print(f"   ... and {len(findings)-3} more locations")
                else:
                    print(f"{len(records):4d} records | No target locations")
                
                # Check if this is a partial page (probable end)
                if len(records) < self.records_per_page:
                    print(f"\n📌 Partial page ({len(records)} records) - checking if more pages exist...")
                    # Continue to next page to confirm it's really the end
                
                # Check completeness
                all_complete = all(
                    len(data['hours']) == 24 
                    for data in all_data.values() 
                    if data['hours']
                )
                
                if all_complete and all_data:
                    print(f"\n✅ COMPLETE: All locations have 24 hours!")
                    break
                
            elif status == 'empty':
                consecutive_empty += 1
                print(f"EMPTY (no data)")
                
                # If we get 2 consecutive empty pages, we're truly at the end
                if consecutive_empty >= 2:
                    print(f"\n📍 Confirmed end of data (2 consecutive empty pages)")
                    break
                    
            elif status == 'error':
                # Permanent error - stop
                print(f"Permanent error - stopping")
                break
            
            page += 1
            
            # Progress update
            if page % 10 == 0:
                elapsed = time.time() - start_time
                print(f"\n⏱️ Progress: {page} pages, {total_records} records, {elapsed:.1f}s")
                
                # Show current coverage
                for node, data in sorted(all_data.items())[:2]:  # Show first 2
                    coverage = len(data['hours']) / 24 * 100
                    print(f"   {node[:30]:30}: {len(data['hours'])}/24 hours ({coverage:.0f}%)")
            
            # Small delay between pages
            time.sleep(0.2)
        
        # Final summary
        elapsed = time.time() - start_time
        print(f"\n{'='*80}")
        print(f"FETCH COMPLETE")
        print(f"Pages successfully fetched: {len(pages_fetched)} pages")
        print(f"Total records: {total_records}")
        print(f"Time elapsed: {elapsed:.1f} seconds")
        print(f"{'='*80}")
        
        # Coverage report
        print(f"\n📊 COVERAGE REPORT:")
        print(f"{'='*50}")
        
        for node in sorted(target_nodes):
            if node in all_data:
                data = all_data[node]
                hours = sorted(data['hours'])
                coverage = len(hours) / 24 * 100
                
                status = "✅" if coverage == 100 else "⚠️" if coverage >= 75 else "❌"
                print(f"\n{status} {node}:")
                print(f"   Pages: {len(data['pages'])} pages")
                print(f"   Hours: {hours[:20]}{'...' if len(hours) > 20 else ''}")
                print(f"   Coverage: {len(hours)}/24 ({coverage:.1f}%)")
                
                if len(hours) < 24:
                    missing = [h for h in range(24) if h not in hours]
                    print(f"   Missing: {missing}")
            else:
                print(f"\n❌ {node}: NO DATA FOUND")
        
        return dict(all_data)


def test_robust_fetcher():
    """
    Test the robust fetcher with different scenarios
    """
    fetcher = RobustFetcher(records_per_page=1000)
    
    # Test with a recent date
    test_date = '2025-08-25'
    
    # Test CMG_ONLINE
    print("\n" + "#"*80)
    print("# TESTING CMG_ONLINE")
    print("#"*80)
    online_data = fetcher.fetch_complete_endpoint('CMG_ONLINE', test_date)
    
    # Test CMG_PID  
    print("\n" + "#"*80)
    print("# TESTING CMG_PID")
    print("#"*80)
    pid_data = fetcher.fetch_complete_endpoint('CMG_PID', test_date)
    
    # Combine results
    print("\n" + "#"*80)
    print("# COMBINED RESULTS")
    print("#"*80)
    
    # Map PID to CMG nodes
    node_mapping = {
        'BA S/E CHILOE 220KV BP1': 'CHILOE________220',
        'BA S/E CHILOE 110KV BP1': 'CHILOE________110',
        'BA S/E QUELLON 110KV BP1': 'QUELLON_______110',
        'BA S/E QUELLON 13KV BP1': 'QUELLON_______013',
        'BA S/E CHONCHI 110KV BP1': 'CHONCHI_______110',
        'BA S/E DALCAHUE 23KV BP1': 'DALCAHUE______023'
    }
    
    combined_coverage = defaultdict(set)
    
    # Add online hours
    for node, data in online_data.items():
        combined_coverage[node].update(data['hours'])
    
    # Add PID hours (mapped)
    for pid_node, cmg_node in node_mapping.items():
        if pid_node in pid_data:
            combined_coverage[cmg_node].update(pid_data[pid_node]['hours'])
    
    # Report combined coverage
    print("\n🎯 COMBINED COVERAGE (ONLINE + PID):")
    print("="*50)
    
    for node in sorted(CHILOE_NODES['CMG']):
        hours = combined_coverage.get(node, set())
        coverage = len(hours) / 24 * 100
        
        if coverage == 100:
            print(f"✅ {node:25}: {len(hours)}/24 hours (100%)")
        elif coverage > 0:
            missing = [h for h in range(24) if h not in hours]
            print(f"⚠️ {node:25}: {len(hours)}/24 hours ({coverage:.0f}%)")
            print(f"   Missing: {missing}")
        else:
            print(f"❌ {node:25}: NO DATA")
    
    return online_data, pid_data


if __name__ == "__main__":
    test_robust_fetcher()