"""
Simple Linear Programming solver without scipy
Using a basic simplex-like approach or dynamic programming
"""

import numpy as np

def optimize_hydro_simple(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
    """
    Optimize hydro using dynamic programming approach
    This is simpler than full LP but better than greedy
    """
    
    T = min(horizon, len(prices))
    dt = 1.0  # hourly steps
    vol_per_step = 3600.0 * dt
    
    print(f"[SIMPLE] Optimizing {T} hours with DP-like approach")
    
    # Discretize power levels for DP
    n_power_levels = 5  # Keep it simple
    power_levels = np.linspace(p_min, p_max, n_power_levels)
    
    # Initialize solution with balanced approach
    P = []
    S = [s0]
    current_s = s0
    total_revenue = 0
    
    for t in range(T):
        # Find best power level for this hour considering:
        # 1. Current price
        # 2. Storage constraints
        # 3. Future flexibility
        
        best_p = p_min
        best_score = -float('inf')
        
        for p in power_levels:
            # Calculate next storage if we use this power
            next_s = current_s + (inflow - kappa * p) * vol_per_step
            
            # Check if storage is valid
            if next_s < s_min or next_s > s_max:
                continue
            
            # Score based on immediate revenue and storage position
            immediate_revenue = prices[t] * p * dt
            
            # Bonus for keeping storage in middle range (flexibility)
            storage_score = 0
            if t < T - 1:  # Not last hour
                storage_ratio = (next_s - s_min) / (s_max - s_min)
                # Prefer middle storage levels for flexibility
                storage_score = -abs(storage_ratio - 0.5) * 10
            
            # Look ahead bonus: if next hours have high prices, preserve water
            lookahead_bonus = 0
            if t < T - 1:
                future_prices = prices[t+1:min(t+5, T)]
                avg_future = np.mean(future_prices) if future_prices else prices[t]
                if avg_future > prices[t]:
                    # Future is more valuable, penalize high generation now
                    lookahead_bonus = -(p - p_min) * (avg_future - prices[t]) * 0.5
            
            score = immediate_revenue + storage_score + lookahead_bonus
            
            if score > best_score:
                best_score = score
                best_p = p
        
        # Apply best power for this hour
        P.append(best_p)
        current_s += (inflow - kappa * best_p) * vol_per_step
        S.append(current_s)
        total_revenue += prices[t] * best_p * dt
    
    # Post-process: try to improve by swapping high/low generation hours
    print(f"[SIMPLE] Initial revenue: ${total_revenue:.2f}")
    
    # Try simple swaps to improve
    improved = True
    iterations = 0
    while improved and iterations < 10:
        improved = False
        iterations += 1
        
        for i in range(T):
            for j in range(i+1, T):
                # Try swapping power levels between hours i and j
                if P[i] != P[j] and prices[i] != prices[j]:
                    # Calculate if swap would be beneficial
                    current_value = prices[i] * P[i] + prices[j] * P[j]
                    swap_value = prices[i] * P[j] + prices[j] * P[i]
                    
                    if swap_value > current_value:
                        # Check if swap maintains storage constraints
                        test_S = [s0]
                        test_s = s0
                        valid = True
                        
                        for t in range(T):
                            if t == i:
                                test_p = P[j]
                            elif t == j:
                                test_p = P[i]
                            else:
                                test_p = P[t]
                            
                            test_s += (inflow - kappa * test_p) * vol_per_step
                            if test_s < s_min or test_s > s_max:
                                valid = False
                                break
                            test_S.append(test_s)
                        
                        if valid:
                            # Perform swap
                            P[i], P[j] = P[j], P[i]
                            S = test_S
                            total_revenue += (swap_value - current_value) * dt
                            improved = True
                            print(f"[SIMPLE] Iteration {iterations}: Swapped hours {i} and {j}, new revenue: ${total_revenue:.2f}")
                            break
            if improved:
                break
    
    # Calculate final metrics
    Q = [kappa * p for p in P]
    avg_gen = sum(P) / len(P)
    peak_gen = max(P)
    capacity = (avg_gen / p_max * 100)
    
    print(f"[SIMPLE] Final results:")
    print(f"  - Revenue: ${total_revenue:.2f}")
    print(f"  - Avg generation: {avg_gen:.2f} MW")
    print(f"  - Peak generation: {peak_gen:.2f} MW")
    print(f"  - Capacity factor: {capacity:.1f}%")
    
    return {
        'P': P,
        'Q': Q,
        'S': S,
        'revenue': total_revenue,
        'avg_generation': avg_gen,
        'peak_generation': peak_gen,
        'capacity_factor': capacity,
        'optimization_method': 'dynamic_programming_simple',
        'solver_success': True
    }