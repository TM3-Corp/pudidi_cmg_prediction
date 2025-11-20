1.- Supuestos:

Pueden preparar 1 hoja resumen con los supuestos usados?

Entre otros: fuentes de datos usados; el modelo se entrenó 1 sola vez o se sigue haciendo; usan el track error del coordinador para mejorar proyecciones?; etc.

 

2.- CEX:

Favor separar en 2 columnas la fecha y la hora de los resultados Scada.

E idealmente que la numeración tenga formato chileno (puntos/comas).


3.- "Test de la blancura": ✅ PLANNED

**Goal**: Visualize how ML and CMG Programado forecasts perform against real CMG Online values.

**Problem**: Current forecast_comparison.html only shows comparisons for ONE specific hour.

**Solution**: Daily and weekly performance heatmaps

---

### 📊 3.1 Daily Heatmap (24x24 Matrix)

**Visualization**:
- **Rows**: Forecast Hour (when forecast was made, 0-23)
- **Columns**: Target Hour (what was being predicted, 0-23)
- **Colors**:
  - 🔴 Red: Forecast ABOVE actual (overpredicted)
  - 🔵 Blue: Forecast BELOW actual (underpredicted)
  - ⚪ White: Forecast close to actual (neutral)
- **Two separate heatmaps**:
  1. ML Predictions heatmap (24 forecasts × 24 targets)
  2. CMG Programado heatmap (24 forecasts × 24 targets)

**Important**: For CMG Programado, only show the **first 24 hours** of each forecast (not all 72), so it's comparable to ML predictions.

**Metrics per heatmap**:
1. **Total Absolute Distance**: Sum of |forecast - actual| for all cells
   - Example: If h0 is +3 and h1 is -4, total = 3 + 4 = 7
2. **Average Distance**: Total distance / 24 (average error per forecast)

**Implementation**:
- Create new page: `public/performance_heatmap.html`
- API endpoint: `/api/performance_heatmap?date=YYYY-MM-DD`
- Query Supabase:
  - Get all ML forecasts for selected date (24 forecast hours × 24 horizons)
  - Get all CMG Programado forecasts for selected date (24 × 24, filter to first 24h only)
  - Get CMG Online actual values for that date (24 hours)
- Calculate: `error = forecast - actual` for each cell
- Color scale:
  - Deep red: +20 or more
  - Light red: +5 to +20
  - White: -5 to +5
  - Light blue: -20 to -5
  - Deep blue: -20 or less

---

### 📈 3.2 Weekly/Custom Range Performance

**Visualization**: Aggregate multiple days of performance with **dual-dimension analysis**

---

#### 🎯 3.2.1 Dual-Dimension Metrics

Two complementary analytical perspectives:

**1. Temporal Dimension (By Day)**
- **Question**: "Which days had better/worse forecast performance?"
- **Metric**: Average absolute distance per day
- **Calculation**: For each day, average |forecast - actual| across all 24 forecast hours and 24 horizons
- **Use case**:
  - Identify outlier days
  - Detect temporal patterns (e.g., weekends vs weekdays)
  - Check day-to-day variability
- **Example output**:
  ```
  Nov 15: ML avg = 15.2, Prog avg = 18.5 ← Good day
  Nov 18: ML avg = 45.8, Prog avg = 52.1 ← Bad day (high variability?)
  ```

**2. Structural Dimension (By Horizon)**
- **Question**: "How does forecast accuracy degrade over time?"
- **Metric**: Average absolute distance per horizon (t+1 to t+24)
- **Calculation**: For each horizon, average |forecast - actual| across all days and all forecast hours
- **Use case**:
  - Understand forecast reliability by time horizon
  - Expected pattern: Near-term (t+1, t+2) more accurate than far-term (t+23, t+24)
  - Compare model degradation curves (ML vs Programado)
- **Example output**:
  ```
  ML: t+1: 8.2, t+2: 10.5, ..., t+24: 35.8 ← Degrades over time
  Prog: t+1: 12.1, t+2: 13.2, ..., t+24: 18.5 ← More stable
  ```

**Why Both Dimensions Matter**:
- **Temporal**: Reveals external factors (weather events, grid conditions)
- **Structural**: Reveals model limitations (how far ahead can we trust?)

---

#### 📊 3.2.2 Chart Types

1. **Line chart - Temporal**: Average distance by day
   - X-axis: Date
   - Y-axis: Average absolute distance ($/MWh)
   - Two lines: ML (blue) vs CMG Programado (orange)
   - Shows variability across time

2. **Line chart - Structural**: Average distance by horizon
   - X-axis: Forecast horizon (t+1 to t+24)
   - Y-axis: Average absolute distance ($/MWh)
   - Two lines: ML vs CMG Programado
   - Shows forecast degradation curve

3. **Bar chart**: Daily performance comparison
   - Grouped bars per day: ML vs Programado
   - Highlights which model performed better each day

4. **Summary stats table**:
   - Overall averages (temporal and structural)
   - Best/worst days
   - Best/worst horizons
   - Model comparison metrics

---

#### 🔧 3.2.3 Implementation

**API endpoint**: `/api/performance_range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

**Query logic**:
1. Fetch all forecasts and actuals for date range
2. Calculate errors: forecast - actual for each (day, hour, horizon)
3. Group and average two ways:
   - **By day**: Average across all hours and horizons
   - **By horizon**: Average across all days and hours

**Frontend**: Add to `public/rendimiento.html` or create new section
- Date range selector
- Four visualizations (2 line charts, 1 bar chart, 1 stats table)
- Toggle between temporal/structural views

---

### 🎯 3.3 Implementation Plan

**Step 1**: Create daily heatmap API endpoint
- File: `api/performance_heatmap.py`
- Query all forecasts and actuals for specific date
- Calculate error matrix (24×24)
- Return structured data with metrics

**Step 2**: Create daily heatmap frontend
- File: `public/performance_heatmap.html`
- Use Chart.js or D3.js for heatmap visualization
- Date selector to pick any historical date
- Two side-by-side heatmaps (ML vs Programado)
- Display total/average distance metrics

**Step 3**: Add weekly aggregation API
- File: `api/performance_range.py`
- Query date range
- Calculate daily metrics
- Return time series

**Step 4**: Add weekly chart to frontend
- Update `public/rendimiento.html`
- Line/bar charts for trends
- Summary statistics table

---

### 📐 Example Data Structure

**Daily Heatmap API Response**:
```json
{
  "success": true,
  "date": "2025-11-19",
  "ml_predictions": {
    "matrix": [[/* 24×24 errors */]],
    "total_distance": 245.6,
    "average_distance": 10.2,
    "actuals_available": 24
  },
  "cmg_programado": {
    "matrix": [[/* 24×24 errors */]],
    "total_distance": 189.3,
    "average_distance": 7.9,
    "actuals_available": 24
  }
}
```

**Range Performance API Response** (with dual-dimension metrics):
```json
{
  "success": true,
  "start_date": "2025-11-13",
  "end_date": "2025-11-19",

  "metrics_by_day": [
    {
      "date": "2025-11-19",
      "ml_avg_distance": 28.3,
      "ml_forecasts_count": 576,
      "prog_avg_distance": 35.2,
      "prog_forecasts_count": 576
    },
    {
      "date": "2025-11-18",
      "ml_avg_distance": 15.7,
      "ml_forecasts_count": 576,
      "prog_avg_distance": 18.9,
      "prog_forecasts_count": 576
    }
    // ... more days
  ],

  "metrics_by_horizon": {
    "ml": [
      {"horizon": 1, "avg_distance": 8.2, "forecast_count": 168},
      {"horizon": 2, "avg_distance": 10.5, "forecast_count": 168},
      {"horizon": 3, "avg_distance": 12.1, "forecast_count": 168},
      // ... up to t+24
      {"horizon": 24, "avg_distance": 35.8, "forecast_count": 168}
    ],
    "programado": [
      {"horizon": 1, "avg_distance": 12.1, "forecast_count": 168},
      {"horizon": 2, "avg_distance": 13.2, "forecast_count": 168},
      {"horizon": 3, "avg_distance": 14.5, "forecast_count": 168},
      // ... up to t+24
      {"horizon": 24, "avg_distance": 18.5, "forecast_count": 168}
    ]
  },

  "summary": {
    "temporal": {
      "ml_best_day": {"date": "2025-11-15", "avg_distance": 12.3},
      "ml_worst_day": {"date": "2025-11-18", "avg_distance": 45.8},
      "ml_overall_avg": 22.7,
      "ml_std_dev": 8.4,
      "prog_best_day": {"date": "2025-11-14", "avg_distance": 15.1},
      "prog_worst_day": {"date": "2025-11-18", "avg_distance": 52.1},
      "prog_overall_avg": 28.3,
      "prog_std_dev": 10.2
    },
    "structural": {
      "ml_best_horizon": {"horizon": 1, "avg_distance": 8.2},
      "ml_worst_horizon": {"horizon": 24, "avg_distance": 35.8},
      "ml_degradation_rate": 1.15,
      "prog_best_horizon": {"horizon": 1, "avg_distance": 12.1},
      "prog_worst_horizon": {"horizon": 24, "avg_distance": 18.5},
      "prog_degradation_rate": 0.27
    },
    "comparison": {
      "ml_wins_days": 4,
      "prog_wins_days": 3,
      "ml_wins_horizons": 8,
      "prog_wins_horizons": 16
    }
  }
}
```

**Interpretation**:
- **Temporal**: ML has lower std_dev (8.4 vs 10.2) → more consistent day-to-day
- **Structural**: Prog has lower degradation_rate (0.27 vs 1.15) → more stable across horizons
- **Comparison**: ML better at near-term (wins 8 horizons), Prog better at far-term (wins 16 horizons)



4.- Upside a pimponear para el 2026:

Ver cómo usar el estudio hídrico del proyecto para extrapolar el caudal usando la lluvia proyectada.

Qué otras oportunidades podrían haber?