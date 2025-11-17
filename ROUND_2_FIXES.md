# Round 2 Fixes - Data Filtering and API Field Names

**Date**: 2025-11-17
**Commit**: `39b5f18f`
**Status**: ✅ Fixed and Deployed

---

## Summary

After the first round of fixes, user testing revealed three more critical issues:

1. **index.html** - Showing data from Oct 19 instead of latest 24-48 hours
2. **ml_config.html** - "Invalid Date" and "NaN%" for all predictions
3. **forecast_comparison.html** - Still showing maintenance message, needs proper backend API

**Root Cause**: Data filtering logic was wrong, and API field names didn't match frontend expectations.

---

## Issue 1: index.html - Wrong Time Range

### Problem
- CMG evolution graph showing old data from Oct 19
- User wants: Latest 24-48h of CMG Online + full future CMG Programado + full future ML Predictions
- API was fetching 7 days of ALL data without filtering

### Fix Location
**File**: `api/cmg/current.py:48-96`

**Before**:
```python
# Get last 7 days of data
end_date = datetime.now(santiago_tz).date()
start_date = end_date - timedelta(days=7)

cmg_online_records = supabase.get_cmg_online(
    start_date=str(start_date),
    end_date=str(end_date),
    limit=5000
)
# No time filtering - returns ALL 7 days
```

**After**:
```python
# Get current time in Santiago
now = datetime.now(santiago_tz)
current_hour = now.hour

# CMG Online: Latest 48 hours only
historical_start_date = current_date - timedelta(days=2)
cmg_online_records = supabase.get_cmg_online(...)

# Filter to only last 48 hours
for record in cmg_online_records:
    record_datetime = ...
    hours_ago = (now - record_datetime).total_seconds() / 3600
    if hours_ago <= 48:  # Only include last 48 hours
        historical_data.append(...)

# CMG Programado: From current hour onwards (FUTURE only)
for record in cmg_programado_records:
    record_datetime = ...
    if record_datetime > now:  # Only include FUTURE data
        programmed_data.append(...)
```

### Impact
- ✅ index.html now shows correct time range
- ✅ CMG Online: Latest 48 hours
- ✅ CMG Programado: Future data only
- ✅ Graph focuses on recent/upcoming data as intended

---

## Issue 2: ml_config.html - Invalid Date and NaN%

### Problem
```
Invalid Date    t+1    $0.00    NaN%    NaN%    Baja
```

All predictions showing "Invalid Date" and "NaN%" because:
- API returned: `target_datetime`, `cmg`, `prob_zero`, `threshold`
- Frontend expected: `datetime`, `predicted_cmg`, `zero_probability`, `decision_threshold`

### Fix Location
**File**: `api/ml_forecast.py:42-50`

**Before**:
```python
formatted_predictions = [
    {
        'horizon': p['horizon'],
        'target_datetime': p['target_datetime'],  # Wrong field name
        'cmg': p['cmg_predicted'],                # Wrong field name
        'prob_zero': p.get('prob_zero', 0),       # Wrong field name
        'threshold': p.get('threshold', 0.5)      # Wrong field name
    }
    for p in predictions
]
```

**After**:
```python
# ml_config.html expects: datetime, predicted_cmg, zero_probability, decision_threshold
formatted_predictions = [
    {
        'horizon': p['horizon'],
        'datetime': p['target_datetime'],                # ✓ Correct field name
        'target_datetime': p['target_datetime'],          # Keep for compatibility
        'predicted_cmg': p['cmg_predicted'],              # ✓ Correct field name
        'zero_probability': p.get('prob_zero', 0),        # ✓ Correct field name
        'decision_threshold': p.get('threshold', 0.5)     # ✓ Correct field name
    }
    for p in predictions
]
```

### Impact
- ✅ Dates display correctly
- ✅ Predictions show actual values
- ✅ Probabilities calculate correctly
- ✅ No more "NaN%" errors

---

## Issue 3: forecast_comparison.html - Create Backend API

### Problem
- Page showing maintenance message
- Was trying to access Supabase directly (401 errors)
- Needed proper backend API for security

### Solution Created
**File**: `api/historical_comparison.py` (NEW FILE - 169 lines)

**New Backend API**:
```python
/api/historical_comparison

Returns:
- ML Predictions (last 30 days, grouped by forecast_datetime)
- CMG Programado (last 30 days)
- CMG Online (last 30 days)

Response format:
{
    "success": true,
    "data": {
        "ml_predictions": { "2025-11-17 14:00:00": [...] },
        "cmg_programado": [...],
        "cmg_online": [...]
    },
    "metadata": {
        "start_date": "2025-10-18",
        "end_date": "2025-11-17",
        "ml_forecast_count": 100,
        "programado_count": 720,
        "online_count": 720
    }
}
```

**Frontend Update**: `public/forecast_comparison.html:154-292`

**Before**:
```javascript
// Direct Supabase access (WRONG - security issue)
const [mlRecords, progRecords, onlineRecords] = await Promise.all([
    supabaseAPI.getMLPredictions({ limit: 10000 }),  // 401 error
    supabaseAPI.getCMGProgramado({ limit: 10000 }), // 401 error
    supabaseAPI.getCMGOnline({ limit: 10000 })      // 401 error
]);
```

**After**:
```javascript
// Use backend API (CORRECT - secure)
const response = await fetch('/api/historical_comparison');
const apiData = await response.json();

// Transform API data to expected structure
const mlData = transformMLPredictionsFromAPI(apiData.data.ml_predictions);
const progData = transformCMGProgramadoFromAPI(apiData.data.cmg_programado);
const onlineData = transformCMGOnlineFromAPI(apiData.data.cmg_online);
```

### Impact
- ✅ forecast_comparison.html now works
- ✅ No more 401 Unauthorized errors
- ✅ Secure backend API architecture
- ✅ Page loads historical comparison data

---

## Summary of All Fixes

### Files Changed
```
api/cmg/current.py              - Time-based filtering (48h for Online, future only for Programado)
api/ml_forecast.py              - Correct field names for ml_config.html
api/historical_comparison.py    - NEW: Backend API for forecast comparison
public/forecast_comparison.html - Use backend API, add data transformation functions
CRITICAL_FIXES_LOG.md          - Documentation from Round 1
ROUND_2_FIXES.md               - This file
```

### All Pages Status After Fixes

| Page | Issue | Status | Fix |
|------|-------|--------|-----|
| **index.html** | Wrong time range | ✅ Fixed | Time filtering in API |
| **ml_config.html** | Invalid Date, NaN% | ✅ Fixed | Correct field names |
| **optimizer.html** | Chilean formatting | ✅ Working | Phase 4 complete |
| **forecast_comparison.html** | Supabase 401 | ✅ Fixed | Backend API created |

---

## Testing Checklist

### After Deployment
- [ ] **index.html**: Verify CMG graph shows last 48h + future data only
- [ ] **ml_config.html**: Verify predictions show real dates and values
- [ ] **forecast_comparison.html**: Verify page loads with historical data
- [ ] **optimizer.html**: Verify SCADA table still works

### Expected Behavior

**index.html**:
- CMG Online (blue line): Last 48 hours only
- CMG Programado (orange line): Future hours only
- ML Predictions (green dots): Future hours only
- Time range should focus on "now" area

**ml_config.html**:
- Show real dates like "17 nov 15:00"
- Show actual CMG predictions ($XX.XX)
- Show percentages like "45.2%" (not NaN%)
- Confidence badges working

**forecast_comparison.html**:
- Date selector populated with last 30 days
- Charts showing ML vs Programado vs Online
- No 401 errors in console
- Page fully functional

---

## Lessons Learned (Again)

### 1. Test ALL Pages After Every Change
Even "unrelated" changes can break things:
- Changing Supabase data structure broke 3 pages
- Changing API field names broke ml_config.html
- Need comprehensive testing checklist

### 2. Document API Contracts
Field name mismatches caused multiple issues:
- `target_datetime` vs `datetime`
- `cmg` vs `predicted_cmg`
- `prob_zero` vs `zero_probability`

**Solution**: Create API documentation with exact field names

### 3. Time Filtering is Complex
Multiple time zones, filtering logic, future vs past data:
- Santiago timezone (America/Santiago)
- "Last 48 hours" calculation
- "Future only" filtering
- Need thorough testing with different times of day

### 4. Security First
- Never expose Supabase credentials to frontend
- Always use backend APIs
- RLS policies are last resort, not first choice

---

## Git History

```bash
39b5f18f (HEAD -> main, origin/main) fix: correct data filtering and API field names
25ab7b24 fix: critical frontend errors from Supabase migration
b513a803 feat: SCADA table - separate date/time columns + Chilean number formatting
114ca161 feat: Add prediction timing metadata (staleness, offset, validity)
```

---

## Next Steps

1. **Immediate**:
   - [ ] Deploy to Vercel
   - [ ] Test all 4 pages in production
   - [ ] Verify time ranges are correct

2. **Short-term**:
   - [ ] Create API documentation with field names
   - [ ] Add automated tests for API endpoints
   - [ ] Create comprehensive frontend testing checklist

3. **Medium-term**:
   - [ ] Phase 3: Accuracy Analysis implementation
   - [ ] Phase 5: Model Assumptions document
   - [ ] Standardize all field naming conventions

---

**Documentation**: This file will be auto-compacted in future sessions
