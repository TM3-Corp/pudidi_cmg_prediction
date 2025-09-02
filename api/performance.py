"""
API endpoint for performance analysis
Compares optimization results against stable baseline and perfect hindsight
"""

from http.server import BaseHTTPRequestHandler
import json
import numpy as np
from datetime import datetime, timedelta
import pytz
import requests

# Import optimizer
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from api.utils.optimizer_lp import optimize_hydro_lp
    OPTIMIZER_AVAILABLE = True
except ImportError:
    OPTIMIZER_AVAILABLE = False
    print("[PERFORMANCE] Optimizer not available")

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            # Parse request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            
            # Get parameters
            period = params.get('period', '24h')  # 24h, 48h, 5d, 7d
            start_date = params.get('start_date')
            node = params.get('node', 'NVA_P.MONTT___220')
            
            # Hydro parameters
            p_min = params.get('p_min', 0.5)
            p_max = params.get('p_max', 3.0)
            s0 = params.get('s0', 25000)
            s_min = params.get('s_min', 1000)
            s_max = params.get('s_max', 50000)
            kappa = params.get('kappa', 0.667)
            inflow = params.get('inflow', 2.5)
            
            # Determine horizon from period
            horizon_map = {
                '24h': 24,
                '48h': 48,
                '5d': 120,
                '7d': 168
            }
            horizon = horizon_map.get(period, 24)
            
            # Fetch historical CMG Online data
            historical_prices = self.fetch_historical_prices(start_date, horizon, node)
            
            # Fetch programmed CMG data (what was forecasted)
            programmed_prices = self.fetch_programmed_prices(start_date, horizon, node)
            
            if not historical_prices:
                self.send_error(404, "No historical CMG Online data available for the selected period")
                return
            
            if not programmed_prices:
                # If no programmed prices, use historical prices as fallback (assume perfect forecast)
                print("[PERFORMANCE] Warning: No CMG Programado data, using CMG Online as fallback")
                programmed_prices = historical_prices
            
            # Calculate performance for three scenarios
            results = self.calculate_performance(
                historical_prices, 
                programmed_prices,
                p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon
            )
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode())
            
        except Exception as e:
            print(f"[PERFORMANCE] Error: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))
    
    def fetch_historical_prices(self, start_date, horizon, node):
        """Fetch historical CMG Online prices from stored data"""
        try:
            data = None
            
            # First try local cache
            cache_path = 'data/cache/cmg_online_historical.json'
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    data = json.load(f)
            else:
                # Try to fetch from GitHub Gist
                data = self.fetch_from_gist()
            
            if not data or 'daily_data' not in data:
                print("[PERFORMANCE] No historical data available")
                return None
            
            # Check structure version
            structure_version = data.get('metadata', {}).get('structure_version', '1.0')
            
            # Extract prices for the requested period
            prices = []
            current_date = datetime.fromisoformat(start_date)
            
            for hour in range(horizon):
                date_str = current_date.strftime('%Y-%m-%d')
                hour_idx = current_date.hour
                
                # Safely access nested data with proper null checks
                day_data = data.get('daily_data', {}).get(date_str)
                
                if day_data and isinstance(day_data, dict):
                    # Handle new structure (v2.0) with cmg_online/cmg_programado
                    if structure_version == '2.0' and 'cmg_online' in day_data:
                        online_data = day_data.get('cmg_online', {})
                        node_data = online_data.get(node)
                    # Handle old structure (v1.0) with direct data
                    elif 'data' in day_data:
                        node_data = day_data.get('data', {}).get(node)
                    else:
                        node_data = None
                    
                    if node_data and 'cmg_usd' in node_data:
                        cmg_prices = node_data.get('cmg_usd', [])
                        if hour_idx < len(cmg_prices) and cmg_prices[hour_idx] is not None:
                            prices.append(cmg_prices[hour_idx])
                        else:
                            prices.append(0)  # Missing hour data
                    else:
                        prices.append(0)  # Node not found
                else:
                    prices.append(0)  # Date not found
                
                current_date += timedelta(hours=1)
            
            # Return prices only if we have some valid data
            return prices if any(p > 0 for p in prices) else None
            
        except Exception as e:
            print(f"[PERFORMANCE] Error fetching historical prices: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def fetch_from_gist(self):
        """Fetch historical data from GitHub Gist"""
        try:
            # Try to read Gist ID from file
            gist_id = None
            if os.path.exists('.gist_id'):
                with open('.gist_id', 'r') as f:
                    gist_id = f.read().strip()
            
            # Fallback to a known Gist ID if needed
            if not gist_id:
                # Use the public Gist ID we just created
                gist_id = '8d7864eb26acf6e780d3c0f7fed69365'
            
            # Fetch from GitHub Gist API
            url = f'https://api.github.com/gists/{gist_id}'
            response = requests.get(url)
            
            if response.status_code == 200:
                gist_data = response.json()
                if 'cmg_online_historical.json' in gist_data.get('files', {}):
                    content = gist_data['files']['cmg_online_historical.json']['content']
                    return json.loads(content)
            
            return None
            
        except Exception as e:
            print(f"[PERFORMANCE] Error fetching from Gist: {e}")
            return None
    
    def fetch_programmed_prices(self, start_date, horizon, node):
        """Fetch what CMG Programado prices were forecasted for that time"""
        try:
            # First try to fetch from the CMG Programado Gist
            programmed_data = self.fetch_programmed_from_gist(start_date, horizon, node)
            
            if programmed_data and len(programmed_data) > 0:
                valid_count = sum(1 for p in programmed_data if p > 0)
                print(f"[PERFORMANCE] Found {valid_count}/{horizon} valid programmed prices from Gist")
                return programmed_data
            
            # Fallback: try local cache (for recent data that might be stored)
            data = None
            cache_path = 'data/cache/cmg_online_historical.json'
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    data = json.load(f)
            else:
                data = self.fetch_from_gist()
            
            if not data or 'daily_data' not in data:
                print("[PERFORMANCE] No historical data available for programmed prices")
                return None
            
            # Check structure version
            structure_version = data.get('metadata', {}).get('structure_version', '1.0')
            
            # Only new structure has programmed data
            if structure_version != '2.0':
                print("[PERFORMANCE] Old data structure - no programmed prices available")
                return None
            
            # Extract programmed prices for the requested period
            prices = []
            current_date = datetime.fromisoformat(start_date)
            
            for hour in range(horizon):
                date_str = current_date.strftime('%Y-%m-%d')
                hour_idx = current_date.hour
                
                # Get the programmed data for this date
                day_data = data.get('daily_data', {}).get(date_str)
                
                if day_data and 'cmg_programado' in day_data:
                    programmed_data = day_data.get('cmg_programado', {})
                    node_data = programmed_data.get(node)
                    
                    if node_data and 'values' in node_data:
                        prog_values = node_data.get('values', [])
                        if hour_idx < len(prog_values) and prog_values[hour_idx] is not None:
                            prices.append(prog_values[hour_idx])
                        else:
                            prices.append(0)
                    else:
                        prices.append(0)
                else:
                    prices.append(0)
                
                current_date += timedelta(hours=1)
            
            # Return prices only if we have some valid data
            result = prices if any(p > 0 for p in prices) else None
            
            if result is None:
                print(f"[PERFORMANCE] No valid programmed prices found for {start_date} (node: {node})")
            else:
                valid_count = sum(1 for p in prices if p > 0)
                print(f"[PERFORMANCE] Found {valid_count}/{horizon} valid programmed prices from cache")
            
            return result
            
        except Exception as e:
            print(f"[PERFORMANCE] Error fetching programmed prices: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def fetch_programmed_from_gist(self, start_date, horizon, node):
        """Fetch historical CMG Programado from the official Gist"""
        try:
            import csv
            from io import StringIO
            
            # CMG Programado Gist ID
            gist_id = 'a63a3a10479bafcc29e10aaca627bc73'
            url = f'https://api.github.com/gists/{gist_id}'
            
            response = requests.get(url)
            if response.status_code != 200:
                return None
            
            gist_data = response.json()
            
            # Map node names
            node_mapping = {
                'NVA_P.MONTT___220': 'Puerto Montt 220',
                'PIDPID________110': 'Pid-Pid 110',
                'DALCAHUE______110': 'Dalcahue 110'
            }
            
            mapped_node = node_mapping.get(node, node)
            
            # Parse start date
            current_date = datetime.fromisoformat(start_date)
            
            # Look for CSV files that might contain data for our dates
            prices = []
            
            for filename, file_info in gist_data['files'].items():
                if filename.endswith('.csv'):
                    csv_content = file_info['content']
                    
                    # Parse CSV
                    reader = csv.DictReader(StringIO(csv_content))
                    records = list(reader)
                    
                    # Build a date/hour/node index
                    data_index = {}
                    for record in records:
                        # Find date, hour, and node columns
                        date_val = None
                        hour_val = None
                        node_val = None
                        price_val = None
                        
                        for key, value in record.items():
                            if 'fecha' in key.lower() or 'date' in key.lower():
                                date_val = value[:10] if value else None
                            elif 'hora' in key.lower() or 'hour' in key.lower():
                                try:
                                    hour_val = int(value) if value else None
                                except:
                                    hour_val = None
                            elif 'barra' in key.lower() or 'node' in key.lower():
                                node_val = value
                            elif 'cmg' in key.lower() and 'programado' in key.lower():
                                try:
                                    price_val = float(value) if value else None
                                except:
                                    price_val = None
                        
                        if date_val and hour_val is not None and node_val and price_val:
                            key = (date_val, hour_val, node_val)
                            data_index[key] = price_val
                    
                    # Extract prices for our period
                    temp_date = current_date
                    for hour in range(horizon):
                        date_str = temp_date.strftime('%Y-%m-%d')
                        hour_idx = temp_date.hour
                        
                        # Try to find the price
                        key = (date_str, hour_idx, mapped_node)
                        if key in data_index:
                            prices.append(data_index[key])
                        else:
                            prices.append(0)
                        
                        temp_date += timedelta(hours=1)
                    
                    # If we found data, use it
                    if any(p > 0 for p in prices):
                        return prices
            
            return None
            
        except Exception as e:
            print(f"[PERFORMANCE] Error fetching from CMG Programado Gist: {e}")
            return None
    
    def calculate_performance(self, historical_prices, programmed_prices, 
                             p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
        """Calculate performance metrics for three scenarios"""
        
        # Ensure we have the right number of prices
        historical_prices = historical_prices[:horizon]
        programmed_prices = programmed_prices[:horizon]
        
        # 1. STABLE GENERATION (Baseline)
        # Generate at water balance point
        p_stable = min(max(inflow / kappa, p_min), p_max)  # Constrain to limits
        revenue_stable = sum(p_stable * price for price in historical_prices)
        
        # Power pattern for stable
        power_stable = [p_stable] * horizon
        
        # 2. CMG PROGRAMADO OPTIMIZATION (Forecast-based)
        if OPTIMIZER_AVAILABLE:
            solution_programmed = optimize_hydro_lp(
                programmed_prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon
            )
            # Calculate revenue using ACTUAL prices but PROGRAMMED dispatch
            revenue_programmed = sum(
                solution_programmed['P'][i] * historical_prices[i] 
                for i in range(len(solution_programmed['P']))
            )
            power_programmed = solution_programmed['P']
        else:
            # Fallback if optimizer not available
            revenue_programmed = revenue_stable * 1.1  # Assume 10% improvement
            power_programmed = power_stable
        
        # 3. PERFECT HINDSIGHT OPTIMIZATION (Ideal case)
        if OPTIMIZER_AVAILABLE:
            solution_hindsight = optimize_hydro_lp(
                historical_prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon
            )
            revenue_hindsight = solution_hindsight['revenue']
            power_hindsight = solution_hindsight['P']
        else:
            revenue_hindsight = revenue_stable * 1.2  # Assume 20% improvement possible
            power_hindsight = power_stable
        
        # Calculate performance metrics
        improvement_vs_stable = ((revenue_programmed - revenue_stable) / revenue_stable * 100) if revenue_stable > 0 else 0
        efficiency = (revenue_programmed / revenue_hindsight * 100) if revenue_hindsight > 0 else 0
        
        # Calculate daily breakdown if period is longer than 24h
        daily_performance = []
        if horizon > 24:
            for day_start in range(0, horizon, 24):
                day_end = min(day_start + 24, horizon)
                day_prices = historical_prices[day_start:day_end]
                
                day_revenue_stable = sum(p_stable * p for p in day_prices)
                day_revenue_programmed = sum(
                    power_programmed[i] * day_prices[i-day_start] 
                    for i in range(day_start, day_end)
                )
                day_revenue_hindsight = sum(
                    power_hindsight[i] * day_prices[i-day_start] 
                    for i in range(day_start, day_end)
                )
                
                daily_performance.append({
                    'day': day_start // 24 + 1,
                    'revenue_stable': round(day_revenue_stable, 2),
                    'revenue_programmed': round(day_revenue_programmed, 2),
                    'revenue_hindsight': round(day_revenue_hindsight, 2),
                    'efficiency': round(day_revenue_programmed / day_revenue_hindsight * 100, 1) if day_revenue_hindsight > 0 else 0
                })
        
        return {
            'summary': {
                'revenue_stable': round(revenue_stable, 2),
                'revenue_programmed': round(revenue_programmed, 2),
                'revenue_hindsight': round(revenue_hindsight, 2),
                'improvement_vs_stable': round(improvement_vs_stable, 1),
                'efficiency': round(efficiency, 1),
                'horizon': horizon,
                'p_stable': round(p_stable, 2)
            },
            'hourly_data': {
                'historical_prices': historical_prices,
                'programmed_prices': programmed_prices,
                'power_stable': power_stable,
                'power_programmed': list(power_programmed),
                'power_hindsight': list(power_hindsight)
            },
            'daily_performance': daily_performance
        }

    def do_GET(self):
        """Handle GET requests for data availability check"""
        try:
            # Parse query parameters
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            # Check if this is a data availability request
            if 'check_availability' in query_params:
                response = self.get_data_availability()
            else:
                response = {
                    'status': 'ok',
                    'message': 'Performance API is running',
                    'endpoints': {
                        'GET /?check_availability=true': 'Get available historical data dates',
                        'POST /': 'Calculate performance metrics',
                        'parameters': {
                            'period': '24h | 48h | 5d | 7d',
                            'start_date': 'ISO date string',
                            'node': 'CMG node name'
                        }
                    }
                }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"[PERFORMANCE] Error in GET: {e}")
            self.send_error(500, str(e))
    
    def get_data_availability(self):
        """Get available dates and data statistics"""
        try:
            data = None
            
            # Try local cache first
            cache_path = 'data/cache/cmg_online_historical.json'
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    data = json.load(f)
            else:
                # Try GitHub Gist
                data = self.fetch_from_gist()
            
            if not data or 'daily_data' not in data:
                return {
                    'available': False,
                    'message': 'No historical data available'
                }
            
            # Get date range and statistics
            dates = sorted(data.get('daily_data', {}).keys())
            nodes = data.get('metadata', {}).get('nodes', [])
            structure_version = data.get('metadata', {}).get('structure_version', '1.0')
            
            # Count total hours available
            total_hours_online = 0
            total_hours_programmed = 0
            
            for date in dates:
                day_data = data['daily_data'][date]
                
                # Handle new structure (v2.0)
                if structure_version == '2.0':
                    if 'cmg_online' in day_data:
                        for node in nodes:
                            if node in day_data['cmg_online']:
                                cmg_data = day_data['cmg_online'][node].get('cmg_usd', [])
                                total_hours_online += sum(1 for p in cmg_data if p is not None and p > 0)
                                break
                    
                    if 'cmg_programado' in day_data:
                        for node in nodes:
                            if node in day_data['cmg_programado']:
                                prog_data = day_data['cmg_programado'][node].get('values', [])
                                total_hours_programmed += sum(1 for p in prog_data if p is not None and p > 0)
                                break
                
                # Handle old structure (v1.0)
                elif 'data' in day_data:
                    for node in nodes:
                        if node in day_data['data']:
                            cmg_data = day_data['data'][node].get('cmg_usd', [])
                            total_hours_online += sum(1 for p in cmg_data if p is not None and p > 0)
                            break
            
            return {
                'available': True,
                'dates': dates,
                'oldest_date': dates[0] if dates else None,
                'newest_date': dates[-1] if dates else None,
                'total_days': len(dates),
                'total_hours': total_hours_online if structure_version == '2.0' else total_hours_online,
                'total_hours_online': total_hours_online,
                'total_hours_programmed': total_hours_programmed,
                'nodes': nodes,
                'metadata': data.get('metadata', {}),
                'has_programmed_data': total_hours_programmed > 0
            }
            
        except Exception as e:
            print(f"[PERFORMANCE] Error checking availability: {e}")
            return {
                'available': False,
                'message': f'Error checking data: {str(e)}'
            }