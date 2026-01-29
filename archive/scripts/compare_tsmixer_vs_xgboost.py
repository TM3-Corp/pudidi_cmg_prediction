#!/usr/bin/env python3
"""
Fair Comparison: TSMixer vs XGBoost/LightGBM

This script performs a rigorous, fair comparison between:
1. TSMixer (NeuralForecast) - Deep learning model
2. LightGBM + XGBoost - Gradient boosting ensemble
3. Persistence Baseline - Same hour yesterday

Methodology:
- Same test period for all models
- Same data source
- No data leakage
- Multiple horizons evaluated (t+1, t+6, t+12, t+24)

Author: CMG Prediction System
Date: 2026-01-29
"""

import os
import sys
import warnings
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Suppress warnings
warnings.filterwarnings('ignore')
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'

import numpy as np
import pandas as pd
import torch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ML Libraries
import lightgbm as lgb
import xgboost as xgb

# NeuralForecast
from neuralforecast import NeuralForecast
from neuralforecast.models import TSMixer
from neuralforecast.losses.pytorch import MAE

# Metrics
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Production feature engineering
from ml_feature_engineering import CleanCMGFeatureEngineering

# Supabase client
from lib.utils.supabase_client import SupabaseClient

# Configuration
torch.set_float32_matmul_precision('high')
np.random.seed(42)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Test configuration
TEST_DAYS = 30  # 30 days for robust evaluation
HORIZONS = [1, 6, 12, 24]  # Key horizons to evaluate

# TSMixer configuration (optimized based on research)
# References:
# - Google Research paper: https://arxiv.org/abs/2303.06053
# - NeuralForecast docs: https://nixtlaverse.nixtla.io/neuralforecast/
# - Energy price forecasting studies recommend longer training sets
TSMIXER_CONFIG = {
    'input_size': 168,      # 1 week of history (matches original notebook)
    'horizon': 24,          # Predict 24 hours at once
    'n_block': 4,           # Number of mixing layers (default: 2, research suggests 4-8)
    'ff_dim': 64,           # Feature feed-forward dimension (default: 64)
    'dropout': 0.5,         # Dropout rate (default: 0.9, research suggests 0.5-0.7 for prices)
    'revin': True,          # Reversible Instance Norm (good for non-stationary prices)
    'max_steps': 2000,      # Training steps (research recommends 1000-2000)
    'learning_rate': 1e-4,  # Learning rate (lower for stability, research: 1e-4)
    'early_stop': 5,        # Early stopping patience
    'batch_size': 32,       # Batch size
    'val_size': 48,         # Validation size (2 days)
}

# Legacy config variables for backward compatibility
TSMIXER_INPUT_SIZE = TSMIXER_CONFIG['input_size']
TSMIXER_HORIZON = TSMIXER_CONFIG['horizon']
TSMIXER_MAX_STEPS = TSMIXER_CONFIG['max_steps']
TSMIXER_EARLY_STOP = TSMIXER_CONFIG['early_stop']

# XGBoost/LightGBM configuration
ROLLING_WINDOWS = [6, 12, 24, 48, 168]
LAG_HOURS = [1, 2, 3, 6, 12, 24, 48, 168]


def fetch_cmg_data(days: int = 730, use_local: bool = True) -> pd.DataFrame:
    """
    Fetch CMG data from local parquet file or Supabase.
    Returns DataFrame with datetime index and CMG column.

    Args:
        days: Number of days of data to fetch (for Supabase)
        use_local: If True, use local parquet file (recommended for more data)
    """
    # Try local parquet file first (has more data)
    local_parquet = Path('/home/paul/projects/Pudidi/traindataset_2023plus.parquet')

    if use_local and local_parquet.exists():
        print(f"Loading data from local parquet: {local_parquet}")
        df = pd.read_parquet(local_parquet)

        # The parquet has datetime as index and CMg column
        if 'CMg' in df.columns:
            df_hourly = df[['CMg']].copy()
            df_hourly.columns = ['CMG']
            df_hourly = df_hourly.sort_index()
            df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

            # Filter to last N days if specified
            if days and days < len(df_hourly) // 24:
                df_hourly = df_hourly.iloc[-(days * 24):]

            print(f"Loaded {len(df_hourly)} hours of data")
            print(f"Date range: {df_hourly.index.min()} to {df_hourly.index.max()}")
            return df_hourly

    # Fallback to Supabase
    print("Using Supabase data source...")
    supabase = SupabaseClient()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    print(f"Fetching CMG data from {start_date.date()} to {end_date.date()}...")

    records = supabase.get_cmg_online(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        limit=days * 24 * 3
    )

    if not records:
        raise ValueError("No CMG data found")

    df = pd.DataFrame(records)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df_hourly = df.groupby('datetime')['cmg_usd'].mean().reset_index()
    df_hourly.columns = ['datetime', 'CMG']
    df_hourly = df_hourly.set_index('datetime').sort_index()
    df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

    print(f"Loaded {len(df_hourly)} hours of data")
    print(f"Date range: {df_hourly.index.min()} to {df_hourly.index.max()}")

    return df_hourly


def prepare_nixtla_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert DataFrame to NeuralForecast (Nixtla) format."""
    df_nf = df.reset_index()
    df_nf.columns = ['ds', 'y']
    df_nf['unique_id'] = 'CMG'
    df_nf = df_nf[['unique_id', 'ds', 'y']]
    return df_nf


def train_tsmixer(
    df_train: pd.DataFrame,
    config: dict = None
) -> NeuralForecast:
    """
    Train TSMixer model using NeuralForecast with optimized hyperparameters.

    Args:
        df_train: Training data in Nixtla format (unique_id, ds, y)
        config: Optional configuration dict (defaults to TSMIXER_CONFIG)

    Returns:
        Trained NeuralForecast model

    Hyperparameter choices based on:
    - Google Research TSMixer paper (arXiv:2303.06053)
    - NeuralForecast documentation
    - Energy price forecasting best practices
    """
    if config is None:
        config = TSMIXER_CONFIG

    print(f"    TSMixer Config:")
    print(f"      input_size: {config['input_size']} hours")
    print(f"      horizon: {config['horizon']} hours")
    print(f"      n_block: {config['n_block']} (mixing layers)")
    print(f"      ff_dim: {config['ff_dim']}")
    print(f"      dropout: {config['dropout']}")
    print(f"      revin: {config['revin']}")
    print(f"      learning_rate: {config['learning_rate']}")
    print(f"      max_steps: {config['max_steps']}")

    model = TSMixer(
        h=config['horizon'],
        input_size=config['input_size'],
        n_series=1,
        n_block=config['n_block'],           # Number of mixing layers
        ff_dim=config['ff_dim'],             # Feed-forward dimension
        dropout=config['dropout'],           # Dropout rate
        revin=config['revin'],               # Reversible Instance Normalization
        max_steps=config['max_steps'],
        val_check_steps=50,
        early_stop_patience_steps=config['early_stop'],
        scaler_type='standard',
        learning_rate=config['learning_rate'],
        batch_size=config['batch_size'],
        valid_loss=MAE(),
        random_seed=42,
    )

    nf = NeuralForecast(models=[model], freq='h')

    # Use validation size from config
    nf.fit(df=df_train, val_size=config['val_size'])

    return nf


def evaluate_tsmixer(
    nf: NeuralForecast,
    df_full: pd.DataFrame,
    test_start_idx: int,
    horizons: List[int] = HORIZONS
) -> Dict[str, float]:
    """
    Evaluate TSMixer with proper rolling backtesting (no leakage).

    The model predicts 24 hours at once, then moves forward 24 hours.
    We extract predictions for specific horizons (t+1, t+6, t+12, t+24).
    """
    results = {f't+{h}': [] for h in horizons}
    actuals = {f't+{h}': [] for h in horizons}

    test_hours = len(df_full) - test_start_idx
    n_predictions = test_hours // TSMIXER_HORIZON

    print(f"  Running {n_predictions} rolling predictions...")

    for day in range(n_predictions):
        # Index where prediction starts
        pred_start_idx = test_start_idx + (day * TSMIXER_HORIZON)

        # Use only data up to prediction point (NO LEAKAGE)
        df_input = df_full.iloc[:pred_start_idx].copy()

        if len(df_input) < TSMIXER_INPUT_SIZE:
            continue

        # Predict 24 hours
        forecast = nf.predict(df=df_input)

        # Extract predictions for each horizon
        for h in horizons:
            target_idx = pred_start_idx + h - 1  # -1 because h is 1-indexed

            if target_idx < len(df_full) and h <= len(forecast):
                pred_value = forecast['TSMixer'].iloc[h - 1]
                actual_value = df_full['y'].iloc[target_idx]

                results[f't+{h}'].append(pred_value)
                actuals[f't+{h}'].append(actual_value)

    # Calculate MAE for each horizon
    mae_results = {}
    for h in horizons:
        key = f't+{h}'
        if results[key]:
            mae = mean_absolute_error(actuals[key], results[key])
            mae_results[key] = mae
            print(f"    {key}: ${mae:.2f} ({len(results[key])} samples)")

    return mae_results


def train_gradient_boosting(
    df_feat: pd.DataFrame,
    feature_names: List[str],
    train_end_idx: int,
    horizon: int
) -> Tuple[lgb.Booster, xgb.Booster]:
    """
    Train LightGBM and XGBoost models for a specific horizon.
    """
    target_col = f'cmg_value_t+{horizon}'

    if target_col not in df_feat.columns:
        raise ValueError(f"Target column {target_col} not found")

    # Split data
    train_df = df_feat.iloc[:train_end_idx]

    # Use last 20% of train for validation
    val_split = int(len(train_df) * 0.8)
    train_split = train_df.iloc[:val_split]
    val_split_df = train_df.iloc[val_split:]

    X_train = train_split[feature_names]
    y_train = train_split[target_col]
    X_val = val_split_df[feature_names]
    y_val = val_split_df[target_col]

    # Handle NaNs
    mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
    mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))

    X_train = X_train[mask_train]
    y_train = y_train[mask_train]
    X_val = X_val[mask_val]
    y_val = y_val[mask_val]

    # Train LightGBM
    lgb_params = {
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

    train_data = lgb.Dataset(X_train, label=y_train)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

    lgb_model = lgb.train(
        lgb_params,
        train_data,
        num_boost_round=500,
        valid_sets=[val_data],
        callbacks=[lgb.early_stopping(50, verbose=False)]
    )

    # Train XGBoost
    xgb_params = {
        'objective': 'reg:squarederror',
        'eval_metric': 'mae',
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'n_jobs': -1
    }

    train_dmatrix = xgb.DMatrix(X_train, label=y_train)
    val_dmatrix = xgb.DMatrix(X_val, label=y_val)

    xgb_model = xgb.train(
        xgb_params,
        train_dmatrix,
        num_boost_round=500,
        evals=[(val_dmatrix, 'val')],
        early_stopping_rounds=50,
        verbose_eval=False
    )

    return lgb_model, xgb_model


def evaluate_gradient_boosting(
    df_feat: pd.DataFrame,
    feature_names: List[str],
    train_end_idx: int,
    horizons: List[int] = HORIZONS
) -> Dict[str, Dict[str, float]]:
    """
    Evaluate LightGBM and XGBoost models.
    """
    results = {'lgb': {}, 'xgb': {}, 'ensemble': {}}

    for h in horizons:
        target_col = f'cmg_value_t+{h}'

        if target_col not in df_feat.columns:
            continue

        print(f"    Training models for t+{h}...")

        # Train models
        lgb_model, xgb_model = train_gradient_boosting(
            df_feat, feature_names, train_end_idx, h
        )

        # Get test data
        test_df = df_feat.iloc[train_end_idx:]
        X_test = test_df[feature_names]
        y_test = test_df[target_col]

        # Handle NaNs
        mask_test = ~(y_test.isna() | X_test.isna().any(axis=1))
        X_test = X_test[mask_test]
        y_test = y_test[mask_test]

        # Predict
        lgb_pred = lgb_model.predict(X_test)
        xgb_pred = xgb_model.predict(xgb.DMatrix(X_test))
        ensemble_pred = (lgb_pred + xgb_pred) / 2

        # Calculate MAE
        results['lgb'][f't+{h}'] = mean_absolute_error(y_test, lgb_pred)
        results['xgb'][f't+{h}'] = mean_absolute_error(y_test, xgb_pred)
        results['ensemble'][f't+{h}'] = mean_absolute_error(y_test, ensemble_pred)

        print(f"      LightGBM: ${results['lgb'][f't+{h}']:.2f}")
        print(f"      XGBoost:  ${results['xgb'][f't+{h}']:.2f}")
        print(f"      Ensemble: ${results['ensemble'][f't+{h}']:.2f}")

    return results


def evaluate_persistence(
    df: pd.DataFrame,
    train_end_idx: int,
    horizons: List[int] = HORIZONS
) -> Dict[str, float]:
    """
    Evaluate persistence baseline (same hour yesterday).
    """
    results = {}
    test_df = df.iloc[train_end_idx:]

    for h in horizons:
        # Persistence: predict CMG[t+h] = CMG[t-24+h] (same hour yesterday)
        # At time t, we know CMG up to t. We want to predict t+h.
        # We use CMG[t-24+h] as the prediction (same hour yesterday from target time)

        # Shift by 24 to get "yesterday's value at target time"
        pred = test_df['CMG'].shift(24)
        actual = test_df['CMG'].shift(-h)

        mask = ~(pred.isna() | actual.isna())
        if mask.sum() > 0:
            mae = mean_absolute_error(actual[mask], pred[mask])
            results[f't+{h}'] = mae

    return results


def run_comparison(test_days: int = TEST_DAYS) -> Dict:
    """
    Run the full model comparison.
    """
    print("=" * 70)
    print("FAIR MODEL COMPARISON: TSMixer vs XGBoost/LightGBM")
    print("=" * 70)
    print()

    # 1. Load data
    print("1. LOADING DATA")
    print("-" * 50)
    df_raw = fetch_cmg_data(days=730)
    print()

    # 2. Define splits
    test_size = test_days * 24
    train_end_idx = len(df_raw) - test_size

    print("2. DATA SPLIT")
    print("-" * 50)
    print(f"   Train: {train_end_idx:,} hours")
    print(f"   Test:  {test_size:,} hours ({test_days} days)")
    print(f"   Train end: {df_raw.index[train_end_idx - 1]}")
    print(f"   Test start: {df_raw.index[train_end_idx]}")
    print(f"   Test end: {df_raw.index[-1]}")
    print()

    # 3. Prepare data for each model type
    print("3. PREPARING DATA")
    print("-" * 50)

    # For TSMixer (Nixtla format)
    df_nixtla = prepare_nixtla_format(df_raw)
    print(f"   TSMixer format: {df_nixtla.shape}")

    # For XGBoost/LightGBM (with features)
    print("   Creating production features...")
    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),
        rolling_windows=ROLLING_WINDOWS,
        lag_hours=LAG_HOURS
    )

    # Feature engineering expects DataFrame with DatetimeIndex and 'CMG [$/MWh]' column
    df_for_features = df_raw.copy()
    df_for_features.columns = ['CMG [$/MWh]']
    df_feat = feature_engineer.create_features(df_for_features, cmg_column='CMG [$/MWh]')
    feature_names = feature_engineer.get_feature_names()
    print(f"   XGBoost format: {df_feat.shape} with {len(feature_names)} features")
    print()

    # 4. Train and evaluate TSMixer
    print("4. EVALUATING TSMIXER")
    print("-" * 50)

    # Train on data up to test start
    df_train_nixtla = df_nixtla.iloc[:train_end_idx].copy()
    print(f"   Training TSMixer on {len(df_train_nixtla)} hours...")
    nf_model = train_tsmixer(df_train_nixtla)

    print("   Evaluating TSMixer (rolling backtest)...")
    tsmixer_results = evaluate_tsmixer(
        nf_model, df_nixtla, train_end_idx, HORIZONS
    )
    print()

    # 5. Train and evaluate XGBoost/LightGBM
    print("5. EVALUATING XGBOOST/LIGHTGBM")
    print("-" * 50)
    gb_results = evaluate_gradient_boosting(
        df_feat, feature_names, train_end_idx, HORIZONS
    )
    print()

    # 6. Evaluate persistence baseline
    print("6. EVALUATING PERSISTENCE BASELINE")
    print("-" * 50)
    persistence_results = evaluate_persistence(df_raw, train_end_idx, HORIZONS)
    for h in HORIZONS:
        print(f"   t+{h}: ${persistence_results.get(f't+{h}', 0):.2f}")
    print()

    # 7. Summary comparison
    print("=" * 70)
    print("RESULTS SUMMARY - MAE (USD/MWh)")
    print("=" * 70)
    print()

    # Create comparison table
    print(f"{'Horizon':<10} {'Persistence':<12} {'LightGBM':<12} {'XGBoost':<12} {'Ensemble':<12} {'TSMixer':<12}")
    print("-" * 70)

    totals = {
        'persistence': 0,
        'lgb': 0,
        'xgb': 0,
        'ensemble': 0,
        'tsmixer': 0
    }

    for h in HORIZONS:
        key = f't+{h}'
        p = persistence_results.get(key, 0)
        l = gb_results['lgb'].get(key, 0)
        x = gb_results['xgb'].get(key, 0)
        e = gb_results['ensemble'].get(key, 0)
        t = tsmixer_results.get(key, 0)

        # Find best (lowest MAE)
        values = {'p': p, 'l': l, 'x': x, 'e': e, 't': t}
        best = min(values, key=values.get)

        # Format with highlighting
        def fmt(val, is_best):
            s = f"${val:.2f}"
            return f"**{s}**" if is_best else s

        print(f"{key:<10} {fmt(p, best=='p'):<12} {fmt(l, best=='l'):<12} {fmt(x, best=='x'):<12} {fmt(e, best=='e'):<12} {fmt(t, best=='t'):<12}")

        totals['persistence'] += p
        totals['lgb'] += l
        totals['xgb'] += x
        totals['ensemble'] += e
        totals['tsmixer'] += t

    print("-" * 70)

    # Averages
    n = len(HORIZONS)
    avg_p = totals['persistence'] / n
    avg_l = totals['lgb'] / n
    avg_x = totals['xgb'] / n
    avg_e = totals['ensemble'] / n
    avg_t = totals['tsmixer'] / n

    print(f"{'AVERAGE':<10} ${avg_p:<11.2f} ${avg_l:<11.2f} ${avg_x:<11.2f} ${avg_e:<11.2f} ${avg_t:<11.2f}")
    print()

    # 8. Analysis
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print()

    # Best model
    models = {
        'Persistence': avg_p,
        'LightGBM': avg_l,
        'XGBoost': avg_x,
        'ML Ensemble': avg_e,
        'TSMixer': avg_t
    }
    best_model = min(models, key=models.get)
    best_mae = models[best_model]

    print(f"Best Overall Model: {best_model} (${best_mae:.2f})")
    print()

    # Improvements over baseline
    print("Improvement over Persistence Baseline:")
    for name, mae in models.items():
        if name != 'Persistence':
            improvement = (avg_p - mae) / avg_p * 100
            sign = "+" if improvement > 0 else ""
            print(f"  {name}: {sign}{improvement:.1f}%")
    print()

    # TSMixer vs ML Ensemble comparison
    if avg_t < avg_e:
        improvement = (avg_e - avg_t) / avg_e * 100
        print(f"TSMixer BEATS ML Ensemble by {improvement:.1f}%")
        recommendation = "CONSIDER INTEGRATING TSMixer"
    elif avg_t > avg_e:
        degradation = (avg_t - avg_e) / avg_e * 100
        print(f"ML Ensemble BEATS TSMixer by {degradation:.1f}%")
        recommendation = "KEEP ML Ensemble in production"
    else:
        print("TSMixer and ML Ensemble are EQUAL")
        recommendation = "Consider ensemble diversity benefits"

    print()
    print(f"RECOMMENDATION: {recommendation}")

    # 9. Save results
    results_summary = {
        'evaluation_date': datetime.now().isoformat(),
        'methodology': 'fair_comparison_no_leakage',
        'test_days': test_days,
        'horizons': HORIZONS,
        'results': {
            'persistence': persistence_results,
            'lightgbm': gb_results['lgb'],
            'xgboost': gb_results['xgb'],
            'ml_ensemble': gb_results['ensemble'],
            'tsmixer': tsmixer_results
        },
        'average_mae': {
            'persistence': float(avg_p),
            'lightgbm': float(avg_l),
            'xgboost': float(avg_x),
            'ml_ensemble': float(avg_e),
            'tsmixer': float(avg_t)
        },
        'best_model': best_model,
        'recommendation': recommendation
    }

    # Save to logs
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    output_path = log_dir / 'tsmixer_comparison_results.json'
    with open(output_path, 'w') as f:
        json.dump(results_summary, f, indent=2, default=str)

    print()
    print(f"Results saved to: {output_path}")

    return results_summary


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Compare TSMixer vs XGBoost/LightGBM')
    parser.add_argument('--test-days', type=int, default=TEST_DAYS,
                        help=f'Number of test days (default: {TEST_DAYS})')

    args = parser.parse_args()

    results = run_comparison(test_days=args.test_days)
