# Horizon Performance Investigation - Verified Findings Report

**Date:** 2025-12-28
**Period Analyzed:** 2025-12-01 to 2025-12-25, verified with 2025-12-21 to 2025-12-27

---

## Executive Summary

After fixing a critical bug in the data query (1000-row limit), the verified findings show:

- **ML models outperform CMG Programado OVERALL** (on average)
- **ML wins at short horizons** (t+1 to t+7) - approx 10 horizons
- **CMG Programado wins at longer horizons** (t+8 to t+24) - approx 14 horizons
- **t+12 is ML's worst horizon** due to systematic under-prediction bias
- **Data is complete** - all days have full 24-hour actuals

---

## Bug Fix Applied

### The Problem
CMG Online (actuals) query was hitting PostgREST's 1000-row limit when querying wide date ranges. This caused:
- Only ~14 days of data to be returned for Dec 1-25
- Rendimiento plots showing incomplete date ranges
- Incorrect performance calculations

### The Fix
Modified `api/performance_range.py` to query CMG Online day-by-day (same pattern used for forecasts):

```python
# Before: Single query hitting 1000 limit
online_params = [("date", f"gte.{start_date}"), ("date", f"lte.{end_date}"), ("limit", "5000")]

# After: Day-by-day queries (72 records max per day)
current_date = start_date
while current_date <= end_date:
    online_params = [("date", f"eq.{current_date}"), ("limit", "1000")]
    # ... query each day
```

---

## Verified Results

### Period: Dec 21-27, 2025 (verified against Rendimiento UI)

| Metric | Value |
|--------|-------|
| ML Overall Average | $26.52 |
| Prog Overall Average | $29.12 |
| **Winner** | **ML WINS** |
| ML Degradation Rate | $0.48/hour |
| Prog Degradation Rate | -$0.83/hour |

**ML wins 5 out of 7 days in this period.**

### Period: Dec 1-25, 2025 (full month)

| Metric | Value |
|--------|-------|
| ML Overall Average | $43.40 |
| Prog Overall Average | $43.88 |
| **Winner** | **ML WINS (marginal)** |
| ML Degradation Rate | $0.56/hour |
| Prog Degradation Rate | -$0.22/hour |

**ML wins 15 out of 25 days in this period.**

---

## Structural Analysis by Horizon

### Dec 21-27, 2025

| Horizon Range | ML Wins | Prog Wins | Notes |
|---------------|---------|-----------|-------|
| t+1 to t+7 | 7 | 0 | ML dominates short-term |
| t+8 to t+11 | 1 | 3 | Crossover zone |
| **t+12** | 0 | 1 | **ML worst horizon** |
| t+13 to t+24 | 2 | 10 | Prog dominates long-term |

**Total: ML wins 10 horizons, Prog wins 14 horizons**

### Crossover Point
The crossover where Prog starts winning occurs around **t+7/t+8**.

---

## Root Cause Analysis: t+12 Pattern

### Finding 1: Systematic Under-Prediction Bias

| Metric | Value |
|--------|-------|
| % Under-predictions at t+12 | 86.4% |
| Average bias at t+12 | -$31.69 |
| Comparison: t+1 bias | -$1.29 |

**ML systematically predicts $32 LOWER than actual at t+12.**

### Finding 2: Target Hour Correlation

t+12 predictions made midday target nighttime hours:
- Forecast at 12:00 → Target 00:00
- Forecast at 15:00 → Target 03:00
- Forecast at 18:00 → Target 06:00

**Nighttime CMG values are HIGH** ($59-66), but ML fails to predict this increase.

### Finding 3: CMG Pattern Explanation

| Time Period | Avg CMG | Volatility |
|-------------|---------|------------|
| 00:00-07:00 (Night) | $44-66 | Low-Medium |
| 08:00-16:00 (Day) | $11-30 | High |
| 20:00-23:00 (Evening) | $59-63 | Low |

**Root Cause:** Chile has high solar generation during the day, driving CMG down. At night, thermal units dispatch at higher costs. ML models learned daytime patterns well but fail to predict the nighttime ramp-up when forecasting 12 hours ahead.

### Finding 4: CMG Programado's Advantage

CMG Programado shows **negative degradation** (improves with horizon):
- t+1: $45.81 error
- t+24: $26.78 error

This suggests CEN (Coordinador Eléctrico Nacional) has access to:
1. Scheduled generation unit commitments
2. Day-ahead dispatch plans
3. Maintenance windows

This information is not available to ML models.

---

## Implications for Model Improvement

### Short-Term Wins

1. **Add hour-of-day feature interaction with horizon**
   - Separate model behavior for daytime vs nighttime targets

2. **Adjust lag features for longer horizons**
   - Current: Same lags for all horizons
   - Proposed: Different lag windows for t+1-6, t+7-12, t+13-24

3. **Add CMG pattern features**
   - Time-of-day CMG typical range
   - Day/night transition indicators

### Medium-Term Improvements

1. **Integrate exogenous data**
   - Solar irradiance forecasts
   - Demand forecasts
   - Scheduled outages

2. **Explore Temporal Fusion Transformer (TFT)**
   - Better at multi-horizon forecasting
   - Handles known future inputs well

### Strategic Insight

ML models excel at short-term (t+1 to t+7) where recent values are predictive.

CMG Programado excels at longer horizons because CEN has access to scheduled dispatch data.

**Recommendation:** Consider a hybrid approach:
- Use ML for t+1 to t+7
- Use CMG Programado for t+8 to t+24
- Or blend predictions based on horizon

---

## Files Modified

| File | Change |
|------|--------|
| `api/performance_range.py` | Fixed CMG Online query to avoid 1000-row limit |
| `scripts/verify_rendimiento_logic.py` | Created diagnostic script matching API logic |
| `scripts/analyze_t12_pattern.py` | Deep-dive analysis of t+12 pattern |

---

## Data Quality Confirmed

- All 25 days (Dec 1-25) have complete CMG Online data (24 hours each)
- ML predictions available for all horizons (t+1 to t+24)
- CMG Programado available for all horizons
- No sampling bias or data gaps affecting results

---

## Next Steps

1. [ ] Deploy API fix to production (Vercel)
2. [ ] Implement hour-of-day × horizon feature interaction
3. [ ] Experiment with hybrid ML + Programado approach
4. [ ] Consider Temporal Fusion Transformer for multi-horizon forecasting
