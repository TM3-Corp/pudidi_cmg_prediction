# CMG Prediction System - Architecture Documentation

## System Overview

The CMG (Marginal Cost) Prediction System is a full-stack web application designed to predict electricity prices in the Chilean energy market and optimize hydroelectric generation schedules. The system uses machine learning predictions, real-time data from the Chilean electricity coordinator (Coordinador Electrico Nacional), and optimization algorithms to maximize revenue from small-scale hydroelectric generation.

**Tech Stack:**
- **Frontend**: HTML5, JavaScript (ES6+), Chart.js for visualizations
- **Backend**: Python serverless functions (Vercel)
- **Database**: Supabase (PostgreSQL) for time-series data storage
- **ML Backend**: Railway (separate Python service for ML predictions)
- **Deployment**: Vercel (frontend + API), Railway (ML service)

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                 │
├─────────────────────────────────────────────────────────────────┤
│  • SIP API (Coordinador) - Real CMG values                      │
│  • CMG Programado (Coordinador) - Forecast values              │
│  • Railway ML Backend - ML predictions                          │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SUPABASE DATABASE                             │
├─────────────────────────────────────────────────────────────────┤
│  • cmg_online (actual CMG values)                               │
│  • cmg_programado (coordinator forecasts)                       │
│  • ml_predictions (ML model predictions)                        │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              VERCEL API ENDPOINTS (Serverless)                   │
├─────────────────────────────────────────────────────────────────┤
│  • /api/cmg/current - Current CMG data                          │
│  • /api/ml_forecast - ML predictions                            │
│  • /api/optimizer - Hydro optimization                          │
│  • /api/performance - Performance analysis                      │
│  • /api/historical_comparison - Forecast comparison             │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FRONTEND VIEWS (HTML)                          │
├─────────────────────────────────────────────────────────────────┤
│  • index.html - Dashboard                                       │
│  • ml_config.html - ML configuration                            │
│  • optimizer.html - Hydro optimizer                             │
│  • rendimiento.html - Performance analysis                      │
│  • forecast_comparison.html - Forecast accuracy                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Views and Their API Endpoints

### 1. index.html
**URL**: `/index.html` (root dashboard)

**Purpose**: Main dashboard displaying real-time CMG data, historical trends, and ML predictions

**API Endpoints Called**:
- **`/api/cmg/current`**
  - **Data Source**: Supabase (cmg_online + cmg_programado tables) with cache fallback
  - **Returns**: Last 48 hours of historical CMG data + next 72 hours of programmed forecasts
  - **Fields**: `{historical: {data, coverage, last_updated}, programmed: {data}, status: {overall}}`

- **`/api/ml_forecast`** (optional, for ML predictions)
  - **Data Source**: Railway ML Backend (proxied through Vercel)
  - **Returns**: Latest 24-hour ML forecast
  - **Fields**: `{success, predictions: [{datetime, predicted_cmg, zero_probability, decision_threshold}]}`

**Data Flow**:
```
Supabase (cmg_online)
  → /api/cmg/current
  → index.html JavaScript
  → Chart.js visualization (historical + programmed overlay)
```

**Key Features**:
- Real-time CMG price display with status indicators
- Historical price charts (last 48 hours)
- Programmed forecast overlay
- Node selection (PMontt220, Pidpid110, Dalcahue110)

---

### 2. ml_config.html
**URL**: `/ml_config.html`

**Purpose**: ML model configuration and prediction visualization interface

**API Endpoints Called**:
- **`/api/ml_thresholds`**
  - **Data Source**: Railway ML Backend (proxy endpoint)
  - **Returns**: ML model threshold configuration
  - **Fields**: `{success, thresholds: [{horizon, threshold, prob_zero}]}`

- **`/api/ml_forecast`**
  - **Data Source**: Railway ML Backend (via Supabase ml_predictions table)
  - **Returns**: Latest ML predictions with confidence intervals
  - **Fields**: `{success, predictions: [{datetime, predicted_cmg, zero_probability, threshold}]}`

**Data Flow**:
```
Railway ML Backend
  → Supabase (ml_predictions table)
  → /api/ml_forecast
  → ml_config.html
  → Chart.js (prediction visualization)
```

**Key Features**:
- Display ML predictions for next 24 hours
- Show zero-probability predictions (special handling for zero CMG)
- Threshold configuration display
- Prediction confidence intervals

---

### 3. optimizer.html
**URL**: `/optimizer.html`

**Purpose**: Hydroelectric generation optimizer using linear programming

**API Endpoints Called**:
- **`/api/optimizer`** (POST)
  - **Data Source**:
    - User selects: ML Predictions (Railway) OR CMG Programado (Supabase)
    - Optimization: Python scipy LinearProgramming with fallback to greedy algorithm
  - **Returns**: Optimal generation schedule, storage trajectory, revenue
  - **Fields**: `{success, solution: {P, Q, S, revenue, avg_generation}, prices, timestamps}`

- **`/api/cache?type=programmed`** (fallback for CMG Programado)
  - **Data Source**: Supabase (cmg_programado table)
  - **Returns**: Cached programmed CMG values
  - **Fields**: `{data: [{datetime, cmg_programmed}]}`

**Data Flow**:
```
USER SELECTION:
  ML Predictions:     Railway → /api/ml_forecast → /api/optimizer
  CMG Programado:     Supabase → /api/optimizer

OPTIMIZATION:
  Prices + Hydro Parameters
    → scipy Linear Programming (or greedy fallback)
    → Optimal generation schedule
    → optimizer.html (charts + results table)
```

**Key Features**:
- User selects data source (ML vs CMG Programado)
- Configure hydro parameters (power limits, storage, inflow)
- Solve linear programming problem for optimal dispatch
- Visualize generation schedule, storage trajectory, and revenue
- Export results table to clipboard

---

### 4. rendimiento.html
**URL**: `/rendimiento.html`

**Purpose**: Performance analysis comparing actual results vs forecast-based optimization

**API Endpoints Called**:
- **`/api/performance`** (POST)
  - **Data Source**:
    - Historical CMG Online (Supabase cmg_online)
    - CMG Programado (Supabase cmg_programado)
    - Optimization engine (Python scipy)
  - **Returns**: Revenue comparison for 3 scenarios (stable, programmed, hindsight)
  - **Fields**: `{summary: {revenue_stable, revenue_programmed, revenue_hindsight, efficiency}, hourly_data, daily_performance}`

- **`/api/performance?check_availability=true`** (GET)
  - **Data Source**: Supabase metadata
  - **Returns**: Available date ranges for historical analysis
  - **Fields**: `{available, dates, programmed_dates, oldest_date, newest_date, total_hours}`

**Data Flow**:
```
User selects date range
  → /api/performance (POST)
  → Fetch CMG Online (actual) from Supabase
  → Fetch CMG Programado (forecast) from Supabase
  → Run 3 optimizations:
      1. Stable baseline (flat generation)
      2. CMG Programado (forecast-based optimization)
      3. Perfect hindsight (actual prices)
  → Compare revenues & calculate efficiency
  → rendimiento.html (charts + metrics)
```

**Key Features**:
- Date range selection with availability check
- Three-way comparison: baseline vs forecast vs perfect hindsight
- Efficiency metric: (forecast-based revenue) / (hindsight revenue) × 100%
- Multi-day analysis with daily breakdown table
- Revenue charts, power dispatch charts, price comparison charts

---

### 5. forecast_comparison.html
**URL**: `/forecast_comparison.html`

**Purpose**: Compare forecast accuracy (ML vs CMG Programado vs Actual)

**API Endpoints Called**:
- **`/api/historical_comparison`**
  - **Data Source**: Supabase (all 3 tables)
    - ml_predictions
    - cmg_programado
    - cmg_online
  - **Returns**: Historical data for all 3 sources over last 30 days
  - **Fields**: `{success, data: {ml_predictions, cmg_programado, cmg_online}, metadata}`

**Data Flow**:
```
Supabase
  → Query last 30 days from all tables
  → /api/historical_comparison
  → forecast_comparison.html
  → Chart.js (3-way comparison charts)
```

**Key Features**:
- Compare ML predictions vs CMG Programado vs actual values
- Forecast accuracy metrics (MAE, RMSE)
- Time-series overlay charts
- Identify systematic forecast bias

---

## API Endpoints Reference

### /api/cmg/current
- **File**: `api/cmg/current.py`
- **Method**: GET
- **Data Source**: Supabase (cmg_online + cmg_programado) with cache fallback
- **Returns**:
  ```json
  {
    "success": true,
    "data": {
      "historical": {
        "available": true,
        "data": [{"date", "hour", "node", "cmg_usd", "datetime"}],
        "coverage": 95.5,
        "last_updated": "2025-01-15T10:00:00"
      },
      "programmed": {
        "available": true,
        "data": [{"date", "hour", "node", "cmg_programmed", "datetime"}]
      },
      "status": {
        "overall": {"status": "operational", "needs_update": false}
      },
      "source": "supabase"
    }
  }
  ```
- **Used By**: `index.html`
- **Cache**: Client-side 60 seconds
- **Node Mapping**: Converts Supabase format to frontend format
  - `NVA_P.MONTT___220` → `PMontt220`
  - `PIDPID________110` → `Pidpid110`
  - `DALCAHUE______110` → `Dalcahue110`

---

### /api/cache
- **File**: `api/cache.py`
- **Method**: GET
- **Query Parameters**: `?type=programmed|historical|metadata`
- **Data Source**: Supabase (formatted as cache-compatible JSON) or cache files
- **Returns**:
  ```json
  {
    "data": [{"datetime", "cmg_programmed"}],  // for type=programmed
    "timestamp": "2025-01-15T10:00:00"
  }
  ```
- **Used By**: `optimizer.html` (fallback)
- **Purpose**: Compatibility layer for legacy cache-based code

---

### /api/historical_comparison
- **File**: `api/historical_comparison.py`
- **Method**: GET
- **Data Source**: Supabase (all 3 tables: ml_predictions, cmg_programado, cmg_online)
- **Returns**:
  ```json
  {
    "success": true,
    "data": {
      "ml_predictions": {
        "2025-01-15T10:00:00": [{"forecast_datetime", "target_datetime", "predicted_cmg"}]
      },
      "cmg_programado": [{"datetime", "cmg_programmed", "node"}],
      "cmg_online": [{"datetime", "cmg_actual", "node"}]
    },
    "metadata": {
      "start_date": "2024-12-15",
      "end_date": "2025-01-15",
      "ml_forecast_count": 156,
      "programado_count": 720,
      "online_count": 720
    },
    "source": "supabase"
  }
  ```
- **Used By**: `forecast_comparison.html`
- **Time Range**: Last 30 days

---

### /api/ml_forecast
- **File**: `api/ml_forecast.py`
- **Method**: GET
- **Data Source**: Supabase (ml_predictions table)
- **Returns**:
  ```json
  {
    "success": true,
    "predictions": [
      {
        "horizon": 1,
        "datetime": "2025-01-15T11:00:00",
        "predicted_cmg": 75.23,
        "zero_probability": 0.12,
        "decision_threshold": 0.5
      }
    ],
    "forecast_time": "2025-01-15T10:00:00",
    "model_version": "v2.0",
    "status": {"available": true, "last_update": "2025-01-15T10:00:00"},
    "source": "supabase"
  }
  ```
- **Used By**: `index.html`, `ml_config.html`
- **Cache**: 5 minutes
- **Limit**: Latest 24 predictions (next 24 hours)

---

### /api/ml_thresholds
- **File**: `api/ml_thresholds.py`
- **Method**: GET
- **Data Source**: Railway ML Backend (proxy endpoint)
- **Returns**:
  ```json
  {
    "success": true,
    "thresholds": [
      {"horizon": 1, "threshold": 0.5, "prob_zero": 0.12}
    ]
  }
  ```
- **Used By**: `ml_config.html`
- **Purpose**: Proxy to Railway ML service for model configuration
- **Environment Variable**: `RAILWAY_ML_URL`

---

### /api/optimizer
- **File**: `api/optimizer.py`
- **Method**: POST, GET
- **Data Source**:
  - **POST**: User-selected (ML Predictions from Railway OR CMG Programado from Supabase)
  - **GET**: CMG Programado from cache (legacy)
- **Request Body (POST)**:
  ```json
  {
    "node": "PMontt220",
    "horizon": 24,
    "p_min": 0.5,
    "p_max": 3.0,
    "s0": 25000,
    "s_min": 1000,
    "s_max": 50000,
    "kappa": 0.667,
    "inflow": 1.1,
    "data_source": "ml_predictions"  // or "cmg_programado"
  }
  ```
- **Returns**:
  ```json
  {
    "success": true,
    "solution": {
      "P": [0.5, 3.0, 2.1, ...],  // Power (MW)
      "Q": [0.334, 2.0, 1.4, ...],  // Water discharge (m³/s)
      "S": [25000, 24500, 22000, ...],  // Storage (m³)
      "revenue": 4567.89,
      "avg_generation": 1.75,
      "peak_generation": 3.0,
      "capacity_factor": 58.3,
      "optimization_method": "scipy_LP",
      "solver_success": true
    },
    "prices": [70.5, 85.2, 65.0, ...],
    "timestamps": ["2025-01-15T11:00:00", ...],
    "data_info": {
      "data_source": "ML Predictions (Railway Backend)",
      "data_source_selected": "ml_predictions",
      "data_source_used": "ml_predictions",
      "using_ml_predictions": true,
      "available_hours": 24
    }
  }
  ```
- **Used By**: `optimizer.html`
- **Optimization Method**:
  1. Try scipy Linear Programming (if available)
  2. Fallback to simple DP solver
  3. Last resort: greedy algorithm
- **Special Features**:
  - Stores optimization results to GitHub Gist for performance tracking
  - ML predictions: Uses ALL available predictions (no t+1 filtering, as confirmed by user)
  - CMG Programado: Filters to t+1 onwards (future values only)

---

### /api/performance
- **File**: `api/performance.py`
- **Method**: POST, GET
- **Data Source**:
  - Supabase (cmg_online for actual values)
  - Supabase (cmg_programado for forecasts)
  - GitHub Gist (for CMG Programado historical data, supports dual structure)
  - Optimization engine (scipy LP)
- **Request Body (POST)**:
  ```json
  {
    "start_date": "2025-01-15T00:00:00",
    "end_date": "2025-01-15T23:59:59",
    "node": "NVA_P.MONTT___220",
    "p_min": 0.5,
    "p_max": 3.0,
    "s0": 25000,
    "s_min": 1000,
    "s_max": 50000,
    "kappa": 0.667,
    "inflow": 2.5
  }
  ```
- **Returns**:
  ```json
  {
    "summary": {
      "revenue_stable": 3200.50,
      "revenue_programmed": 3850.75,
      "revenue_hindsight": 4100.00,
      "improvement_vs_stable": 20.3,
      "efficiency": 93.9,
      "horizon": 24,
      "p_stable": 1.75,
      "water_balance": 1.65
    },
    "hourly_data": {
      "historical_prices": [70, 85, 60, ...],
      "programmed_prices": [72, 80, 65, ...],
      "power_stable": [1.75, 1.75, ...],
      "power_programmed": [0.5, 3.0, 2.0, ...],
      "power_hindsight": [0.5, 3.0, 2.5, ...],
      "start_date": "2025-01-15T00:00:00"
    },
    "daily_performance": [
      {
        "day": 1,
        "revenue_stable": 3200.50,
        "revenue_programmed": 3850.75,
        "revenue_hindsight": 4100.00,
        "efficiency": 93.9
      }
    ]
  }
  ```
- **GET**: `?check_availability=true` returns available date ranges
- **Used By**: `rendimiento.html`
- **Special Features**:
  - Three-scenario comparison: stable baseline, forecast-based, perfect hindsight
  - Efficiency capped at 99.9% (can't exceed perfect hindsight)
  - Supports multi-day analysis with daily breakdown
  - Fetches CMG Programado from dual structure Gist (Aug 26 - Sep 9 + Oct 13 onwards)

---

### /api/index
- **File**: `api/index.py`
- **Method**: GET
- **Data Source**: SIP API (Coordinador) with cache fallback
- **Returns**: Legacy endpoint for ML predictions using SIP API data
- **Status**: Legacy - being replaced by /api/ml_forecast
- **Used By**: None (deprecated)

---

### /api/debug/supabase
- **File**: `api/debug/supabase.py`
- **Method**: GET
- **Data Source**: Supabase (direct queries for debugging)
- **Returns**: Debug information about Supabase queries
- **Used By**: Development/debugging only
- **Example Tests**:
  - Query with no filters
  - Query with start_date only
  - Query with date range
  - CMG Programado query

---

## Database Schema (Supabase)

### Tables

#### 1. cmg_online
**Purpose**: Actual CMG values from SIP API (Coordinador)

**Schema**:
```sql
CREATE TABLE cmg_online (
    id BIGSERIAL PRIMARY KEY,
    datetime TIMESTAMPTZ NOT NULL,
    date DATE NOT NULL,
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    node TEXT NOT NULL,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'SIP_API_v4',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_cmg_online_datetime_node UNIQUE(datetime, node)
);
```

**Indexes**:
- `idx_cmg_online_datetime` on `datetime DESC`
- `idx_cmg_online_date_node` on `(date, node)`
- `idx_cmg_online_created` on `created_at DESC`

**Row Level Security**:
- Public read access (anonymous users)
- Write access only for service_role

**Data Retention**: Unlimited (all historical data)

**Sample Data**:
```json
{
  "datetime": "2025-01-15T10:00:00+00:00",
  "date": "2025-01-15",
  "hour": 10,
  "node": "NVA_P.MONTT___220",
  "cmg_usd": 75.23,
  "source": "SIP_API_v4"
}
```

---

#### 2. cmg_programado
**Purpose**: CMG forecast values from Coordinador (scraped from website)

**Schema**:
```sql
CREATE TABLE cmg_programado (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,
    forecast_date DATE NOT NULL,
    forecast_hour INTEGER NOT NULL CHECK (forecast_hour >= 0 AND forecast_hour <= 23),
    target_datetime TIMESTAMPTZ NOT NULL,
    target_date DATE NOT NULL,
    target_hour INTEGER NOT NULL CHECK (target_hour >= 0 AND target_hour <= 23),
    node TEXT NOT NULL,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'Coordinador',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_cmg_prog_forecast_target_node UNIQUE(forecast_datetime, target_datetime, node)
);
```

**Indexes**:
- `idx_cmg_prog_forecast_dt` on `forecast_datetime DESC`
- `idx_cmg_prog_target_dt` on `target_datetime DESC`
- `idx_cmg_prog_node` on `node`
- `idx_cmg_prog_target_date` on `target_date`

**Row Level Security**:
- Public read access (anonymous users)
- Write access only for service_role

**Data Retention**: Unlimited (all forecast history for accuracy analysis)

**Sample Data**:
```json
{
  "forecast_datetime": "2025-01-15T06:00:00+00:00",
  "target_datetime": "2025-01-15T10:00:00+00:00",
  "node": "NVA_P.MONTT___220",
  "cmg_usd": 72.50,
  "source": "Coordinador"
}
```

**Special Note**:
- `cmg_usd` column name is used for consistency, but actually stores `cmg_programmed` values
- Node names stored in Supabase format (e.g., `NVA_P.MONTT___220`)
- Frontend displays as `PMontt220` via NODE_DB_TO_FRONTEND mapping

---

#### 3. ml_predictions
**Purpose**: ML model predictions for CMG values

**Schema**:
```sql
CREATE TABLE ml_predictions (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,
    forecast_date DATE NOT NULL,
    forecast_hour INTEGER NOT NULL CHECK (forecast_hour >= 0 AND forecast_hour <= 23),
    target_datetime TIMESTAMPTZ NOT NULL,
    target_date DATE NOT NULL,
    target_hour INTEGER NOT NULL CHECK (target_hour >= 0 AND target_hour <= 23),
    horizon INTEGER NOT NULL CHECK (horizon >= 1 AND horizon <= 48),
    cmg_predicted DECIMAL(10, 2),
    prob_zero DECIMAL(5, 4) CHECK (prob_zero >= 0 AND prob_zero <= 1),
    threshold DECIMAL(5, 4) CHECK (threshold >= 0 AND threshold <= 1),
    value_pred DECIMAL(10, 2),
    confidence_lower DECIMAL(10, 2),
    confidence_upper DECIMAL(10, 2),
    model_version TEXT DEFAULT 'gpu_enhanced_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_ml_pred_forecast_target UNIQUE(forecast_datetime, target_datetime)
);
```

**Indexes**:
- `idx_ml_pred_forecast_dt` on `forecast_datetime DESC`
- `idx_ml_pred_target_dt` on `target_datetime DESC`
- `idx_ml_pred_horizon` on `horizon`
- `idx_ml_pred_target_date` on `target_date`
- `idx_ml_pred_prob_zero` on `prob_zero DESC WHERE prob_zero > 0.7` (for zero predictions)

**Row Level Security**:
- Public read access (anonymous users)
- Write access only for service_role (Railway ML backend)

**Data Retention**: Unlimited (all prediction history for accuracy analysis)

**Sample Data**:
```json
{
  "forecast_datetime": "2025-01-15T10:00:00+00:00",
  "target_datetime": "2025-01-15T11:00:00+00:00",
  "horizon": 1,
  "cmg_predicted": 75.23,
  "prob_zero": 0.12,
  "threshold": 0.5,
  "value_pred": 75.23,
  "confidence_lower": 68.50,
  "confidence_upper": 82.00,
  "model_version": "v2.0"
}
```

**Special Fields**:
- `prob_zero`: Probability that CMG = 0 (special ML model for zero detection)
- `threshold`: Decision threshold for zero classification (typically 0.5)
- `value_pred`: Raw regression value before zero thresholding
- `cmg_predicted`: Final prediction (0 if prob_zero > threshold, else value_pred)
- `horizon`: Forecast horizon (t+1 to t+48)

---

### Views

#### latest_cmg_online
```sql
CREATE VIEW latest_cmg_online AS
SELECT DISTINCT ON (node)
    datetime, date, hour, node, cmg_usd, source
FROM cmg_online
ORDER BY node, datetime DESC;
```
**Purpose**: Get the most recent CMG value for each node

---

#### latest_ml_predictions
```sql
CREATE VIEW latest_ml_predictions AS
SELECT DISTINCT ON (horizon)
    forecast_datetime, target_datetime, horizon,
    cmg_predicted, prob_zero, threshold, model_version
FROM ml_predictions
ORDER BY horizon, forecast_datetime DESC;
```
**Purpose**: Get the latest prediction for each forecast horizon

---

#### ml_forecast_accuracy
```sql
CREATE VIEW ml_forecast_accuracy AS
SELECT
    ml.forecast_datetime,
    ml.target_datetime,
    ml.horizon,
    ml.cmg_predicted,
    ml.prob_zero,
    actual.cmg_usd AS actual_cmg,
    ABS(ml.cmg_predicted - actual.cmg_usd) AS absolute_error,
    CASE
        WHEN actual.cmg_usd = 0 THEN (ml.prob_zero > ml.threshold)
        ELSE (ml.prob_zero <= ml.threshold)
    END AS zero_classification_correct
FROM ml_predictions ml
LEFT JOIN cmg_online actual
    ON ml.target_datetime = actual.datetime
    AND actual.node = 'NVA_P.MONTT___220'
WHERE actual.cmg_usd IS NOT NULL;
```
**Purpose**: Compare ML predictions against actual values for accuracy metrics

**Usage Example**:
```sql
-- Calculate MAE and zero accuracy over last 7 days
SELECT
    AVG(absolute_error) AS mae,
    AVG(zero_classification_correct::int) AS zero_accuracy
FROM ml_forecast_accuracy
WHERE target_datetime > NOW() - INTERVAL '7 days';
```

---

## Integration Status

### Fully Migrated to Supabase

#### Primary Endpoints (Production-Ready)
- **/api/cmg/current** - Main dashboard data
  - Uses: `cmg_online` + `cmg_programado` tables
  - Fallback: Cache files
  - Status: Fully operational

- **/api/ml_forecast** - ML predictions
  - Uses: `ml_predictions` table
  - Fallback: None (returns empty if unavailable)
  - Status: Fully operational

- **/api/historical_comparison** - Forecast accuracy
  - Uses: All 3 tables (`ml_predictions`, `cmg_programado`, `cmg_online`)
  - Fallback: None (requires Supabase)
  - Status: Fully operational

#### Cache Compatibility Layer
- **/api/cache** - Legacy cache API
  - Uses: Supabase tables (formatted as cache JSON)
  - Fallback: Physical cache files
  - Status: Operational (for backward compatibility)

---

### Using Cache Fallback

#### Optimizer (Hybrid Approach)
- **/api/optimizer** - Hydro optimization
  - Primary: User-selected data source
    - ML Predictions: Railway ML Backend → Supabase
    - CMG Programado: Supabase OR cache files
  - Fallback: Cache files if Supabase unavailable
  - Status: Hybrid (prefers Supabase, falls back gracefully)

#### Performance Analysis (Hybrid Approach)
- **/api/performance** - Performance comparison
  - Primary: Supabase (`cmg_online`)
  - Secondary: GitHub Gist (for historical CMG Programado with dual structure support)
  - Fallback: Local cache files
  - Status: Hybrid (uses multiple sources strategically)

---

### External Dependencies

#### Railway ML Backend
- **/api/ml_thresholds** - Proxy to Railway
  - Source: Railway ML service (separate Python app)
  - Environment Variable: `RAILWAY_ML_URL`
  - Status: Proxy only (does not use Supabase)
  - Purpose: Fetch ML model configuration

---

### Not Using Supabase

#### Legacy/Deprecated
- **/api/index** - Old ML predictions endpoint
  - Source: SIP API directly (no database)
  - Status: Deprecated (being replaced by `/api/ml_forecast`)
  - Usage: None (legacy code)

#### Debug/Development
- **/api/debug/supabase** - Debug queries
  - Source: Direct Supabase queries
  - Purpose: Testing and debugging only
  - Status: Development tool only

---

## Migration Summary

### Migration Complete
- CMG Online data collection → Supabase
- CMG Programado data storage → Supabase
- ML predictions storage → Supabase
- Main dashboard (`index.html`) → Supabase
- Forecast comparison (`forecast_comparison.html`) → Supabase
- ML config (`ml_config.html`) → Supabase

### Hybrid (Supabase + Fallback)
- Optimizer (`optimizer.html`) → Supabase preferred, cache fallback
- Performance analysis (`rendimiento.html`) → Supabase + GitHub Gist + cache

### No Migration Needed
- ML Thresholds → Railway backend (external service)
- Debug endpoints → Direct queries (development only)

---

## Data Sources Configuration

### Environment Variables Required

```bash
# Supabase (required for all production endpoints)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Railway ML Backend (required for ML predictions)
RAILWAY_ML_URL=https://your-railway-app.railway.app

# GitHub (optional, for optimization result storage)
GITHUB_TOKEN=your-github-token
```

### Cache File Locations
```
/data/cache/
  ├── cmg_programmed_latest.json      # CMG Programado cache
  ├── cmg_historical_latest.json      # CMG Online cache
  └── metadata.json                   # Cache metadata
```

### GitHub Gist Storage
- **CMG Online Historical**: Gist ID `8d7864eb26acf6e780d3c0f7fed69365`
- **CMG Programado Historical**: Gist ID `d68bb21360b1ac549c32a80195f99b09`
  - Supports dual structure:
    - Old: Aug 26 - Sep 9 (historical_data)
    - New: Oct 13 onwards (daily_data with cmg_programado_forecasts)
- **Optimization Results**: Gist ID `b7c9e8f3d2a1b4c5e6f7a8b9c0d1e2f3`

---

## Performance Considerations

### Caching Strategy
- **Client-side caching**: 60 seconds for `/api/cmg/current`
- **Server-side caching**: 5 minutes for `/api/ml_forecast`
- **No caching**: `/api/optimizer`, `/api/performance` (always fresh optimization)

### Query Optimization
- All tables have indexes on datetime and node columns
- Views use `DISTINCT ON` for efficient latest-value queries
- Date range queries limited to relevant ranges (e.g., 48 hours, 30 days)

### Scaling
- Supabase handles time-series data efficiently with indexes
- API endpoints are stateless serverless functions (Vercel)
- ML backend is separate service (Railway) to avoid blocking frontend

---

## Security

### Row Level Security (RLS)
- All tables have RLS enabled
- Anonymous users: READ-only access
- Service role: FULL access (write operations)
- API uses anon key for reads, service_role key for writes

### CORS
- All API endpoints have `Access-Control-Allow-Origin: *`
- Suitable for public dashboard use case
- Consider restricting in production if needed

---

## Future Enhancements

### Planned Improvements
1. **Real-time Updates**: Use Supabase Realtime for live dashboard updates
2. **Historical Data Archival**: Implement data retention policies (e.g., keep 1 year)
3. **Advanced Analytics**: Add more views for accuracy metrics, forecast bias analysis
4. **User Authentication**: Add user accounts for personalized configurations
5. **Multi-node Support**: Expand beyond Puerto Montt to other nodes

### Technical Debt
1. **Cache Fallback Removal**: Once Supabase is proven stable, remove cache file dependencies
2. **Gist Migration**: Move historical CMG Programado data from Gist to Supabase
3. **API Consolidation**: Merge `/api/index` functionality into `/api/ml_forecast`
4. **Error Handling**: Improve error messages and fallback strategies

---

## Development Guide

### Adding a New View
1. Create HTML file in `/public/`
2. Add JavaScript for API calls
3. Use Chart.js for visualizations
4. Follow naming convention: `<feature>.html`

### Adding a New API Endpoint
1. Create Python file in `/api/` directory
2. Implement `handler(BaseHTTPRequestHandler)` class
3. Add CORS headers
4. Use `SupabaseClient` for database access
5. Return JSON response
6. Add to this documentation

### Testing Supabase Queries
Use `/api/debug/supabase` to test queries:
```
GET /api/debug/supabase
```

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SUPABASE_URL=your-url
export SUPABASE_ANON_KEY=your-key

# Run Vercel dev server
vercel dev
```

---

## Troubleshooting

### Common Issues

#### "Supabase unavailable, falling back to cache"
- Check `SUPABASE_URL` and `SUPABASE_ANON_KEY` environment variables
- Verify Supabase project is active
- Check network connectivity

#### "No ML predictions available yet"
- Verify Railway ML backend is running
- Check `RAILWAY_ML_URL` environment variable
- Ensure ML service has pushed predictions to Supabase

#### "Insufficient data: X hours available but Y requested"
- Check available data in Supabase tables
- Reduce horizon parameter
- Verify data collection scripts are running

#### "CMG Programado selected but not available in cache"
- This is expected - user should select ML Predictions instead
- Or wait for CMG Programado data to be collected
- Check Supabase `cmg_programado` table

---

## Appendix: Node Mapping

### Database → Frontend Mapping
```javascript
NODE_DB_TO_FRONTEND = {
    'NVA_P.MONTT___220': 'PMontt220',
    'PIDPID________110': 'Pidpid110',
    'DALCAHUE______110': 'Dalcahue110'
}
```

### Frontend → Database Mapping
```javascript
NODE_FRONTEND_TO_DB = {
    'PMontt220': 'NVA_P.MONTT___220',
    'Pidpid110': 'PIDPID________110',
    'Dalcahue110': 'DALCAHUE______110'
}
```

**Why**: Supabase stores official node names from SIP API, frontend uses friendly names.

---

## Version History

- **v1.0** (2025-01-15): Initial documentation with full Supabase migration
- Database schema finalized
- All primary endpoints migrated
- Cache fallback strategy documented

---

**Document Maintained By**: Claude Code
**Last Updated**: 2025-01-15
**Status**: Production-Ready
