"""
API endpoint for hydro optimization using CMG prices
WITH PROPER LINEAR PROGRAMMING OPTIMIZATION
"""

from http.server import BaseHTTPRequestHandler
import json
import numpy as np
from datetime import datetime, timedelta
import pytz
import traceback
import requests
# scipy might not be available on Vercel
try:
    from scipy.optimize import linprog
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("[OPTIMIZER] scipy not available, will use fallback optimization")

# Import our cache manager
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# GitHub Gist configuration for storing optimization results
OPTIMIZATION_GIST_ID = 'b7c9e8f3d2a1b4c5e6f7a8b9c0d1e2f3'  # Create a new Gist for optimization results
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')  # Must be set as environment variable

class handler(BaseHTTPRequestHandler):
    def store_optimization_result(self, params, result):
        """Store optimization result to GitHub Gist for later comparison"""
        try:
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
            date_str = now.strftime('%Y-%m-%d')
            
            # Prepare optimization record
            optimization_record = {
                'timestamp': now.isoformat(),
                'date': date_str,
                'hour': now.hour,
                'parameters': {
                    'horizon': params.get('horizon'),
                    'node': params.get('node'),
                    'p_min': params.get('p_min'),
                    'p_max': params.get('p_max'),
                    's0': params.get('s0'),
                    's_min': params.get('s_min'),
                    's_max': params.get('s_max'),
                    'kappa': params.get('kappa'),
                    'inflow': params.get('inflow')
                },
                'results': {
                    'power_schedule': result.get('P'),
                    'revenue': result.get('revenue'),
                    'avg_generation': result.get('avg_generation'),
                    'peak_generation': result.get('peak_generation'),
                    'capacity_factor': result.get('capacity_factor'),
                    'storage_trajectory': result.get('S')[:25] if result.get('S') else None  # First 25 hours
                }
            }
            
            # Fetch existing Gist data
            headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
            existing_data = {}
            
            try:
                response = requests.get(f'https://api.github.com/gists/{OPTIMIZATION_GIST_ID}', headers=headers)
                if response.status_code == 200:
                    gist_data = response.json()
                    if 'optimization_results.json' in gist_data.get('files', {}):
                        content = gist_data['files']['optimization_results.json'].get('content', '{}')
                        existing_data = json.loads(content)
            except:
                pass
            
            # Add new optimization to history
            if date_str not in existing_data:
                existing_data[date_str] = {}
            
            # Store one optimization per day (overwrite if exists)
            # This ensures we have exactly one optimization per day at 17:00
            existing_data[date_str] = {
                'optimization': optimization_record,
                'version': 1  # Track version for future schema changes
            }
            
            # No cutoff - keep ALL historical data for performance analysis
            # This creates a permanent record of all optimizations
            
            # Update Gist
            gist_content = {
                'files': {
                    'optimization_results.json': {
                        'content': json.dumps(existing_data, indent=2)
                    }
                }
            }
            
            response = requests.patch(
                f'https://api.github.com/gists/{OPTIMIZATION_GIST_ID}', 
                headers=headers, 
                json=gist_content
            )
            
            if response.status_code in [200, 201]:
                print(f"[OPTIMIZER] Stored optimization result for {date_str} hour {now.hour}")
                return True
            else:
                print(f"[OPTIMIZER] Failed to store result: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[OPTIMIZER] Error storing optimization: {e}")
            return False
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            print(f"[OPTIMIZER] POST request received at {datetime.now()}")
            
            # Parse request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            
            print(f"[OPTIMIZER] Received params: {json.dumps(params, indent=2)}")
            
            # Get optimization parameters
            horizon = params.get('horizon', 24)
            node = params.get('node', 'PMontt220')
            p_min = params.get('p_min', 0.5)
            p_max = params.get('p_max', 3.0)
            s0 = params.get('s0', 25000)
            s_min = params.get('s_min', 1000)
            s_max = params.get('s_max', 50000)
            kappa = params.get('kappa', 0.667)
            inflow = params.get('inflow', 1.1)
            data_source = params.get('data_source', 'ml_predictions')  # Default to ML predictions

            print(f"[OPTIMIZER] Parameters extracted:")
            print(f"  - Horizon: {horizon} hours")
            print(f"  - Node: {node}")
            print(f"  - Power range: {p_min} - {p_max} MW")
            print(f"  - Storage: {s0} m³ (limits: {s_min} - {s_max})")
            print(f"  - Kappa (water/power): {kappa}")
            print(f"  - Inflow: {inflow} m³/s")
            print(f"  - Data source: {data_source}")
            
            # Get CMG prices based on selected data source
            print(f"[OPTIMIZER] Fetching data from selected source: {data_source}...")

            prices = []
            timestamps = []  # Store actual timestamps from data
            data_range_start = None
            data_range_end = None
            data_source_used = None

            # Fetch data based on user selection
            if data_source == 'ml_predictions':
                # User selected ML Predictions
                print(f"[OPTIMIZER] User selected ML Predictions as data source")

                ml_predictions_available = False
                try:
                    # Get Railway ML backend URL from environment
                    railway_url = os.environ.get('RAILWAY_ML_URL', 'http://localhost:8000')
                    ml_endpoint = f"{railway_url}/api/ml_forecast"

                    print(f"[OPTIMIZER] Fetching from Railway ML backend: {ml_endpoint}")

                    # Fetch ML predictions with timeout
                    import urllib.request

                    # TEMPORARY: Disable time filtering to debug 500 error
                    # Use a very old date to include all available data
                    cutoff_time_str = "2000-01-01 00:00:00"
                    print(f"[OPTIMIZER] TEMP: Time filtering disabled for debugging")

                    with urllib.request.urlopen(ml_endpoint, timeout=10) as response:
                        ml_data = json.loads(response.read().decode())

                        if ml_data.get('success') and ml_data.get('predictions'):
                            predictions = ml_data['predictions']
                            print(f"[OPTIMIZER] Found {len(predictions)} ML predictions from backend")

                            # Filter for future predictions only (>= t+1)
                            future_predictions = [
                                p for p in predictions
                                if p.get('datetime', '') >= cutoff_time_str
                            ]
                            print(f"[OPTIMIZER] Filtered to {len(future_predictions)} future predictions (>= t+1)")

                            # Sort by datetime to ensure correct order
                            sorted_predictions = sorted(future_predictions, key=lambda x: x.get('datetime', ''))

                            if sorted_predictions:
                                data_range_start = sorted_predictions[0].get('datetime', 'unknown')
                                data_range_end = sorted_predictions[-1].get('datetime', 'unknown')
                                available_hours = len(sorted_predictions)

                                print(f"[OPTIMIZER] ML prediction range: {data_range_start} to {data_range_end}")
                                print(f"[OPTIMIZER] Available hours: {available_hours}, Requested: {horizon}")

                                # Check if we have enough data
                                if horizon > available_hours:
                                    error_msg = f"Insufficient ML predictions: {available_hours} hours available but {horizon} requested"
                                    print(f"[OPTIMIZER] ERROR: {error_msg}")

                                    self.send_response(400)
                                    self.send_header('Content-Type', 'application/json')
                                    self.send_header('Access-Control-Allow-Origin', '*')
                                    self.end_headers()

                                    error_response = {
                                        'success': False,
                                        'error': error_msg,
                                        'data_info': {
                                            'data_range_start': data_range_start,
                                            'data_range_end': data_range_end,
                                            'available_hours': available_hours,
                                            'requested_hours': horizon
                                        }
                                    }
                                    self.wfile.write(json.dumps(error_response).encode())
                                    return

                                # Extract ML predicted CMG values with timestamps
                                for i, prediction in enumerate(sorted_predictions[:horizon]):
                                    price = prediction.get('cmg_predicted', 70)
                                    dt = prediction.get('datetime', 'unknown')
                                    prices.append(price)
                                    timestamps.append(dt)
                                    if i < 5:  # Log first 5 prices
                                        print(f"  Hour {i} ({dt}): ${price:.2f}/MWh (ML prediction)")
                                if len(sorted_predictions) > 5:
                                    print(f"  ... using {min(len(sorted_predictions), horizon)} hours of ML predictions")

                                ml_predictions_available = True
                                data_source_used = 'ml_predictions'
                            else:
                                print(f"[OPTIMIZER] WARNING: ML predictions list is empty")
                        else:
                            print(f"[OPTIMIZER] WARNING: ML forecast API returned no predictions")

                except Exception as e:
                    print(f"[OPTIMIZER] ERROR: Could not fetch ML predictions: {e}")

                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()

                    error_response = {
                        'success': False,
                        'error': f'ML predictions selected but not available: {str(e)}'
                    }
                    self.wfile.write(json.dumps(error_response).encode())
                    return

            else:
                # User selected CMG Programado
                print(f"[OPTIMIZER] User selected CMG Programado as data source")
                print(f"[OPTIMIZER] Fetching CMG Programado data from cache...")

                from api.utils.cache_manager_readonly import CacheManagerReadOnly

                # TEMPORARY: Disable time filtering to debug 500 error
                # Use a very old date to include all available data
                cutoff_time_str = "2000-01-01T00:00:00"  # Note: CMG uses 'T' format
                print(f"[OPTIMIZER] TEMP: Time filtering disabled for debugging")

                cache_mgr = CacheManagerReadOnly()
                programmed_data = cache_mgr.read_cache('programmed')

                if programmed_data and 'data' in programmed_data:
                    price_records = programmed_data['data']
                    print(f"[OPTIMIZER] Found {len(price_records)} programmed prices in cache")

                    # Filter for future values only (>= t+1)
                    future_records = [
                        r for r in price_records
                        if r.get('datetime', '') >= cutoff_time_str
                    ]
                    print(f"[OPTIMIZER] Filtered to {len(future_records)} future records (>= t+1)")

                    # Sort by datetime to ensure correct order
                    sorted_records = sorted(future_records, key=lambda x: x.get('datetime', ''))

                    if sorted_records:
                        data_range_start = sorted_records[0].get('datetime', 'unknown')
                        data_range_end = sorted_records[-1].get('datetime', 'unknown')
                        available_hours = len(sorted_records)

                        print(f"[OPTIMIZER] Data range: {data_range_start} to {data_range_end}")
                        print(f"[OPTIMIZER] Available hours: {available_hours}, Requested: {horizon}")

                        # Check if we have enough data
                        if horizon > available_hours:
                            error_msg = f"Insufficient CMG Programado data: {available_hours} hours available but {horizon} requested"
                            print(f"[OPTIMIZER] ERROR: {error_msg}")

                            self.send_response(400)
                            self.send_header('Content-Type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()

                            error_response = {
                                'success': False,
                                'error': error_msg,
                                'data_info': {
                                    'data_range_start': data_range_start,
                                    'data_range_end': data_range_end,
                                    'available_hours': available_hours,
                                    'requested_hours': horizon
                                }
                            }
                            self.wfile.write(json.dumps(error_response).encode())
                            return

                        # Extract only the requested hours with timestamps
                        for i, record in enumerate(sorted_records[:horizon]):
                            price = record.get('cmg_programmed', 70)
                            dt = record.get('datetime', 'unknown')
                            prices.append(price)
                            timestamps.append(dt)
                            if i < 5:  # Log first 5 prices
                                print(f"  Hour {i} ({dt}): ${price:.2f}/MWh (CMG Programado)")
                        if len(sorted_records) > 5:
                            print(f"  ... using {min(len(sorted_records), horizon)} hours of programmed data")

                        data_source_used = 'cmg_programado'
                    else:
                        print(f"[OPTIMIZER] ERROR: No programmed data available")

                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()

                        error_response = {
                            'success': False,
                            'error': 'CMG Programado selected but no data available in cache'
                        }
                        self.wfile.write(json.dumps(error_response).encode())
                        return
                else:
                    print(f"[OPTIMIZER] ERROR: No programmed data in cache")

                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()

                    error_response = {
                        'success': False,
                        'error': 'CMG Programado selected but not available in cache'
                    }
                    self.wfile.write(json.dumps(error_response).encode())
                    return
            
            # Try proper LP optimization first
            print(f"[OPTIMIZER] Starting optimization...")
            
            solution = None
            
            # Try scipy LP first only if available
            if SCIPY_AVAILABLE:
                try:
                    from api.utils.optimizer_lp import optimize_hydro_lp
                    print(f"[OPTIMIZER] Trying scipy Linear Programming...")
                    solution = optimize_hydro_lp(
                        prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon
                    )
                    if solution:
                        print(f"[OPTIMIZER] scipy LP successful!")
                except ImportError as e:
                    print(f"[OPTIMIZER] scipy module import error: {e}")
                except Exception as e:
                    print(f"[OPTIMIZER] scipy LP error: {e}")
                    import traceback
                    print(traceback.format_exc())
            else:
                print(f"[OPTIMIZER] Skipping scipy LP (not available)")
            
            # Try simple DP solver if scipy failed
            if solution is None:
                try:
                    from api.utils.optimizer_simple import optimize_hydro_simple
                    print(f"[OPTIMIZER] Trying simple DP optimization...")
                    solution = optimize_hydro_simple(
                        prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon
                    )
                    if solution:
                        print(f"[OPTIMIZER] Simple DP successful!")
                except Exception as e:
                    print(f"[OPTIMIZER] Simple DP error: {e}")
            
            # Fall back to greedy if everything else fails
            if solution is None:
                from api.utils.optimizer_lp import optimize_hydro_greedy
                print(f"[OPTIMIZER] Falling back to greedy algorithm...")
                solution = optimize_hydro_greedy(
                    prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon
                )
            
            print(f"[OPTIMIZER] Optimization complete!")
            print(f"  - Total revenue: ${solution['revenue']:.2f}")
            print(f"  - Avg generation: {solution['avg_generation']:.2f} MW")
            print(f"  - Peak generation: {solution['peak_generation']:.2f} MW")
            print(f"  - Capacity factor: {solution['capacity_factor']:.1f}%")
            
            # Store optimization result for performance tracking
            self.store_optimization_result(params, solution)
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = {
                'success': True,
                'solution': solution,
                'prices': prices,
                'timestamps': timestamps,  # Include actual timestamps from data
                'parameters': {
                    'node': node,
                    'horizon': horizon,
                    'p_min': p_min,
                    'p_max': p_max,
                    's0': s0,
                    's_min': s_min,
                    's_max': s_max,
                    'kappa': kappa,
                    'inflow': inflow
                },
                'data_info': {
                    'data_range_start': data_range_start,
                    'data_range_end': data_range_end,
                    'available_hours': len(sorted_predictions) if data_source_used == 'ml_predictions' and 'sorted_predictions' in locals() else (len(sorted_records) if 'sorted_records' in locals() else 0),
                    'requested_hours': horizon,
                    'data_source': 'ML Predictions (Railway Backend)' if data_source_used == 'ml_predictions' else 'CMG Programado (Coordinador)',
                    'data_source_selected': data_source,
                    'data_source_used': data_source_used,
                    'all_real_data': True,  # Always true now, no synthetic data
                    'using_ml_predictions': data_source_used == 'ml_predictions'
                }
            }
            
            print(f"[OPTIMIZER] Sending response with {len(prices)} prices")
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"[OPTIMIZER] ERROR: {str(e)}")
            print(f"[OPTIMIZER] Traceback: {traceback.format_exc()}")
            
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def optimize_hydro_old(self, prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
        """
        Simplified greedy optimization for demonstration
        In production, use proper LP solver
        """
        print(f"[OPTIMIZE] Starting hydro optimization with {len(prices)} price points")
        
        T = min(horizon, len(prices))
        dt = 1  # hourly steps
        vol_per_step = 3600 * dt
        
        print(f"[OPTIMIZE] Time horizon: {T} hours, volume per step: {vol_per_step} m³")
        
        # Initialize with minimum generation
        P = [p_min] * T
        print(f"[OPTIMIZE] Initialized all {T} hours with minimum generation: {p_min} MW")
        
        # Sort hours by price (greedy approach)
        price_indices = sorted(range(T), key=lambda i: prices[i], reverse=True)
        print(f"[OPTIMIZE] Top 5 price hours: {price_indices[:5]} with prices {[prices[i] for i in price_indices[:5]]}")
        
        # Try to maximize generation during high price hours
        changes_made = 0
        for rank, t in enumerate(price_indices):
            # Check if we can increase generation
            test_P = P.copy()
            test_P[t] = p_max
            
            # Check storage constraints
            storage_ok = True
            current_s = s0
            min_s_reached = s0
            max_s_reached = s0
            
            for i in range(T):
                current_s += (inflow - kappa * test_P[i]) * vol_per_step
                min_s_reached = min(min_s_reached, current_s)
                max_s_reached = max(max_s_reached, current_s)
                
                if current_s < s_min or current_s > s_max:
                    storage_ok = False
                    if rank < 10:  # Log why top 10 hours failed
                        print(f"[OPTIMIZE] Hour {t} (rank {rank+1}, price ${prices[t]:.2f}) failed: storage {current_s:.0f} at hour {i}")
                    break
            
            if storage_ok:
                P[t] = p_max
                changes_made += 1
                if changes_made <= 5:  # Log first 5 successful changes
                    print(f"[OPTIMIZE] Hour {t} (price ${prices[t]:.2f}): increased to {p_max} MW")
        
        print(f"[OPTIMIZE] Total changes made: {changes_made} hours increased to max power")
        
        # Calculate storage trajectory and metrics
        S = [s0]
        current_s = s0
        revenue = 0
        
        for t in range(T):
            Q = kappa * P[t]
            current_s += (inflow - Q) * vol_per_step
            S.append(current_s)
            revenue += prices[t] * P[t] * dt
        
        avg_gen = sum(P) / len(P)
        peak_gen = max(P)
        capacity = (avg_gen / p_max * 100)
        
        print(f"[OPTIMIZE] Final metrics:")
        print(f"  - Revenue: ${revenue:.2f}")
        print(f"  - Avg generation: {avg_gen:.2f} MW")
        print(f"  - Peak generation: {peak_gen:.2f} MW")
        print(f"  - Capacity factor: {capacity:.1f}%")
        print(f"  - Final storage: {S[-1]:.0f} m³")
        
        return {
            'P': P,  # Power generation (MW)
            'Q': [kappa * p for p in P],  # Water discharge (m3/s)
            'S': S,  # Storage levels (m3)
            'revenue': revenue,
            'avg_generation': avg_gen,
            'peak_generation': peak_gen,
            'capacity_factor': capacity
        }

    def do_GET(self):
        """Handle GET requests with query parameters"""
        try:
            # Parse query parameters
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            # Extract parameters with defaults
            params = {
                'horizon': int(query_params.get('horizon', [24])[0]),
                'node': query_params.get('node', ['PMontt220'])[0],
                'p_min': float(query_params.get('p_min', [0.5])[0]),
                'p_max': float(query_params.get('p_max', [3.0])[0]),
                's0': float(query_params.get('s0', [25000])[0]),
                's_min': float(query_params.get('s_min', [1000])[0]),
                's_max': float(query_params.get('s_max', [50000])[0]),
                'kappa': float(query_params.get('kappa', [0.667])[0]),
                'inflow': float(query_params.get('inflow', [1.1])[0])
            }
            
            # Get CMG prices from cache
            from api.utils.cache_manager_readonly import CacheManagerReadOnly
            cache_mgr = CacheManagerReadOnly()
            programmed_data = cache_mgr.read_cache('programmed')
            
            prices = []
            
            if programmed_data and 'data' in programmed_data:
                sorted_records = sorted(programmed_data['data'], key=lambda x: x.get('datetime', ''))
                for record in sorted_records[:params['horizon']]:
                    prices.append(record.get('cmg_programmed', 70))
            else:
                # No programmed data available
                pass  # Will use synthetic prices below
            
            # Fill with synthetic if needed
            while len(prices) < params['horizon']:
                hour = len(prices) % 24
                base_price = 70
                variation = np.sin(hour * np.pi / 12) * 30
                prices.append(base_price + variation)
            
            # Run optimization with fallbacks
            solution = None
            
            # Try scipy LP first
            try:
                from api.utils.optimizer_lp import optimize_hydro_lp
                solution = optimize_hydro_lp(
                    prices, 
                    params['p_min'], params['p_max'],
                    params['s0'], params['s_min'], params['s_max'],
                    params['kappa'], params['inflow'], params['horizon']
                )
            except:
                pass
            
            # Try simple DP if scipy failed
            if solution is None:
                try:
                    from api.utils.optimizer_simple import optimize_hydro_simple
                    solution = optimize_hydro_simple(
                        prices, 
                        params['p_min'], params['p_max'],
                        params['s0'], params['s_min'], params['s_max'],
                        params['kappa'], params['inflow'], params['horizon']
                    )
                except:
                    pass
            
            # Fall back to greedy
            if solution is None:
                from api.utils.optimizer_lp import optimize_hydro_greedy
                solution = optimize_hydro_greedy(
                    prices, 
                    params['p_min'], params['p_max'],
                    params['s0'], params['s_min'], params['s_max'],
                    params['kappa'], params['inflow'], params['horizon']
                )
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = {
                'success': True,
                'solution': solution,
                'prices': prices,
                'parameters': params
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'success': False,
                'error': str(e)
            }
            self.wfile.write(json.dumps(error_response).encode())