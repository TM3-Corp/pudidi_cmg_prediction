"""
Simple Linear Programming solver without scipy
Using a basic simplex-like approach or dynamic programming
With spillage support for high-inflow scenarios
"""

import numpy as np

def optimize_hydro_simple(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
    """
    Optimize hydro using dynamic programming approach with spillage support.
    When storage would exceed s_max, excess water is spilled.
    """

    T = min(horizon, len(prices))
    dt = 1.0
    vol_per_step = 3600.0 * dt

    max_discharge = kappa * p_max
    needs_spillage = inflow > max_discharge
    warnings = []

    if needs_spillage:
        warnings.append({
            'type': 'spillage_required',
            'message': f'Caudal ({inflow:.2f} m³/s) excede descarga máxima ({max_discharge:.3f} m³/s). Vertimiento requerido.',
        })

    print(f"[SIMPLE] Optimizing {T} hours with DP-like approach (spillage={'yes' if needs_spillage else 'no'})")

    # Discretize power levels for DP
    n_power_levels = 5
    power_levels = np.linspace(p_min, p_max, n_power_levels)

    # Initialize solution with balanced approach
    P = []
    S = [s0]
    spill_values = []
    current_s = s0
    total_revenue = 0

    for t in range(T):
        best_p = p_min
        best_score = -float('inf')
        best_spill = 0.0

        for p in power_levels:
            # Calculate next storage
            net = inflow - kappa * p
            next_s = current_s + net * vol_per_step
            step_spill = 0.0

            # Spillage: if storage exceeds s_max, spill the excess
            if next_s > s_max:
                step_spill = (next_s - s_max) / vol_per_step
                next_s = s_max

            # Check if storage is valid (only reject if below s_min)
            if next_s < s_min:
                continue

            # Score based on immediate revenue and storage position
            immediate_revenue = prices[t] * p * dt

            # Bonus for keeping storage in middle range (flexibility)
            storage_score = 0
            if t < T - 1:
                storage_ratio = (next_s - s_min) / (s_max - s_min)
                storage_score = -abs(storage_ratio - 0.5) * 10

            # Look ahead bonus
            lookahead_bonus = 0
            if t < T - 1:
                future_prices = prices[t+1:min(t+5, T)]
                avg_future = np.mean(future_prices) if future_prices else prices[t]
                if avg_future > prices[t]:
                    lookahead_bonus = -(p - p_min) * (avg_future - prices[t]) * 0.5

            score = immediate_revenue + storage_score + lookahead_bonus

            if score > best_score:
                best_score = score
                best_p = p
                best_spill = step_spill

        # Apply best power for this hour
        P.append(best_p)
        net = inflow - kappa * best_p
        new_s = current_s + net * vol_per_step
        if new_s > s_max:
            best_spill = (new_s - s_max) / vol_per_step
            new_s = s_max
        spill_values.append(best_spill)
        current_s = new_s
        S.append(current_s)
        total_revenue += prices[t] * best_p * dt

    print(f"[SIMPLE] Initial revenue: ${total_revenue:.2f}")

    # Try simple swaps to improve
    improved = True
    iterations = 0
    while improved and iterations < 10:
        improved = False
        iterations += 1

        for i in range(T):
            for j in range(i+1, T):
                if P[i] != P[j] and prices[i] != prices[j]:
                    current_value = prices[i] * P[i] + prices[j] * P[j]
                    swap_value = prices[i] * P[j] + prices[j] * P[i]

                    if swap_value > current_value:
                        # Check if swap maintains storage constraints (with spillage)
                        test_S = [s0]
                        test_spill = [0.0] * T
                        test_s = s0
                        valid = True

                        for t_idx in range(T):
                            if t_idx == i:
                                test_p = P[j]
                            elif t_idx == j:
                                test_p = P[i]
                            else:
                                test_p = P[t_idx]

                            net = inflow - kappa * test_p
                            test_s += net * vol_per_step
                            if test_s > s_max:
                                test_spill[t_idx] = (test_s - s_max) / vol_per_step
                                test_s = s_max
                            if test_s < s_min:
                                valid = False
                                break
                            test_S.append(test_s)

                        if valid:
                            P[i], P[j] = P[j], P[i]
                            S = test_S
                            spill_values = test_spill
                            total_revenue += (swap_value - current_value) * dt
                            improved = True
                            break
            if improved:
                break

    # Recalculate final trajectory after swaps
    Q = [kappa * p for p in P]
    S = [s0]
    spill_values = [0.0] * T
    current_s = s0
    for t in range(T):
        net = inflow - Q[t]
        new_s = current_s + net * vol_per_step
        if new_s > s_max:
            spill_values[t] = (new_s - s_max) / vol_per_step
            new_s = s_max
        current_s = new_s
        S.append(current_s)

    avg_gen = sum(P) / len(P)
    peak_gen = max(P)
    capacity = (avg_gen / p_max * 100)
    total_spill = sum(s * vol_per_step for s in spill_values)
    spill_hours = [t for t in range(T) if spill_values[t] > 0.001]

    if spill_hours:
        warnings.append({
            'type': 'spillage_active',
            'message': f'Vertimiento activo en {len(spill_hours)} hora(s). Volumen total: {total_spill:.0f} m³.',
            'spill_hours': spill_hours,
            'total_spill_m3': total_spill
        })

    print(f"[SIMPLE] Final results:")
    print(f"  - Revenue: ${total_revenue:.2f}")
    print(f"  - Avg generation: {avg_gen:.2f} MW")
    print(f"  - Peak generation: {peak_gen:.2f} MW")
    print(f"  - Capacity factor: {capacity:.1f}%")
    if spill_hours:
        print(f"  - Spillage in {len(spill_hours)} hours, total: {total_spill:.0f} m³")

    return {
        'P': P,
        'Q': Q,
        'S': S,
        'spill': spill_values,
        'revenue': total_revenue,
        'avg_generation': avg_gen,
        'peak_generation': peak_gen,
        'capacity_factor': capacity,
        'optimization_method': 'dynamic_programming_simple',
        'solver_success': True,
        'warnings': warnings,
        'spill_hours': spill_hours,
        'total_spill_m3': total_spill
    }
