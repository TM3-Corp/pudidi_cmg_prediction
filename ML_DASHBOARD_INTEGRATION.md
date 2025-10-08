# 📊 ML Predictions Dashboard Integration Guide

## ✅ What's Ready

### 1. ML Forecast API
**Endpoint**: `/api/ml_forecast`
**Status**: ✅ Ready to use
**Updates**: Hourly (when GitHub Actions runs)

**Response Format**:
```json
{
  "success": true,
  "generated_at": "2025-10-08 17:16:12 UTC",
  "base_datetime": "2025-09-06 01:00:00",
  "predictions_count": 24,
  "predictions": [
    {
      "datetime": "2025-09-06 02:00:00",
      "hour": 2,
      "horizon": 1,
      "cmg_predicted": 0.0,
      "zero_probability": 0.4143,
      "decision_threshold": 0.3382,
      "value_prediction": 55.68,
      "confidence_lower": 32.67,
      "confidence_median": 55.68,
      "confidence_upper": 62.09,
      "is_ml_prediction": true
    },
    // ... 23 more hours
  ]
}
```

### 2. ML Thresholds API
**Endpoint**: `/api/ml_thresholds`
**Status**: ✅ Ready to use

**Response Format**:
```json
{
  "success": true,
  "thresholds": [
    {
      "horizon": 1,
      "horizon_label": "t+1",
      "optimal_threshold": 0.3382,
      "current_threshold": 0.3382,
      "min_allowed": 0.2706,
      "max_allowed": 0.4058,
      "precision": 0.603,
      "recall": 0.764,
      "f1": 0.674,
      "auc": 0.922
    },
    // ... 23 more horizons
  ],
  "info": {
    "description": "Decision thresholds for zero-CMG classification",
    "adjustable": true,
    "safe_range_note": "Adjustments limited to ±20% from optimal value",
    "impact": "Lower threshold = more zero predictions (conservative)"
  }
}
```

---

## 📈 Integration into "Evolución del CMG - Todos los Nodos" Chart

### Step 1: Add ML Predictions Line

In your chart component, fetch ML predictions:

```javascript
// Fetch ML predictions
const fetchMLPredictions = async () => {
  try {
    const response = await fetch('/api/ml_forecast');
    const data = await response.json();

    if (data.success) {
      return data.predictions.map(pred => ({
        datetime: new Date(pred.datetime),
        cmg: pred.cmg_predicted,
        type: 'ml_prediction',
        confidence_lower: pred.confidence_lower,
        confidence_upper: pred.confidence_upper,
        zero_probability: pred.zero_probability
      }));
    }
    return [];
  } catch (error) {
    console.error('Failed to fetch ML predictions:', error);
    return [];
  }
};
```

### Step 2: Add to Chart Data

```javascript
// Combine all data sources
const chartData = {
  historical: cmgOnlineData,      // Past CMG values (solid line)
  programmed: cmgProgramadoData,  // Official forecast (dashed line)
  ml_prediction: mlPredictionData // ML forecast (NEW - dotted line)
};

// Chart configuration
const series = [
  {
    name: 'CMG Online (Real)',
    data: chartData.historical,
    type: 'line',
    lineStyle: { type: 'solid', width: 2 },
    color: '#1f77b4'
  },
  {
    name: 'CMG Programado (Official)',
    data: chartData.programmed,
    type: 'line',
    lineStyle: { type: 'dashed', width: 2 },
    color: '#ff7f0e'
  },
  {
    name: 'ML Prediction',
    data: chartData.ml_prediction,
    type: 'line',
    lineStyle: { type: 'dotted', width: 3 },
    color: '#2ca02c',  // Green for ML
    markPoint: {
      data: chartData.ml_prediction
        .filter(p => p.cmg === 0)  // Highlight zero predictions
        .map(p => ({
          coord: [p.datetime, p.cmg],
          symbol: 'circle',
          symbolSize: 6,
          itemStyle: { color: '#d62728' }  // Red dot for zeros
        }))
    }
  }
];
```

### Step 3: Add Confidence Interval (Optional)

```javascript
// Add shaded confidence interval
{
  name: 'ML Confidence Interval',
  type: 'line',
  data: chartData.ml_prediction.map(p => [p.datetime, p.confidence_upper]),
  lineStyle: { opacity: 0 },
  areaStyle: {
    color: 'rgba(44, 160, 44, 0.1)',  // Light green
    origin: 'start'
  },
  stack: 'confidence',
  smooth: true
},
{
  name: 'ML Confidence Interval Lower',
  type: 'line',
  data: chartData.ml_prediction.map(p => [p.datetime, p.confidence_lower]),
  lineStyle: { opacity: 0 },
  areaStyle: {
    color: 'rgba(44, 160, 44, 0.1)',
    origin: 'start'
  },
  stack: 'confidence',
  smooth: true
}
```

---

## ⚙️ Threshold Configuration Dashboard

### Create Threshold Settings Component

```javascript
const ThresholdSettings = () => {
  const [thresholds, setThresholds] = useState([]);
  const [selectedHorizon, setSelectedHorizon] = useState(null);

  useEffect(() => {
    // Fetch thresholds
    fetch('/api/ml_thresholds')
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setThresholds(data.thresholds);
        }
      });
  }, []);

  return (
    <div className="threshold-settings">
      <h3>ML Decision Thresholds</h3>
      <p className="info">{thresholds.info?.impact}</p>

      <table className="threshold-table">
        <thead>
          <tr>
            <th>Horizon</th>
            <th>Optimal</th>
            <th>Current</th>
            <th>Range</th>
            <th>Precision</th>
            <th>Recall</th>
            <th>F1</th>
          </tr>
        </thead>
        <tbody>
          {thresholds.map(t => (
            <tr key={t.horizon}>
              <td>t+{t.horizon}</td>
              <td>{t.optimal_threshold.toFixed(4)}</td>
              <td>
                <input
                  type="range"
                  min={t.min_allowed}
                  max={t.max_allowed}
                  step="0.001"
                  value={t.current_threshold}
                  onChange={(e) => handleThresholdChange(t.horizon, e.target.value)}
                />
                <span>{t.current_threshold.toFixed(4)}</span>
              </td>
              <td>[{t.min_allowed.toFixed(3)}, {t.max_allowed.toFixed(3)}]</td>
              <td>{(t.precision * 100).toFixed(1)}%</td>
              <td>{(t.recall * 100).toFixed(1)}%</td>
              <td>{(t.f1 * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
```

---

## 🔄 Automatic Data Handling

### Handling Missing Latest Hour

The ML forecast script automatically uses the **last available data point** as the base time:

```
Current time: 14:30 (Oct 8)
Latest CMG Online: 13:00 (Oct 8)  ← Missing 14:00
Base time used: 13:00              ← Automatically detected
Predictions: 14:00, 15:00, ... 13:00 (next day)
```

**In your chart**:
- Show CMG Online up to 13:00 (solid line)
- Show ML predictions from 14:00 onwards (dotted line)
- The gap is natural and expected

---

## 📊 Example Chart Labels

```javascript
const legend = {
  data: [
    'CMG Online (Real)',
    'CMG Programado (Official)',
    'ML Prediction',  // NEW
    'Zero CMG (ML)'   // NEW - Red dots for predicted zeros
  ]
};

const tooltip = {
  trigger: 'axis',
  formatter: (params) => {
    let result = `<b>${params[0].axisValue}</b><br/>`;

    params.forEach(item => {
      if (item.seriesName === 'ML Prediction') {
        const pred = mlPredictionData.find(p => p.datetime === item.axisValue);
        result += `
          ${item.marker} ${item.seriesName}: $${item.value}<br/>
          &nbsp;&nbsp;Zero Probability: ${(pred.zero_probability * 100).toFixed(1)}%<br/>
          &nbsp;&nbsp;Confidence: [$${pred.confidence_lower}, $${pred.confidence_upper}]
        `;
      } else {
        result += `${item.marker} ${item.seriesName}: $${item.value}<br/>`;
      }
    });

    return result;
  }
};
```

---

## 🚀 Deployment Checklist

- [x] ML forecast script created (`scripts/ml_hourly_forecast.py`)
- [x] Optimal thresholds configured
- [x] ML forecast API created (`/api/ml_forecast`)
- [x] ML thresholds API created (`/api/ml_thresholds`)
- [ ] Add GitHub Actions workflow for hourly predictions
- [ ] Integrate ML predictions into chart
- [ ] Add threshold configuration UI
- [ ] Test with live data

---

## 📝 Next Steps

1. **Test API endpoints locally**:
   ```bash
   # Test ML forecast
   curl http://localhost:3000/api/ml_forecast | jq '.predictions[0]'

   # Test thresholds
   curl http://localhost:3000/api/ml_thresholds | jq '.thresholds[0]'
   ```

2. **Add to GitHub Actions** (create `.github/workflows/ml_hourly_forecast.yml`):
   ```yaml
   name: ML Hourly Forecast

   on:
     schedule:
       - cron: '10 * * * *'  # Run at :10 every hour
     workflow_dispatch:

   jobs:
     forecast:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v4
           with:
             python-version: '3.11'
         - run: pip install pandas numpy lightgbm xgboost scikit-learn
         - run: python scripts/ml_hourly_forecast.py
         - run: |
             git config user.name "GitHub Actions"
             git config user.email "actions@github.com"
             git add data/ml_predictions/
             git commit -m "🤖 ML Forecast: $(date -u +'%Y-%m-%d %H:00 UTC')" || echo "No changes"
             git push
   ```

3. **Update dashboard** to fetch and display ML predictions

---

**You're all set to display ML predictions on your dashboard!** 🎉
