# Pudidi CMG Prediction System - Complete Technical Documentation

## Executive Summary

The **Pudidi CMG Prediction System** is a sophisticated real-time analytics platform designed to predict Marginal Costs of Power Generation (CMG - *Costo Marginal de Generación*) for the Chilean electrical grid. The platform helps hydroelectric operators optimize generation dispatch to maximize revenue by predicting when CMG prices will be high (ideal for selling energy) and when they'll drop to zero (indicating energy surplus - not ideal for generation).

**Key Statistics:**
- **192 trained ML models** (96 for zero detection, 96 for value prediction)
- **24-hour forecast horizon** with hourly granularity
- **32% better accuracy** than official CMG Programado forecasts ($30.43 MAE vs $45 baseline)
- **Hourly automated updates** via GitHub Actions
- **Three data sources**: CMG Online (actual), CMG Programado (official forecasts), ML Predictions

---

## 1. Business Context & Purpose

### Why CMG Matters for Hydroelectric Operations

In Chile's electrical grid, **CMG (Costo Marginal de Generación)** represents the cost of generating one additional MWh of electricity. For hydroelectric plants with small reservoirs:

1. **Water is Limited**: Small reservoirs can't store unlimited water
2. **CMG = Revenue**: When injecting power to the grid, operators receive CMG × MWh generated
3. **Zero CMG Problem**: When CMG = $0 (energy surplus), generating wastes water with zero revenue
4. **Optimization Goal**: Generate when CMG is HIGH, conserve water when CMG is LOW/ZERO

### Target User: Chiloé Hydroelectric Operations

The platform monitors three nodes in southern Chile:
- **NVA_P.MONTT___220** (Nueva Puerto Montt, 220kV) - Primary focus
- **PIDPID________110** (Pidpid-Piduco, 110kV)
- **DALCAHUE______110** (Dalcahue, 110kV)

### Value Proposition

| Without Platform | With Platform |
|-----------------|---------------|
| Rely on official forecasts (45 MAE error) | ML predictions (30 MAE error) |
| Reactive dispatch decisions | Proactive 24-hour planning |
| Water wasted during zero-CMG periods | Zero-detection alerts (F1=0.74) |
| Manual analysis | Automated optimization recommendations |

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES (External)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  SIP API (Coordinador)          │  Web Scraping (Playwright)            │
│  ├─ CMG Online (actual prices)  │  └─ CMG Programado (official forecast)│
│  └─ Real-time, hourly updates   │                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DATA PIPELINE (GitHub Actions)                        │
├─────────────────────────────────────────────────────────────────────────┤
│  Runs hourly at :05 UTC                                                  │
│  ├─ 1. Fetch CMG Programado (web scraping)                              │
│  ├─ 2. Fetch CMG Online (SIP API v4)                                    │
│  ├─ 3. Generate ML 24h Forecast (192 models)                            │
│  ├─ 4. Store to Supabase + GitHub Gists                                 │
│  └─ 5. Trigger Vercel deployment                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA STORAGE                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  Supabase (PostgreSQL)           │  GitHub Gists (Backup)               │
│  ├─ cmg_online                   │  ├─ CMG historical data              │
│  ├─ cmg_programado               │  ├─ ML predictions archive           │
│  └─ ml_predictions               │  └─ Optimization results             │
│                                   │                                      │
│  Local Cache (/data/cache/)      │                                      │
│  └─ JSON snapshots for failover  │                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API LAYER                                        │
├─────────────────────────────────────────────────────────────────────────┤
│  Vercel Serverless                │  Railway ML Backend                  │
│  ├─ /api/cmg/current             │  └─ FastAPI for ML predictions       │
│  ├─ /api/ml_forecast             │                                      │
│  ├─ /api/optimizer               │                                      │
│  ├─ /api/performance_range       │                                      │
│  └─ /api/historical_comparison   │                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (5 Pages)                               │
├─────────────────────────────────────────────────────────────────────────┤
│  index.html          - Real-time CMG monitoring dashboard               │
│  rendimiento.html    - Performance analysis (ML vs Programado)          │
│  optimizer.html      - Hydroelectric dispatch optimization              │
│  forecast_comparison - Historical forecast comparison matrix            │
│  performance_heatmap - Error visualization (24×24 heatmap)              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Machine Learning Prediction System

### 3.1 Two-Stage Ensemble Architecture

The ML system uses a **two-stage architecture** specifically designed to handle CMG's unique characteristic: **frequent zero values** (indicating energy surplus in the grid).

#### Stage 1: Zero-Risk Detection (Binary Classification)

**Purpose**: Predict probability that CMG will be $0 for each future hour

**Models per horizon**:
- 24 LightGBM binary classifiers
- 24 XGBoost binary classifiers
- 24 Meta-calibrators (ensemble refinement)
- **Total: 72 models**

**Output**: `P(CMG = 0)` for each hour t+1 to t+24

#### Stage 2: Value Prediction (Quantile Regression)

**Purpose**: Predict the actual CMG value (when not zero)

**Models per horizon**:
- 24 LightGBM median (q50) regressors
- 24 LightGBM q10 regressors (lower confidence bound)
- 24 LightGBM q90 regressors (upper confidence bound)
- 24 XGBoost regressors
- **Total: 96 models**

**Output**: Predicted CMG value with 80% confidence interval

#### Final Decision Logic

```python
for each horizon h in [1, 24]:
    if zero_probability[h] > optimal_threshold[h]:
        final_prediction = 0
    else:
        final_prediction = max(0, median_prediction[h])
```

**Total Models: 192** (96 Stage 1 + 96 Stage 2)

### 3.2 Features (150 Total)

The feature engineering creates **78 base features** for Stage 1, which then generates **72 meta-features** that combine with base features to create **150 features** for Stage 2.

| Category | Count | Examples |
|----------|-------|----------|
| **Temporal** | 11 | hour, hour_sin, hour_cos, is_weekend, is_peak_hour |
| **Lag Features** | 9 | cmg_lag_1h, cmg_lag_24h, cmg_lag_168h (weekly) |
| **Rolling Statistics** | 30 | mean/std/min/max/range/cv for 6h/12h/24h/48h/168h windows |
| **Zero Patterns** | 12 | zeros_count_24h, hours_since_zero, was_zero_1h_ago |
| **Trend Features** | 4 | cmg_change_1h, cmg_change_24h |
| **Seasonal** | 5 | cmg_same_hour_yesterday, cmg_7d_median_same_hour |
| **Time Categories** | 4 | is_night, is_morning, is_afternoon, is_evening |
| **Meta-Features** | 72 | zero_risk_lgb_t+{1-24}, zero_risk_xgb_t+{1-24} |

### 3.3 Model Performance

| Metric | Value | Comparison |
|--------|-------|------------|
| **MAE (Mean Absolute Error)** | $30.43/MWh | 32% better than baseline |
| **Baseline (CMG Programado)** | ~$45/MWh | Official forecasts |
| **Zero Detection F1** | 0.7439 | Good zero/non-zero classification |
| **ECE (Calibration Error)** | 0.0108 | Excellent probability calibration |

### 3.4 Feature Importance (Top 5)

| Rank | Feature | Importance | Interpretation |
|------|---------|-----------|-----------------|
| 1 | `cmg_lag_1h` | 15-20% | CMG is persistent (autocorrelated) |
| 2 | `cmg_lag_24h` | 10-12% | Daily seasonality pattern |
| 3 | `hour` | 8-10% | Intra-day demand variation |
| 4 | `cmg_rolling_mean_24h` | 7-9% | Recent trend indicator |
| 5 | `cmg_rolling_std_24h` | 6-8% | Market volatility |

**Key Insight**: The model is fundamentally a **persistence + seasonality forecaster** - recent CMG values and daily patterns are the strongest predictors.

### 3.5 Anti-Leakage Implementation

**Critical fix applied** to prevent data leakage:

```python
# WRONG (includes current hour in statistics):
df['cmg_mean_24h'] = df['CMG'].rolling(24).mean()

# CORRECT (only historical data):
shifted_series = df['CMG'].shift(1)  # Exclude current hour
df['cmg_mean_24h'] = shifted_series.rolling(24, min_periods=1).mean()
```

All rolling features use `shift(1)` before aggregation to ensure no lookahead bias.

---

## 4. Data Sources

### 4.1 CMG Online (Actual Realized Values)

**Source**: SIP API (Sistema de Información de Precios)
- **Endpoint**: `https://sipub.api.coordinador.cl:443/costo-marginal-online/v4/findByDate`
- **Type**: Actual real-time CMG prices from Chilean grid
- **Update Frequency**: Hourly (post-hoc)
- **Usage**: Ground truth for model evaluation

**Fetching Strategy**:
- Smart pagination with 4000 records/page
- Priority pages fetched first for complete coverage
- Up to 10 retries with exponential backoff

### 4.2 CMG Programado (Official Forecasts)

**Source**: Coordinador Eléctrico Nacional (Chilean System Operator)
- **Endpoint**: `https://sipub.api.coordinador.cl:443/cmg-programado-pid/v4/findByDate`
- **Type**: Official programmed/scheduled forecasts (PID)
- **Fetching**: Web scraping via Playwright (headless Chrome)
- **Coverage**: 48-72 hours ahead
- **Usage**: Baseline comparison for ML model performance

### 4.3 ML Predictions (Custom Forecasts)

**Source**: Internal ML system
- **Generation**: Hourly via GitHub Actions
- **Horizon**: 24 hours ahead
- **Features**: Confidence intervals, zero probability, model version
- **Storage**: Supabase + GitHub Gist backups

---

## 5. Data Storage Architecture

### 5.1 Primary: Supabase (PostgreSQL)

**Connection**: `https://btyfbrclgmphcjgrvcgd.supabase.co`

#### Table: `cmg_online`
```sql
CREATE TABLE cmg_online (
    id BIGSERIAL PRIMARY KEY,
    datetime TIMESTAMPTZ NOT NULL,
    date DATE NOT NULL,
    hour INTEGER (0-23) NOT NULL,
    node TEXT NOT NULL,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'SIP_API_v4',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_cmg_online_datetime_node UNIQUE(datetime, node)
);
```

#### Table: `cmg_programado`
```sql
CREATE TABLE cmg_programado (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,   -- When forecast was made
    target_datetime TIMESTAMPTZ NOT NULL,      -- What hour is predicted
    node TEXT NOT NULL,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'Coordinador',
    CONSTRAINT unique_cmg_prog UNIQUE(forecast_datetime, target_datetime, node)
);
```

#### Table: `ml_predictions`
```sql
CREATE TABLE ml_predictions (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,
    target_datetime TIMESTAMPTZ NOT NULL,
    horizon INTEGER (1-24) NOT NULL,
    cmg_predicted DECIMAL(10, 2),
    prob_zero DECIMAL(5, 4),        -- Probability price = $0
    threshold DECIMAL(5, 4),        -- Decision threshold
    confidence_lower DECIMAL(10, 2),
    confidence_upper DECIMAL(10, 2),
    model_version TEXT DEFAULT 'gpu_enhanced_v1',
    CONSTRAINT unique_ml_pred UNIQUE(forecast_datetime, target_datetime)
);
```

### 5.2 Backup: GitHub Gists

| Gist ID | Purpose |
|---------|---------|
| `8d7864eb26acf6e780d3c0f7fed69365` | CMG Online historical |
| `d68bb21360b1ac549c32a80195f99b09` | CMG Programado |
| `38b3f9b1cdae5362d3676911ab27f606` | ML Predictions |

### 5.3 Local Cache

**Path**: `/data/cache/`
- `cmg_historical_latest.json` - Latest CMG Online
- `cmg_programmed_latest.json` - Latest CMG Programado
- `ml_predictions_historical.json` - ML prediction history

---

## 6. Data Pipeline (Hourly Automation)

### 6.1 GitHub Actions Workflow

**File**: `.github/workflows/cmg_online_hourly.yml`
**Schedule**: Every hour at :05 UTC

```yaml
Execution Flow:
1. Fetch CMG Programado (Playwright web scraping)    ~30-40s
2. Fetch CMG Online (SIP API v4)                     ~45-50s
3. Generate ML 24h Forecast (192 models)             ~2-3s
4. Store ML Predictions → Supabase + Gist
5. Store CMG Programado → Supabase + Gist
6. Store CMG Online → Supabase + Gist
7. Verify data integrity
8. Git commit & push
9. Trigger Vercel deployment

Total Duration: ~2-3 minutes per cycle
```

### 6.2 Key Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `scripts/smart_cmg_online_update.py` | Fetch CMG Online from SIP API |
| `scripts/download_cmg_programado_simple.py` | Web scrape CMG Programado |
| `scripts/ml_hourly_forecast.py` | Generate 24h ML predictions |
| `scripts/ml_feature_engineering.py` | Create 78 base features |
| `scripts/store_ml_predictions.py` | Store to Supabase + Gist |
| `scripts/store_cmg_online_dual.py` | Dual-write CMG Online |
| `scripts/store_cmg_programado.py` | Store CMG Programado |

---

## 7. API Endpoints

### 7.1 Vercel Serverless Functions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/cmg/current` | GET | Current CMG data (historical + programmed) |
| `/api/ml_forecast` | GET | Latest 24h ML predictions |
| `/api/optimizer` | POST | Run hydro optimization solver |
| `/api/performance_range` | GET/POST | Performance analysis for date range |
| `/api/performance_heatmap` | GET | 24×24 error heatmap data |
| `/api/historical_comparison` | GET | Forecast matrix comparison |
| `/api/ml_thresholds` | GET | ML model configuration |

### 7.2 Response Structure Example

**`/api/ml_forecast` Response**:
```json
{
  "generated_at": "2025-12-28 11:30:45",
  "base_datetime": "2025-12-28 10:00:00",
  "model_version": "gpu_enhanced_v1",
  "forecasts": [
    {
      "horizon": 1,
      "target_datetime": "2025-12-28 11:00:00",
      "predicted_cmg": 48.75,
      "zero_probability": 0.0342,
      "decision_threshold": 0.4921,
      "confidence_interval": {
        "lower_10th": 30.45,
        "median": 48.75,
        "upper_90th": 67.23
      }
    }
  ]
}
```

### 7.3 Railway ML Backend

**URL**: FastAPI service on Railway
**Endpoints**:
- `GET /` - Health check
- `GET /api/ml_forecast` - ML predictions
- `GET /api/ml_thresholds` - Model thresholds

---

## 8. Frontend Dashboard

### 8.1 Main Pages

| Page | URL | Purpose |
|------|-----|---------|
| **CMG Monitor** | `/index.html` | Real-time CMG tracking, multi-node charts |
| **Performance** | `/rendimiento.html` | ML vs Programado accuracy analysis |
| **Optimizer** | `/optimizer.html` | Hydroelectric dispatch optimization |
| **Comparison** | `/forecast_comparison.html` | Historical forecast matrices |
| **Heatmap** | `/performance_heatmap.html` | 24×24 error visualization |

### 8.2 Visualization Stack

- **Plotly.js 2.27.0**: Line charts, bar charts, heatmaps
- **Chart.js**: Generation/storage charts in optimizer
- **Tailwind CSS**: Responsive UI framework

### 8.3 Key Dashboard Features

**CMG Monitor (index.html)**:
- Real-time CMG value display
- Multi-node comparison chart
- Data quality indicators (coverage %)
- Status badges (Live/Recent/Stale)

**Performance Analysis (rendimiento.html)**:
- Date range selector
- Temporal metrics (daily trends)
- Structural degradation curve (horizon performance)
- 4 KPI cards: ML MAE, Programado MAE, improvement %

**Optimizer (optimizer.html)**:
- Power generation limits (0.3-2.3 MW)
- Reservoir constraints (1,000-50,000 m³)
- Projected revenue calculation
- SCADA-style hourly schedule table

---

## 9. Hydroelectric Optimization Engine

### 9.1 Optimization Objective

**Maximize**: `Σ P(t) × CMG(t)` (Revenue = Power × Price)

**Subject to**:
- `p_min ≤ P(t) ≤ p_max` (Power limits)
- `s_min ≤ S(t) ≤ s_max` (Storage limits)
- `S(t+1) = S(t) + inflow - P(t) × κ` (Water balance)

Where:
- `P(t)`: Power generation at hour t (MW)
- `S(t)`: Reservoir storage at hour t (m³)
- `κ`: Water-to-power conversion factor (0.667 default)

### 9.2 Solver

**Technology**: Linear Programming (`scipy.linprog`)
**Fallback**: Greedy heuristic if scipy unavailable

### 9.3 Output Metrics

- **Projected Revenue**: Total USD from dispatch schedule
- **Capacity Factor**: Avg generation / Max capacity (%)
- **Peak Generation**: Maximum power in horizon
- **SCADA Schedule**: Hourly power/storage table

---

## 10. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **ML Framework** | LightGBM, XGBoost | Gradient boosting models |
| **Feature Engineering** | pandas, numpy | Data processing |
| **API Framework** | Python 3.9, FastAPI | Backend services |
| **Database** | Supabase (PostgreSQL) | Primary storage |
| **Frontend** | HTML5, Tailwind CSS | UI framework |
| **Charting** | Plotly.js, Chart.js | Visualizations |
| **Optimization** | scipy.linprog | Linear programming |
| **Deployment** | Vercel, Railway | Serverless + containers |
| **Automation** | GitHub Actions | Hourly data pipeline |
| **Web Scraping** | Playwright | CMG Programado fetching |

---

## 11. Key File Structure

```
/vercel_deploy/
├── api/                              # Vercel serverless functions
│   ├── cmg/current.py               # Main CMG endpoint
│   ├── ml_forecast.py               # ML predictions
│   ├── optimizer.py                 # Hydro optimization
│   ├── performance_range.py         # Performance analysis
│   └── historical_comparison.py     # Forecast comparison
│
├── scripts/                          # Data pipeline scripts
│   ├── ml_feature_engineering.py    # 78 feature creation
│   ├── ml_hourly_forecast.py        # 192-model prediction
│   ├── smart_cmg_online_update.py   # SIP API fetcher
│   └── store_*.py                   # Storage handlers
│
├── models_24h/                       # Trained ML models
│   ├── zero_detection/              # 96 Stage 1 models
│   │   ├── lgb_t+{1-24}.txt
│   │   ├── xgb_t+{1-24}.json
│   │   ├── meta_calibrator.pkl
│   │   └── optimal_thresholds_by_hour_calibrated.npy
│   └── value_prediction/            # 96 Stage 2 models
│       ├── lgb_median_t+{1-24}.txt
│       ├── lgb_q10_t+{1-24}.txt
│       ├── lgb_q90_t+{1-24}.txt
│       └── xgb_t+{1-24}.json
│
├── public/                           # Frontend assets
│   ├── index.html                   # Main dashboard
│   ├── rendimiento.html             # Performance page
│   ├── optimizer.html               # Optimization page
│   └── js/                          # Client scripts
│
├── lib/utils/                        # Shared utilities
│   ├── supabase_client.py           # Database client
│   └── cache_manager_readonly.py    # Caching logic
│
├── data/cache/                       # Local cache files
│   ├── cmg_historical_latest.json
│   ├── cmg_programmed_latest.json
│   └── ml_predictions_historical.json
│
└── .github/workflows/                # Automation
    ├── cmg_online_hourly.yml        # Main hourly pipeline
    ├── daily_optimization.yml        # Daily optimization
    └── cmg_5pm_snapshot.yml          # Daily snapshot
```

---

## 12. Summary

The Pudidi CMG Prediction System is a **production-grade ML pipeline** that:

1. **Predicts CMG prices** 24 hours ahead using 192 trained models
2. **Detects zero-price periods** with 74% F1 score (critical for avoiding water waste)
3. **Outperforms official forecasts** by 32% (MAE $30.43 vs $45)
4. **Automates data collection** hourly via GitHub Actions
5. **Provides optimization** for hydroelectric dispatch scheduling
6. **Offers comprehensive visualization** across 5 dashboard pages

The system is designed specifically for the Chilean electrical grid's marginal cost dynamics and the unique constraints of small-reservoir hydroelectric operations.
