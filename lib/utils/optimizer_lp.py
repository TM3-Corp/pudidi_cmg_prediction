"""
Proper Linear Programming optimization for hydro dispatch
Using scipy.optimize.linprog (works on Vercel)
With equal initial/final storage constraint
"""

import numpy as np
from scipy.optimize import linprog

def optimize_hydro_lp(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
    """
    Solve hydro optimization using Linear Programming
    
    Decision variables: P[0], P[1], ..., P[T-1]
    
    Objective: maximize Σ(price[t] * P[t] * dt)
    
    Constraints:
    1. Power bounds: p_min <= P[t] <= p_max
    2. Storage evolution: S[t+1] = S[t] + (I[t] - kappa*P[t])*3600
    3. Storage bounds: s_min <= S[t] <= s_max
    """
    
    # Validate inputs
    if not prices or len(prices) == 0:
        print("[LP] Error: Empty or invalid price array")
        return {
            'P': [p_min] * horizon,  # Return minimum generation
            'S': [s0] * (horizon + 1),
            'revenue': 0,
            'success': False,
            'message': 'Empty price array'
        }
    
    T = min(horizon, len(prices))
    if T == 0:
        print("[LP] Error: No valid time periods")
        return {
            'P': [],
            'S': [s0],
            'revenue': 0,
            'success': False,
            'message': 'No valid time periods'
        }
    
    dt = 1.0  # hourly steps
    vol_per_step = 3600.0 * dt  # seconds per step
    
    print(f"[LP] Setting up optimization for {T} time steps")
    
    # Decision variables: P[0], ..., P[T-1]
    # We'll use scipy's linprog which minimizes, so we negate the objective
    
    # Objective: minimize -Σ(price[t] * P[t] * dt)
    c = [-price * dt for price in prices[:T]]
    
    # Bounds for P[t]: p_min <= P[t] <= p_max
    bounds = [(p_min, p_max) for _ in range(T)]
    
    # Storage constraints as linear inequalities
    # We need to express storage evolution constraints
    
    # Storage at time t: S[t] = s0 + Σ(i=0 to t-1)[(inflow - kappa*P[i])*vol_per_step]
    # This needs to satisfy: s_min <= S[t] <= s_max
    
    # Build constraint matrix for storage bounds
    # For each time step t, we have two constraints:
    # 1. S[t] >= s_min  =>  s0 + Σ(inflow - kappa*P[i])*vol >= s_min
    # 2. S[t] <= s_max  =>  s0 + Σ(inflow - kappa*P[i])*vol <= s_max
    
    A_ub = []
    b_ub = []

    # EQUAL STORAGE CONSTRAINT: S[final] = S[initial]
    # This is a REQUIRED operational constraint for the hydroelectric plant
    # Ensures sustainable day-to-day operation and respects water commitments
    # Σ(inflow - kappa*P[i])*vol = 0 over the entire horizon
    # Or equivalently: Σ(kappa*P[i]) = T * inflow
    A_eq = []
    b_eq = []

    # Equal storage constraint: sum of all discharges equals sum of all inflows
    equal_storage_row = [kappa * vol_per_step] * T
    equal_storage_value = T * inflow * vol_per_step
    A_eq.append(equal_storage_row)
    b_eq.append(equal_storage_value)
    
    for t in range(T):
        # Lower bound: -S[t] <= -s_min
        # -s0 - Σ(inflow*vol) + Σ(kappa*P[i]*vol) <= -s_min
        row_lower = [0.0] * T
        for i in range(t + 1):
            row_lower[i] = kappa * vol_per_step
        
        b_lower = -s_min + s0 + sum(inflow * vol_per_step for _ in range(t + 1))
        A_ub.append(row_lower)
        b_ub.append(b_lower)
        
        # Upper bound: S[t] <= s_max
        # s0 + Σ(inflow*vol) - Σ(kappa*P[i]*vol) <= s_max
        row_upper = [0.0] * T
        for i in range(t + 1):
            row_upper[i] = -kappa * vol_per_step
        
        b_upper = s_max - s0 - sum(inflow * vol_per_step for _ in range(t + 1))
        A_ub.append(row_upper)
        b_ub.append(b_upper)
    
    print(f"[LP] Created {len(A_ub)} inequality constraints")
    if c:
        print(f"[LP] Objective coefficients range: [{min(c):.2f}, {max(c):.2f}]")
    else:
        print("[LP] Warning: Empty objective coefficients")
    
    # Solve the LP
    try:
        result = linprog(
            c=c,
            A_ub=A_ub if A_ub else None,
            b_ub=b_ub if b_ub else None,
            A_eq=np.array(A_eq) if A_eq else None,
            b_eq=np.array(b_eq) if b_eq else None,
            bounds=bounds,
            method='highs',  # Use HiGHS solver (efficient)
            options={'disp': False}
        )
        
        if result.success:
            P = list(result.x)
            print(f"[LP] Optimization successful! Objective value: {-result.fun:.2f}")
            
            # Calculate Q and S from P
            Q = [kappa * p for p in P]
            
            # Calculate storage trajectory
            S = [s0]
            current_s = s0
            for t in range(T):
                current_s += (inflow - Q[t]) * vol_per_step
                S.append(current_s)
            
            # Calculate total revenue
            revenue = sum(prices[t] * P[t] * dt for t in range(T))
            
            # Metrics
            avg_gen = sum(P) / len(P)
            peak_gen = max(P)
            capacity = (avg_gen / p_max * 100)
            
            print(f"[LP] Results:")
            print(f"  - Revenue: ${revenue:.2f}")
            print(f"  - Avg generation: {avg_gen:.2f} MW")
            print(f"  - Peak generation: {peak_gen:.2f} MW")
            print(f"  - Capacity factor: {capacity:.1f}%")
            print(f"  - Final storage: {S[-1]:.0f} m³")
            
            # Show generation pattern
            high_gen_hours = sum(1 for p in P if p > (p_min + p_max) / 2)
            print(f"[LP] High generation in {high_gen_hours}/{T} hours")
            
            return {
                'P': P,  # Power generation (MW)
                'Q': Q,  # Water discharge (m3/s)
                'S': S,  # Storage levels (m3)
                'revenue': revenue,
                'avg_generation': avg_gen,
                'peak_generation': peak_gen,
                'capacity_factor': capacity,
                'optimization_method': 'linear_programming',
                'solver_success': True
            }
        else:
            print(f"[LP] Optimization failed: {result.message}")
            # Fall back to greedy if LP fails
            return None
            
    except Exception as e:
        print(f"[LP] Error in optimization: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None

def optimize_hydro_greedy(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
    """
    Fallback greedy optimization (original simplified version)
    """
    print(f"[GREEDY] Using fallback greedy optimization")
    
    T = min(horizon, len(prices))
    dt = 1  # hourly steps
    vol_per_step = 3600 * dt
    
    # Initialize with minimum generation
    P = [p_min] * T
    
    # Sort hours by price (greedy approach)
    price_indices = sorted(range(T), key=lambda i: prices[i], reverse=True)
    
    # Try to maximize generation during high price hours
    changes_made = 0
    for rank, t in enumerate(price_indices):
        test_P = P.copy()
        test_P[t] = p_max
        
        # Check storage constraints
        storage_ok = True
        current_s = s0
        
        for i in range(T):
            current_s += (inflow - kappa * test_P[i]) * vol_per_step
            if current_s < s_min or current_s > s_max:
                storage_ok = False
                break
        
        if storage_ok:
            P[t] = p_max
            changes_made += 1
    
    print(f"[GREEDY] Made {changes_made} changes to max power")
    
    # Calculate results
    Q = [kappa * p for p in P]
    S = [s0]
    current_s = s0
    revenue = 0
    
    for t in range(T):
        current_s += (inflow - Q[t]) * vol_per_step
        S.append(current_s)
        revenue += prices[t] * P[t] * dt
    
    avg_gen = sum(P) / len(P)
    peak_gen = max(P)
    capacity = (avg_gen / p_max * 100)
    
    return {
        'P': P,
        'Q': Q,
        'S': S,
        'revenue': revenue,
        'avg_generation': avg_gen,
        'peak_generation': peak_gen,
        'capacity_factor': capacity,
        'optimization_method': 'greedy_heuristic',
        'solver_success': False
    }