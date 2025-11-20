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

**Visualization**: Aggregate multiple days of performance

**Metrics per day**:
1. **Daily Total Distance**: Sum of absolute errors for all 24×24 cells
2. **Daily Average Distance**: Total / 24 (average error per forecast hour)

**Chart types**:
1. **Line chart**: Total distance over time (one line for ML, one for CMG Programado)
2. **Bar chart**: Average distance per day (grouped bars: ML vs Programado)
3. **Summary stats**:
   - Best day (lowest error)
   - Worst day (highest error)
   - Overall average accuracy
   - Trend (improving/worsening over time)

**Implementation**:
- Add to existing `public/rendimiento.html` or create new section
- API endpoint: `/api/performance_range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- Query Supabase for date range
- Group by date, calculate daily metrics
- Return time series data for charting

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

**Weekly Range API Response**:
```json
{
  "success": true,
  "start_date": "2025-11-13",
  "end_date": "2025-11-19",
  "daily_performance": [
    {
      "date": "2025-11-19",
      "ml_total_distance": 245.6,
      "ml_average_distance": 10.2,
      "prog_total_distance": 189.3,
      "prog_average_distance": 7.9
    },
    // ... more days
  ],
  "summary": {
    "ml_best_day": "2025-11-15",
    "ml_worst_day": "2025-11-19",
    "ml_overall_avg": 8.5,
    "prog_best_day": "2025-11-14",
    "prog_worst_day": "2025-11-18",
    "prog_overall_avg": 7.1
  }
}
```



4.- Upside a pimponear para el 2026:

Ver cómo usar el estudio hídrico del proyecto para extrapolar el caudal usando la lluvia proyectada.

Qué otras oportunidades podrían haber?