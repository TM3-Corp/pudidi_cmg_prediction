# Data Format Documentation - CMG Prediction System

**Created**: 2025-11-17
**Purpose**: Document all data formats across Gist → Supabase → API → Frontend

---

## Overview

We have **3 data sources** flowing through **4 layers**:

```
GitHub Gist (v3.0) → Supabase Tables → API Endpoints → Frontend (index.html, ml_config.html)
```

---

## 1. CMG ONLINE (Historical Data)

### Gist Format
**URL**: https://gist.github.com/PVSH97/8d7864eb26acf6e780d3c0f7fed69365
**File**: `cmg_online_historical.json`

```json
{
  "metadata": {
    "last_update": "2025-11-17T13:42:27.756740-03:00",
    "structure_version": "3.0",
    "total_days": 77,
    "oldest_date": "2025-09-02",
    "newest_date": "2025-11-17",
    "nodes": ["NVA_P.MONTT___220", "PIDPID________110", "DALCAHUE______110"]
  },
  "daily_data": {
    "2025-11-17": {
      "hours": [0, 1, 2, ..., 23],
      "cmg_online": {
        "NVA_P.MONTT___220": {
          "cmg_usd": [42.32, 40.52, ...],   // 24 values
          "cmg_real": [40156.0, 38443.0, ...]
        },
        "DALCAHUE______110": {...},
        "PIDPID________110": {...}
      }
    }
  }
}
```

**Nodes**:
- `NVA_P.MONTT___220` ✅ USED in frontend
- `DALCAHUE______110` ✅ USED in frontend
- `PIDPID________110` ❌ NOT USED (skipped at index.html:549)

### Supabase Table: `cmg_online`

**Columns** (inferred from insert_cmg_online_batch):
- `datetime` (timestamp with timezone) - PRIMARY KEY part
- `date` (date)
- `hour` (integer 0-23)
- `node` (text) - PRIMARY KEY part
- `cmg_usd` (numeric)
- `source` (text) - e.g. 'SIP_API_v4'
- `created_at` (timestamp)

**Unique Constraint**: `(datetime, node)`

**Sample Row**:
```json
{
  "datetime": "2025-11-17T14:00:00+00:00",
  "date": "2025-11-17",
  "hour": 14,
  "node": "NVA_P.MONTT___220",
  "cmg_usd": 42.32,
  "source": "SIP_API_v4"
}
```

### API Response: `/api/cmg/current`

**Current Status**: ❌ `historical: { available: false, data: [] }`

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "historical": {
      "available": true,
      "data": [
        {
          "date": "2025-11-17",
          "hour": 14,
          "node": "NVA_P.MONTT___220",
          "cmg_usd": 42.32,
          "datetime": "2025-11-17 14:00:00"
        }
      ],
      "coverage": 100
    }
  }
}
```

### Frontend Expectations (index.html)

**Usage**: Lines 519-529, 583-595
```javascript
// Expects array of objects
data.historical.data.forEach(record => {
  // record.date (string "YYYY-MM-DD")
  // record.hour (integer)
  // record.node (string)
  // record.cmg_usd (number)
  // record.datetime (string "YYYY-MM-DD HH:MM:SS")
});
```

---

## 2. CMG PROGRAMADO (Forecast Data)

### Gist Format
**URL**: https://gist.github.com/PVSH97/d68bb21360b1ac549c32a80195f99b09
**File**: `cmg_programado_historical.json`

```json
{
  "metadata": {
    "last_update": "2025-11-17T13:42:22.753757-03:00",
    "structure_version": "3.0",
    "total_days": 29,
    "oldest_date": "2025-10-20",
    "newest_date": "2025-11-17"
  },
  "daily_data": {
    "2025-11-17": {
      "cmg_programado_forecasts": {
        "12": {  // Hour when forecast was made
          "forecast_time": "2025-11-17T12:32:12-03:00",
          "forecasts": {
            "NVA_P.MONTT___220": [  // ⚠️ Stored as this node
              {
                "datetime": "2025-11-17T13:00:00",
                "cmg": 95.0
              }
            ]
          }
        }
      }
    }
  }
}
```

**Node Mapping** (scripts/store_cmg_programado.py:31-34):
```python
NODE_MAPPING = {
    'PMontt220': 'NVA_P.MONTT___220',  // ⚠️ Maps scraper node to storage node
    'Pidpid110': 'PIDPID________110',
    'Dalcahue110': 'DALCAHUE______110'
}
```

### Supabase Table: `cmg_programado`

**Columns** (inferred):
- `datetime` (timestamp) - PRIMARY KEY part
- `date` (date)
- `hour` (integer)
- `node` (text) - PRIMARY KEY part (stored as 'NVA_P.MONTT___220')
- `cmg_programmed` (numeric)
- `fetched_at` (timestamp)
- `created_at` (timestamp)

**Unique Constraint**: `(datetime, node)`

### API Response: `/api/cmg/current`

**Current Response**:
```json
{
  "programmed": {
    "available": true,
    "data": [
      {
        "date": "2025-11-18",
        "hour": 14,
        "node": "NVA_P.MONTT___220",  // ⚠️ Wrong! Should be "PMontt220"
        "cmg_programmed": 130.4,
        "datetime": "2025-11-18 14:00:00"
      }
    ]
  }
}
```

### Frontend Expectations (index.html)

**Issue**: Lines 199, 202, 283 expect node = `PMontt220`
```html
<option value="PMontt220">📈 Puerto Montt 220kV (Programado)</option>
```

```javascript
'PMontt220': '#8b5cf6'  // Frontend uses this node name
```

**⚠️ MISMATCH**: API returns `NVA_P.MONTT___220` but frontend expects `PMontt220`

---

## 3. ML PREDICTIONS

### Gist Format
**URL**: https://gist.github.com/PVSH97/38b3f9b1cdae5362d3676911ab27f606
**File**: `ml_predictions_historical.json`

```json
{
  "metadata": {
    "last_update": "2025-11-17T13:42:17.390654-03:00",
    "structure_version": "3.0",
    "total_days": 6
  },
  "daily_data": {
    "2025-11-17": {
      "ml_forecasts": {
        "10": {  // Hour when forecast was made
          "forecast_time": "2025-11-17T10:35:39-03:00",
          "predictions": [
            {
              "horizon": 1,
              "target_datetime": "2025-11-17 11:00:00",
              "cmg": 61.55,
              "prob_zero": 0.0271,
              "threshold": 0.3607,
              "value_pred": 61.55
            }
          ]
        }
      }
    }
  }
}
```

### Supabase Table: `ml_predictions`

**Columns** (inferred):
- `id` (primary key)
- `forecast_datetime` (timestamp) - When forecast was made
- `target_datetime` (timestamp) - What time is being predicted
- `horizon` (integer) - Hours ahead (t+1, t+2, etc)
- `cmg_predicted` (numeric)
- `prob_zero` (numeric)
- `threshold` (numeric)
- `model_version` (text)
- `node` (text) - Optional, may be NULL
- `created_at` (timestamp)

### API Response: `/api/ml_forecast`

**Current Response**:
```json
{
  "success": true,
  "predictions": [
    {
      "horizon": 1,
      "datetime": "2025-11-17T17:00:00+00:00",
      "target_datetime": "2025-11-17T17:00:00+00:00",
      "predicted_cmg": 139.45,
      "zero_probability": 0.0151,
      "decision_threshold": 0.3695
    }
  ],
  "forecast_time": "2025-11-17T16:35:39+00:00",
  "model_version": "gpu_enhanced_v1"
}
```

### Frontend Expectations

**index.html** (line 622):
```javascript
y: mlData.map(d => d.predicted_cmg || d.cmg_predicted || 0)
```
✅ Has fallback for both field names

**ml_config.html** (line 500):
```javascript
const cmgValue = pred.predicted_cmg || pred.cmg_predicted || 0;
```
✅ Has fallback for both field names

---

## Critical Issues Found

### Issue 1: CMG Online Not Returning Data ❌

**Problem**: API returns `historical: { available: false, data: [] }`

**Possible Causes**:
1. Date range filter bug (FIXED in commit 5196c926)
2. No data in Supabase yet (workflow writes but query doesn't find it)
3. Timezone mismatch in query
4. Deployment not complete

**Action**: Wait for deployment, then test query directly

### Issue 2: CMG Programado Node Name Mismatch ⚠️

**Problem**:
- Supabase stores: `NVA_P.MONTT___220`
- API returns: `NVA_P.MONTT___220`
- Frontend expects: `PMontt220`

**Impact**: Frontend cannot match programado data to chart

**Fix Needed**: Transform node name in API response or frontend

### Issue 3: Duplicate Key Errors in Workflow

**Status**: FIXED in commits da61242c and 5196c926
- Filter to last 7 days only
- Return True on 409 Conflict
- Filter to active nodes only (exclude PIDPID)

---

## Data Flow Summary

```
GIST v3.0 (historical archive)
    ↓
WORKFLOW (hourly GitHub Actions)
    ↓
SUPABASE (production database)
    ↓
API ENDPOINTS (Vercel serverless functions)
    ↓
FRONTEND (index.html, ml_config.html)
```

**Key Transformation Points**:
1. **Gist → Supabase**: Flatten daily_data structure to rows
2. **Supabase → API**: Apply time filters, format response
3. **API → Frontend**: Must match expected field names and node names

---

## Next Steps

1. ✅ Document all data formats (THIS FILE)
2. ⏳ Wait for deployment to complete
3. 🔍 Test `/api/cmg/current` returns CMG Online data
4. 🐛 Fix CMG Programado node name mismatch
5. 🧪 Verify all pages load correctly
