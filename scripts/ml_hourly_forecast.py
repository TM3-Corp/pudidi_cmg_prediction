#!/usr/bin/env python3
"""
ML Hourly Forecast Script
==========================

Generates 24-hour CMG forecasts using trained models.

Runs every hour via GitHub Actions:
1. Loads latest CMG Online data
2. Creates features using production feature engineering
3. Loads trained models (Stage 1 + Stage 2)
4. Generates 24-hour forecast
5. Saves predictions to JSON

Output:
- data/ml_predictions/latest.json
- data/ml_predictions/archive/YYYY-MM-DD-HH.json
"""

import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

import lightgbm as lgb
import xgboost as xgb
from ml_feature_engineering import CleanCMGFeatureEngineering

# Constants
MODELS_DIR = Path(__file__).parent.parent / "models_24h"
DATA_DIR = Path(__file__).parent.parent / "data"
CMG_ONLINE_FILE = DATA_DIR / "cmg_online_from_csv.json"
OUTPUT_DIR = DATA_DIR / "ml_predictions"
ARCHIVE_DIR = OUTPUT_DIR / "archive"


def load_cmg_online_data():
    """Load latest CMG Online data from JSON"""
    print(f"[1/5] Loading CMG Online data from {CMG_ONLINE_FILE}...")

    try:
        with open(CMG_ONLINE_FILE, 'r') as f:
            data = json.load(f)

        # Parse structure: daily_data -> date -> cmg_online -> node -> cmg_usd
        records = []

        # Get the node we're interested in (PID PID or first available)
        target_node = "PIDPID________110"  # Default to PID PID

        daily_data = data.get('daily_data', {})

        for date_str, date_data in daily_data.items():
            hours = date_data.get('hours', [])
            cmg_online = date_data.get('cmg_online', {})

            # Try to get target node, or first available node
            if target_node in cmg_online:
                node_data = cmg_online[target_node]
            else:
                # Use first available node
                node_data = list(cmg_online.values())[0] if cmg_online else {}

            cmg_values = node_data.get('cmg_usd', [])

            # Create hourly records
            for hour, cmg_value in zip(hours, cmg_values):
                if cmg_value is not None:  # Skip null values
                    datetime_str = f"{date_str} {hour:02d}:00:00"
                    records.append({
                        'fecha_hora': datetime_str,
                        'CMG [$/MWh]': float(cmg_value)
                    })

        if not records:
            raise ValueError("No CMG data found in JSON file")

        df = pd.DataFrame(records)
        df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
        df = df.sort_values('fecha_hora').set_index('fecha_hora')

        # Get last 168 hours (needed for features)
        df = df.tail(168)

        print(f"  ✓ Loaded {len(df)} hours of CMG data")
        print(f"  Latest: {df.index[-1]}")
        print(f"  Value: ${df['CMG [$/MWh]'].iloc[-1]:.2f}")

        return df

    except FileNotFoundError:
        print(f"  ⚠️  CMG Online data not found at {CMG_ONLINE_FILE}")
        print("  Using fallback: loading from CSV if available")

        # Fallback: try loading from CSV
        csv_file = Path(__file__).parent.parent.parent.parent / "CMG_Real_ML_2023_2025.csv"
        if csv_file.exists():
            df = pd.read_csv(csv_file)
            df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
            df = df.rename(columns={'CMG_real': 'CMG [$/MWh]'})
            df = df.set_index('fecha_hora').sort_index()
            df = df.tail(168)
            print(f"  ✓ Loaded {len(df)} hours from CSV")
            return df
        else:
            raise FileNotFoundError("No CMG data available")


def generate_stage1_meta_features(X_base):
    """Generate Stage 1 meta-features (zero-risk predictions)"""
    print("  Generating Stage 1 meta-features...")

    # Load Stage 1 feature names to ensure correct order
    import pickle
    stage1_feature_names_file = MODELS_DIR / "zero_detection" / "feature_names.pkl"
    with open(stage1_feature_names_file, 'rb') as f:
        stage1_feature_names = pickle.load(f)

    # Reorder X_base to match Stage 1 training
    X_base_ordered = X_base[stage1_feature_names]

    meta_features = pd.DataFrame(index=X_base.index)

    for h in range(1, 25):
        lgb_path = MODELS_DIR / "zero_detection" / f"lgb_t+{h}.txt"
        xgb_path = MODELS_DIR / "zero_detection" / f"xgb_t+{h}.json"

        if not lgb_path.exists() or not xgb_path.exists():
            print(f"    ⚠️  Missing Stage 1 models for t+{h}")
            continue

        # Load models
        lgb_model = lgb.Booster(model_file=str(lgb_path))
        xgb_model = xgb.Booster(model_file=str(xgb_path))

        # Generate predictions with correctly ordered features
        lgb_pred = lgb_model.predict(X_base_ordered)[0]
        xgb_pred = xgb_model.predict(xgb.DMatrix(X_base_ordered))[0]
        avg_pred = (lgb_pred + xgb_pred) / 2

        # Add to meta features
        meta_features[f'zero_risk_lgb_t+{h}'] = lgb_pred
        meta_features[f'zero_risk_xgb_t+{h}'] = xgb_pred
        meta_features[f'zero_risk_avg_t+{h}'] = avg_pred

    print(f"  ✓ Generated {len(meta_features.columns)} meta-features")

    return meta_features


def create_features(cmg_df):
    """Create features for prediction"""
    print("\n[2/5] Creating features...")

    # Step 1: Create base features (78 features)
    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168]
    )

    df_with_features = feature_engineer.create_features(cmg_df)

    # Get base feature columns (exclude targets and raw CMG column)
    base_feature_cols = [col for col in df_with_features.columns
                        if not col.startswith(('is_zero_t+', 'cmg_value_t+'))
                        and col != 'CMG [$/MWh]']

    # Get latest available hour (handle missing data)
    latest_hour = df_with_features.index[-1]
    X_base = df_with_features.loc[[latest_hour], base_feature_cols]

    print(f"  ✓ Created {len(base_feature_cols)} base features")
    print(f"  📅 Using base time: {latest_hour} (last available data point)")

    # Step 2: Generate Stage 1 meta-features (72 features)
    meta_features = generate_stage1_meta_features(X_base)

    # Step 3: Combine base + meta features
    X_full = pd.concat([X_base, meta_features], axis=1)

    # Clean features
    X_full = X_full.replace([np.inf, -np.inf], np.nan).fillna(0).clip(-1e6, 1e6)

    # Load saved feature names to ensure correct order
    import pickle
    feature_names_file = MODELS_DIR / "value_prediction" / "feature_names.pkl"
    with open(feature_names_file, 'rb') as f:
        training_feature_names = pickle.load(f)

    # Reorder to match training
    X_final = X_full[training_feature_names]

    print(f"  ✓ Total features: {len(training_feature_names)} (78 base + 72 meta)")
    print(f"  Base time: {latest_hour}")

    # Also return base features for Stage 1 predictions
    # Load Stage 1 feature names
    stage1_feature_names_file = MODELS_DIR / "zero_detection" / "feature_names.pkl"
    with open(stage1_feature_names_file, 'rb') as f:
        stage1_feature_names = pickle.load(f)

    X_base_for_stage1 = X_full[stage1_feature_names]

    return X_final, X_base_for_stage1, latest_hour, training_feature_names


def load_optimal_thresholds():
    """Load optimal decision thresholds for each horizon"""
    thresholds_file = MODELS_DIR / "zero_detection" / "optimal_thresholds.csv"

    if not thresholds_file.exists():
        print("  ⚠️  Optimal thresholds not found, using fixed 0.5")
        return {h: 0.5 for h in range(1, 25)}

    thresholds_df = pd.read_csv(thresholds_file)

    # Parse horizon from 't+X' format
    thresholds_dict = {}
    for _, row in thresholds_df.iterrows():
        horizon_str = row['horizon']
        if isinstance(horizon_str, str) and horizon_str.startswith('t+'):
            horizon = int(horizon_str.replace('t+', ''))
            thresholds_dict[horizon] = row['threshold']

    print(f"  ✓ Loaded {len(thresholds_dict)} optimal thresholds (range: {min(thresholds_dict.values()):.3f}-{max(thresholds_dict.values()):.3f})")

    return thresholds_dict


def load_models():
    """Load trained models"""
    print("\n[3/5] Loading trained models...")

    models = {
        'zero_detection': {},
        'value_prediction': {},
        'optimal_thresholds': load_optimal_thresholds()
    }

    horizons = list(range(1, 25))

    # Load zero detection models
    for h in horizons:
        lgb_path = MODELS_DIR / "zero_detection" / f"lgb_t+{h}.txt"
        xgb_path = MODELS_DIR / "zero_detection" / f"xgb_t+{h}.json"

        if lgb_path.exists() and xgb_path.exists():
            models['zero_detection'][h] = {
                'lgb': lgb.Booster(model_file=str(lgb_path)),
                'xgb': xgb.Booster(model_file=str(xgb_path))
            }

    # Load value prediction models
    for h in horizons:
        lgb_med_path = MODELS_DIR / "value_prediction" / f"lgb_median_t+{h}.txt"
        lgb_q10_path = MODELS_DIR / "value_prediction" / f"lgb_q10_t+{h}.txt"
        lgb_q90_path = MODELS_DIR / "value_prediction" / f"lgb_q90_t+{h}.txt"
        xgb_path = MODELS_DIR / "value_prediction" / f"xgb_t+{h}.json"

        if all(p.exists() for p in [lgb_med_path, lgb_q10_path, lgb_q90_path, xgb_path]):
            xgb_model = xgb.Booster()
            xgb_model.load_model(str(xgb_path))

            models['value_prediction'][h] = {
                'lgb_median': lgb.Booster(model_file=str(lgb_med_path)),
                'lgb_q10': lgb.Booster(model_file=str(lgb_q10_path)),
                'lgb_q90': lgb.Booster(model_file=str(lgb_q90_path)),
                'xgb': xgb_model
            }

    zero_count = len(models['zero_detection'])
    value_count = len(models['value_prediction'])

    print(f"  ✓ Loaded {zero_count} zero detection model pairs")
    print(f"  ✓ Loaded {value_count} value prediction model sets")

    if zero_count < 24 or value_count < 24:
        print(f"  ⚠️  Warning: Expected 24 horizons, got {min(zero_count, value_count)}")

    return models


def generate_forecast(models, X_stage2, X_stage1, base_datetime):
    """Generate 24-hour forecast

    Args:
        models: Dict with 'zero_detection' and 'value_prediction' models
        X_stage2: Features for Stage 2 (value prediction) - 150 features
        X_stage1: Features for Stage 1 (zero detection) - 78 features
        base_datetime: Base datetime for forecast
    """
    print("\n[4/5] Generating 24-hour forecast...")

    forecasts = []

    for h in range(1, 25):
        if h not in models['zero_detection'] or h not in models['value_prediction']:
            print(f"  ⚠️  Skipping t+{h} (models not found)")
            continue

        # Stage 1: Zero detection (uses 78 base features)
        lgb_zero = models['zero_detection'][h]['lgb'].predict(X_stage1)[0]
        xgb_zero = models['zero_detection'][h]['xgb'].predict(xgb.DMatrix(X_stage1))[0]
        zero_prob = (lgb_zero + xgb_zero) / 2

        # Stage 2: Value prediction (uses 150 features including meta-features)
        lgb_value = models['value_prediction'][h]['lgb_median'].predict(X_stage2)[0]
        xgb_dmatrix = xgb.DMatrix(X_stage2)
        xgb_value = models['value_prediction'][h]['xgb'].predict(xgb_dmatrix)[0]
        value_median = (lgb_value + xgb_value) / 2

        # Quantiles for uncertainty
        value_q10 = models['value_prediction'][h]['lgb_q10'].predict(X_stage2)[0]
        value_q90 = models['value_prediction'][h]['lgb_q90'].predict(X_stage2)[0]

        # Final prediction: use optimal threshold for this horizon
        optimal_threshold = models['optimal_thresholds'].get(h, 0.5)
        final_prediction = 0 if zero_prob > optimal_threshold else max(0, value_median)

        # Target datetime
        target_time = base_datetime + timedelta(hours=h)

        forecasts.append({
            'horizon': h,
            'target_datetime': target_time.strftime('%Y-%m-%d %H:00:00'),
            'predicted_cmg': round(final_prediction, 2),
            'zero_probability': round(zero_prob, 4),
            'decision_threshold': round(optimal_threshold, 4),
            'value_prediction': round(value_median, 2),
            'confidence_interval': {
                'lower_10th': round(value_q10, 2),
                'median': round(value_median, 2),
                'upper_90th': round(value_q90, 2)
            }
        })

    print(f"  ✓ Generated {len(forecasts)} predictions")
    print(f"  t+1:  ${forecasts[0]['predicted_cmg']:.2f} (zero_prob: {forecasts[0]['zero_probability']:.2%})")
    print(f"  t+6:  ${forecasts[5]['predicted_cmg']:.2f} (zero_prob: {forecasts[5]['zero_probability']:.2%})")
    print(f"  t+12: ${forecasts[11]['predicted_cmg']:.2f} (zero_prob: {forecasts[11]['zero_probability']:.2%})")
    print(f"  t+24: ${forecasts[23]['predicted_cmg']:.2f} (zero_prob: {forecasts[23]['zero_probability']:.2%})")

    return {
        'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'base_datetime': base_datetime.strftime('%Y-%m-%d %H:00:00'),
        'model_version': 'gpu_enhanced_v1',
        'model_performance': {
            'test_mae': 32.43,
            'baseline_mae': 32.20
        },
        'forecasts': forecasts
    }


def save_predictions(forecast):
    """Save predictions to JSON"""
    print("\n[5/5] Saving predictions...")

    # Create directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Save latest
    latest_file = OUTPUT_DIR / "latest.json"
    with open(latest_file, 'w') as f:
        json.dump(forecast, f, indent=2)

    print(f"  ✓ Saved to {latest_file}")

    # Save archive
    timestamp = datetime.utcnow().strftime('%Y-%m-%d-%H')
    archive_file = ARCHIVE_DIR / f"{timestamp}.json"
    with open(archive_file, 'w') as f:
        json.dump(forecast, f, indent=2)

    print(f"  ✓ Archived to {archive_file}")


def main():
    """Main forecast generation pipeline"""
    print("="*80)
    print("ML HOURLY FORECAST GENERATOR")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        # 1. Load data
        cmg_df = load_cmg_online_data()

        # 2. Create features
        X_stage2, X_stage1, base_datetime, feature_cols = create_features(cmg_df)

        # 3. Load models
        models = load_models()

        # 4. Generate forecast
        forecast = generate_forecast(models, X_stage2, X_stage1, base_datetime)

        # 5. Save predictions
        save_predictions(forecast)

        print("\n" + "="*80)
        print("✅ FORECAST GENERATION COMPLETE!")
        print("="*80)
        print(f"Base time: {forecast['base_datetime']}")
        print(f"Generated: {forecast['generated_at']}")
        print(f"Horizons: {len(forecast['forecasts'])}")
        print()

        return 0

    except Exception as e:
        print("\n" + "="*80)
        print(f"❌ ERROR: {str(e)}")
        print("="*80)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
