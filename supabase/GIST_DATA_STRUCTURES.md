# Gist Data Structures - Supabase Migration Documentation

**Date:** 2025-10-28
**Purpose:** Document current Gist data structures to ensure successful migration to Supabase

---

## Overview

The CMG prediction system currently stores data in 3 GitHub Gists:

1. **CMG Online Gist** (`8d7864eb...`) - Real-time CMG values from SIP API
2. **CMG Programado Gist** (`d68bb213...`) - Official CMG forecasts from coordinator
3. **ML Predictions Gist** (`38b3f9b1...`) - Our ML model predictions

Each Gist has a corresponding cache file in `data/cache/` that mirrors its structure.

---

## 1. CMG Online Gist

**File:** `data/cache/cmg_online_historical.json`
**Update Frequency:** Hourly (GitHub Actions workflow)
**Source:** SIP API (Sistema de Información Pública)

### Structure

```json
{
  "metadata": {
    "last_update": "2025-10-28T17:39:44.925663-03:00",
    "total_days": 57,
    "oldest_date": "2025-09-02",
    "newest_date": "2025-10-28",
    "nodes": [
      "NVA_P.MONTT___220",
      "PIDPID________110",
      "DALCAHUE______110"
    ],
    "structure_version": "3.0",
    "rolling_window_days": null
  },
  "daily_data": {
    "2025-10-13": {
      "hours": [0, 1, 2, ..., 23],
      "cmg_online": {
        "DALCAHUE______110": {
          "cmg_usd": [42.32, 40.52, 0.0, ...],  // 24 values
          "cmg_real": [40156.0, 38443.0, 0.0, ...]  // 24 values in CLP
        },
        "NVA_P.MONTT___220": {
          "cmg_usd": [...],
          "cmg_real": [...]
        },
        "PIDPID________110": {
          "cmg_usd": [...],
          "cmg_real": [...]
        }
      }
    }
  }
}
```

### Key Characteristics

- **3 nodes** tracked simultaneously
- **24 hourly values** per node per day
- **Values can be 0.0** when SIP API data is not available
- Both USD and CLP (Chilean Peso) values stored
- Nested structure: `daily_data[date][cmg_online][node][cmg_usd/cmg_real][hour_index]`

### Data Volume

- 57 days of historical data
- 3 nodes × 24 hours × 57 days = **4,104 records per currency**
- Total: ~8,200 data points

---

## 2. CMG Programado Gist

**File:** `data/cache/cmg_programado_historical.json`
**Update Frequency:** Hourly (GitHub Actions workflow)
**Source:** CMG Programado CSV from Coordinador Eléctrico

### Structure

```json
{
  "historical_data": {
    "2025-10-19": {
      "0": {
        "value": 58.0,
        "node": "PMontt220",
        "timestamp": "2025-10-19T00:00:00-03:00",
        "source": "CMG Programado",
        "update_time": "2025-10-20T07:34:48.917464-03:00"
      },
      "1": {
        "value": 55.5,
        "node": "PMontt220",
        "timestamp": "2025-10-19T01:00:00-03:00",
        "source": "CMG Programado",
        "update_time": "2025-10-20T07:34:48.917496-03:00"
      },
      // ... hours 2-23
    },
    "2025-10-20": { /* ... */ }
  },
  "daily_data": {
    "2025-10-20": {
      "cmg_programado_forecasts": {
        "4": {  // Hour when forecast was created (4 AM)
          "forecast_time": "2025-10-20T04:32:12.484191-03:00",
          "forecasts": {
            "NVA_P.MONTT___220": [
              {
                "datetime": "2025-10-20T05:00:00",
                "cmg": 32.8
              },
              {
                "datetime": "2025-10-20T06:00:00",
                "cmg": 48.9
              },
              // ... up to 72 hours ahead
            ]
          }
        },
        "5": { /* another forecast snapshot at 5 AM */ },
        // ... multiple hourly forecast snapshots
      }
    }
  }
}
```

### Key Characteristics

- **Single node:** PMontt220 (Puerto Montt 220kV)
- **Two sections:**
  - `historical_data`: Flat past values (24 hours per day)
  - `daily_data`: Multiple forecast snapshots per day
- **Forecast horizon:** Up to 72 hours ahead
- **Multiple snapshots:** Each hour produces a new 72-hour forecast
- Values in USD/MWh

### Data Volume (historical_data)

- Approximately 30+ days of historical data
- 1 node × 24 hours × 30 days = **720 records**

### Data Volume (daily_data forecasts)

- 24 forecast snapshots per day
- Each snapshot: up to 72 hourly predictions
- 30 days × 24 snapshots × 72 predictions = **51,840 forecast records**

---

## 3. ML Predictions Gist

**File:** `data/cache/ml_predictions_historical.json`
**Update Frequency:** Hourly (GitHub Actions workflow)
**Source:** Internal ML models (GPU-enhanced)

### Structure

```json
{
  "metadata": {
    "last_update": "2025-10-28T17:39:40.639110-03:00",
    "structure_version": "3.0",
    "rolling_window_days": null,
    "total_days": 6,
    "oldest_date": "2025-10-23",
    "newest_date": "2025-10-28"
  },
  "daily_data": {
    "2025-10-23": {
      "ml_forecasts": {
        "6": {  // Hour when forecast was generated (6 AM)
          "forecast_time": "2025-10-23 06:00:00",
          "generated_at": "2025-10-23 11:27:29 UTC",
          "model_version": "gpu_enhanced_v1",
          "predictions": [
            {
              "horizon": 1,
              "target_datetime": "2025-10-23 07:00:00",
              "cmg": 48.42,
              "prob_zero": 0.0062,
              "threshold": 0.3706,
              "value_pred": 48.42
            },
            {
              "horizon": 2,
              "target_datetime": "2025-10-23 08:00:00",
              "cmg": 43.94,
              "prob_zero": 0.1497,
              "threshold": 0.3707,
              "value_pred": 43.94
            },
            // ... horizons 3-24
          ]
        },
        "7": { /* forecast at 7 AM */ },
        // ... up to 24 hourly forecast snapshots
      }
    }
  }
}
```

### Key Characteristics

- **24-hour rolling forecasts** generated hourly
- **Rich prediction metadata:**
  - `horizon`: Hours ahead (1-24)
  - `target_datetime`: When the prediction is for
  - `cmg`: Final predicted value (0 if prob_zero > threshold)
  - `prob_zero`: Probability of zero CMG
  - `threshold`: Dynamic threshold per hour
  - `value_pred`: Raw regression value (before zero detection)
- **Multiple snapshots:** One forecast every hour (24 per day)
- Model version tracking for reproducibility

### Data Volume

- 6 days of historical forecasts currently stored
- 24 forecast snapshots per day
- Each snapshot: 24 hourly predictions
- 6 days × 24 snapshots × 24 predictions = **3,456 prediction records**

---

## Supabase Schema Mapping

### Table 1: `cmg_online`

Maps CMG Online Gist data to normalized rows.

| Gist Field | Supabase Column | Type | Notes |
|------------|----------------|------|-------|
| `daily_data[date]` | `date` | DATE | Extract from key |
| `daily_data[date].hours[i]` | `hour` | INTEGER | Index in array (0-23) |
| `daily_data[date].cmg_online[node]` | `node` | TEXT | Node identifier |
| `daily_data[date].cmg_online[node].cmg_usd[i]` | `cmg_usd` | NUMERIC(10,2) | Value in USD |
| - | `datetime` | TIMESTAMPTZ | Computed: date + hour |
| - | `source` | TEXT | Default: 'sip_api' |
| `metadata.last_update` | `updated_at` | TIMESTAMPTZ | Sync timestamp |

**Transformation Logic:**

```python
# Pseudo-code for transformation
for date, day_data in gist['daily_data'].items():
    for node_name, node_data in day_data['cmg_online'].items():
        for hour_index, cmg_value in enumerate(node_data['cmg_usd']):
            if cmg_value != 0.0:  # Skip missing values
                record = {
                    'datetime': f"{date}T{hour_index:02d}:00:00-03:00",
                    'date': date,
                    'hour': hour_index,
                    'node': node_name,
                    'cmg_usd': cmg_value,
                    'source': 'sip_api'
                }
```

**Expected Records:** ~4,100 rows (57 days × 3 nodes × 24 hours, minus nulls)

---

### Table 2: `cmg_programado`

Maps CMG Programado historical data (not forecasts).

| Gist Field | Supabase Column | Type | Notes |
|------------|----------------|------|-------|
| `historical_data[date][hour_str]` | - | - | Hour index as string |
| `.timestamp` | `datetime` | TIMESTAMPTZ | Target datetime |
| `.timestamp` (date part) | `date` | DATE | Extract date |
| `.timestamp` (hour part) | `hour` | INTEGER | Extract hour |
| `.node` | `node` | TEXT | Always 'PMontt220' |
| `.value` | `cmg_programmed` | NUMERIC(10,2) | CMG value in USD |
| `.update_time` | `fetched_at` | TIMESTAMPTZ | When data was fetched |

**Transformation Logic:**

```python
# Pseudo-code for transformation
for date, hours_dict in gist['historical_data'].items():
    for hour_str, record in hours_dict.items():
        row = {
            'datetime': record['timestamp'],
            'date': parse_date(record['timestamp']),
            'hour': parse_hour(record['timestamp']),
            'node': record['node'],  # 'PMontt220'
            'cmg_programmed': record['value'],
            'fetched_at': record['update_time']
        }
```

**Expected Records:** ~720 rows (30 days × 24 hours)

**Note:** We are NOT migrating `daily_data.cmg_programado_forecasts` at this time. Only historical confirmed values go into this table.

---

### Table 3: `ml_predictions`

Maps ML prediction snapshots to forecasts.

| Gist Field | Supabase Column | Type | Notes |
|------------|----------------|------|-------|
| `daily_data[date].ml_forecasts[hour].forecast_time` | `forecast_datetime` | TIMESTAMPTZ | When prediction was made |
| `.predictions[i].target_datetime` | `target_datetime` | TIMESTAMPTZ | What hour it predicts |
| `.predictions[i].horizon` | `horizon` | INTEGER | Hours ahead (1-24) |
| `.predictions[i].cmg` | `cmg_predicted` | NUMERIC(10,2) | Final predicted value |
| `.predictions[i].prob_zero` | `prob_zero` | NUMERIC(5,4) | Zero probability |
| `.predictions[i].threshold` | `threshold` | NUMERIC(5,4) | Decision threshold |
| `.model_version` | `model_version` | TEXT | Model identifier |

**Transformation Logic:**

```python
# Pseudo-code for transformation
for date, day_data in gist['daily_data'].items():
    for hour_str, forecast_snapshot in day_data['ml_forecasts'].items():
        forecast_time = forecast_snapshot['forecast_time']
        model_version = forecast_snapshot['model_version']

        for prediction in forecast_snapshot['predictions']:
            row = {
                'forecast_datetime': forecast_time,
                'target_datetime': prediction['target_datetime'],
                'horizon': prediction['horizon'],
                'cmg_predicted': prediction['cmg'],
                'prob_zero': prediction['prob_zero'],
                'threshold': prediction['threshold'],
                'model_version': model_version
            }
```

**Expected Records:** ~3,456 rows (6 days × 24 snapshots × 24 predictions)

---

## Migration Considerations

### 1. Data Integrity

**Unique Constraints:**
- `cmg_online`: `(datetime, node)` - One value per node per hour
- `cmg_programado`: `(datetime, node)` - One programmed value per hour
- `ml_predictions`: `(forecast_datetime, target_datetime)` - One prediction per forecast-target pair

**Handling Duplicates:**
- CMG Online: Skip records where `cmg_usd == 0.0` (missing data)
- Use `resolution=merge-duplicates` in Supabase REST API header
- Deduplicate in memory before batch insert

### 2. Timezone Handling

All timestamps in Gists use **Santiago timezone (UTC-3)**.

- Ensure PostgreSQL columns are `TIMESTAMPTZ` (timezone-aware)
- Timestamps will be stored in UTC internally
- Application layer should handle timezone conversion

### 3. Null vs Zero

- **CMG Online:** `0.0` represents missing data (SIP API unavailable)
- **CMG Programado:** `0.0` is a valid forecast (zero price predicted)
- **ML Predictions:** `cmg: 0` means model predicted zero (prob_zero > threshold)

**Migration Rule:** Skip CMG Online records with `cmg_usd == 0.0`

### 4. Data Volume Estimates

| Table | Current Records | Growth Rate | 1 Month | 1 Year |
|-------|----------------|-------------|---------|--------|
| `cmg_online` | ~4,100 | 72/day | 6,260 | 26,280 |
| `cmg_programado` | ~720 | 24/day | 1,440 | 8,760 |
| `ml_predictions` | ~3,456 | 576/day | 20,736 | 210,240 |
| **Total** | **8,276** | **672/day** | **28,436** | **245,280** |

### 5. Migration Order

1. **CMG Online** (smallest, simplest structure)
2. **CMG Programado** (historical only)
3. **ML Predictions** (largest, most complex)

### 6. Validation Checks

After migration, verify:

```sql
-- Check record counts
SELECT COUNT(*) FROM cmg_online;
SELECT COUNT(*) FROM cmg_programado;
SELECT COUNT(*) FROM ml_predictions;

-- Check date ranges
SELECT MIN(date), MAX(date) FROM cmg_online;
SELECT MIN(date), MAX(date) FROM cmg_programado;
SELECT MIN(forecast_datetime), MAX(forecast_datetime) FROM ml_predictions;

-- Check for nulls
SELECT COUNT(*) FROM cmg_online WHERE cmg_usd IS NULL;
SELECT COUNT(*) FROM cmg_programado WHERE cmg_programmed IS NULL;
SELECT COUNT(*) FROM ml_predictions WHERE cmg_predicted IS NULL;

-- Check for duplicates
SELECT datetime, node, COUNT(*)
FROM cmg_online
GROUP BY datetime, node
HAVING COUNT(*) > 1;
```

---

## ETL Updates Required

After migration, update these scripts to write to Supabase instead of Gist:

### Scripts to Modify

1. **scripts/smart_cmg_online_update.py**
   - Currently updates CMG Online Gist
   - Change to: Batch insert to `cmg_online` table
   - Keep local cache file sync for frontend

2. **scripts/store_cmg_programado.py**
   - Currently updates CMG Programado Gist
   - Change to: Insert to `cmg_programado` table
   - Update historical_data structure

3. **scripts/store_ml_predictions.py**
   - Currently updates ML Predictions Gist
   - Change to: Batch insert to `ml_predictions` table
   - Implement rolling window (keep last 7 days)

### GitHub Actions Workflow

**.github/workflows/cmg_online_hourly.yml** already has Supabase environment variables configured:

```yaml
env:
  SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
  SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
```

No changes needed for credentials.

---

## Rollback Plan

If migration fails or issues arise:

1. **Keep Gists intact** - Do NOT delete Gist data
2. **Dual-write period** - Write to both Gist and Supabase for 7 days
3. **Feature flag** - Add `USE_SUPABASE=true/false` environment variable
4. **Frontend fallback** - Cache files (`data/cache/*.json`) remain as backup

---

## Next Steps

1. ✅ **Analyze Gist structures** (COMPLETE)
2. ✅ **Document mappings** (COMPLETE - this file)
3. ⏳ **Validate schema compatibility** (Run SQL checks)
4. ⏳ **Execute migration** (Run `scripts/migrate_to_supabase.py`)
5. ⏳ **Verify data integrity** (Run validation queries)
6. ⏳ **Update ETL scripts** (Point to Supabase)
7. ⏳ **Update frontend** (Fetch from Supabase API)
8. ⏳ **Monitor production** (7-day dual-write period)

---

**Documentation maintained by:** Claude Code
**Last updated:** 2025-10-28
**Migration status:** Planning phase
