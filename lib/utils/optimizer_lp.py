"""
Proper Linear Programming optimization for hydro dispatch
Using scipy.optimize.linprog (works on Vercel)
With equal initial/final storage constraint and spillage modeling
"""

import numpy as np
from scipy.optimize import linprog

def optimize_hydro_lp(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
    """
    Solve hydro optimization using Linear Programming with spillage modeling.

    Decision variables: P[0..T-1] (power MW), spill[0..T-1] (spillage m³/s)

    Objective: maximize Σ(price[t] * P[t] * dt)

    Constraints:
    1. Power bounds: p_min <= P[t] <= p_max
    2. Spillage bounds: 0 <= spill[t] (no upper bound)
    3. Storage evolution: S[t+1] = S[t] + (inflow - kappa*P[t] - spill[t]) * 3600
    4. Storage bounds: s_min <= S[t] <= s_max
    5. Equal storage (when feasible): S[T] = S[0]
    """

    if not prices or len(prices) == 0:
        print("[LP] Error: Empty or invalid price array")
        return {
            'P': [p_min] * horizon,
            'S': [s0] * (horizon + 1),
            'revenue': 0,
            'success': False,
            'message': 'Empty price array',
            'warnings': []
        }

    T = min(horizon, len(prices))
    if T == 0:
        print("[LP] Error: No valid time periods")
        return {
            'P': [],
            'S': [s0],
            'revenue': 0,
            'success': False,
            'message': 'No valid time periods',
            'warnings': []
        }

    dt = 1.0
    vol_per_step = 3600.0 * dt

    # --- Feasibility check ---
    max_discharge = kappa * p_max
    needs_spillage = inflow > max_discharge
    warnings = []

    if needs_spillage:
        net_inflow = inflow - max_discharge
        daily_excess = net_inflow * vol_per_step * T
        warnings.append({
            'type': 'spillage_required',
            'message': (
                f'Caudal ({inflow:.2f} m³/s) excede la descarga máxima de turbinas '
                f'({max_discharge:.3f} m³/s). Se requiere vertimiento.'
            ),
            'details': {
                'inflow': inflow,
                'max_discharge': max_discharge,
                'net_excess_per_hour': net_inflow * vol_per_step,
                'total_excess': daily_excess
            }
        })
        print(f"[LP] WARNING: Inflow ({inflow}) > max discharge ({max_discharge:.3f}). Spillage required.")
        print(f"[LP] Net excess per hour: {net_inflow * vol_per_step:.0f} m³")

    print(f"[LP] Setting up optimization for {T} time steps (spillage={'yes' if needs_spillage else 'no'})")

    # Decision variables layout:
    #   x[0..T-1]     = P[t] (power generation)
    #   x[T..2T-1]    = spill[t] (spillage in m³/s)
    n_vars = 2 * T

    # Objective: minimize -Σ(price[t] * P[t] * dt) + 0 * spill[t]
    # Spillage has zero cost (wasted water, no revenue impact)
    c = [-price * dt for price in prices[:T]] + [0.0] * T

    # Bounds: p_min <= P[t] <= p_max, 0 <= spill[t] <= None
    bounds = [(p_min, p_max) for _ in range(T)] + [(0, None) for _ in range(T)]

    # Storage constraints
    # S[t+1] = S[0] + Σ_{i=0}^{t} (inflow - kappa*P[i] - spill[i]) * vol_per_step
    # Must satisfy: s_min <= S[t+1] <= s_max

    A_ub = []
    b_ub = []
    A_eq = []
    b_eq = []

    # Equal storage constraint: S[T] = S[0] (only when feasible)
    # Σ (kappa*P[i] + spill[i]) * vol = T * inflow * vol
    if not needs_spillage:
        eq_row = [0.0] * n_vars
        for i in range(T):
            eq_row[i] = kappa * vol_per_step       # P coefficient
            eq_row[T + i] = vol_per_step            # spill coefficient
        eq_val = T * inflow * vol_per_step
        A_eq.append(eq_row)
        b_eq.append(eq_val)

    for t in range(T):
        # Cumulative inflow volume up to step t+1
        cum_inflow_vol = (t + 1) * inflow * vol_per_step

        # Lower bound: S[t+1] >= s_min
        # s0 + cum_inflow_vol - Σ_{i<=t}(kappa*P[i] + spill[i])*vol >= s_min
        # => Σ_{i<=t}(kappa*P[i] + spill[i])*vol <= s0 + cum_inflow_vol - s_min
        row_lower = [0.0] * n_vars
        for i in range(t + 1):
            row_lower[i] = kappa * vol_per_step        # P coefficient
            row_lower[T + i] = vol_per_step             # spill coefficient
        b_lower = s0 + cum_inflow_vol - s_min
        A_ub.append(row_lower)
        b_ub.append(b_lower)

        # Upper bound: S[t+1] <= s_max
        # s0 + cum_inflow_vol - Σ_{i<=t}(kappa*P[i] + spill[i])*vol <= s_max
        # => -Σ_{i<=t}(kappa*P[i] + spill[i])*vol <= s_max - s0 - cum_inflow_vol
        row_upper = [0.0] * n_vars
        for i in range(t + 1):
            row_upper[i] = -kappa * vol_per_step       # P coefficient
            row_upper[T + i] = -vol_per_step            # spill coefficient
        b_upper = s_max - s0 - cum_inflow_vol
        A_ub.append(row_upper)
        b_ub.append(b_upper)

    print(f"[LP] Created {len(A_ub)} inequality + {len(A_eq)} equality constraints, {n_vars} variables")

    # Solve the LP
    try:
        result = linprog(
            c=c,
            A_ub=A_ub if A_ub else None,
            b_ub=b_ub if b_ub else None,
            A_eq=np.array(A_eq) if A_eq else None,
            b_eq=np.array(b_eq) if b_eq else None,
            bounds=bounds,
            method='highs',
            options={'disp': False}
        )

        if result.success:
            P = list(result.x[:T])
            spill = list(result.x[T:])
            print(f"[LP] Optimization successful! Objective value: {-result.fun:.2f}")

            Q = [kappa * p for p in P]

            # Calculate storage trajectory
            S = [s0]
            current_s = s0
            storage_violations = []
            for t in range(T):
                current_s += (inflow - Q[t] - spill[t]) * vol_per_step
                # Clamp to bounds (numerical precision)
                if current_s > s_max + 1:
                    storage_violations.append({'hour': t + 1, 'storage': current_s, 'bound': 's_max'})
                elif current_s < s_min - 1:
                    storage_violations.append({'hour': t + 1, 'storage': current_s, 'bound': 's_min'})
                current_s = max(s_min, min(s_max, current_s))
                S.append(current_s)

            if storage_violations:
                warnings.append({
                    'type': 'storage_violations',
                    'message': f'Almacenamiento excedió límites en {len(storage_violations)} hora(s) (corregido con vertimiento).',
                    'violations': storage_violations[:5]
                })

            revenue = sum(prices[t] * P[t] * dt for t in range(T))
            avg_gen = sum(P) / len(P)
            peak_gen = max(P)
            capacity = (avg_gen / p_max * 100)
            total_spill = sum(s * vol_per_step for s in spill)
            spill_hours = [t for t in range(T) if spill[t] > 0.001]

            if spill_hours:
                warnings.append({
                    'type': 'spillage_active',
                    'message': f'Vertimiento activo en {len(spill_hours)} hora(s). Volumen total vertido: {total_spill:.0f} m³.',
                    'spill_hours': spill_hours,
                    'total_spill_m3': total_spill
                })

            print(f"[LP] Results:")
            print(f"  - Revenue: ${revenue:.2f}")
            print(f"  - Avg generation: {avg_gen:.2f} MW")
            print(f"  - Peak generation: {peak_gen:.2f} MW")
            print(f"  - Capacity factor: {capacity:.1f}%")
            print(f"  - Final storage: {S[-1]:.0f} m³")
            if spill_hours:
                print(f"  - Spillage in {len(spill_hours)} hours, total: {total_spill:.0f} m³")

            return {
                'P': P,
                'Q': Q,
                'S': S,
                'spill': spill,
                'revenue': revenue,
                'avg_generation': avg_gen,
                'peak_generation': peak_gen,
                'capacity_factor': capacity,
                'optimization_method': 'linear_programming',
                'solver_success': True,
                'warnings': warnings,
                'spill_hours': spill_hours,
                'total_spill_m3': total_spill
            }
        else:
            print(f"[LP] Optimization failed: {result.message}")
            return None

    except Exception as e:
        print(f"[LP] Error in optimization: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None

def optimize_hydro_greedy(prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon):
    """
    Fallback greedy optimization with spillage support
    """
    print(f"[GREEDY] Using fallback greedy optimization")

    T = min(horizon, len(prices))
    dt = 1
    vol_per_step = 3600 * dt
    max_discharge = kappa * p_max
    needs_spillage = inflow > max_discharge
    warnings = []

    if needs_spillage:
        warnings.append({
            'type': 'spillage_required',
            'message': f'Caudal ({inflow:.2f} m³/s) excede descarga máxima ({max_discharge:.3f} m³/s). Vertimiento requerido.',
        })

    # Initialize with minimum generation
    P = [p_min] * T

    # Sort hours by price (greedy approach)
    price_indices = sorted(range(T), key=lambda i: prices[i], reverse=True)

    # Try to maximize generation during high price hours
    changes_made = 0
    for rank, t in enumerate(price_indices):
        test_P = P.copy()
        test_P[t] = p_max

        # Check storage constraints (with spillage clamping)
        storage_ok = True
        current_s = s0

        for i in range(T):
            net = inflow - kappa * test_P[i]
            current_s += net * vol_per_step
            # Allow spillage: clamp at s_max
            if current_s > s_max:
                current_s = s_max
            if current_s < s_min:
                storage_ok = False
                break

        if storage_ok:
            P[t] = p_max
            changes_made += 1

    print(f"[GREEDY] Made {changes_made} changes to max power")

    # Calculate results with spillage
    Q = [kappa * p for p in P]
    S = [s0]
    spill = [0.0] * T
    current_s = s0
    revenue = 0

    for t in range(T):
        net = inflow - Q[t]
        new_s = current_s + net * vol_per_step
        if new_s > s_max:
            spill[t] = (new_s - s_max) / vol_per_step
            new_s = s_max
        current_s = new_s
        S.append(current_s)
        revenue += prices[t] * P[t] * dt

    avg_gen = sum(P) / len(P)
    peak_gen = max(P)
    capacity = (avg_gen / p_max * 100)
    total_spill = sum(s * vol_per_step for s in spill)
    spill_hours = [t for t in range(T) if spill[t] > 0.001]

    if spill_hours:
        warnings.append({
            'type': 'spillage_active',
            'message': f'Vertimiento activo en {len(spill_hours)} hora(s). Volumen total: {total_spill:.0f} m³.',
            'spill_hours': spill_hours,
            'total_spill_m3': total_spill
        })

    return {
        'P': P,
        'Q': Q,
        'S': S,
        'spill': spill,
        'revenue': revenue,
        'avg_generation': avg_gen,
        'peak_generation': peak_gen,
        'capacity_factor': capacity,
        'optimization_method': 'greedy_heuristic',
        'solver_success': False,
        'warnings': warnings,
        'spill_hours': spill_hours,
        'total_spill_m3': total_spill
    }
