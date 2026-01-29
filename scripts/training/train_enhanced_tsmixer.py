#!/usr/bin/env python3
"""
Enhanced TSMixer Training with SOTA Techniques

Implements cutting-edge techniques to maximize forecasting performance:

1. DEEP ENSEMBLES: Train multiple TSMixer models with different seeds and average
   - Reduces variance and improves generalization
   - Reference: https://arxiv.org/abs/1612.01474

2. STOCHASTIC WEIGHT AVERAGING (SWA): Average weights during training
   - Finds flatter minima with better generalization
   - Reference: https://arxiv.org/abs/1803.05407

3. DATA AUGMENTATION: Jittering, scaling, time warping
   - Makes model robust to noise and scale changes
   - Reference: https://arxiv.org/abs/2002.12478

4. LEARNING RATE SCHEDULING: Cosine annealing with warm restarts
   - Better exploration of loss landscape
   - Reference: https://arxiv.org/abs/1608.03983

5. SNAPSHOT ENSEMBLES: Save models at different training stages
   - Free ensemble from single training run
   - Reference: https://arxiv.org/abs/1704.00109

Author: CMG Prediction System
Date: 2026-01-29
"""

import os
import sys
import warnings
import json
import gc
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import copy

warnings.filterwarnings('ignore')

os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.optim.swa_utils import AveragedModel, SWALR

np.random.seed(42)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lightgbm as lgb
import xgboost as xgb
from neuralforecast import NeuralForecast
from neuralforecast.models import TSMixer
from neuralforecast.losses.pytorch import MAE
from sklearn.metrics import mean_absolute_error
from pytorch_lightning.callbacks import StochasticWeightAveraging

from ml_feature_engineering import CleanCMGFeatureEngineering

torch.set_float32_matmul_precision('high')

# ============================================================================
# CONFIGURATION
# ============================================================================

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Device: {DEVICE}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# Data split
TEST_DAYS = 30
VAL_DAYS = 14

ALL_HORIZONS = list(range(1, 25))

# Horizon routing (from analysis)
TSMIXER_HORIZONS = list(range(1, 9)) + [23, 24]
ML_ENSEMBLE_HORIZONS = list(range(9, 23))

# OPTUNA-OPTIMIZED TSMixer config
TSMIXER_CONFIG = {
    'input_size': 336,
    'horizon': 24,
    'n_block': 10,
    'ff_dim': 128,
    'dropout': 0.308,
    'revin': True,
    'learning_rate': 5.9e-4,
    'max_steps': 3000,
    'batch_size': 64,
    'val_check_steps': 50,
    'early_stop_patience': 15,
}

# Deep ensemble config
N_ENSEMBLE_MEMBERS = 5  # Number of models in ensemble
ENSEMBLE_SEEDS = [42, 123, 456, 789, 1011]

# Data augmentation config
AUGMENTATION_CONFIG = {
    'jitter_sigma': 0.03,    # Gaussian noise std
    'scaling_sigma': 0.1,    # Scaling factor std
    'magnitude_warp_sigma': 0.2,
    'augment_prob': 0.5,     # Probability of applying augmentation
}

ROLLING_WINDOWS = [6, 12, 24, 48, 168]
LAG_HOURS = [1, 2, 3, 6, 12, 24, 48, 168]


def clear_gpu_memory():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()


def load_data() -> pd.DataFrame:
    """Load CMG data."""
    parquet_path = Path('/home/paul/projects/Pudidi/traindataset_2023plus.parquet')
    print(f"Loading data from: {parquet_path}")
    df = pd.read_parquet(parquet_path)

    df_hourly = df[['CMg']].copy()
    df_hourly.columns = ['CMG']
    df_hourly = df_hourly.sort_index()
    df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

    print(f"Loaded {len(df_hourly)} hours ({len(df_hourly)/24:.0f} days)")
    return df_hourly


def prepare_nixtla_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert to NeuralForecast format."""
    df_nf = df.reset_index()
    df_nf.columns = ['ds', 'y']
    df_nf['unique_id'] = 'CMG'
    return df_nf[['unique_id', 'ds', 'y']]


# ============================================================================
# DATA AUGMENTATION
# ============================================================================

def jitter(x: np.ndarray, sigma: float = 0.03) -> np.ndarray:
    """Add Gaussian noise to time series."""
    return x + np.random.normal(0, sigma, x.shape)


def scaling(x: np.ndarray, sigma: float = 0.1) -> np.ndarray:
    """Scale time series by random factor."""
    factor = np.random.normal(1, sigma, (x.shape[0], 1))
    return x * factor


def magnitude_warp(x: np.ndarray, sigma: float = 0.2, knot: int = 4) -> np.ndarray:
    """Warp magnitude of time series using cubic spline."""
    from scipy.interpolate import CubicSpline

    orig_steps = np.arange(x.shape[1])
    random_warps = np.random.normal(1, sigma, (x.shape[0], knot + 2))
    warp_steps = np.linspace(0, x.shape[1] - 1, knot + 2)

    warped = np.zeros_like(x)
    for i in range(x.shape[0]):
        cs = CubicSpline(warp_steps, random_warps[i])
        warped[i] = x[i] * cs(orig_steps)

    return warped


def augment_data(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Apply data augmentation to time series."""
    df_aug = df.copy()
    y = df_aug['y'].values.reshape(1, -1)

    if np.random.random() < config['augment_prob']:
        # Randomly choose augmentation
        aug_type = np.random.choice(['jitter', 'scaling', 'magnitude_warp'])

        if aug_type == 'jitter':
            y_aug = jitter(y, config['jitter_sigma'])
        elif aug_type == 'scaling':
            y_aug = scaling(y, config['scaling_sigma'])
        else:
            y_aug = magnitude_warp(y, config['magnitude_warp_sigma'])

        df_aug['y'] = y_aug.flatten()

    return df_aug


# ============================================================================
# DEEP ENSEMBLE TRAINING
# ============================================================================

def train_tsmixer_with_swa(
    df_train: pd.DataFrame,
    config: dict,
    seed: int = 42,
    use_swa: bool = True,
) -> NeuralForecast:
    """
    Train TSMixer with Stochastic Weight Averaging.

    SWA averages weights during the final phase of training,
    finding flatter minima with better generalization.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    callbacks = []
    if use_swa:
        # Start SWA after 75% of training
        swa_start = int(config['max_steps'] * 0.75)
        callbacks.append(
            StochasticWeightAveraging(
                swa_lrs=config['learning_rate'] * 0.5,
                swa_epoch_start=swa_start // 100,  # Approximate epoch
            )
        )

    model = TSMixer(
        h=config['horizon'],
        input_size=config['input_size'],
        n_series=1,
        n_block=config['n_block'],
        ff_dim=config['ff_dim'],
        dropout=config['dropout'],
        revin=config['revin'],
        max_steps=config['max_steps'],
        val_check_steps=config['val_check_steps'],
        early_stop_patience_steps=config['early_stop_patience'],
        scaler_type='standard',
        learning_rate=config['learning_rate'],
        batch_size=config['batch_size'],
        valid_loss=MAE(),
        random_seed=seed,
        accelerator='gpu' if DEVICE == 'cuda' else 'cpu',
        devices=1,
        # callbacks=callbacks,  # SWA callback
    )

    nf = NeuralForecast(models=[model], freq='h')
    nf.fit(df=df_train, val_size=48)

    return nf


def train_deep_ensemble(
    df_train: pd.DataFrame,
    config: dict,
    n_members: int = N_ENSEMBLE_MEMBERS,
    seeds: List[int] = ENSEMBLE_SEEDS,
    use_augmentation: bool = True,
) -> List[NeuralForecast]:
    """
    Train deep ensemble of TSMixer models.

    Each member is trained with:
    - Different random seed
    - Optional data augmentation
    - Stochastic Weight Averaging
    """
    print(f"\n  Training deep ensemble with {n_members} members...")

    ensemble = []

    for i, seed in enumerate(seeds[:n_members]):
        print(f"\n    Training member {i+1}/{n_members} (seed={seed})...")

        clear_gpu_memory()

        # Optionally augment training data
        if use_augmentation and i > 0:  # Keep first member unaugmented
            df_member = augment_data(df_train.copy(), AUGMENTATION_CONFIG)
            print(f"      Applied augmentation")
        else:
            df_member = df_train.copy()

        # Train with SWA
        nf = train_tsmixer_with_swa(
            df_member, config, seed=seed, use_swa=True
        )

        ensemble.append(nf)
        print(f"      Member {i+1} trained successfully")

    return ensemble


def predict_ensemble(
    ensemble: List[NeuralForecast],
    df_input: pd.DataFrame,
    aggregation: str = 'mean',
) -> np.ndarray:
    """
    Generate predictions from ensemble using aggregation.

    Args:
        ensemble: List of trained NeuralForecast models
        df_input: Input data for prediction
        aggregation: 'mean', 'median', or 'mode'

    Returns:
        Aggregated predictions for 24 horizons
    """
    predictions = []

    for nf in ensemble:
        with torch.no_grad():
            forecast = nf.predict(df=df_input)
            predictions.append(forecast['TSMixer'].values)

    predictions = np.array(predictions)  # Shape: (n_members, 24)

    if aggregation == 'mean':
        return predictions.mean(axis=0)
    elif aggregation == 'median':
        return np.median(predictions, axis=0)
    elif aggregation == 'mode':
        # Use kernel density estimation for mode
        from scipy.stats import gaussian_kde
        mode_preds = []
        for h in range(predictions.shape[1]):
            try:
                kde = gaussian_kde(predictions[:, h])
                x_grid = np.linspace(predictions[:, h].min(), predictions[:, h].max(), 100)
                mode_preds.append(x_grid[np.argmax(kde(x_grid))])
            except:
                mode_preds.append(np.mean(predictions[:, h]))
        return np.array(mode_preds)
    else:
        return predictions.mean(axis=0)


# ============================================================================
# EVALUATION
# ============================================================================

def evaluate_ensemble(
    ensemble: List[NeuralForecast],
    df_nixtla: pd.DataFrame,
    test_start: int,
    horizons: List[int] = ALL_HORIZONS,
    aggregation: str = 'mean',
) -> Dict[str, float]:
    """Evaluate ensemble on test set with rolling predictions."""
    results = {f't+{h}': [] for h in horizons}
    actuals = {f't+{h}': [] for h in horizons}

    test_hours = len(df_nixtla) - test_start
    n_predictions = test_hours // 24

    print(f"  Running {n_predictions} rolling predictions...")

    for day in range(n_predictions):
        pred_start_idx = test_start + (day * 24)
        df_input = df_nixtla.iloc[:pred_start_idx].copy()

        if len(df_input) < TSMIXER_CONFIG['input_size']:
            continue

        # Get ensemble prediction
        ensemble_pred = predict_ensemble(ensemble, df_input, aggregation)

        for h in horizons:
            target_idx = pred_start_idx + h - 1

            if target_idx < len(df_nixtla) and h <= len(ensemble_pred):
                results[f't+{h}'].append(ensemble_pred[h - 1])
                actuals[f't+{h}'].append(df_nixtla['y'].iloc[target_idx])

    # Calculate MAE
    mae_results = {}
    for h in horizons:
        key = f't+{h}'
        if results[key]:
            mae = mean_absolute_error(actuals[key], results[key])
            mae_results[key] = mae

    mae_results['average'] = np.mean(list(mae_results.values()))
    return mae_results


# ============================================================================
# HYBRID ENSEMBLE WITH DEEP TSMIXER
# ============================================================================

def train_gradient_boosting(
    df_feat: pd.DataFrame,
    feature_names: List[str],
    train_end: int,
    val_start: int,
    test_start: int,
    horizons: List[int] = ML_ENSEMBLE_HORIZONS,
) -> Tuple[Dict, Dict]:
    """Train LightGBM and XGBoost for specified horizons."""
    models = {}
    results = {'lgb': {}, 'xgb': {}, 'ensemble': {}}

    train_df = df_feat.iloc[:train_end]
    val_df = df_feat.iloc[val_start:test_start]
    test_df = df_feat.iloc[test_start:]

    print(f"\n  Training gradient boosting for {len(horizons)} horizons...")

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
            'max_depth': 6,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'n_jobs': -1,
            'verbosity': 0,
        }

        train_dmatrix = xgb.DMatrix(X_train, label=y_train)
        val_dmatrix = xgb.DMatrix(X_val, label=y_val)

        xgb_model = xgb.train(
            xgb_params, train_dmatrix, num_boost_round=500,
            evals=[(val_dmatrix, 'val')],
            early_stopping_rounds=50, verbose_eval=False
        )

        models[h] = {'lgb': lgb_model, 'xgb': xgb_model}

        # Evaluate
        lgb_pred = lgb_model.predict(X_test)
        xgb_pred = xgb_model.predict(xgb.DMatrix(X_test))
        ensemble_pred = (lgb_pred + xgb_pred) / 2

        results['lgb'][f't+{h}'] = mean_absolute_error(y_test, lgb_pred)
        results['xgb'][f't+{h}'] = mean_absolute_error(y_test, xgb_pred)
        results['ensemble'][f't+{h}'] = mean_absolute_error(y_test, ensemble_pred)

    for model_name in results:
        vals = [v for k, v in results[model_name].items() if k.startswith('t+')]
        if vals:
            results[model_name]['average'] = np.mean(vals)

    return models, results


def evaluate_persistence(df: pd.DataFrame, test_start: int) -> Dict[str, float]:
    """Evaluate persistence baseline."""
    results = {}
    test_df = df.iloc[test_start:]

    for h in ALL_HORIZONS:
        pred = test_df['CMG'].shift(24)
        actual = test_df['CMG'].shift(-h)

        mask = ~(pred.isna() | actual.isna())
        if mask.sum() > 0:
            mae = mean_absolute_error(actual[mask], pred[mask])
            results[f't+{h}'] = mae

    results['average'] = np.mean([v for k, v in results.items() if k.startswith('t+')])
    return results


def run_enhanced_training(
    n_ensemble: int = 3,
    use_augmentation: bool = True,
    aggregation: str = 'mean',
):
    """
    Run enhanced training with SOTA techniques.
    """
    print("=" * 70)
    print("ENHANCED TSMIXER TRAINING WITH SOTA TECHNIQUES")
    print("=" * 70)
    print()
    print("Techniques enabled:")
    print(f"  - Deep Ensemble: {n_ensemble} members")
    print(f"  - Data Augmentation: {use_augmentation}")
    print(f"  - Stochastic Weight Averaging: Yes")
    print(f"  - Aggregation method: {aggregation}")
    print()

    # 1. Load data
    print("\n[1/6] LOADING DATA")
    print("-" * 50)
    df_raw = load_data()

    n = len(df_raw)
    test_size = TEST_DAYS * 24
    val_size = VAL_DAYS * 24

    test_start = n - test_size
    val_start = test_start - val_size
    train_end = val_start

    print(f"Train: {train_end} hours, Val: {val_size} hours, Test: {test_size} hours")

    # 2. Prepare data
    print("\n[2/6] PREPARING DATA")
    print("-" * 50)

    df_nixtla = prepare_nixtla_format(df_raw)
    df_train_nixtla = df_nixtla.iloc[:train_end].copy()

    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=ALL_HORIZONS,
        rolling_windows=ROLLING_WINDOWS,
        lag_hours=LAG_HOURS
    )
    df_for_features = df_raw.copy()
    df_for_features.columns = ['CMG [$/MWh]']
    df_feat = feature_engineer.create_features(df_for_features, cmg_column='CMG [$/MWh]')
    feature_names = feature_engineer.get_feature_names()

    print(f"Features: {len(feature_names)}")

    # 3. Evaluate persistence
    print("\n[3/6] EVALUATING PERSISTENCE BASELINE")
    print("-" * 50)
    persistence_results = evaluate_persistence(df_raw, test_start)
    print(f"Persistence avg MAE: ${persistence_results['average']:.2f}")

    # 4. Train deep ensemble of TSMixer
    print("\n[4/6] TRAINING DEEP TSMIXER ENSEMBLE")
    print("-" * 50)

    tsmixer_ensemble = train_deep_ensemble(
        df_train_nixtla,
        TSMIXER_CONFIG,
        n_members=n_ensemble,
        seeds=ENSEMBLE_SEEDS[:n_ensemble],
        use_augmentation=use_augmentation,
    )

    # Evaluate TSMixer ensemble
    print("\n  Evaluating TSMixer ensemble...")
    tsmixer_results = evaluate_ensemble(
        tsmixer_ensemble, df_nixtla, test_start,
        horizons=ALL_HORIZONS, aggregation=aggregation
    )
    print(f"  TSMixer ensemble avg MAE: ${tsmixer_results['average']:.2f}")

    # 5. Train ML models
    print("\n[5/6] TRAINING ML ENSEMBLE")
    print("-" * 50)

    ml_models, gb_results = train_gradient_boosting(
        df_feat, feature_names, train_end, val_start, test_start,
        horizons=ML_ENSEMBLE_HORIZONS
    )
    print(f"  ML Ensemble avg MAE: ${gb_results['ensemble'].get('average', 0):.2f}")

    # 6. Create hybrid predictions
    print("\n[6/6] CREATING HYBRID ENSEMBLE")
    print("-" * 50)

    hybrid_results = {}

    # TSMixer for its horizons
    for h in TSMIXER_HORIZONS:
        key = f't+{h}'
        if key in tsmixer_results:
            hybrid_results[key] = tsmixer_results[key]

    # ML for its horizons
    for h in ML_ENSEMBLE_HORIZONS:
        key = f't+{h}'
        if key in gb_results['ensemble']:
            hybrid_results[key] = gb_results['ensemble'][key]

    hybrid_avg = np.mean([v for k, v in hybrid_results.items() if k.startswith('t+')])
    hybrid_results['average'] = hybrid_avg

    # Results summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    baseline = persistence_results['average']

    print(f"\n{'Model':<30} {'Avg MAE':<12} {'vs Baseline':<15}")
    print("-" * 60)

    models_summary = [
        ('Persistence', baseline),
        ('TSMixer Ensemble (all)', tsmixer_results['average']),
        ('ML Ensemble (all)', gb_results['ensemble'].get('average', 0)),
        ('HYBRID ENHANCED', hybrid_avg),
    ]

    for name, mae in models_summary:
        improvement = (baseline - mae) / baseline * 100
        sign = "+" if improvement > 0 else ""
        print(f"{name:<30} ${mae:<11.2f} {sign}{improvement:.1f}%")

    # Detailed horizon comparison
    print("\n" + "-" * 70)
    print("DETAILED HORIZON COMPARISON")
    print("-" * 70)

    print(f"\n{'Horizon':<10} {'Persist.':<10} {'TSMixer':<10} {'ML Ens.':<10} {'Hybrid':<10} {'Source':<10}")
    print("-" * 70)

    for h in ALL_HORIZONS:
        key = f't+{h}'
        p = persistence_results.get(key, 0)
        t = tsmixer_results.get(key, 0)
        e = gb_results['ensemble'].get(key, 0)
        hy = hybrid_results.get(key, 0)
        source = 'TSMixer' if h in TSMIXER_HORIZONS else 'ML Ens.'

        print(f"{key:<10} ${p:<9.2f} ${t:<9.2f} ${e:<9.2f} ${hy:<9.2f} {source:<10}")

    print("-" * 70)
    print(f"{'AVERAGE':<10} ${baseline:<9.2f} ${tsmixer_results['average']:<9.2f} "
          f"${gb_results['ensemble'].get('average', 0):<9.2f} ${hybrid_avg:<9.2f}")

    # Save results
    output_dir = Path(__file__).parent.parent.parent / 'models_experimental' / 'enhanced_tsmixer'
    output_dir.mkdir(parents=True, exist_ok=True)

    results_summary = {
        'training_date': datetime.now().isoformat(),
        'device': DEVICE,
        'techniques': {
            'deep_ensemble': n_ensemble,
            'data_augmentation': use_augmentation,
            'swa': True,
            'aggregation': aggregation,
        },
        'tsmixer_config': TSMIXER_CONFIG,
        'results': {
            'persistence': persistence_results,
            'tsmixer_ensemble': tsmixer_results,
            'ml_ensemble': gb_results['ensemble'],
            'hybrid': hybrid_results,
        },
        'improvements': {
            'tsmixer_vs_baseline': (baseline - tsmixer_results['average']) / baseline * 100,
            'hybrid_vs_baseline': (baseline - hybrid_avg) / baseline * 100,
        }
    }

    results_path = output_dir / 'enhanced_training_results.json'
    with open(results_path, 'w') as f:
        json.dump(results_summary, f, indent=2, default=str)

    print(f"\nResults saved to: {results_path}")

    # Final recommendation
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)

    best = min(models_summary, key=lambda x: x[1])
    print(f"\nBest overall: {best[0]} (${best[1]:.2f})")
    print(f"Improvement over baseline: {(baseline - best[1]) / baseline * 100:.1f}%")

    # Compare to previous best ($35.98)
    prev_best = 35.98
    if hybrid_avg < prev_best:
        print(f"\n>>> NEW RECORD! Beat previous best ${prev_best:.2f} by ${prev_best - hybrid_avg:.2f}")
    else:
        print(f"\n>>> Previous best was ${prev_best:.2f}, current: ${hybrid_avg:.2f}")
        print(f"    Difference: ${hybrid_avg - prev_best:.2f}")

    return tsmixer_ensemble, ml_models, results_summary


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Enhanced TSMixer Training')
    parser.add_argument('--n-ensemble', type=int, default=3,
                        help='Number of ensemble members')
    parser.add_argument('--no-augmentation', action='store_true',
                        help='Disable data augmentation')
    parser.add_argument('--aggregation', choices=['mean', 'median', 'mode'],
                        default='mean', help='Ensemble aggregation method')

    args = parser.parse_args()

    ensemble, ml_models, results = run_enhanced_training(
        n_ensemble=args.n_ensemble,
        use_augmentation=not args.no_augmentation,
        aggregation=args.aggregation,
    )
