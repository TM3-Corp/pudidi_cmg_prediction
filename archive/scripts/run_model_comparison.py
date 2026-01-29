#!/usr/bin/env python3
"""
Fair Model Comparison Script: NeuralProphet vs Production ML
=============================================================

This script runs a rigorous, fair comparison between NeuralProphet
and the production ML models (LightGBM + XGBoost).

Key features:
1. NO DATA LEAKAGE: True out-of-sample evaluation
2. ADEQUATE TEST SIZE: 60+ days of test data
3. CROSS-VALIDATION: TimeSeriesSplit with k folds
4. PER-HORIZON METRICS: Separate MAE for t+1, t+6, t+12, t+24

Usage:
    python scripts/run_model_comparison.py
    python scripts/run_model_comparison.py --test-days 60 --cv-folds 5
    python scripts/run_model_comparison.py --skip-neuralprophet  # ML models only

Author: CMG Prediction System
Date: 2026-01-28
"""

import os
import sys
import json
import argparse
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_path}")
except ImportError:
    # Try manual loading if python-dotenv not available
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
        print(f"Loaded environment from {env_path}")

# Suppress warnings
warnings.filterwarnings('ignore')

# ML imports
import lightgbm as lgb
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

# Local imports
from ml_feature_engineering import CleanCMGFeatureEngineering

# Configuration
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def get_supabase_client():
    """Initialize Supabase client"""
    try:
        from lib.utils.supabase_client import SupabaseClient
        return SupabaseClient()
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        return None


def fetch_cmg_data(days: int = 730) -> pd.DataFrame:
    """
    Fetch CMG Online data from Supabase with proper pagination.

    Note: Supabase/PostgREST has a 1000 row limit per query.
    We fetch in smaller batches (10 days) to ensure we get all data.

    Returns DataFrame with datetime index and CMG column.
    """
    supabase = get_supabase_client()
    if supabase is None:
        raise ValueError("Could not initialize Supabase client")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    print(f"Fetching CMG data from {start_date.date()} to {end_date.date()}...")
    print(f"  (Using 10-day batches to handle API 1000-row limit)")

    # Fetch data in 10-day batches (10 days * 24 hours * 3 nodes = 720 records < 1000 limit)
    all_records = []
    current_start = start_date
    batch_days = 10  # 10 days at a time to stay under 1000 limit

    while current_start < end_date:
        current_end = min(current_start + timedelta(days=batch_days), end_date)

        records = supabase.get_cmg_online(
            start_date=current_start.strftime('%Y-%m-%d'),
            end_date=current_end.strftime('%Y-%m-%d'),
            limit=1000  # Max allowed by API
        )

        if records:
            all_records.extend(records)
            if len(all_records) % 3000 == 0 or current_end >= end_date:
                print(f"  Fetched up to {current_end.strftime('%Y-%m-%d')}: {len(all_records)} total records")

        current_start = current_end + timedelta(days=1)

    if not all_records:
        raise ValueError("No CMG data found in Supabase")

    print(f"  Total fetched: {len(all_records)} records")

    df = pd.DataFrame(all_records)
    df['datetime'] = pd.to_datetime(df['datetime'])

    # Average across nodes for each hour
    df_hourly = df.groupby('datetime')['cmg_usd'].mean().reset_index()
    df_hourly.columns = ['datetime', 'CMG [$/MWh]']
    df_hourly = df_hourly.set_index('datetime').sort_index()
    df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

    # Fill any missing hours with forward fill
    full_range = pd.date_range(start=df_hourly.index.min(), end=df_hourly.index.max(), freq='H')
    df_hourly = df_hourly.reindex(full_range)
    missing_count = df_hourly['CMG [$/MWh]'].isna().sum()
    if missing_count > 0:
        print(f"  Filling {missing_count} missing hours with forward fill")
        df_hourly['CMG [$/MWh]'] = df_hourly['CMG [$/MWh]'].ffill().bfill()

    print(f"  Processed {len(df_hourly)} unique hours")
    print(f"  Date range: {df_hourly.index.min()} to {df_hourly.index.max()}")

    return df_hourly


def create_production_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Create features using production pipeline"""
    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168]
    )

    df_feat = feature_engineer.create_features(df)
    feature_names = feature_engineer.get_feature_names()

    return df_feat, feature_names


def train_lgb_model(X_train, y_train, X_val, y_val):
    """Train LightGBM model"""
    mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
    mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))

    X_train_clean = X_train[mask_train]
    y_train_clean = y_train[mask_train]
    X_val_clean = X_val[mask_val]
    y_val_clean = y_val[mask_val]

    if len(X_train_clean) < 100:
        return None

    params = {
        'objective': 'regression',
        'metric': 'mae',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'feature_fraction': 0.8,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'verbose': -1,
        'n_jobs': -1
    }

    train_data = lgb.Dataset(X_train_clean, label=y_train_clean)
    val_data = lgb.Dataset(X_val_clean, label=y_val_clean, reference=train_data)

    model = lgb.train(
        params,
        train_data,
        num_boost_round=500,
        valid_sets=[val_data],
        callbacks=[lgb.early_stopping(50, verbose=False)]
    )

    return model


def train_xgb_model(X_train, y_train, X_val, y_val):
    """Train XGBoost model"""
    mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
    mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))

    X_train_clean = X_train[mask_train]
    y_train_clean = y_train[mask_train]
    X_val_clean = X_val[mask_val]
    y_val_clean = y_val[mask_val]

    if len(X_train_clean) < 100:
        return None

    params = {
        'objective': 'reg:squarederror',
        'eval_metric': 'mae',
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'n_jobs': -1
    }

    train_data = xgb.DMatrix(X_train_clean, label=y_train_clean)
    val_data = xgb.DMatrix(X_val_clean, label=y_val_clean)

    model = xgb.train(
        params,
        train_data,
        num_boost_round=500,
        evals=[(val_data, 'val')],
        early_stopping_rounds=50,
        verbose_eval=False
    )

    return model


def evaluate_production_ml(
    df_feat: pd.DataFrame,
    feature_names: List[str],
    train_end_idx: int,
    horizons: List[int]
) -> Dict:
    """Evaluate production ML models"""
    results = {'lgb': {}, 'xgb': {}, 'ensemble': {}}
    predictions = {'lgb': {}, 'xgb': {}, 'ensemble': {}}
    actuals_dict = {}

    train_df = df_feat.iloc[:train_end_idx]
    test_df = df_feat.iloc[train_end_idx:]

    val_split = int(len(train_df) * 0.8)
    train_split = train_df.iloc[:val_split]
    val_split_df = train_df.iloc[val_split:]

    for h in horizons:
        print(f"    Evaluating horizon t+{h}...")
        target_col = f'cmg_value_t+{h}'

        if target_col not in df_feat.columns:
            continue

        X_train = train_split[feature_names]
        y_train = train_split[target_col]
        X_val = val_split_df[feature_names]
        y_val = val_split_df[target_col]
        X_test = test_df[feature_names]
        y_test = test_df[target_col]

        lgb_model = train_lgb_model(X_train, y_train, X_val, y_val)
        xgb_model = train_xgb_model(X_train, y_train, X_val, y_val)

        if lgb_model is None or xgb_model is None:
            continue

        mask_test = ~(y_test.isna() | X_test.isna().any(axis=1))
        X_test_clean = X_test[mask_test]
        y_test_clean = y_test[mask_test]

        lgb_pred = lgb_model.predict(X_test_clean)
        xgb_pred = xgb_model.predict(xgb.DMatrix(X_test_clean))
        ensemble_pred = (lgb_pred + xgb_pred) / 2

        results['lgb'][f't+{h}'] = float(mean_absolute_error(y_test_clean, lgb_pred))
        results['xgb'][f't+{h}'] = float(mean_absolute_error(y_test_clean, xgb_pred))
        results['ensemble'][f't+{h}'] = float(mean_absolute_error(y_test_clean, ensemble_pred))

        predictions['lgb'][f't+{h}'] = lgb_pred.tolist()
        predictions['xgb'][f't+{h}'] = xgb_pred.tolist()
        predictions['ensemble'][f't+{h}'] = ensemble_pred.tolist()
        actuals_dict[f't+{h}'] = y_test_clean.values.tolist()

    return results, predictions, actuals_dict


def evaluate_persistence(
    df: pd.DataFrame,
    train_end_idx: int,
    horizons: List[int]
) -> Dict:
    """Evaluate persistence baseline"""
    results = {}
    test_df = df.iloc[train_end_idx:]

    for h in horizons:
        pred = test_df['CMG [$/MWh]'].shift(24)
        actual = test_df['CMG [$/MWh]'].shift(-h)

        mask = ~(pred.isna() | actual.isna())
        if mask.sum() > 0:
            mae = mean_absolute_error(actual[mask], pred[mask])
            results[f't+{h}'] = float(mae)

    return results


def evaluate_neuralprophet(
    df: pd.DataFrame,
    train_end_idx: int,
    horizons: List[int],
    sample_every: int = 12
) -> Dict:
    """Evaluate NeuralProphet with TRUE out-of-sample (no leakage)"""
    try:
        from neuralprophet import NeuralProphet, set_log_level
        set_log_level('ERROR')
    except ImportError:
        print("  Warning: NeuralProphet not installed. Skipping.")
        return {}

    # Prepare data - ensure no missing values
    df_np = df.reset_index()
    df_np.columns = ['ds', 'y']

    # Fill any remaining NaN values
    if df_np['y'].isna().any():
        print(f"    Filling {df_np['y'].isna().sum()} NaN values...")
        df_np['y'] = df_np['y'].ffill().bfill()

    df_train = df_np.iloc[:train_end_idx].copy()
    df_test = df_np.iloc[train_end_idx:].copy()

    # Create model - use n_forecasts=24 to get all horizons at once
    max_h = max(horizons)
    print(f"    Creating NeuralProphet model (n_forecasts={max_h})...")
    model = NeuralProphet(
        n_lags=168,
        n_forecasts=max_h,  # Predict all horizons at once
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=True,
        seasonality_mode='multiplicative',
        growth='discontinuous',
        n_changepoints=20,
        changepoints_range=0.9,
        trend_reg=0.05,
        learning_rate=0.01,
        epochs=50,
        batch_size=64,
        ar_reg=0.1,
        ar_layers=[32, 16],
        lagged_reg_layers=[16],
        drop_missing=True,  # Handle any remaining missing values
    )

    # Train
    print("    Training NeuralProphet...")
    model.fit(df_train, freq='H')

    # Evaluate
    print("    Evaluating (true out-of-sample)...")
    results = {}
    max_h = max(horizons)

    predictions_dict = {h: [] for h in horizons}
    actuals_dict = {h: [] for h in horizons}

    n_origins = (len(df_test) - max_h) // sample_every
    print(f"    Evaluating {n_origins} forecast origins...")

    for i, origin_idx in enumerate(range(0, len(df_test) - max_h, sample_every)):
        # Build history up to this point
        if origin_idx > 0:
            df_history = pd.concat([
                df_train[['ds', 'y']],
                df_test[['ds', 'y']].iloc[:origin_idx]
            ], ignore_index=True)
        else:
            df_history = df_train[['ds', 'y']].copy()

        # Make multi-step forecast
        future = model.make_future_dataframe(df_history, periods=max_h)
        forecast = model.predict(future)

        # Debug: print info on first iteration
        if i == 0:
            print(f"      Forecast shape: {forecast.shape}")
            print(f"      Forecast columns: {list(forecast.columns)[:10]}...")
            # With n_forecasts=24, columns are yhat1, yhat2, ..., yhat24
            yhat_cols = [c for c in forecast.columns if c.startswith('yhat')]
            print(f"      yhat columns: {len(yhat_cols)} (yhat1 to yhat{max_h})")

        # With n_forecasts=24, NeuralProphet outputs yhat1, yhat2, ..., yhat24
        # Each column represents the h-step ahead prediction
        # The prediction is in the LAST row of the forecast (the most recent observation)
        for h in horizons:
            target_idx = origin_idx + h
            if target_idx < len(df_test):
                # The column name is yhat{h}
                col_name = f'yhat{h}'
                if col_name in forecast.columns:
                    # Get the last non-NaN value for this horizon
                    pred_series = forecast[col_name].dropna()
                    if len(pred_series) > 0:
                        pred_val = pred_series.iloc[-1]
                        predictions_dict[h].append(float(pred_val))
                        actuals_dict[h].append(float(df_test['y'].iloc[target_idx]))
                    elif i == 0:
                        print(f"      h={h}: No valid predictions in {col_name}")
                elif i == 0:
                    print(f"      h={h}: Column {col_name} not found")

        if (i + 1) % 20 == 0:
            print(f"      {i + 1}/{n_origins} origins completed")

    # Calculate MAE per horizon
    for h in horizons:
        if predictions_dict[h]:
            mae = mean_absolute_error(actuals_dict[h], predictions_dict[h])
            results[f't+{h}'] = float(mae)
            print(f"      t+{h}: ${mae:.2f}")

    return results


def cross_validate_models(
    df_raw: pd.DataFrame,
    df_feat: pd.DataFrame,
    feature_names: List[str],
    horizons: List[int],
    n_splits: int = 5,
    test_size: int = 720,
    include_neuralprophet: bool = True
) -> Dict:
    """Run TimeSeriesSplit cross-validation"""
    tscv = TimeSeriesSplit(n_splits=n_splits, test_size=test_size)

    cv_results = {
        'ml_ensemble': {h: [] for h in horizons},
        'neuralprophet': {h: [] for h in horizons}
    }

    for fold, (train_idx, test_idx) in enumerate(tscv.split(df_feat)):
        print(f"\n  Fold {fold + 1}/{n_splits}")
        print(f"    Train: {len(train_idx)} samples")
        print(f"    Test: {len(test_idx)} samples")

        # ML Ensemble
        print("    Training ML models...")
        train_df = df_feat.iloc[train_idx]
        test_df = df_feat.iloc[test_idx]

        val_split = int(len(train_df) * 0.8)
        train_split = train_df.iloc[:val_split]
        val_split_df = train_df.iloc[val_split:]

        for h in horizons:
            target_col = f'cmg_value_t+{h}'
            if target_col not in df_feat.columns:
                continue

            X_train = train_split[feature_names]
            y_train = train_split[target_col]
            X_val = val_split_df[feature_names]
            y_val = val_split_df[target_col]
            X_test = test_df[feature_names]
            y_test = test_df[target_col]

            lgb_model = train_lgb_model(X_train, y_train, X_val, y_val)
            xgb_model = train_xgb_model(X_train, y_train, X_val, y_val)

            if lgb_model is None or xgb_model is None:
                continue

            mask_test = ~(y_test.isna() | X_test.isna().any(axis=1))
            X_test_clean = X_test[mask_test]
            y_test_clean = y_test[mask_test]

            lgb_pred = lgb_model.predict(X_test_clean)
            xgb_pred = xgb_model.predict(xgb.DMatrix(X_test_clean))
            ensemble_pred = (lgb_pred + xgb_pred) / 2

            mae = mean_absolute_error(y_test_clean, ensemble_pred)
            cv_results['ml_ensemble'][h].append(mae)
            print(f"      ML t+{h}: ${mae:.2f}")

        # NeuralProphet (if requested)
        if include_neuralprophet:
            print("    Training NeuralProphet...")
            try:
                np_results = evaluate_neuralprophet(
                    df=df_raw,
                    train_end_idx=train_idx[-1] + 1,
                    horizons=horizons,
                    sample_every=24  # Sample every 24h for CV speed
                )
                for h in horizons:
                    if f't+{h}' in np_results:
                        cv_results['neuralprophet'][h].append(np_results[f't+{h}'])
            except Exception as e:
                print(f"      NeuralProphet error: {e}")

    # Calculate summary statistics
    summary = {}
    for model_name, model_results in cv_results.items():
        summary[model_name] = {}
        for h, maes in model_results.items():
            if maes:
                summary[model_name][f't+{h}'] = {
                    'mae_mean': float(np.mean(maes)),
                    'mae_std': float(np.std(maes)),
                    'mae_folds': [float(m) for m in maes]
                }

    return summary


def main():
    parser = argparse.ArgumentParser(description='Run fair model comparison')
    parser.add_argument('--test-days', type=int, default=60,
                        help='Number of days for test set (default: 60)')
    parser.add_argument('--cv-folds', type=int, default=3,
                        help='Number of cross-validation folds (default: 3)')
    parser.add_argument('--horizons', type=str, default='1,6,12,24',
                        help='Horizons to evaluate (default: 1,6,12,24)')
    parser.add_argument('--skip-neuralprophet', action='store_true',
                        help='Skip NeuralProphet evaluation')
    parser.add_argument('--skip-cv', action='store_true',
                        help='Skip cross-validation')
    parser.add_argument('--data-days', type=int, default=730,
                        help='Days of historical data to fetch (default: 730)')
    args = parser.parse_args()

    # Parse horizons
    horizons = [int(h) for h in args.horizons.split(',')]

    print("=" * 70)
    print("FAIR MODEL COMPARISON: NeuralProphet vs Production ML")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Test period: {args.test_days} days")
    print(f"  CV folds: {args.cv_folds}")
    print(f"  Horizons: {horizons}")
    print(f"  Include NeuralProphet: {not args.skip_neuralprophet}")
    print()

    # Fetch data
    print("=" * 70)
    print("STEP 1: Fetching Data")
    print("=" * 70)
    df_raw = fetch_cmg_data(days=args.data_days)

    # Create features
    print("\n" + "=" * 70)
    print("STEP 2: Creating Production ML Features")
    print("=" * 70)
    df_feat, feature_names = create_production_features(df_raw)
    print(f"Created {len(feature_names)} features")

    # Define train/test split
    test_size = args.test_days * 24
    train_end_idx = len(df_raw) - test_size

    # Check if we have enough data
    min_train_size = 500  # At least 500 hours for training
    if train_end_idx < min_train_size:
        print(f"\nWarning: Not enough data for requested test period.")
        print(f"  Available: {len(df_raw)} hours")
        print(f"  Requested test: {test_size} hours")
        print(f"  Would leave only {train_end_idx} hours for training (min: {min_train_size})")
        # Adjust test size
        test_size = max(24, len(df_raw) - min_train_size)
        train_end_idx = len(df_raw) - test_size
        print(f"  Adjusted test size: {test_size} hours ({test_size // 24} days)")

    if train_end_idx <= 0 or test_size <= 0:
        raise ValueError(f"Not enough data: {len(df_raw)} hours available, need at least {min_train_size + 24}")

    print(f"\nTrain/Test Split:")
    print(f"  Train: {train_end_idx} hours ({df_raw.index[0]} to {df_raw.index[train_end_idx-1]})")
    print(f"  Test: {test_size} hours ({df_raw.index[train_end_idx]} to {df_raw.index[-1]})")

    results = {
        'evaluation_date': datetime.now().isoformat(),
        'config': {
            'test_days': args.test_days,
            'cv_folds': args.cv_folds,
            'horizons': horizons,
            'data_days': args.data_days
        },
        'data_info': {
            'total_hours': len(df_raw),
            'train_hours': train_end_idx,
            'test_hours': test_size,
            'date_range': f"{df_raw.index.min()} to {df_raw.index.max()}"
        }
    }

    # Evaluate Persistence Baseline
    print("\n" + "=" * 70)
    print("STEP 3: Evaluating Persistence Baseline")
    print("=" * 70)
    baseline_results = evaluate_persistence(df_raw, train_end_idx, horizons)
    print("  Results:")
    for h, mae in baseline_results.items():
        print(f"    {h}: ${mae:.2f}")
    results['persistence_baseline'] = baseline_results

    # Evaluate Production ML
    print("\n" + "=" * 70)
    print("STEP 4: Evaluating Production ML (LightGBM + XGBoost)")
    print("=" * 70)
    ml_results, ml_predictions, ml_actuals = evaluate_production_ml(
        df_feat, feature_names, train_end_idx, horizons
    )
    print("\n  Results:")
    for model_name, metrics in ml_results.items():
        print(f"    {model_name.upper()}:")
        for h, mae in metrics.items():
            print(f"      {h}: ${mae:.2f}")
    results['production_ml'] = ml_results

    # Evaluate NeuralProphet
    if not args.skip_neuralprophet:
        print("\n" + "=" * 70)
        print("STEP 5: Evaluating NeuralProphet (Corrected - No Leakage)")
        print("=" * 70)
        np_results = evaluate_neuralprophet(
            df_raw, train_end_idx, horizons, sample_every=12
        )
        print("\n  Results:")
        for h, mae in np_results.items():
            print(f"    {h}: ${mae:.2f}")
        results['neuralprophet'] = np_results

    # Cross-validation
    if not args.skip_cv:
        print("\n" + "=" * 70)
        print("STEP 6: TimeSeriesSplit Cross-Validation")
        print("=" * 70)
        cv_results = cross_validate_models(
            df_raw, df_feat, feature_names, horizons,
            n_splits=args.cv_folds,
            test_size=720,  # 30 days per fold
            include_neuralprophet=not args.skip_neuralprophet
        )
        results['cross_validation'] = cv_results

    # Summary
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)

    print("\nMAE by Horizon (USD/MWh):")
    print("-" * 70)
    print(f"{'Horizon':<10} {'Persistence':<15} {'ML Ensemble':<15} {'NeuralProphet':<15}")
    print("-" * 70)

    for h in horizons:
        key = f't+{h}'
        baseline = baseline_results.get(key, float('nan'))
        ml_ens = ml_results['ensemble'].get(key, float('nan'))
        np_mae = results.get('neuralprophet', {}).get(key, float('nan'))
        print(f"{key:<10} ${baseline:<14.2f} ${ml_ens:<14.2f} ${np_mae:<14.2f}")

    # Calculate averages
    avg_baseline = np.mean([v for v in baseline_results.values()])
    avg_ml = np.mean([v for v in ml_results['ensemble'].values()])
    avg_np = np.mean([v for v in results.get('neuralprophet', {}).values()]) if 'neuralprophet' in results else float('nan')

    print("-" * 70)
    print(f"{'AVERAGE':<10} ${avg_baseline:<14.2f} ${avg_ml:<14.2f} ${avg_np:<14.2f}")

    results['summary'] = {
        'avg_persistence': float(avg_baseline),
        'avg_ml_ensemble': float(avg_ml),
        'avg_neuralprophet': float(avg_np) if not np.isnan(avg_np) else None
    }

    # Save results
    output_path = LOGS_DIR / f"model_comparison_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n\nResults saved to: {output_path}")

    # Also save latest results
    latest_path = LOGS_DIR / "model_comparison_results_latest.json"
    with open(latest_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Latest results: {latest_path}")

    # Conclusions
    print("\n" + "=" * 70)
    print("CONCLUSIONS")
    print("=" * 70)

    if 'neuralprophet' in results and results['neuralprophet']:
        if avg_np < avg_ml * 0.95:
            print("\n  RECOMMENDATION: INTEGRATE NeuralProphet")
            print(f"  NeuralProphet outperforms ML Ensemble by {(avg_ml - avg_np) / avg_ml * 100:.1f}%")
        elif avg_np < avg_ml * 1.05:
            print("\n  RECOMMENDATION: CONSIDER NeuralProphet")
            print("  Performance is comparable - could use for ensemble diversity")
        else:
            print("\n  RECOMMENDATION: RETAIN Production ML")
            print(f"  ML Ensemble outperforms NeuralProphet by {(avg_np - avg_ml) / avg_ml * 100:.1f}%")

    print("\n  Note: The original NeuralProphet MAE of ~$10.88 was invalid due to data leakage.")
    print("  This evaluation uses correct methodology with no data leakage.")

    print("\n\nDone!")
    return results


if __name__ == "__main__":
    main()
