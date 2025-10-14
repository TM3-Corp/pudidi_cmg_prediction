# Complete ETL Workflow Documentation

## 📊 Data Flow for forecast_comparison.html

This document explains how data flows from source → storage → display for the forecast comparison view.

---

## 🔄 Hourly Workflow (Every hour at :05)

**Workflow:** `.github/workflows/cmg_online_hourly.yml`

**Runs:** Every hour at minute 5 (e.g., 00:05, 01:05, 02:05, etc.)

### Step-by-Step Process:

#### **STEP 0: Fetch CMG Programado (Web Scraping)**
```bash
Script: scripts/cmg_programado_pipeline.py
Method: Playwright web scraping
Source: https://www.coordinador.cl/operacion/graficos/operacion-programada/costo-marginal-programado/
Output: data/cache/cmg_programmed_latest.json
Duration: ~30-60 seconds
```

- Downloads CSV from Coordinador website
- Extracts forecast values for Puerto Montt 220kV (PMontt220)
- Stores 48-72 hour forecast array
- **Format:**
  ```json
  {
    "timestamp": "2025-10-14T15:00:00-03:00",
    "data": [
      {
        "datetime": "2025-10-14T16:00:00",
        "node": "PMontt220",
        "cmg_programmed": 51.5
      },
      ...
    ]
  }
  ```

#### **STEP 1: Fetch CMG Online (API)**
```bash
Script: scripts/smart_cmg_online_update.py
Method: REST API (SIP API v4)
Source: https://sipub.api.coordinador.cl/costo-marginal-online/v4/findByDate
Output: data/cache/cmg_historical_latest.json
Duration: ~2-5 minutes
```

- Fetches actual CMG values from SIP API
- Gets data for 3 nodes (NVA_P.MONTT, PIDPID, DALCAHUE)
- Smart caching - only fetches missing hours
- **Format:**
  ```json
  {
    "metadata": {
      "last_update": "2025-10-14T15:05:00-03:00",
      "total_records": 3000
    },
    "data": [
      {
        "datetime": "2025-10-14T15:00:00",
        "node": "NVA_P.MONTT___220",
        "cmg_usd": 58.5,
        "cmg_real": 58500
      },
      ...
    ]
  }
  ```

#### **STEP 2: Generate ML Predictions**
```bash
Script: scripts/ml_hourly_forecast.py
Method: LightGBM + XGBoost ensemble
Input: Historical CMG data, time features
Output: ml_predictions/latest.json
Duration: ~5-10 seconds
```

- Trains ensemble model on historical data
- Generates 24-hour forecast (t+1 to t+24)
- **Format:**
  ```json
  {
    "forecast_time": "2025-10-14T15:05:00-03:00",
    "predictions": [
      {
        "target_datetime": "2025-10-14T16:00:00",
        "cmg": 59.2,
        "horizon": 1
      },
      ...
    ]
  }
  ```

#### **STEP 3A: Store ML Predictions to Gist**
```bash
Script: scripts/store_ml_predictions.py
Target: ML Predictions Gist (38b3f9b1cdae5362d3676911ab27f606)
Duration: ~2 seconds
```

- Reads `ml_predictions/latest.json`
- Organizes by date and hour
- Stores to Gist in structure:
  ```json
  {
    "daily_data": {
      "2025-10-14": {
        "ml_forecasts": {
          "15": {
            "forecast_time": "2025-10-14T15:05:00-03:00",
            "predictions": [...]
          }
        }
      }
    }
  }
  ```

#### **STEP 3B: Store CMG Programado to Gist**
```bash
Script: scripts/store_cmg_programado.py
Target: CMG Programado Gist (d68bb21360b1ac549c32a80195f99b09)
Duration: ~2 seconds
```

- Reads `data/cache/cmg_programmed_latest.json`
- Filters forecasts to t+1 onwards (removes t+0)
- Maps node names (PMontt220 → NVA_P.MONTT___220)
- Stores to Gist in structure:
  ```json
  {
    "daily_data": {
      "2025-10-14": {
        "cmg_programado_forecasts": {
          "15": {
            "forecast_time": "2025-10-14T15:05:00-03:00",
            "forecasts": {
              "NVA_P.MONTT___220": [
                {"datetime": "2025-10-14T16:00:00", "cmg": 51.5},
                {"datetime": "2025-10-14T17:00:00", "cmg": 49.2},
                ...
              ]
            }
          }
        }
      }
    }
  }
  ```

#### **STEP 3C: Store CMG Online to Gist**
```bash
Script: scripts/store_historical.py
Target: CMG Online Gist (8d7864eb26acf6e780d3c0f7fed69365)
Duration: ~2 seconds
```

- Reads `data/cache/cmg_historical_latest.json`
- Organizes by date with 24-hour arrays
- Stores to Gist in structure:
  ```json
  {
    "daily_data": {
      "2025-10-14": {
        "hours": [0, 1, 2, ..., 23],
        "cmg_online": {
          "NVA_P.MONTT___220": {
            "cmg_usd": [null, null, ..., 58.5, ...],
            "cmg_real": [null, null, ..., 58500, ...]
          }
        }
      }
    }
  }
  ```

---

## 🌐 Frontend Data Loading

### forecast_comparison.html

**Data Sources (3 Gists):**

1. **ML Predictions Gist**
   - URL: `https://gist.githubusercontent.com/PVSH97/38b3f9b1cdae5362d3676911ab27f606/raw/ml_predictions_historical.json`
   - Contains: ML forecast matrices stored hourly

2. **CMG Programado Gist**
   - URL: `https://gist.githubusercontent.com/PVSH97/d68bb21360b1ac549c32a80195f99b09/raw/cmg_programado_historical.json`
   - Contains: CMG Programado forecast matrices stored hourly

3. **CMG Online Gist**
   - URL: `https://gist.githubusercontent.com/PVSH97/8d7864eb26acf6e780d3c0f7fed69365/raw/cmg_online_historical.json`
   - Contains: Actual CMG Online values (1 value per hour per node)

**Loading Process:**

1. Fetch all 3 Gists concurrently
2. Merge into unified structure:
   ```javascript
   {
     daily_data: {
       "2025-10-14": {
         ml_forecasts: {...},           // From ML Gist
         cmg_programado_forecasts: {...}, // From CMG Programado Gist
         cmg_online: {...}               // From CMG Online Gist
       }
     }
   }
   ```
3. Populate date/hour selectors
4. On selection, display:
   - ML Predictions for selected hour
   - CMG Programado forecasts for selected hour
   - Actual CMG Online values

---

## 🔧 Why CMG Programado Wasn't Working

### The Problem:

1. **Old workflow (`cmg_programado_hourly.yml`) was archived** during cleanup
2. This workflow fetched fresh CMG Programado data via web scraping
3. Without it, `cmg_programmed_latest.json` became stale
4. `store_cmg_programado.py` filtered out stale forecasts (all in the past)
5. Result: No new CMG Programado data stored to Gist for Oct 14

### The Fix:

1. **Integrated CMG Programado fetch into unified hourly workflow**
2. Now runs BEFORE storing to Gist
3. Ensures fresh data is always available
4. Complete pipeline: Fetch → Process → Store → Display

---

## 📈 Data Update Frequency

| Data Type | Update Frequency | Method | Duration |
|-----------|-----------------|---------|----------|
| CMG Programado | Hourly | Web scraping (Playwright) | ~30-60s |
| CMG Online | Hourly | REST API | ~2-5min |
| ML Predictions | Hourly | Model training | ~5-10s |
| Gist Storage | Hourly | GitHub API | ~2s each |

---

## ✅ Verification Steps

To verify the complete ETL is working:

1. **Check GitHub Actions**: All hourly runs should succeed
2. **Check Gists**: All 3 Gists should have today's data
3. **Check forecast_comparison.html**: Should show all 3 data sources for today's hours
4. **Check cache files**:
   - `data/cache/cmg_programmed_latest.json` (recent timestamp)
   - `data/cache/cmg_historical_latest.json` (recent timestamp)
   - `ml_predictions/latest.json` (recent timestamp)

---

## 🚨 Common Issues

### Issue: CMG Programado not showing in forecast_comparison.html

**Diagnosis:**
```bash
# Check if workflow is running
gh workflow list

# Check last run status
gh run list --workflow=cmg_online_hourly.yml --limit 5

# Check cache file timestamp
ls -lh data/cache/cmg_programmed_latest.json

# Check Gist for today's date
curl https://gist.githubusercontent.com/PVSH97/d68bb21360b1ac549c32a80195f99b09/raw/cmg_programado_historical.json | jq '.daily_data | keys'
```

**Solution:**
- Ensure `cmg_online_hourly.yml` workflow is running
- Check Playwright installation succeeded
- Verify Coordinador website is accessible
- Check for error messages in workflow logs

### Issue: Missing hours in forecast_comparison.html

**Diagnosis:**
- Check if hourly workflow failed
- Check Gist content for specific date/hour
- Check browser console for fetch errors

**Solution:**
- Trigger manual workflow run
- Check that all 3 Gists have data for the missing hour
- Clear browser cache and reload

---

## 📝 Maintenance

### Adding New Nodes

1. Update `CMG_NODES` in `smart_cmg_online_update.py`
2. Update node mapping in `store_cmg_programado.py`
3. Update frontend node selectors

### Changing Update Frequency

- Edit cron schedule in `.github/workflows/cmg_online_hourly.yml`
- Currently: `'5 * * * *'` (every hour at :05)

### Debugging

Enable detailed logging:
```bash
# In workflow
export DEBUG=1
python scripts/cmg_programado_pipeline.py
```

---

**Last Updated:** 2025-10-14
**Version:** 3.0 (3-Gist Architecture)
