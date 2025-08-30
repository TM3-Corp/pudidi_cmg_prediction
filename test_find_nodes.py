#!/usr/bin/env python3
"""
Test script to find Puerto Montt and PID-related nodes in historical CMG data
"""

import requests
import json
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

# API Configuration
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

def search_nodes():
    """Search for Puerto Montt and PID-related nodes"""
    
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    today = now.strftime('%Y-%m-%d')
    
    print("="*80)
    print(f"🔍 SEARCHING FOR PUERTO MONTT AND PID NODES")
    print(f"📅 Date: {today}")
    print("="*80)
    
    # Fetch a few pages to find all unique nodes
    url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
    
    all_nodes = set()
    puerto_montt_nodes = []
    pid_nodes = []
    dalcahue_nodes = []
    
    # Fetch first 5 pages to get a good sample
    for page in range(1, 6):
        params = {
            'startDate': today,
            'endDate': today,
            'page': page,
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        print(f"\nFetching page {page}...")
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                print(f"  Got {len(records)} records")
                
                for record in records:
                    node = record.get('barra_transf', '')
                    if node:
                        all_nodes.add(node)
                        
                        # Check for Puerto Montt variations
                        node_lower = node.lower()
                        if 'montt' in node_lower or 'pmontt' in node_lower or 'puerto' in node_lower:
                            if node not in puerto_montt_nodes:
                                puerto_montt_nodes.append(node)
                                print(f"  ✅ Found Puerto Montt node: {node}")
                        
                        # Check for PID variations
                        if 'pid' in node_lower:
                            if node not in pid_nodes:
                                pid_nodes.append(node)
                                print(f"  ✅ Found PID node: {node}")
                        
                        # Check for Dalcahue
                        if 'dalcahue' in node_lower:
                            if node not in dalcahue_nodes:
                                dalcahue_nodes.append(node)
                                print(f"  ✅ Found Dalcahue node: {node}")
                
                if len(records) < 1000:
                    print(f"  Last page reached")
                    break
                    
            else:
                print(f"  Error: {response.status_code}")
                break
                
        except Exception as e:
            print(f"  Exception: {e}")
            break
    
    print("\n" + "="*80)
    print("📊 SEARCH RESULTS")
    print("="*80)
    
    print(f"\nTotal unique nodes found: {len(all_nodes)}")
    
    print(f"\n🏙️ PUERTO MONTT nodes ({len(puerto_montt_nodes)}):")
    for node in sorted(puerto_montt_nodes):
        print(f"  - {node}")
    
    print(f"\n🔌 PID nodes ({len(pid_nodes)}):")
    for node in sorted(pid_nodes):
        print(f"  - {node}")
    
    print(f"\n🏝️ DALCAHUE nodes ({len(dalcahue_nodes)}):")
    for node in sorted(dalcahue_nodes):
        print(f"  - {node}")
    
    # Show all nodes that might be related
    print("\n📝 All nodes (searching for patterns):")
    print("\nNodes containing 'MONTT':")
    for node in sorted(all_nodes):
        if 'MONTT' in node.upper():
            print(f"  - {node}")
    
    print("\nNodes containing 'PID':")
    for node in sorted(all_nodes):
        if 'PID' in node.upper():
            print(f"  - {node}")
    
    print("\nNodes containing '220' (common voltage level):")
    montt_220_found = False
    for node in sorted(all_nodes):
        if '220' in node:
            if 'MONTT' in node.upper():
                print(f"  - {node} ⭐ (PUERTO MONTT 220)")
                montt_220_found = True
    
    if not montt_220_found:
        print("\nSearching for nodes with 'P' at start (might be Puerto Montt):")
        for node in sorted(all_nodes):
            if node.startswith('P') and '220' in node:
                print(f"  - {node}")
    
    # Test fetching data for found nodes
    if puerto_montt_nodes or dalcahue_nodes:
        print("\n" + "="*80)
        print("📈 TESTING DATA FETCH FOR FOUND NODES")
        print("="*80)
        
        test_nodes = (puerto_montt_nodes[:1] if puerto_montt_nodes else []) + \
                     (dalcahue_nodes[:1] if dalcahue_nodes else [])
        
        for test_node in test_nodes:
            print(f"\nFetching data for: {test_node}")
            
            params = {
                'startDate': today,
                'endDate': today,
                'page': 1,
                'limit': 100,
                'user_key': SIP_API_KEY
            }
            
            try:
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    records = data.get('data', [])
                    
                    node_data = []
                    for record in records:
                        if record.get('barra_transf') == test_node:
                            node_data.append({
                                'hour': record.get('hra', 0),
                                'cmg_usd': record.get('cmg_usd_mwh', 0)
                            })
                    
                    if node_data:
                        node_data.sort(key=lambda x: x['hour'])
                        print(f"  ✅ Found {len(node_data)} hours of data")
                        print(f"  Sample: Hour {node_data[0]['hour']:02d}:00 = ${node_data[0]['cmg_usd']:.2f} USD/MWh")
                    else:
                        print(f"  ❌ No data found for this node")
                        
            except Exception as e:
                print(f"  Error fetching data: {e}")

if __name__ == "__main__":
    search_nodes()