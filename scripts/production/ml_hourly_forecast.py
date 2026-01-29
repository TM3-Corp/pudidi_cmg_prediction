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

# Constants - paths relative to project root (scripts/production/ -> project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models_24h"
DATA_DIR = PROJECT_ROOT / "data"
CMG_ONLINE_FILE = DATA_DIR / "cache" / "cmg_historical_latest.json"  # Use latest cache
OUTPUT_DIR = DATA_DIR / "ml_predictions"
ARCHIVE_DIR = OUTPUT_DIR / "archive"


def load_cmg_online_data():
    """
    Load latest CMG Online data from cache.

    Returns last 168 hours (1 week) needed for feature engineering.
    Automatically finds the LATEST timestamp to use as base for predictions.

    Tries multiple cache files in order of preference.
    """
    print(f"[1/5] Loading CMG Online data...")

    # Try multiple cache files
    cache_files = [
        DATA_DIR / "cache" / "cmg_historical_latest.json",  # Preferred
        DATA_DIR / "cache" / "cmg_online_historical.json",  # Fallback
    ]

    for cache_file in cache_files:
        if not cache_file.exists():
            continue

        print(f"  Trying: {cache_file.name}")

        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)

            # Try different data structures
            records = []

            # Structure 1: data key contains list of records
            if 'data' in data and data['data']:
                print(f"    Format: data key with list")
                records = data['data']
                df = pd.DataFrame(records)
                df['fecha_hora'] = pd.to_datetime(df['datetime'], format='ISO8601')
                df['CMG [$/MWh]'] = df['cmg_usd']

            # Structure 2: daily_data key with nested structure
            elif 'daily_data' in data and data['daily_data']:
                print(f"    Format: daily_data key with nested structure")
                for date_str, day_data in data['daily_data'].items():
                    for node, node_data in day_data.get('cmg_online', {}).items():
                        for hour, cmg_usd in zip(day_data.get('hours', []), node_data.get('cmg_usd', [])):
                            if cmg_usd is not None:  # Skip only nulls, keep zeros
                                records.append({
                                    'fecha_hora': f"{date_str} {hour:02d}:00:00",
                                    'CMG [$/MWh]': float(cmg_usd)
                                })
                if len(records) == 0:
                    print(f"    ⚠️  No valid records found in daily_data")
                    continue
                df = pd.DataFrame(records)
                df['fecha_hora'] = pd.to_datetime(df['fecha_hora'], format='%Y-%m-%d %H:%M:%S')

            else:
                print(f"    ⚠️  Unknown format, skipping")
                continue

            if len(df) == 0:
                print(f"    ⚠️  No records found, skipping")
                continue

            # Process DataFrame
            df = df.set_index('fecha_hora').sort_index()

            # Take average across nodes if multiple nodes for same timestamp
            if df.index.duplicated().any():
                df = df.groupby('fecha_hora')['CMG [$/MWh]'].mean().to_frame()

            # Get last 168 hours (1 week) - needed for lag features
            df = df.tail(168)

            latest_time = df.index[-1]
            latest_value = df['CMG [$/MWh]'].iloc[-1]

            print(f"  ✅ Successfully loaded {len(df)} hours of CMG data")
            print(f"  📅 Latest timestamp: {latest_time}")
            print(f"  💵 Latest value: ${latest_value:.2f}/MWh")
            print(f"  🎯 Predictions will start from: {latest_time + timedelta(hours=1)}")

            return df

        except Exception as e:
            print(f"    ❌ Error: {e}")
            continue

    # If we get here, no cache file worked
    raise FileNotFoundError(
        f"Could not load CMG data from any cache file. "
        f"Tried: {[str(f.name) for f in cache_files]}"
    )


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
    """Load optimal decision thresholds - now hour-based instead of horizon-based"""
    # Try new hour-based calibrated thresholds first
    hour_thresholds_npy = MODELS_DIR / "zero_detection" / "optimal_thresholds_by_hour_calibrated.npy"
    hour_thresholds_csv = MODELS_DIR / "zero_detection" / "optimal_thresholds_by_hour_calibrated.csv"

    if hour_thresholds_npy.exists():
        thresholds_array = np.load(hour_thresholds_npy)
        thresholds_dict = {h: float(thresholds_array[h]) for h in range(24)}
        print(f"  ✓ Loaded hour-based calibrated thresholds (range: {min(thresholds_dict.values()):.3f}-{max(thresholds_dict.values()):.3f})")
        return thresholds_dict, 'hour-based'

    elif hour_thresholds_csv.exists():
        thresholds_df = pd.read_csv(hour_thresholds_csv)
        thresholds_dict = {int(row['target_hour']): row['threshold'] for _, row in thresholds_df.iterrows()}
        print(f"  ✓ Loaded hour-based thresholds (range: {min(thresholds_dict.values()):.3f}-{max(thresholds_dict.values()):.3f})")
        return thresholds_dict, 'hour-based'

    # Fallback to old horizon-based thresholds
    horizon_thresholds_file = MODELS_DIR / "zero_detection" / "optimal_thresholds.csv"
    if horizon_thresholds_file.exists():
        thresholds_df = pd.read_csv(horizon_thresholds_file)
        thresholds_dict = {}
        for _, row in thresholds_df.iterrows():
            horizon_str = row['horizon']
            if isinstance(horizon_str, str) and horizon_str.startswith('t+'):
                horizon = int(horizon_str.replace('t+', ''))
                thresholds_dict[horizon] = row['threshold']
        print(f"  ⚠️  Using old horizon-based thresholds (range: {min(thresholds_dict.values()):.3f}-{max(thresholds_dict.values()):.3f})")
        return thresholds_dict, 'horizon-based'

    # Last resort
    print("  ⚠️  No thresholds found, using fixed 0.5")
    return {h: 0.5 for h in range(24)}, 'fixed'


def load_models():
    """Load trained models"""
    print("\n[3/5] Loading trained models...")

    # Load thresholds
    thresholds, threshold_type = load_optimal_thresholds()

    # Load meta-calibrator if available
    meta_calibrator_path = MODELS_DIR / "zero_detection" / "meta_calibrator.pkl"
    meta_calibrator = None
    if meta_calibrator_path.exists():
        import joblib
        meta_calibrator = joblib.load(meta_calibrator_path)
        print(f"  ✓ Loaded meta-calibrator for probability calibration")

    models = {
        'zero_detection': {},
        'value_prediction': {},
        'optimal_thresholds': thresholds,
        'threshold_type': threshold_type,
        'meta_calibrator': meta_calibrator
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
        models: Dict with 'zero_detection', 'value_prediction', 'meta_calibrator', 'optimal_thresholds'
        X_stage2: Features for Stage 2 (value prediction) - 150 features
        X_stage1: Features for Stage 1 (zero detection) - 78 features
        base_datetime: Base datetime for forecast
    """
    print("\n[4/5] Generating 24-hour forecast...")

    # Calculate data staleness
    now = datetime.now()
    data_staleness_hours = (now - base_datetime).total_seconds() / 3600

    forecasts = []

    for h in range(1, 25):
        if h not in models['zero_detection'] or h not in models['value_prediction']:
            print(f"  ⚠️  Skipping t+{h} (models not found)")
            continue

        # Target datetime
        target_time = base_datetime + timedelta(hours=h)

        # Stage 1: Zero detection (uses 78 base features)
        lgb_zero = models['zero_detection'][h]['lgb'].predict(X_stage1)[0]
        xgb_zero = models['zero_detection'][h]['xgb'].predict(xgb.DMatrix(X_stage1))[0]
        zero_prob_raw = (lgb_zero + xgb_zero) / 2

        # Apply meta-calibrator if available
        if models['meta_calibrator'] is not None:
            from scipy.special import logit, expit

            # Prepare meta-features
            meta_features_dict = {
                'logit_p': logit(np.clip(zero_prob_raw, 1e-6, 1 - 1e-6)),
                'hour_sin': np.sin(2 * np.pi * target_time.hour / 24),
                'hour_cos': np.cos(2 * np.pi * target_time.hour / 24),
                'month_sin': np.sin(2 * np.pi * target_time.month / 12),
                'month_cos': np.cos(2 * np.pi * target_time.month / 12),
                'zeros_24h': X_stage1['zeros_count_24h'].values[0] if 'zeros_count_24h' in X_stage1.columns else 0,
                'zeros_168h': X_stage1['zeros_count_168h'].values[0] if 'zeros_count_168h' in X_stage1.columns else 0,
                'horizon': h
            }

            meta_features_df = pd.DataFrame([meta_features_dict])
            zero_prob = models['meta_calibrator'].predict_proba(meta_features_df)[:, 1][0]
        else:
            zero_prob = zero_prob_raw

        # Stage 2: Value prediction (uses 150 features including meta-features)
        lgb_value = models['value_prediction'][h]['lgb_median'].predict(X_stage2)[0]
        xgb_dmatrix = xgb.DMatrix(X_stage2)
        xgb_value = models['value_prediction'][h]['xgb'].predict(xgb_dmatrix)[0]
        value_median = (lgb_value + xgb_value) / 2

        # Quantiles for uncertainty
        value_q10 = models['value_prediction'][h]['lgb_q10'].predict(X_stage2)[0]
        value_q90 = models['value_prediction'][h]['lgb_q90'].predict(X_stage2)[0]

        # Final prediction: use hour-based threshold if available, else horizon-based
        if models['threshold_type'] == 'hour-based':
            optimal_threshold = models['optimal_thresholds'].get(target_time.hour, 0.5)
        else:
            optimal_threshold = models['optimal_thresholds'].get(h, 0.5)

        final_prediction = 0 if zero_prob > optimal_threshold else max(0, value_median)

        # Calculate real-time offset and validity
        real_time_offset = (target_time - now).total_seconds() / 3600
        is_valid_forecast = (target_time > now)

        forecasts.append({
            'horizon': h,
            'target_datetime': target_time.strftime('%Y-%m-%d %H:00:00'),
            'predicted_cmg': round(final_prediction, 2),
            'real_time_offset': round(real_time_offset, 1),
            'is_valid_forecast': is_valid_forecast,
            'zero_probability': round(zero_prob, 4),
            'zero_probability_raw': round(zero_prob_raw, 4) if models['meta_calibrator'] is not None else None,
            'decision_threshold': round(optimal_threshold, 4),
            'value_prediction': round(value_median, 2),
            'confidence_interval': {
                'lower_10th': round(value_q10, 2),
                'median': round(value_median, 2),
                'upper_90th': round(value_q90, 2)
            }
        })

    print(f"  ✓ Generated {len(forecasts)} predictions")

    # Count valid forecasts
    valid_count = sum(1 for f in forecasts if f['is_valid_forecast'])
    print(f"  ✓ Data staleness: {data_staleness_hours:.1f} hours")
    print(f"  ✓ Valid future forecasts: {valid_count}/{len(forecasts)}")

    print(f"  t+1:  ${forecasts[0]['predicted_cmg']:.2f} (zero_prob: {forecasts[0]['zero_probability']:.2%}) [offset: {forecasts[0]['real_time_offset']:.1f}h]")
    print(f"  t+6:  ${forecasts[5]['predicted_cmg']:.2f} (zero_prob: {forecasts[5]['zero_probability']:.2%}) [offset: {forecasts[5]['real_time_offset']:.1f}h]")
    print(f"  t+12: ${forecasts[11]['predicted_cmg']:.2f} (zero_prob: {forecasts[11]['zero_probability']:.2%}) [offset: {forecasts[11]['real_time_offset']:.1f}h]")
    print(f"  t+24: ${forecasts[23]['predicted_cmg']:.2f} (zero_prob: {forecasts[23]['zero_probability']:.2%}) [offset: {forecasts[23]['real_time_offset']:.1f}h]")

    return {
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'base_datetime': base_datetime.strftime('%Y-%m-%d %H:00:00'),
        'data_staleness_hours': round(data_staleness_hours, 1),
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
