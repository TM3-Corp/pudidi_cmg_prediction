# Efficiency >100% Investigation

**Date:** October 6, 2025
**Issue:** Performance page showing efficiency >100% (programmed revenue > hindsight revenue)

---

## 🎯 The Problem

You saw:
```
Ingreso Optimizado (Programmed):  $1,499
Ingreso Óptimo (Hindsight):       $1,451  ← Should be highest!
Eficiencia:                        99.9% (capped from >100%)
```

**This is mathematically impossible** if both optimizations have:
- Same constraints (equal storage, power bounds, storage bounds)
- Same parameters (p_min, p_max, s0, s_min, s_max, kappa, inflow)
- Hindsight uses ACTUAL prices (should achieve maximum possible revenue)

---

## 🔍 Root Causes (Possible)

### 1. **Stored Optimization with Different Constraints** ⭐ (Most Likely)

From `api/performance.py` lines 543-555:
```python
# First try to fetch stored optimization results
stored_optimization = self.fetch_optimization_results(start_date)

if stored_optimization and 'power_schedule' in stored_optimization:
    # Use stored optimization results
    power_programmed = stored_optimization['power_schedule'][:horizon]

    # Calculate revenue using ACTUAL prices but STORED dispatch
    revenue_programmed = sum(
        power_programmed[i] * historical_prices[i]
        for i in range(min(len(power_programmed), len(historical_prices)))
    )
```

**The Issue:**
The stored optimization might have been run with **different constraints**:
- Different `s0` (initial storage)
- Different horizon (48h instead of 24h)
- Different `inflow`
- Different time of day (3PM vs 5PM)

**Example Scenario:**
```
Stored optimization (from 3PM):
  - s0 = 35,000 m³ (middle of range, more flexibility)
  - horizon = 48h
  - Optimized dispatch for hours 3PM-3PM next day
  - Revenue with actual prices: $1,499

Fresh hindsight (at rendering time):
  - s0 = 25,000 m³ (at minimum, less flexibility)
  - horizon = 24h
  - Optimized for hours 5PM-5PM next day
  - Revenue with actual prices: $1,451
```

The stored optimization had **more favorable constraints**, so it achieved higher revenue even though it used forecast prices during optimization.

### 2. **Revenue Calculation Inconsistency**

From `api/performance.py`:

**Programmed** (line 552-555):
```python
revenue_programmed = sum(
    power_programmed[i] * historical_prices[i]
    for i in range(min(len(power_programmed), len(historical_prices)))
)
```

**Hindsight** (line 601):
```python
revenue_hindsight = solution_hindsight['revenue']  # From optimizer
```

**The Issue:**
The optimizer calculates revenue as (from `optimizer_lp.py` line 141):
```python
revenue = sum(prices[t] * P[t] * dt for t in range(T))
```

If there's ANY difference in how these are calculated (rounding, range, etc.), you could get inconsistencies.

### 3. **Different Horizon Lengths**

If programmed optimization uses a longer horizon than hindsight:

```
Programmed: 48-hour optimization
  - More flexibility to shift generation
  - Can save water for hour 25-48 if needed
  - Higher revenue from hours 1-24

Hindsight: 24-hour optimization
  - Must meet equal storage constraint within 24h
  - Less flexibility
  - Lower revenue from hours 1-24
```

###  4. **Optimizer Numerical Issues**

Linear programming solvers might find different solutions if:
- Problem is numerically ill-conditioned
- Multiple optimal solutions exist (ties in prices)
- Solver tolerance settings differ

---

## 🔧 How to Diagnose

### Test 1: Check if Stored Optimization is Used

Add logging to see which path is taken:
```python
if stored_optimization:
    print(f"[DEBUG] Using STORED optimization")
    print(f"  Stored constraints: {stored_optimization.get('metadata')}")
else:
    print(f"[DEBUG] Running FRESH optimization")
```

### Test 2: Force Fresh Optimization for Both

Temporarily disable stored optimization:
```python
# stored_optimization = self.fetch_optimization_results(start_date)
stored_optimization = None  # Force fresh optimization
```

Then both programmed and hindsight will run with IDENTICAL constraints. If efficiency is still >100%, there's a deeper bug.

### Test 3: Log All Parameters

Add detailed logging:
```python
print(f"[DEBUG] Programmed optimization:")
print(f"  Prices (first 5): {programmed_prices[:5]}")
print(f"  s0={s0}, s_min={s_min}, s_max={s_max}")
print(f"  horizon={horizon}, inflow={inflow}")

print(f"[DEBUG] Hindsight optimization:")
print(f"  Prices (first 5): {historical_prices[:5]}")
print(f"  s0={s0}, s_min={s_min}, s_max={s_max}")
print(f"  horizon={horizon}, inflow={inflow}")
```

Compare the parameters - they should be IDENTICAL.

### Test 4: Compare Dispatch Schedules

```python
print(f"[DEBUG] Programmed dispatch (first 10h):")
for i in range(min(10, len(power_programmed))):
    print(f"  Hour {i}: {power_programmed[i]:.2f} MW @ ${historical_prices[i]:.2f}")

print(f"[DEBUG] Hindsight dispatch (first 10h):")
for i in range(min(10, len(power_hindsight))):
    print(f"  Hour {i}: {power_hindsight[i]:.2f} MW @ ${historical_prices[i]:.2f}")
```

If hindsight has objectively better dispatch (more generation at high prices), but lower revenue, there's a calculation bug.

### Test 5: Manual Revenue Verification

```python
# Manually calculate both revenues the same way
manual_revenue_programmed = sum(
    power_programmed[i] * historical_prices[i]
    for i in range(min(len(power_programmed), len(historical_prices)))
)

manual_revenue_hindsight = sum(
    power_hindsight[i] * historical_prices[i]
    for i in range(min(len(power_hindsight), len(historical_prices)))
)

print(f"[DEBUG] Manual revenue calculation:")
print(f"  Programmed: ${manual_revenue_programmed:.2f}")
print(f"  Hindsight:  ${manual_revenue_hindsight:.2f}")
print(f"  Optimizer revenue: ${solution_hindsight['revenue']:.2f}")
```

If manual differs from optimizer, there's a calculation bug.

---

## 🎯 Most Likely Solution

Based on the code structure, **Scenario 1** (stored optimization with different constraints) is most likely.

**What's happening:**
1. At some point, you ran an optimization with parameters A (e.g., s0=35000, horizon=48h)
2. That optimization was stored
3. Performance page uses that stored optimization for "programmed" revenue
4. But runs fresh "hindsight" optimization with parameters B (e.g., s0=25000, horizon=24h)
5. Stored optimization had better constraints → higher revenue despite worse forecast

**Solution:**
Either:
- **A) Always use fresh optimization** for both (disable stored optimization fetching)
- **B) Store metadata with optimization** and verify constraints match before using
- **C) Store multiple optimizations** per day and fetch the one matching current parameters

---

## 📊 Recommended Fix

### Option A: Disable Stored Optimization (Quick Fix)

```python
def calculate_performance(self, ...):
    # ... existing code ...

    # 2. CMG PROGRAMADO OPTIMIZATION (Forecast-based)
    # ALWAYS run fresh optimization instead of using stored
    stored_optimization = None  # Disable stored optimization lookup

    # Now both programmed and hindsight use same constraints
    if OPTIMIZER_AVAILABLE:
        solution_programmed = optimize_hydro_lp(
            programmed_prices, p_min, p_max, s0, s_min, s_max, kappa, inflow, horizon
        )
        # ... rest of code ...
```

This ensures both optimizations run with IDENTICAL constraints, so hindsight MUST be ≥ programmed.

### Option B: Verify Stored Optimization Matches (Better Fix)

```python
stored_optimization = self.fetch_optimization_results(start_date)

if stored_optimization:
    # Verify constraints match
    stored_params = stored_optimization.get('parameters', {})

    params_match = (
        stored_params.get('s0') == s0 and
        stored_params.get('horizon') == horizon and
        stored_params.get('p_min') == p_min and
        stored_params.get('p_max') == p_max
        # ... check all parameters
    )

    if not params_match:
        print(f"[PERFORMANCE] Stored optimization has different constraints, running fresh")
        stored_optimization = None
```

This allows using stored optimization when constraints match, but runs fresh if they differ.

### Option C: Always Calculate Revenue Consistently (Best Fix)

```python
# For BOTH programmed and hindsight, always manually calculate revenue
revenue_programmed = sum(
    power_programmed[i] * historical_prices[i]
    for i in range(min(len(power_programmed), len(historical_prices)))
)

revenue_hindsight = sum(
    power_hindsight[i] * historical_prices[i]
    for i in range(min(len(power_hindsight), len(historical_prices)))
)

# Don't use solution_hindsight['revenue']
```

This ensures revenue is calculated identically for both scenarios.

---

## 🚀 Next Steps

1. **Add debug logging** to see which optimization path is taken
2. **Check stored optimization metadata** - when was it run? what constraints?
3. **Test with fresh optimization** - disable stored optimization temporarily
4. **Implement one of the fixes above**

Once efficiency is consistently <100%, you'll have proof that hindsight is truly optimal!

---

## 📝 Summary

The equal storage constraint is correct and necessary. The efficiency >100% issue is likely because:
- Stored optimization was run with different (more favorable) constraints
- Revenue calculation differs between programmed (manual) and hindsight (from optimizer)
- Solution: Either disable stored optimization or verify constraints match before using

**The optimizer itself is working correctly** - this is a comparison/bookkeeping issue in the performance analysis.
