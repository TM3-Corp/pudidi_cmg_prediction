# Production Models

This document describes the ML models currently deployed in production for the CMG prediction system.

## Overview

The system uses two types of predictions:
1. **CMG Price Prediction** - Forecasts the CMG value ($/MWh) for each hour
2. **CMG Zero Detection** - Binary classification to detect CMG=0 hours

## CMG Price Prediction

### Model Architecture
- **Ensemble**: LightGBM + XGBoost (averaged predictions)
- **Training**: Walk-forward validation with expanding window
- **Horizons**: 24 separate models, one per forecast hour (t+1 to t+24)

### Model Location
```
models_24h/
├── value_prediction/
│   ├── lightgbm_h{01-24}.json    # 24 LightGBM models
│   └── xgboost_h{01-24}.json     # 24 XGBoost models
```

### Performance
- **MAE**: ~$40 (varies by test period)
- **Baseline (Persistence)**: $63.57 (CMG[t+h] = CMG[t-24])
- **Improvement**: ~37% over baseline

### Key Features
- Recent CMG values (lags 1-24, 48, 72, 168)
- Hour of day (cyclical encoding)
- Day of week (cyclical encoding)
- Rolling statistics (mean, std, min, max)
- Weekend/holiday indicators

### Training Script
`scripts/training/ml_model_training.py`

## CMG Zero Detection

### Purpose
Detect hours where CMG=0 (zero marginal cost), which typically occur during:
- High solar generation (midday hours 10-17)
- Low demand periods
- Grid curtailment events

### Model Architecture
- **Primary**: LightGBM binary classifier per horizon
- **Secondary**: XGBoost binary classifier per horizon
- **Meta-calibrator**: Isotonic regression for probability calibration

### Model Location
```
models_24h/
├── zero_detection/
│   ├── lightgbm_zero_h{01-24}.json     # 24 LightGBM classifiers
│   ├── xgboost_zero_h{01-24}.json      # 24 XGBoost classifiers
│   ├── meta_calibrator_h{01-24}.joblib # 24 meta-calibrators
│   └── optimal_thresholds_by_hour_calibrated.csv
```

### Threshold Strategy
- **Production Thresholds**: 36-37% (NOT 50%)
- **Rationale**: Prioritize recall over precision - catching CMG=0 hours is more valuable than avoiding false positives
- **Trade-off**: Accept some false positives to avoid missing actual zero-price hours

### Performance by Hour (Peak Solar Hours)

| Hour | Threshold | Precision | Recall | F1 |
|------|-----------|-----------|--------|-----|
| 10 | 37.0% | 80.1% | 91.1% | 85.2% |
| 11 | 37.0% | 78.8% | 84.3% | 81.5% |
| 12 | 36.9% | 74.0% | 89.3% | 81.0% |
| 13 | 37.0% | 76.5% | 88.7% | 82.1% |
| 14 | 37.0% | 77.8% | 87.5% | 82.4% |
| 15 | 37.0% | 78.2% | 87.9% | 82.7% |
| 16 | 36.9% | 80.9% | 84.9% | 82.8% |
| 17 | 36.9% | 77.3% | 81.2% | 79.2% |

### Key Insight
Hours 10-17 achieve 80-91% recall for zero detection. These are peak solar hours when CMG=0 is most common and most valuable to predict.

### Training Script
`scripts/training/ml_model_training.py`

## Prediction Pipeline

### Hourly Workflow (GitHub Actions)
1. `cmg_online_hourly.yml` triggers every hour at :05
2. Fetches latest CMG data from SIP API
3. Runs `ml_hourly_forecast.py` to generate 24h predictions
4. Stores predictions to Supabase + Gist backup
5. Updates cache files for frontend

### Scripts
- `scripts/production/ml_hourly_forecast.py` - Main prediction script
- `scripts/production/store_ml_predictions.py` - Storage handler
- `scripts/training/ml_feature_engineering.py` - Feature creation

## Model Updates

Models are retrained when:
1. Significant performance degradation detected
2. New features added
3. Seasonal retraining (quarterly recommended)

### Retraining Process
```bash
# Full retraining with walk-forward validation
python scripts/training/ml_model_training.py --full-retrain

# Feature engineering updates
python scripts/training/ml_feature_engineering.py
```

## Related Documentation
- [Experimental Results](./EXPERIMENTAL_RESULTS.md) - History of model experiments
- [Methodology](./METHODOLOGY.md) - Evaluation methodology
- [Technical Overview](../TECHNICAL_OVERVIEW.md) - System architecture
