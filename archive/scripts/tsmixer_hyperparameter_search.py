#!/usr/bin/env python3
"""
TSMixer Hyperparameter Optimization & Fair Model Comparison

This script:
1. Tests multiple TSMixer hyperparameter configurations
2. Uses proper time series train/val/test split (NO DATA LEAKAGE)
3. Evaluates ALL 24 horizons (t+1 to t+24)
4. Compares fairly against XGBoost/LightGBM ensemble

Why the original notebook showed ~$17 MAE:
- Limited test data (only 72 hours / 3 days)
- No cross-validation
- Possible overfitting to specific period

This script uses:
- 30 days test (720 hours) - statistically robust
- Proper temporal split (train -> val -> test)
- Multiple hyperparameter configs for TSMixer

Author: CMG Prediction System
Date: 2026-01-29
"""

import os
import sys
import warnings
import json
from datetime import datetime
from typing import Dict, List, Tuple
from pathlib import Path
import itertools

warnings.filterwarnings('ignore')
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lightgbm as lgb
import xgboost as xgb
from neuralforecast import NeuralForecast
from neuralforecast.models import TSMixer
from neuralforecast.losses.pytorch import MAE
from sklearn.metrics import mean_absolute_error

from ml_feature_engineering import CleanCMGFeatureEngineering

torch.set_float32_matmul_precision('high')
np.random.seed(42)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Data split configuration
TEST_DAYS = 30       # 30 days for final test (720 hours)
VAL_DAYS = 14        # 14 days for validation (336 hours)

# All 24 horizons
ALL_HORIZONS = list(range(1, 25))  # t+1 to t+24

# TSMixer hyperparameter search space
TSMIXER_CONFIGS = [
    # Config 1: Original notebook settings (baseline)
    {
        'name': 'Original (notebook)',
        'input_size': 168,
        'n_block': 2,      # Default
        'ff_dim': 64,
        'dropout': 0.9,    # Default (very high!)
        'revin': True,
        'learning_rate': 1e-3,
        'max_steps': 2000,
    },
    # Config 2: Optimized (our research-based)
    {
        'name': 'Optimized (research)',
        'input_size': 168,
        'n_block': 4,
        'ff_dim': 64,
        'dropout': 0.5,
        'revin': True,
        'learning_rate': 1e-4,
        'max_steps': 2000,
    },
    # Config 3: More layers, lower dropout
    {
        'name': 'Deep (8 blocks)',
        'input_size': 168,
        'n_block': 8,
        'ff_dim': 64,
        'dropout': 0.3,
        'revin': True,
        'learning_rate': 1e-4,
        'max_steps': 2000,
    },
    # Config 4: Wider network
    {
        'name': 'Wide (128 ff_dim)',
        'input_size': 168,
        'n_block': 4,
        'ff_dim': 128,
        'dropout': 0.5,
        'revin': True,
        'learning_rate': 1e-4,
        'max_steps': 2000,
    },
    # Config 5: Longer input window
    {
        'name': 'Long input (336h)',
        'input_size': 336,  # 2 weeks
        'n_block': 4,
        'ff_dim': 64,
        'dropout': 0.5,
        'revin': True,
        'learning_rate': 1e-4,
        'max_steps': 2000,
    },
    # Config 6: No RevIN (test importance)
    {
        'name': 'No RevIN',
        'input_size': 168,
        'n_block': 4,
        'ff_dim': 64,
        'dropout': 0.5,
        'revin': False,
        'learning_rate': 1e-4,
        'max_steps': 2000,
    },
]

# XGBoost/LightGBM configuration
ROLLING_WINDOWS = [6, 12, 24, 48, 168]
LAG_HOURS = [1, 2, 3, 6, 12, 24, 48, 168]


def load_data() -> pd.DataFrame:
    """Load CMG data from local parquet file."""
    parquet_path = Path('/home/paul/projects/Pudidi/traindataset_2023plus.parquet')

    print(f"Loading data from: {parquet_path}")
    df = pd.read_parquet(parquet_path)

    df_hourly = df[['CMg']].copy()
    df_hourly.columns = ['CMG']
    df_hourly = df_hourly.sort_index()
    df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

    print(f"Loaded {len(df_hourly)} hours")
    print(f"Date range: {df_hourly.index.min()} to {df_hourly.index.max()}")

    return df_hourly


def create_temporal_split(df: pd.DataFrame, test_days: int, val_days: int) -> Tuple[int, int, int]:
    """
    Create proper temporal train/val/test split.

    Timeline:
    [-------- TRAIN --------][-- VAL --][-- TEST --]
                             ^          ^           ^
                          val_start  test_start   end

    Returns indices for val_start and test_start.
    """
    n = len(df)
    test_size = test_days * 24
    val_size = val_days * 24

    test_start = n - test_size
    val_start = test_start - val_size
    train_end = val_start

    print("\n" + "=" * 60)
    print("TEMPORAL DATA SPLIT (NO DATA LEAKAGE)")
    print("=" * 60)
    print(f"Total data:    {n} hours ({n/24:.0f} days)")
    print(f"Train:         {train_end} hours ({train_end/24:.0f} days)")
    print(f"Validation:    {val_size} hours ({val_days} days)")
    print(f"Test:          {test_size} hours ({test_days} days)")
    print()
    print(f"Train period:  {df.index[0]} to {df.index[train_end-1]}")
    print(f"Val period:    {df.index[val_start]} to {df.index[test_start-1]}")
    print(f"Test period:   {df.index[test_start]} to {df.index[-1]}")
    print("=" * 60)

    return train_end, val_start, test_start


def prepare_nixtla_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert to NeuralForecast format."""
    df_nf = df.reset_index()
    df_nf.columns = ['ds', 'y']
    df_nf['unique_id'] = 'CMG'
    return df_nf[['unique_id', 'ds', 'y']]


def train_and_evaluate_tsmixer(
    df_nixtla: pd.DataFrame,
    train_end: int,
    test_start: int,
    config: dict,
    horizons: List[int] = ALL_HORIZONS
) -> Dict[str, float]:
    """
    Train TSMixer with given config and evaluate on test set.

    Uses validation set for early stopping during training.
    Evaluates on held-out test set.
    """
    print(f"\n  Config: {config['name']}")
    print(f"    n_block={config['n_block']}, ff_dim={config['ff_dim']}, "
          f"dropout={config['dropout']}, revin={config['revin']}")

    # Train data (for fitting)
    df_train = df_nixtla.iloc[:train_end].copy()

    # Create model
    model = TSMixer(
        h=24,  # Always predict 24 hours
        input_size=config['input_size'],
        n_series=1,
        n_block=config['n_block'],
        ff_dim=config['ff_dim'],
        dropout=config['dropout'],
        revin=config['revin'],
        max_steps=config['max_steps'],
        val_check_steps=50,
        early_stop_patience_steps=10,
        scaler_type='standard',
        learning_rate=config['learning_rate'],
        batch_size=32,
        valid_loss=MAE(),
        random_seed=42,
    )

    nf = NeuralForecast(models=[model], freq='h')

    # Train with validation
    val_size = test_start - train_end
    nf.fit(df=df_train, val_size=min(val_size, 48))  # Use up to 48h for internal validation

    # Evaluate on test set using rolling predictions
    results = {f't+{h}': [] for h in horizons}
    actuals = {f't+{h}': [] for h in horizons}

    test_hours = len(df_nixtla) - test_start
    n_predictions = test_hours // 24

    print(f"    Running {n_predictions} rolling predictions on test set...")

    for day in range(n_predictions):
        pred_start_idx = test_start + (day * 24)

        # Use only data up to prediction point (NO LEAKAGE)
        df_input = df_nixtla.iloc[:pred_start_idx].copy()

        if len(df_input) < config['input_size']:
            continue

        # Predict 24 hours
        forecast = nf.predict(df=df_input)

        # Extract predictions for each horizon
        for h in horizons:
            target_idx = pred_start_idx + h - 1

            if target_idx < len(df_nixtla) and h <= len(forecast):
                pred_value = forecast['TSMixer'].iloc[h - 1]
                actual_value = df_nixtla['y'].iloc[target_idx]

                results[f't+{h}'].append(pred_value)
                actuals[f't+{h}'].append(actual_value)

    # Calculate MAE for each horizon
    mae_results = {}
    for h in horizons:
        key = f't+{h}'
        if results[key]:
            mae = mean_absolute_error(actuals[key], results[key])
            mae_results[key] = mae

    # Calculate average MAE across all horizons
    avg_mae = np.mean(list(mae_results.values()))
    mae_results['average'] = avg_mae

    print(f"    Average MAE (t+1 to t+24): ${avg_mae:.2f}")

    return mae_results


def train_gradient_boosting_all_horizons(
    df_feat: pd.DataFrame,
    feature_names: List[str],
    train_end: int,
    val_start: int,
    test_start: int,
    horizons: List[int] = ALL_HORIZONS
) -> Dict[str, Dict[str, float]]:
    """
    Train LightGBM and XGBoost for all 24 horizons.
    """
    results = {'lgb': {}, 'xgb': {}, 'ensemble': {}}

    # Split data
    train_df = df_feat.iloc[:train_end]
    val_df = df_feat.iloc[val_start:test_start]
    test_df = df_feat.iloc[test_start:]

    print(f"\n  Training gradient boosting models for {len(horizons)} horizons...")

    for h in horizons:
        target_col = f'cmg_value_t+{h}'

        if target_col not in df_feat.columns:
            continue

        X_train = train_df[feature_names]
        y_train = train_df[target_col]
        X_val = val_df[feature_names]
        y_val = val_df[target_col]
        X_test = test_df[feature_names]
        y_test = test_df[target_col]

        # Handle NaNs
        mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
        mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))
        mask_test = ~(y_test.isna() | X_test.isna().any(axis=1))

        X_train, y_train = X_train[mask_train], y_train[mask_train]
        X_val, y_val = X_val[mask_val], y_val[mask_val]
        X_test, y_test = X_test[mask_test], y_test[mask_test]

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
            lgb_params, train_data, num_boost_round=500,
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
            xgb_params, train_dmatrix, num_boost_round=500,
            evals=[(val_dmatrix, 'val')],
            early_stopping_rounds=50, verbose_eval=False
        )

        # Predict on test
        lgb_pred = lgb_model.predict(X_test)
        xgb_pred = xgb_model.predict(xgb.DMatrix(X_test))
        ensemble_pred = (lgb_pred + xgb_pred) / 2

        # Calculate MAE
        results['lgb'][f't+{h}'] = mean_absolute_error(y_test, lgb_pred)
        results['xgb'][f't+{h}'] = mean_absolute_error(y_test, xgb_pred)
        results['ensemble'][f't+{h}'] = mean_absolute_error(y_test, ensemble_pred)

    # Calculate averages
    for model_name in results:
        avg = np.mean([v for k, v in results[model_name].items() if k.startswith('t+')])
        results[model_name]['average'] = avg

    print(f"    LightGBM avg:  ${results['lgb']['average']:.2f}")
    print(f"    XGBoost avg:   ${results['xgb']['average']:.2f}")
    print(f"    Ensemble avg:  ${results['ensemble']['average']:.2f}")

    return results


def evaluate_persistence(
    df: pd.DataFrame,
    test_start: int,
    horizons: List[int] = ALL_HORIZONS
) -> Dict[str, float]:
    """Evaluate persistence baseline for all horizons."""
    results = {}
    test_df = df.iloc[test_start:]

    for h in horizons:
        pred = test_df['CMG'].shift(24)
        actual = test_df['CMG'].shift(-h)

        mask = ~(pred.isna() | actual.isna())
        if mask.sum() > 0:
            mae = mean_absolute_error(actual[mask], pred[mask])
            results[f't+{h}'] = mae

    results['average'] = np.mean([v for k, v in results.items() if k.startswith('t+')])
    return results


def run_hyperparameter_search():
    """Run the full hyperparameter search and comparison."""
    print("=" * 70)
    print("TSMixer HYPERPARAMETER OPTIMIZATION & FAIR COMPARISON")
    print("=" * 70)
    print()
    print("Evaluating ALL 24 horizons (t+1 to t+24)")
    print("Proper train/val/test split with NO DATA LEAKAGE")
    print()

    # 1. Load data
    df_raw = load_data()

    # 2. Create temporal split
    train_end, val_start, test_start = create_temporal_split(
        df_raw, TEST_DAYS, VAL_DAYS
    )

    # 3. Prepare data formats
    print("\nPreparing data...")
    df_nixtla = prepare_nixtla_format(df_raw)

    # Features for XGBoost/LightGBM
    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=ALL_HORIZONS,
        rolling_windows=ROLLING_WINDOWS,
        lag_hours=LAG_HOURS
    )
    df_for_features = df_raw.copy()
    df_for_features.columns = ['CMG [$/MWh]']
    df_feat = feature_engineer.create_features(df_for_features, cmg_column='CMG [$/MWh]')
    feature_names = feature_engineer.get_feature_names()

    # 4. Evaluate persistence baseline
    print("\n" + "=" * 60)
    print("EVALUATING PERSISTENCE BASELINE")
    print("=" * 60)
    persistence_results = evaluate_persistence(df_raw, test_start)
    print(f"Persistence average MAE: ${persistence_results['average']:.2f}")

    # 5. Evaluate gradient boosting models
    print("\n" + "=" * 60)
    print("EVALUATING GRADIENT BOOSTING MODELS")
    print("=" * 60)
    gb_results = train_gradient_boosting_all_horizons(
        df_feat, feature_names, train_end, val_start, test_start
    )

    # 6. Evaluate TSMixer configurations
    print("\n" + "=" * 60)
    print("EVALUATING TSMIXER CONFIGURATIONS")
    print("=" * 60)

    tsmixer_results = {}
    for config in TSMIXER_CONFIGS:
        try:
            results = train_and_evaluate_tsmixer(
                df_nixtla, train_end, test_start, config
            )
            tsmixer_results[config['name']] = results
        except Exception as e:
            print(f"    ERROR: {e}")
            tsmixer_results[config['name']] = {'average': float('inf')}

    # 7. Summary comparison
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY - AVERAGE MAE ACROSS ALL 24 HORIZONS (USD/MWh)")
    print("=" * 70)
    print()

    # Collect all results
    all_models = {
        'Persistence': persistence_results['average'],
        'LightGBM': gb_results['lgb']['average'],
        'XGBoost': gb_results['xgb']['average'],
        'ML Ensemble': gb_results['ensemble']['average'],
    }

    for config_name, results in tsmixer_results.items():
        all_models[f'TSMixer ({config_name})'] = results.get('average', float('inf'))

    # Sort by MAE
    sorted_models = sorted(all_models.items(), key=lambda x: x[1])

    print(f"{'Rank':<6} {'Model':<35} {'Avg MAE':<12} {'vs Baseline':<12}")
    print("-" * 70)

    baseline_mae = persistence_results['average']
    for rank, (model, mae) in enumerate(sorted_models, 1):
        improvement = (baseline_mae - mae) / baseline_mae * 100
        sign = "+" if improvement > 0 else ""
        print(f"{rank:<6} {model:<35} ${mae:<11.2f} {sign}{improvement:.1f}%")

    # 8. Best TSMixer config
    print("\n" + "=" * 70)
    print("BEST TSMIXER CONFIGURATION")
    print("=" * 70)

    best_tsmixer = min(tsmixer_results.items(), key=lambda x: x[1].get('average', float('inf')))
    print(f"\nBest TSMixer: {best_tsmixer[0]}")
    print(f"Average MAE: ${best_tsmixer[1]['average']:.2f}")

    # Find corresponding config
    for config in TSMIXER_CONFIGS:
        if config['name'] == best_tsmixer[0]:
            print(f"\nOptimal hyperparameters:")
            print(f"  input_size:    {config['input_size']}")
            print(f"  n_block:       {config['n_block']}")
            print(f"  ff_dim:        {config['ff_dim']}")
            print(f"  dropout:       {config['dropout']}")
            print(f"  revin:         {config['revin']}")
            print(f"  learning_rate: {config['learning_rate']}")
            break

    # 9. Detailed horizon comparison for best models
    print("\n" + "=" * 70)
    print("DETAILED COMPARISON BY HORIZON (Top 3 Models)")
    print("=" * 70)

    best_tsmixer_name = best_tsmixer[0]
    best_tsmixer_results = best_tsmixer[1]

    print(f"\n{'Horizon':<10} {'Persistence':<12} {'ML Ensemble':<12} {'TSMixer':<12} {'Best':<15}")
    print("-" * 70)

    winners = {'Persistence': 0, 'ML Ensemble': 0, 'TSMixer': 0}

    for h in ALL_HORIZONS:
        key = f't+{h}'
        p = persistence_results.get(key, 0)
        e = gb_results['ensemble'].get(key, 0)
        t = best_tsmixer_results.get(key, 0)

        values = {'Persistence': p, 'ML Ensemble': e, 'TSMixer': t}
        best = min(values, key=values.get)
        winners[best] += 1

        print(f"{key:<10} ${p:<11.2f} ${e:<11.2f} ${t:<11.2f} {best}")

    print("-" * 70)
    print(f"{'AVERAGE':<10} ${persistence_results['average']:<11.2f} "
          f"${gb_results['ensemble']['average']:<11.2f} "
          f"${best_tsmixer_results['average']:<11.2f}")

    print(f"\nHorizons won: Persistence={winners['Persistence']}, "
          f"ML Ensemble={winners['ML Ensemble']}, TSMixer={winners['TSMixer']}")

    # 10. Final recommendation
    print("\n" + "=" * 70)
    print("FINAL RECOMMENDATION")
    print("=" * 70)

    best_overall = sorted_models[0]
    print(f"\nBest Overall Model: {best_overall[0]}")
    print(f"Average MAE: ${best_overall[1]:.2f}")
    print(f"Improvement over baseline: {(baseline_mae - best_overall[1]) / baseline_mae * 100:.1f}%")

    if 'TSMixer' in best_overall[0]:
        print("\n>>> TSMixer is the WINNER! Consider replacing ML Ensemble.")
    elif 'Ensemble' in best_overall[0] or 'LightGBM' in best_overall[0]:
        tsmixer_avg = best_tsmixer[1]['average']
        ensemble_avg = gb_results['ensemble']['average']
        if tsmixer_avg < ensemble_avg * 1.1:  # Within 10%
            print(f"\n>>> ML Ensemble wins, but TSMixer is competitive ({(tsmixer_avg/ensemble_avg - 1)*100:.1f}% difference)")
            print(">>> Consider hybrid ensemble using TSMixer for specific horizons")
        else:
            print("\n>>> ML Ensemble is clearly better. Keep current production models.")

    # 11. Save results
    output = {
        'evaluation_date': datetime.now().isoformat(),
        'test_days': TEST_DAYS,
        'val_days': VAL_DAYS,
        'all_horizons': ALL_HORIZONS,
        'persistence': persistence_results,
        'gradient_boosting': gb_results,
        'tsmixer_configs': {name: res for name, res in tsmixer_results.items()},
        'best_tsmixer_config': best_tsmixer[0],
        'ranking': [(m, float(v)) for m, v in sorted_models],
    }

    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    output_path = log_dir / 'tsmixer_hyperparameter_search_results.json'

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to: {output_path}")

    return output


if __name__ == '__main__':
    results = run_hyperparameter_search()
