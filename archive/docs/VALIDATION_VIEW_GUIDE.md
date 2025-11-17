# CMG Forecast Validation - How to Compare Programado vs Online
**Date:** October 5, 2025

## 🎯 Quick Answer

**YES!** You have a validation page: **https://pudidicmgprediction.vercel.app/validation.html**

---

## 📊 What It Shows

The `validation.html` page compares:
- **CMG Programado** (Forecast/Prediction)
- **vs**
- **CMG Online** (Actual values)

With:
- ✅ Line charts comparing forecast vs actual
- ✅ Scatter plots showing accuracy
- ✅ Error metrics (MAE, RMSE, MAPE)
- ✅ Detailed hourly comparison table

---

## 🚨 Current Status

**Issue:** The validation API is looking for `cmg_programado_forecasts.json` which doesn't exist yet.

### What You Have:
- ✅ `data/cache/cmg_online_historical.json` - CMG Online actuals (working!)
- ✅ `data/cache/cmg_programmed_latest.json` - Latest CMG Programado forecast
- ❌ `data/cache/cmg_programado_forecasts.json` - Historical forecasts with timestamps (NOT created yet)

### Why It Matters:
The validation API (`api/forecast_validation.py`) is designed for **proper forecast validation** which tracks:
- When forecast was made (forecast_time)
- What time it was forecasting for (target_time)
- Forecast horizon (t+1h, t+6h, t+24h)

This allows you to answer questions like:
- "How accurate is the 24-hour-ahead forecast?"
- "Does accuracy degrade as forecast horizon increases?"
- "Which hours are hardest to predict?"

---

## 🔧 Two Options to Enable Validation

### Option 1: Simple Comparison (Quick - Use Current Data)

Compare the **latest** CMG Programado forecast against **actual** CMG Online values.

**Pros:**
- ✅ Works with existing data
- ✅ Simple to implement
- ✅ Shows you forecast accuracy for recent days

**Cons:**
- ⚠️ Doesn't track forecast horizon (t+1 vs t+24)
- ⚠️ Can't analyze how accuracy degrades over time

**Implementation:**
I can create a simplified validation endpoint that uses `cmg_programmed_latest.json` directly.

### Option 2: Proper Forecast Tracking (Better - From Previous Session)

Implement the **5PM snapshot system** from your previous session.

**How it works:**
1. Every day at 5PM, capture CMG Programado forecast
2. Store it with timestamp: when forecast was made
3. After 24 hours, compare forecast vs actual
4. Track t+1, t+6, t+24 hour accuracy

**Pros:**
- ✅ Proper forecast validation
- ✅ Track accuracy degradation
- ✅ Identify systematic biases
- ✅ Perfect for your 5PM SCADA optimization use case

**Implementation:**
Scripts already exist from previous session:
- `scripts/capture_5pm_forecast_snapshot.py`
- `scripts/analyze_5pm_forecasts.py`

Just need to:
1. Add GitHub Action to run at 5PM daily
2. Let it collect data for 7 days
3. Then start analyzing

---

## 📋 Quick Test - See What You Have Now

### Current Data Check:
```bash
# Check CMG Online data
python3 -c "
import json
from pathlib import Path

online_file = Path('data/cache/cmg_online_historical.json')
if online_file.exists():
    data = json.load(open(online_file))
    dates = list(data.get('daily_data', {}).keys())
    print(f'CMG Online (Actual):')
    print(f'  Dates: {len(dates)} days')
    print(f'  Range: {dates[0]} to {dates[-1]}')
    print(f'  ✅ Ready for comparison')
else:
    print('❌ No CMG Online data')

prog_file = Path('data/cache/cmg_programmed_latest.json')
if prog_file.exists():
    data = json.load(open(prog_file))
    dates = sorted(set(r['date'] for r in data.get('data', [])))
    print(f'\\nCMG Programado (Forecast):')
    print(f'  Dates: {dates}')
    print(f'  Hours: {len(data.get(\"data\", []))}')
    print(f'  ✅ Ready for simple comparison')
else:
    print('❌ No CMG Programado data')
"
```

### Simple Comparison (Current Data):
You can compare dates where both exist:
- CMG Online: Sept 2 - Oct 5 ✅
- CMG Programado: Oct 5-7 ✅
- **Overlap:** Oct 5 ← You can compare this day!

---

## 🎯 Recommended Path Forward

### Immediate (Today):
1. **Delete unnecessary workflows** (per WORKFLOW_CLEANUP_PLAN.md)
2. **Test simple comparison:**
   - I'll create a simple validation view
   - Uses current `cmg_programmed_latest.json`
   - Compare Oct 5 forecast vs actual

### Short-term (Next Week):
3. **Implement 5PM snapshot system:**
   - Add workflow to capture forecasts daily at 5PM
   - Let it run for 7 days
   - Start proper forecast validation

### Medium-term (Ongoing):
4. **Monitor forecast accuracy:**
   - Track t+1, t+6, t+24 hour accuracy
   - Identify patterns (which hours are hardest to predict)
   - Use for your 5PM SCADA optimization decisions

---

## 🔍 Example: What You'll See

### Simple Comparison (Option 1):
```
Date: 2025-10-05
Hour | CMG Online (Actual) | CMG Programado (Forecast) | Error
-----|---------------------|---------------------------|-------
00   | $45.20             | $51.60                    | +$6.40
01   | $42.80             | $49.60                    | +$6.80
02   | $38.50             | $45.80                    | +$7.30
...  | ...                | ...                       | ...
23   | $52.30             | $47.90                    | -$4.40

Metrics:
- MAE (Mean Absolute Error): $5.80
- RMSE: $7.20
- MAPE: 12.5%
```

### Proper Tracking (Option 2):
```
Forecast Accuracy by Horizon (Oct 1-7):

t+1 hour (forecast made 1h before):
  MAE: $3.20, RMSE: $4.50, MAPE: 7.2%

t+6 hours (forecast made 6h before):
  MAE: $5.80, RMSE: $7.80, MAPE: 11.5%

t+24 hours (forecast made 24h before):
  MAE: $8.50, RMSE: $12.10, MAPE: 18.3%

→ Accuracy degrades as horizon increases (expected!)
```

---

## 🚀 What Do You Want?

**Choose your path:**

**A) Quick & Simple** (today):
- "I just want to see if forecasts match actuals"
- → I'll create simple comparison using current data
- → Works immediately, basic validation

**B) Proper & Complete** (this week):
- "I want to track forecast accuracy properly for SCADA optimization"
- → I'll set up 5PM snapshot system
- → Takes 7 days to collect data, then full analysis
- → Better for decision-making

**C) Both** (recommended):
- Start with simple comparison today (see what you have)
- Set up proper tracking in parallel
- Best of both worlds!

---

## 📁 Files

**Validation Page:**
- `public/validation.html` - Frontend comparison view

**API Endpoint:**
- `api/forecast_validation.py` - Backend comparison logic

**Data Sources:**
- `data/cache/cmg_online_historical.json` - Actuals ✅
- `data/cache/cmg_programmed_latest.json` - Latest forecast ✅
- `data/cache/cmg_programado_forecasts.json` - Historical forecasts (not created yet)

**Scripts (from previous session):**
- `scripts/capture_5pm_forecast_snapshot.py` - Capture daily forecasts
- `scripts/analyze_5pm_forecasts.py` - Analyze accuracy

---

**Ready to proceed?** Let me know which option you prefer and I'll set it up for you!
