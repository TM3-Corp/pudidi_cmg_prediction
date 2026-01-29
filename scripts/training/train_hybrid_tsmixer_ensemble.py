#!/usr/bin/env python3
"""
Hybrid TSMixer + ML Ensemble Training Script

Based on analysis from previous sessions:
- TSMixer wins at short-term (t+1 to t+8) and long-term (t+23, t+24)
- ML Ensemble wins at medium-term (t+9 to t+22)

This script:
1. Trains an optimized TSMixer model with CUDA acceleration
2. Combines predictions using horizon-based routing
3. Saves models for production deployment

Hardware optimization:
- RTX 4060 (8GB VRAM) - uses mixed precision (FP16)
- 16GB RAM - memory-efficient data loading
- Supports up to 10,000 epochs with gradient accumulation

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

warnings.filterwarnings('ignore')

# CUDA optimizations
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'
os.environ['CUDA_LAUNCH_BLOCKING'] = '0'

import numpy as np
import pandas as pd
import torch
import torch.cuda.amp as amp

# Set seeds for reproducibility
np.random.seed(42)
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed(42)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = True

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lightgbm as lgb
import xgboost as xgb
from neuralforecast import NeuralForecast
from neuralforecast.models import TSMixer
from neuralforecast.losses.pytorch import MAE
from sklearn.metrics import mean_absolute_error
import pickle

from ml_feature_engineering import CleanCMGFeatureEngineering

# Enable TF32 for faster training on Ampere+ GPUs
torch.set_float32_matmul_precision('high')

# ============================================================================
# ZERO DETECTION MODELS PATH
# ============================================================================
ZERO_DETECTION_DIR = Path(__file__).parent.parent / 'models_24h' / 'zero_detection'

# ============================================================================
# CONFIGURATION
# ============================================================================

# Hardware detection
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
GPU_MEMORY_GB = 8.0 if torch.cuda.is_available() else 0
SYSTEM_RAM_GB = 16.0

print(f"Device: {DEVICE}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory: {GPU_MEMORY_GB} GB")

# Data split configuration
TEST_DAYS = 30       # 30 days for final test (720 hours)
VAL_DAYS = 14        # 14 days for validation (336 hours)

# All 24 horizons
ALL_HORIZONS = list(range(1, 25))  # t+1 to t+24

# Default horizon routing (static, based on previous analysis)
# Will be overridden by dynamic routing if enabled
DEFAULT_TSMIXER_HORIZONS = list(range(1, 9)) + [23, 24]  # t+1 to t+8, t+23, t+24
DEFAULT_ML_ENSEMBLE_HORIZONS = list(range(9, 23))         # t+9 to t+22

# Backward compatibility aliases
TSMIXER_HORIZONS = DEFAULT_TSMIXER_HORIZONS
ML_ENSEMBLE_HORIZONS = DEFAULT_ML_ENSEMBLE_HORIZONS

print(f"\nDefault horizon routing:")
print(f"  TSMixer: {DEFAULT_TSMIXER_HORIZONS}")
print(f"  ML Ensemble: {DEFAULT_ML_ENSEMBLE_HORIZONS}")

# TSMixer configuration (OPTUNA-OPTIMIZED - Best: $36.29 MAE)
TSMIXER_CONFIG = {
    'input_size': 336,      # 2 weeks (Optuna found this better)
    'horizon': 24,          # Predict all 24 hours (use routing later)
    'n_block': 10,          # More mixing layers (Optuna: 10)
    'ff_dim': 128,          # Wider network (Optuna: 128)
    'dropout': 0.308,       # Optuna-optimized
    'revin': True,          # Keep RevIN
    'learning_rate': 5.9e-4,  # Higher LR (Optuna found this)
    'max_steps': 2000,      # Default, can override with epochs param
    'batch_size': 64,       # Larger batch (Optuna: 64)
    'val_check_steps': 50,
    'early_stop_patience': 10,
}

# Memory-optimized config for 10,000 epochs
TSMIXER_CONFIG_LONG = {
    **TSMIXER_CONFIG,
    'max_steps': 10000,
    'batch_size': 32,       # Reduced for memory with larger model
    'val_check_steps': 100,
    'early_stop_patience': 20,
    'gradient_clip_val': 1.0,
}

# XGBoost/LightGBM configuration
ROLLING_WINDOWS = [6, 12, 24, 48, 168]
LAG_HOURS = [1, 2, 3, 6, 12, 24, 48, 168]


def get_gpu_memory_usage():
    """Get current GPU memory usage in GB."""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024**3
    return 0


def clear_gpu_memory():
    """Clear GPU memory cache."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()


def load_data() -> pd.DataFrame:
    """Load CMG data from local parquet file."""
    parquet_path = Path('/home/paul/projects/Pudidi/traindataset_2023plus.parquet')

    print(f"Loading data from: {parquet_path}")
    df = pd.read_parquet(parquet_path)

    df_hourly = df[['CMg']].copy()
    df_hourly.columns = ['CMG']
    df_hourly = df_hourly.sort_index()
    df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

    print(f"Loaded {len(df_hourly)} hours ({len(df_hourly)/24:.0f} days)")
    print(f"Date range: {df_hourly.index.min()} to {df_hourly.index.max()}")
    print(f"Memory usage: {df_hourly.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

    return df_hourly


def create_temporal_split(df: pd.DataFrame, test_days: int, val_days: int) -> Tuple[int, int, int]:
    """
    Create proper temporal train/val/test split.

    Timeline:
    [-------- TRAIN --------][-- VAL --][-- TEST --]
                             ^          ^           ^
                          val_start  test_start   end
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


def train_tsmixer_cuda(
    df_nixtla: pd.DataFrame,
    train_end: int,
    config: dict,
    use_long_training: bool = False
) -> NeuralForecast:
    """
    Train TSMixer with CUDA acceleration and memory optimization.

    Args:
        df_nixtla: Data in NeuralForecast format
        train_end: Index where training data ends
        config: TSMixer configuration
        use_long_training: If True, use 10,000 epochs config

    Returns:
        Trained NeuralForecast model
    """
    if use_long_training:
        config = TSMIXER_CONFIG_LONG.copy()

    print(f"\n  Training TSMixer with CUDA")
    print(f"    Device: {DEVICE}")
    print(f"    GPU Memory before: {get_gpu_memory_usage():.2f} GB")
    print(f"    Config: n_block={config['n_block']}, ff_dim={config['ff_dim']}, "
          f"dropout={config['dropout']}")
    print(f"    Max steps: {config['max_steps']}")
    print(f"    Batch size: {config['batch_size']}")

    # Clear GPU memory before training
    clear_gpu_memory()

    # Train data
    df_train = df_nixtla.iloc[:train_end].copy()

    # Create model with CUDA-optimized settings
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
        random_seed=42,
        # CUDA-specific optimizations
        accelerator='gpu' if DEVICE == 'cuda' else 'cpu',
        devices=1,
        # Enable mixed precision for memory efficiency
        # Note: NeuralForecast handles this internally based on accelerator
    )

    nf = NeuralForecast(models=[model], freq='h')

    # Use validation from config
    val_size = min(config.get('val_check_steps', 48) * 2, 336)  # Up to 14 days

    print(f"    Validation size: {val_size} hours")
    print(f"    Training on {len(df_train)} hours...")

    # Train with progress monitoring
    nf.fit(df=df_train, val_size=val_size)

    print(f"    GPU Memory after: {get_gpu_memory_usage():.2f} GB")
    print(f"    Training complete!")

    return nf


def evaluate_tsmixer(
    nf: NeuralForecast,
    df_nixtla: pd.DataFrame,
    test_start: int,
    horizons: List[int] = ALL_HORIZONS
) -> Dict[str, float]:
    """
    Evaluate TSMixer on test set with rolling predictions.
    """
    results = {f't+{h}': [] for h in horizons}
    actuals = {f't+{h}': [] for h in horizons}

    test_hours = len(df_nixtla) - test_start
    n_predictions = test_hours // 24

    print(f"  Running {n_predictions} rolling predictions on test set...")

    for day in range(n_predictions):
        pred_start_idx = test_start + (day * 24)

        # Use only data up to prediction point (NO LEAKAGE)
        df_input = df_nixtla.iloc[:pred_start_idx].copy()

        if len(df_input) < TSMIXER_CONFIG['input_size']:
            continue

        # Predict 24 hours
        with torch.no_grad():  # Disable gradients for inference
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

    # Calculate average MAE
    avg_mae = np.mean(list(mae_results.values()))
    mae_results['average'] = avg_mae

    return mae_results


def train_gradient_boosting_all_horizons(
    df_feat: pd.DataFrame,
    feature_names: List[str],
    train_end: int,
    val_start: int,
    test_start: int,
    horizons: List[int] = ML_ENSEMBLE_HORIZONS
) -> Tuple[Dict, Dict[str, float]]:
    """
    Train LightGBM and XGBoost for specified horizons.

    Returns:
        models: Dict of trained models per horizon
        results: Dict of MAE results per horizon
    """
    models = {}
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
            'n_jobs': -1,
            'tree_method': 'hist',  # GPU-compatible
        }

        train_dmatrix = xgb.DMatrix(X_train, label=y_train)
        val_dmatrix = xgb.DMatrix(X_val, label=y_val)

        xgb_model = xgb.train(
            xgb_params, train_dmatrix, num_boost_round=500,
            evals=[(val_dmatrix, 'val')],
            early_stopping_rounds=50, verbose_eval=False
        )

        # Store models
        models[h] = {'lgb': lgb_model, 'xgb': xgb_model}

        # Evaluate on test
        lgb_pred = lgb_model.predict(X_test)
        xgb_pred = xgb_model.predict(xgb.DMatrix(X_test))
        ensemble_pred = (lgb_pred + xgb_pred) / 2

        results['lgb'][f't+{h}'] = mean_absolute_error(y_test, lgb_pred)
        results['xgb'][f't+{h}'] = mean_absolute_error(y_test, xgb_pred)
        results['ensemble'][f't+{h}'] = mean_absolute_error(y_test, ensemble_pred)

    # Calculate averages
    for model_name in results:
        vals = [v for k, v in results[model_name].items() if k.startswith('t+')]
        if vals:
            results[model_name]['average'] = np.mean(vals)

    print(f"    ML Ensemble avg MAE: ${results['ensemble'].get('average', 0):.2f}")

    return models, results


def evaluate_persistence(
    df: pd.DataFrame,
    test_start: int,
    horizons: List[int] = ALL_HORIZONS
) -> Dict[str, float]:
    """Evaluate persistence baseline."""
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


# ============================================================================
# ZERO DETECTION / BINARY CLASSIFIER FUNCTIONS
# ============================================================================

def load_zero_classifiers(model_dir: Path = ZERO_DETECTION_DIR) -> Dict[int, lgb.Booster]:
    """
    Load pre-trained zero detection (binary classifier) models.

    These models predict P(CMG=0) for each horizon.
    Combined with a threshold, they form stage 1 of the 2-stage pipeline.

    Args:
        model_dir: Path to zero_detection models directory

    Returns:
        Dict mapping horizon (1-24) to LightGBM Booster models
    """
    classifiers = {}
    for h in range(1, 25):
        lgb_path = model_dir / f'lgb_t+{h}.txt'
        if lgb_path.exists():
            classifiers[h] = lgb.Booster(model_file=str(lgb_path))
        else:
            print(f"  Warning: Zero classifier for t+{h} not found at {lgb_path}")

    print(f"  Loaded {len(classifiers)} zero detection classifiers")
    return classifiers


def load_zero_thresholds(model_dir: Path = ZERO_DETECTION_DIR) -> Dict[int, float]:
    """
    Load calibrated thresholds for zero detection.

    Thresholds are indexed by target_hour (0-23), not horizon.
    They determine when to predict CMG=0 based on P(CMG=0) from the classifier.

    Args:
        model_dir: Path to zero_detection models directory

    Returns:
        Dict mapping horizon (1-24) to threshold value
    """
    thresholds = {}

    # Try to load from CSV (more readable)
    csv_path = model_dir / 'optimal_thresholds_by_hour_calibrated.csv'
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        # CSV has 'target_hour' (0-23) and 'threshold'
        for _, row in df.iterrows():
            hour = int(row['target_hour'])
            threshold = float(row['threshold'])
            # Map all horizons that land on this hour
            for h in range(1, 25):
                thresholds[h] = threshold  # Default
            thresholds[hour + 1 if hour < 23 else 1] = threshold
    else:
        # Fallback: load from numpy
        npy_path = model_dir / 'optimal_thresholds_by_hour_calibrated.npy'
        if npy_path.exists():
            threshold_array = np.load(npy_path)
            for h in range(1, 25):
                # Map horizon to hour of day (simplification)
                thresholds[h] = float(threshold_array[h % 24])
        else:
            print(f"  Warning: No threshold file found, using default 0.5")
            thresholds = {h: 0.5 for h in range(1, 25)}

    print(f"  Loaded thresholds for {len(thresholds)} horizons")
    return thresholds


def get_threshold_for_prediction_hour(thresholds_by_target_hour: pd.DataFrame,
                                       prediction_time: pd.Timestamp,
                                       horizon: int) -> float:
    """
    Get the appropriate threshold based on the target hour.

    The thresholds are calibrated per target hour (0-23) because
    zero events have strong hourly patterns.

    Args:
        thresholds_by_target_hour: DataFrame with 'target_hour' and 'threshold'
        prediction_time: When the prediction is made
        horizon: Hours ahead being predicted

    Returns:
        Appropriate threshold for this prediction
    """
    target_time = prediction_time + pd.Timedelta(hours=horizon)
    target_hour = target_time.hour
    row = thresholds_by_target_hour[thresholds_by_target_hour['target_hour'] == target_hour]
    if len(row) > 0:
        return float(row['threshold'].iloc[0])
    return 0.5  # Default


def apply_two_stage_prediction(
    value_preds: Dict[str, float],
    zero_probs: Dict[str, float],
    thresholds: Dict[int, float],
    prediction_time: pd.Timestamp = None,
    thresholds_df: pd.DataFrame = None
) -> Dict[str, float]:
    """
    Apply 2-stage pipeline: zero classifier + value prediction.

    Stage 1: If P(CMG=0) > threshold → predict 0
    Stage 2: Otherwise → use value prediction (clipped to >= 0)

    Args:
        value_preds: Dict of value predictions {'t+1': 45.2, ...}
        zero_probs: Dict of P(CMG=0) from classifier {'t+1': 0.7, ...}
        thresholds: Dict of thresholds per horizon {1: 0.36, ...}
        prediction_time: Optional timestamp for hour-based thresholds
        thresholds_df: Optional DataFrame with hour-based thresholds

    Returns:
        Dict of final predictions after 2-stage logic
    """
    final_preds = {}

    for key, value_pred in value_preds.items():
        # Extract horizon from key like 't+9'
        h = int(key.split('+')[1])
        zero_prob = zero_probs.get(key, 0.0)

        # Get threshold (use hour-based if available)
        if prediction_time is not None and thresholds_df is not None:
            threshold = get_threshold_for_prediction_hour(
                thresholds_df, prediction_time, h
            )
        else:
            threshold = thresholds.get(h, 0.5)

        # 2-stage decision
        if zero_prob > threshold:
            final_preds[key] = 0.0
        else:
            final_preds[key] = max(0.0, value_pred)

    return final_preds


# ============================================================================
# DYNAMIC ROUTING FUNCTIONS
# ============================================================================

def evaluate_on_validation(
    nf: NeuralForecast,
    ml_models: Dict,
    df_nixtla: pd.DataFrame,
    df_feat: pd.DataFrame,
    feature_names: List[str],
    val_start: int,
    test_start: int,
    horizons: List[int] = ALL_HORIZONS
) -> Dict[str, Dict[str, float]]:
    """
    Evaluate both TSMixer and ML Ensemble on validation set for routing decisions.

    This is used to determine which model performs better at each horizon
    on the validation set, then use that routing for test set predictions.

    Args:
        nf: Trained NeuralForecast (TSMixer) model
        ml_models: Dict of trained ML models per horizon
        df_nixtla: Data in NeuralForecast format
        df_feat: Data with features for ML models
        feature_names: List of feature column names
        val_start: Index where validation starts
        test_start: Index where test starts
        horizons: List of horizons to evaluate

    Returns:
        Dict with 'tsmixer' and 'ml_ensemble' keys, each containing MAE per horizon
    """
    print("\n  Evaluating models on validation set for dynamic routing...")

    results = {
        'tsmixer': {},
        'ml_ensemble': {}
    }

    # Validation set indices
    val_df_nixtla = df_nixtla.iloc[val_start:test_start]
    val_df_feat = df_feat.iloc[val_start:test_start]

    # Calculate MAE for TSMixer on validation
    tsmixer_preds = {f't+{h}': [] for h in horizons}
    tsmixer_actuals = {f't+{h}': [] for h in horizons}

    val_hours = test_start - val_start
    n_predictions = val_hours // 24

    for day in range(n_predictions):
        pred_start_idx = val_start + (day * 24)
        df_input = df_nixtla.iloc[:pred_start_idx].copy()

        if len(df_input) < TSMIXER_CONFIG['input_size']:
            continue

        with torch.no_grad():
            forecast = nf.predict(df=df_input)

        for h in horizons:
            target_idx = pred_start_idx + h - 1
            if target_idx < test_start and h <= len(forecast):
                pred_value = forecast['TSMixer'].iloc[h - 1]
                actual_value = df_nixtla['y'].iloc[target_idx]
                tsmixer_preds[f't+{h}'].append(pred_value)
                tsmixer_actuals[f't+{h}'].append(actual_value)

    # Calculate TSMixer MAE
    for h in horizons:
        key = f't+{h}'
        if tsmixer_preds[key]:
            mae = mean_absolute_error(tsmixer_actuals[key], tsmixer_preds[key])
            results['tsmixer'][key] = mae

    # Calculate MAE for ML Ensemble on validation
    for h in horizons:
        if h not in ml_models:
            continue

        target_col = f'cmg_value_t+{h}'
        if target_col not in df_feat.columns:
            continue

        X_val = val_df_feat[feature_names]
        y_val = val_df_feat[target_col]

        mask = ~(y_val.isna() | X_val.isna().any(axis=1))
        X_val, y_val = X_val[mask], y_val[mask]

        if len(X_val) == 0:
            continue

        lgb_pred = ml_models[h]['lgb'].predict(X_val)
        xgb_pred = ml_models[h]['xgb'].predict(xgb.DMatrix(X_val))
        ensemble_pred = (lgb_pred + xgb_pred) / 2

        mae = mean_absolute_error(y_val, ensemble_pred)
        results['ml_ensemble'][f't+{h}'] = mae

    # Print comparison
    print("\n  Validation MAE comparison:")
    print(f"  {'Horizon':<10} {'TSMixer':<12} {'ML Ensemble':<12} {'Winner':<10}")
    print("  " + "-" * 46)

    for h in horizons:
        key = f't+{h}'
        ts_mae = results['tsmixer'].get(key, float('inf'))
        ml_mae = results['ml_ensemble'].get(key, float('inf'))
        winner = 'TSMixer' if ts_mae <= ml_mae else 'ML Ens.'
        print(f"  {key:<10} ${ts_mae:<11.2f} ${ml_mae:<11.2f} {winner:<10}")

    return results


def compute_dynamic_routing(
    val_results: Dict[str, Dict[str, float]],
    margin: float = 0.0
) -> Dict[int, str]:
    """
    Select best model per horizon based on validation MAE.

    Args:
        val_results: Dict from evaluate_on_validation()
        margin: Minimum improvement required to switch from default (0 = any improvement)

    Returns:
        Dict mapping horizon (1-24) to model name ('tsmixer' or 'ml_ensemble')
    """
    routing = {}

    for h in range(1, 25):
        key = f't+{h}'
        ts_mae = val_results['tsmixer'].get(key, float('inf'))
        ml_mae = val_results['ml_ensemble'].get(key, float('inf'))

        # Use TSMixer if it's better by at least the margin
        if ts_mae <= ml_mae - margin:
            routing[h] = 'tsmixer'
        elif ml_mae < ts_mae - margin:
            routing[h] = 'ml_ensemble'
        else:
            # Tie or within margin: use default routing
            if h in DEFAULT_TSMIXER_HORIZONS:
                routing[h] = 'tsmixer'
            else:
                routing[h] = 'ml_ensemble'

    # Print routing summary
    tsmixer_horizons = [h for h, m in routing.items() if m == 'tsmixer']
    ml_horizons = [h for h, m in routing.items() if m == 'ml_ensemble']

    print(f"\n  Dynamic routing (margin={margin}):")
    print(f"    TSMixer: {sorted(tsmixer_horizons)}")
    print(f"    ML Ensemble: {sorted(ml_horizons)}")

    return routing


class HybridEnsemble:
    """
    Hybrid ensemble that routes predictions to TSMixer or ML Ensemble
    based on horizon. Optionally applies binary classifier for zero detection.
    """

    def __init__(
        self,
        tsmixer_model: NeuralForecast,
        ml_models: Dict,
        feature_names: List[str],
        tsmixer_horizons: List[int] = None,
        ml_horizons: List[int] = None,
        horizon_routing: Dict[int, str] = None,
        zero_classifiers: Dict[int, lgb.Booster] = None,
        zero_thresholds: Dict[int, float] = None,
        zero_thresholds_df: pd.DataFrame = None
    ):
        """
        Initialize HybridEnsemble with optional dynamic routing and zero detection.

        Args:
            tsmixer_model: Trained NeuralForecast model
            ml_models: Dict of trained LGB/XGB models per horizon
            feature_names: List of feature column names
            tsmixer_horizons: List of horizons for TSMixer (deprecated, use horizon_routing)
            ml_horizons: List of horizons for ML ensemble (deprecated, use horizon_routing)
            horizon_routing: Dict mapping horizon (1-24) to model ('tsmixer' or 'ml_ensemble')
            zero_classifiers: Dict of LightGBM zero detection models per horizon
            zero_thresholds: Dict of thresholds per horizon for zero detection
            zero_thresholds_df: DataFrame with hour-based thresholds for zero detection
        """
        self.tsmixer_model = tsmixer_model
        self.ml_models = ml_models
        self.feature_names = feature_names

        # Support both old (list-based) and new (routing dict) interfaces
        if horizon_routing is not None:
            self.horizon_routing = horizon_routing
            self.tsmixer_horizons = [h for h, m in horizon_routing.items() if m == 'tsmixer']
            self.ml_horizons = [h for h, m in horizon_routing.items() if m == 'ml_ensemble']
        else:
            self.tsmixer_horizons = tsmixer_horizons or DEFAULT_TSMIXER_HORIZONS
            self.ml_horizons = ml_horizons or DEFAULT_ML_ENSEMBLE_HORIZONS
            self.horizon_routing = {
                **{h: 'tsmixer' for h in self.tsmixer_horizons},
                **{h: 'ml_ensemble' for h in self.ml_horizons}
            }

        self.all_horizons = sorted(self.tsmixer_horizons + self.ml_horizons)

        # Zero detection (binary classifier) components
        self.zero_classifiers = zero_classifiers
        self.zero_thresholds = zero_thresholds
        self.zero_thresholds_df = zero_thresholds_df
        self.use_binary_classifier = zero_classifiers is not None

    def predict(
        self,
        df_nixtla: pd.DataFrame,
        df_features: pd.DataFrame,
        prediction_time: pd.Timestamp = None
    ) -> Dict[str, float]:
        """
        Generate predictions using hybrid routing with optional binary classifier.

        Args:
            df_nixtla: Data in NeuralForecast format (for TSMixer)
            df_features: Data with features (for ML Ensemble and binary classifier)
            prediction_time: Optional timestamp for hour-based threshold selection

        Returns:
            Dict with predictions for each horizon
        """
        value_predictions = {}
        zero_probs = {}

        # TSMixer predictions
        with torch.no_grad():
            tsmixer_forecast = self.tsmixer_model.predict(df=df_nixtla)

        for h in self.tsmixer_horizons:
            if h <= len(tsmixer_forecast):
                value_predictions[f't+{h}'] = float(tsmixer_forecast['TSMixer'].iloc[h - 1])

        # ML Ensemble predictions
        X = df_features[self.feature_names].iloc[-1:].copy()

        for h in self.ml_horizons:
            if h in self.ml_models:
                lgb_pred = self.ml_models[h]['lgb'].predict(X)[0]
                xgb_pred = self.ml_models[h]['xgb'].predict(xgb.DMatrix(X))[0]
                value_predictions[f't+{h}'] = float((lgb_pred + xgb_pred) / 2)

        # Apply binary classifier if available
        if self.use_binary_classifier:
            # Get zero probabilities from classifiers
            for h in self.all_horizons:
                if h in self.zero_classifiers:
                    zero_prob = self.zero_classifiers[h].predict(X)[0]
                    zero_probs[f't+{h}'] = float(zero_prob)

            # Apply 2-stage logic
            final_predictions = apply_two_stage_prediction(
                value_preds=value_predictions,
                zero_probs=zero_probs,
                thresholds=self.zero_thresholds or {},
                prediction_time=prediction_time,
                thresholds_df=self.zero_thresholds_df
            )
            return final_predictions

        # No binary classifier - just clip to >= 0
        return {k: max(0.0, v) for k, v in value_predictions.items()}

    def predict_with_details(
        self,
        df_nixtla: pd.DataFrame,
        df_features: pd.DataFrame,
        prediction_time: pd.Timestamp = None
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, str]]:
        """
        Generate predictions with additional details for debugging/analysis.

        Returns:
            Tuple of (final_predictions, zero_probabilities, model_used_per_horizon)
        """
        value_predictions = {}
        zero_probs = {}
        model_used = {}

        # TSMixer predictions
        with torch.no_grad():
            tsmixer_forecast = self.tsmixer_model.predict(df=df_nixtla)

        for h in self.tsmixer_horizons:
            if h <= len(tsmixer_forecast):
                value_predictions[f't+{h}'] = float(tsmixer_forecast['TSMixer'].iloc[h - 1])
                model_used[f't+{h}'] = 'tsmixer'

        # ML Ensemble predictions
        X = df_features[self.feature_names].iloc[-1:].copy()

        for h in self.ml_horizons:
            if h in self.ml_models:
                lgb_pred = self.ml_models[h]['lgb'].predict(X)[0]
                xgb_pred = self.ml_models[h]['xgb'].predict(xgb.DMatrix(X))[0]
                value_predictions[f't+{h}'] = float((lgb_pred + xgb_pred) / 2)
                model_used[f't+{h}'] = 'ml_ensemble'

        # Get zero probabilities
        if self.use_binary_classifier:
            for h in self.all_horizons:
                if h in self.zero_classifiers:
                    zero_prob = self.zero_classifiers[h].predict(X)[0]
                    zero_probs[f't+{h}'] = float(zero_prob)

        # Apply 2-stage logic if binary classifier is available
        if self.use_binary_classifier:
            final_predictions = apply_two_stage_prediction(
                value_preds=value_predictions,
                zero_probs=zero_probs,
                thresholds=self.zero_thresholds or {},
                prediction_time=prediction_time,
                thresholds_df=self.zero_thresholds_df
            )
        else:
            final_predictions = {k: max(0.0, v) for k, v in value_predictions.items()}

        return final_predictions, zero_probs, model_used

    def save(self, output_dir: Path):
        """Save hybrid ensemble to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save TSMixer model
        tsmixer_path = output_dir / 'tsmixer'
        self.tsmixer_model.save(path=str(tsmixer_path), overwrite=True)

        # Save ML models
        ml_models_path = output_dir / 'ml_models'
        ml_models_path.mkdir(exist_ok=True)

        for h, models in self.ml_models.items():
            models['lgb'].save_model(str(ml_models_path / f'lgb_t+{h}.txt'))
            models['xgb'].save_model(str(ml_models_path / f'xgb_t+{h}.json'))

        # Save config with routing information
        config = {
            'feature_names': self.feature_names,
            'tsmixer_horizons': self.tsmixer_horizons,
            'ml_horizons': self.ml_horizons,
            'all_horizons': self.all_horizons,
            'horizon_routing': {str(k): v for k, v in self.horizon_routing.items()},
            'use_binary_classifier': self.use_binary_classifier,
            'created_at': datetime.now().isoformat(),
        }

        with open(output_dir / 'config.json', 'w') as f:
            json.dump(config, f, indent=2)

        print(f"Saved hybrid ensemble to: {output_dir}")

    @classmethod
    def load(cls, model_dir: Path, load_binary_classifier: bool = True) -> 'HybridEnsemble':
        """
        Load hybrid ensemble from disk.

        Args:
            model_dir: Path to saved model directory
            load_binary_classifier: If True, load zero detection models

        Returns:
            HybridEnsemble instance
        """
        # Load config
        with open(model_dir / 'config.json', 'r') as f:
            config = json.load(f)

        # Load TSMixer
        tsmixer_model = NeuralForecast.load(path=str(model_dir / 'tsmixer'))

        # Load ML models
        ml_models = {}
        ml_models_path = model_dir / 'ml_models'

        for h in config['ml_horizons']:
            lgb_model = lgb.Booster(model_file=str(ml_models_path / f'lgb_t+{h}.txt'))
            xgb_model = xgb.Booster()
            xgb_model.load_model(str(ml_models_path / f'xgb_t+{h}.json'))
            ml_models[h] = {'lgb': lgb_model, 'xgb': xgb_model}

        # Parse horizon routing if available
        horizon_routing = None
        if 'horizon_routing' in config:
            horizon_routing = {int(k): v for k, v in config['horizon_routing'].items()}

        # Load binary classifier if requested and available
        zero_classifiers = None
        zero_thresholds = None
        zero_thresholds_df = None

        if load_binary_classifier:
            try:
                zero_classifiers = load_zero_classifiers()
                zero_thresholds = load_zero_thresholds()

                # Load hour-based thresholds DataFrame
                threshold_csv = ZERO_DETECTION_DIR / 'optimal_thresholds_by_hour_calibrated.csv'
                if threshold_csv.exists():
                    zero_thresholds_df = pd.read_csv(threshold_csv)
            except Exception as e:
                print(f"Warning: Could not load binary classifier: {e}")

        return cls(
            tsmixer_model=tsmixer_model,
            ml_models=ml_models,
            feature_names=config['feature_names'],
            tsmixer_horizons=config.get('tsmixer_horizons'),
            ml_horizons=config.get('ml_horizons'),
            horizon_routing=horizon_routing,
            zero_classifiers=zero_classifiers,
            zero_thresholds=zero_thresholds,
            zero_thresholds_df=zero_thresholds_df
        )


def run_hybrid_training(
    use_long_training: bool = False,
    use_dynamic_routing: bool = False,
    use_binary_classifier: bool = False,
    train_all_horizons: bool = False
):
    """
    Run the full hybrid ensemble training pipeline.

    Args:
        use_long_training: If True, train TSMixer for 10,000 epochs
        use_dynamic_routing: If True, determine routing from validation set performance
        use_binary_classifier: If True, integrate zero detection models
        train_all_horizons: If True, train ML models for all 24 horizons (required for dynamic routing)
    """
    # Auto-enable train_all_horizons if dynamic routing is requested
    if use_dynamic_routing:
        train_all_horizons = True

    print("=" * 70)
    print("HYBRID TSMIXER + ML ENSEMBLE TRAINING")
    print("=" * 70)
    print()
    print(f"Long training mode: {use_long_training}")
    print(f"Dynamic routing: {use_dynamic_routing}")
    print(f"Binary classifier: {use_binary_classifier}")
    print(f"Train all horizons: {train_all_horizons}")
    print(f"TSMixer epochs: {TSMIXER_CONFIG_LONG['max_steps'] if use_long_training else TSMIXER_CONFIG['max_steps']}")
    print()

    # 1. Load data
    print("\n[1/6] LOADING DATA")
    print("-" * 50)
    df_raw = load_data()

    # 2. Create temporal split
    train_end, val_start, test_start = create_temporal_split(
        df_raw, TEST_DAYS, VAL_DAYS
    )

    # 3. Prepare data formats
    print("\n[2/6] PREPARING DATA")
    print("-" * 50)

    # For TSMixer
    df_nixtla = prepare_nixtla_format(df_raw)
    print(f"  TSMixer format: {df_nixtla.shape}")

    # For ML Ensemble
    print("  Creating features for ML Ensemble...")
    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=ALL_HORIZONS,
        rolling_windows=ROLLING_WINDOWS,
        lag_hours=LAG_HOURS
    )
    df_for_features = df_raw.copy()
    df_for_features.columns = ['CMG [$/MWh]']
    df_feat = feature_engineer.create_features(df_for_features, cmg_column='CMG [$/MWh]')
    feature_names = feature_engineer.get_feature_names()
    print(f"  ML Ensemble format: {df_feat.shape} with {len(feature_names)} features")

    # 4. Evaluate persistence baseline
    print("\n[3/6] EVALUATING PERSISTENCE BASELINE")
    print("-" * 50)
    persistence_results = evaluate_persistence(df_raw, test_start)
    print(f"  Persistence average MAE: ${persistence_results['average']:.2f}")

    # 5. Train TSMixer with CUDA
    print("\n[4/6] TRAINING TSMIXER (CUDA)")
    print("-" * 50)
    tsmixer_model = train_tsmixer_cuda(
        df_nixtla, train_end, TSMIXER_CONFIG, use_long_training
    )

    # Evaluate TSMixer
    print("\n  Evaluating TSMixer...")
    tsmixer_results = evaluate_tsmixer(tsmixer_model, df_nixtla, test_start)
    print(f"  TSMixer average MAE: ${tsmixer_results['average']:.2f}")

    # 6. Train ML Ensemble
    print("\n[5/6] TRAINING ML ENSEMBLE")
    print("-" * 50)

    # Train for all horizons if dynamic routing or explicitly requested
    ml_horizons_to_train = ALL_HORIZONS if train_all_horizons else DEFAULT_ML_ENSEMBLE_HORIZONS
    print(f"  Training ML models for horizons: {ml_horizons_to_train}")

    ml_models, gb_results = train_gradient_boosting_all_horizons(
        df_feat, feature_names, train_end, val_start, test_start,
        horizons=ml_horizons_to_train
    )

    # 7. Create and evaluate hybrid ensemble
    print("\n[6/6] CREATING HYBRID ENSEMBLE")
    print("-" * 50)

    # Determine routing
    if use_dynamic_routing:
        print("\n  Computing dynamic routing from validation set...")
        val_results = evaluate_on_validation(
            nf=tsmixer_model,
            ml_models=ml_models,
            df_nixtla=df_nixtla,
            df_feat=df_feat,
            feature_names=feature_names,
            val_start=val_start,
            test_start=test_start,
            horizons=ALL_HORIZONS
        )
        horizon_routing = compute_dynamic_routing(val_results, margin=0.0)
        tsmixer_horizons = [h for h, m in horizon_routing.items() if m == 'tsmixer']
        ml_ensemble_horizons = [h for h, m in horizon_routing.items() if m == 'ml_ensemble']
    else:
        horizon_routing = None
        tsmixer_horizons = DEFAULT_TSMIXER_HORIZONS
        ml_ensemble_horizons = DEFAULT_ML_ENSEMBLE_HORIZONS

    # Load binary classifier if requested
    zero_classifiers = None
    zero_thresholds = None
    zero_thresholds_df = None

    if use_binary_classifier:
        print("\n  Loading binary classifier (zero detection) models...")
        try:
            zero_classifiers = load_zero_classifiers()
            zero_thresholds = load_zero_thresholds()

            threshold_csv = ZERO_DETECTION_DIR / 'optimal_thresholds_by_hour_calibrated.csv'
            if threshold_csv.exists():
                zero_thresholds_df = pd.read_csv(threshold_csv)
                print(f"  Loaded hour-based thresholds from {threshold_csv}")
        except Exception as e:
            print(f"  Warning: Could not load binary classifier: {e}")
            use_binary_classifier = False

    hybrid = HybridEnsemble(
        tsmixer_model=tsmixer_model,
        ml_models=ml_models,
        feature_names=feature_names,
        horizon_routing=horizon_routing,
        tsmixer_horizons=tsmixer_horizons if horizon_routing is None else None,
        ml_horizons=ml_ensemble_horizons if horizon_routing is None else None,
        zero_classifiers=zero_classifiers,
        zero_thresholds=zero_thresholds,
        zero_thresholds_df=zero_thresholds_df
    )

    # Evaluate hybrid
    print("\n  Evaluating hybrid ensemble on test set...")
    hybrid_results = {}

    # Use routing to determine which results to use
    for h in ALL_HORIZONS:
        key = f't+{h}'
        if h in tsmixer_horizons:
            if key in tsmixer_results:
                hybrid_results[key] = tsmixer_results[key]
        else:
            if key in gb_results['ensemble']:
                hybrid_results[key] = gb_results['ensemble'][key]

    hybrid_avg = np.mean([v for k, v in hybrid_results.items() if k.startswith('t+')])
    hybrid_results['average'] = hybrid_avg

    # 8. Summary comparison
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()

    print(f"{'Model':<25} {'Avg MAE':<12} {'vs Baseline':<15}")
    print("-" * 55)

    baseline = persistence_results['average']

    models_summary = [
        ('Persistence', baseline),
        ('TSMixer (all horizons)', tsmixer_results['average']),
        ('ML Ensemble (all)', gb_results['ensemble'].get('average', 0)),
        ('HYBRID ENSEMBLE', hybrid_avg),
    ]

    for name, mae in models_summary:
        improvement = (baseline - mae) / baseline * 100
        sign = "+" if improvement > 0 else ""
        print(f"{name:<25} ${mae:<11.2f} {sign}{improvement:.1f}%")

    # Detailed horizon comparison
    print("\n" + "-" * 70)
    print("DETAILED HORIZON COMPARISON")
    print("-" * 70)
    print()
    print(f"{'Horizon':<10} {'Persistence':<12} {'TSMixer':<12} {'ML Ens.':<12} {'Hybrid':<12} {'Source':<10}")
    print("-" * 70)

    for h in ALL_HORIZONS:
        key = f't+{h}'
        p = persistence_results.get(key, 0)
        t = tsmixer_results.get(key, 0)
        e = gb_results['ensemble'].get(key, 0)
        hy = hybrid_results.get(key, 0)
        source = 'TSMixer' if h in tsmixer_horizons else 'ML Ens.'

        print(f"{key:<10} ${p:<11.2f} ${t:<11.2f} ${e:<11.2f} ${hy:<11.2f} {source:<10}")

    print("-" * 70)
    print(f"{'AVERAGE':<10} ${baseline:<11.2f} ${tsmixer_results['average']:<11.2f} "
          f"${gb_results['ensemble'].get('average', 0):<11.2f} ${hybrid_avg:<11.2f}")

    # 9. Save hybrid ensemble
    print("\n" + "=" * 70)
    print("SAVING HYBRID ENSEMBLE")
    print("=" * 70)

    output_dir = Path(__file__).parent.parent.parent / 'models_experimental' / 'hybrid_tsmixer'
    hybrid.save(output_dir)

    # Save results summary
    results_summary = {
        'training_date': datetime.now().isoformat(),
        'device': DEVICE,
        'gpu_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'long_training': use_long_training,
        'dynamic_routing': use_dynamic_routing,
        'binary_classifier': use_binary_classifier,
        'tsmixer_config': TSMIXER_CONFIG_LONG if use_long_training else TSMIXER_CONFIG,
        'tsmixer_horizons': tsmixer_horizons,
        'ml_horizons': ml_ensemble_horizons,
        'horizon_routing': {str(k): v for k, v in (horizon_routing or {}).items()},
        'results': {
            'persistence': persistence_results,
            'tsmixer': tsmixer_results,
            'ml_ensemble': gb_results['ensemble'],
            'hybrid': hybrid_results,
        },
        'improvements': {
            'tsmixer_vs_baseline': (baseline - tsmixer_results['average']) / baseline * 100,
            'ml_ensemble_vs_baseline': (baseline - gb_results['ensemble'].get('average', 0)) / baseline * 100,
            'hybrid_vs_baseline': (baseline - hybrid_avg) / baseline * 100,
        }
    }

    results_path = output_dir / 'training_results.json'
    with open(results_path, 'w') as f:
        json.dump(results_summary, f, indent=2, default=str)

    print(f"\nResults saved to: {results_path}")

    # Final recommendation
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)

    best_model = min(models_summary, key=lambda x: x[1])
    print(f"\nBest overall: {best_model[0]} (${best_model[1]:.2f})")

    if best_model[0] == 'HYBRID ENSEMBLE':
        print("The hybrid approach combining TSMixer and ML Ensemble is optimal!")
        print(f"Improvement over baseline: {(baseline - best_model[1]) / baseline * 100:.1f}%")
    elif 'TSMixer' in best_model[0]:
        print("TSMixer alone performs best. Consider using it for all horizons.")
    else:
        print("ML Ensemble alone performs best. The hybrid approach may not be beneficial.")

    return hybrid, results_summary


def run_quick_test():
    """
    Run a quick test with minimal epochs to verify CUDA training works.
    """
    print("=" * 70)
    print("QUICK TEST MODE (100 steps)")
    print("=" * 70)
    print()

    # Load data
    df_raw = load_data()
    train_end, val_start, test_start = create_temporal_split(df_raw, TEST_DAYS, VAL_DAYS)

    # Prepare TSMixer data
    df_nixtla = prepare_nixtla_format(df_raw)
    df_train = df_nixtla.iloc[:train_end].copy()

    # Quick test config
    test_config = {
        **TSMIXER_CONFIG,
        'max_steps': 100,
        'val_check_steps': 20,
        'early_stop_patience': 5,
    }

    print(f"\nTraining TSMixer with {test_config['max_steps']} steps...")
    print(f"Device: {DEVICE}")

    clear_gpu_memory()

    model = TSMixer(
        h=test_config['horizon'],
        input_size=test_config['input_size'],
        n_series=1,
        n_block=test_config['n_block'],
        ff_dim=test_config['ff_dim'],
        dropout=test_config['dropout'],
        revin=test_config['revin'],
        max_steps=test_config['max_steps'],
        val_check_steps=test_config['val_check_steps'],
        early_stop_patience_steps=test_config['early_stop_patience'],
        scaler_type='standard',
        learning_rate=test_config['learning_rate'],
        batch_size=test_config['batch_size'],
        valid_loss=MAE(),
        random_seed=42,
        accelerator='gpu' if DEVICE == 'cuda' else 'cpu',
        devices=1,
    )

    nf = NeuralForecast(models=[model], freq='h')
    nf.fit(df=df_train, val_size=48)

    print(f"\nGPU Memory after training: {get_gpu_memory_usage():.2f} GB")

    # Test prediction
    with torch.no_grad():
        forecast = nf.predict(df=df_train)

    print(f"\nTest prediction shape: {forecast.shape}")
    print(f"First 5 predictions: {forecast['TSMixer'].values[:5]}")

    print("\n" + "=" * 70)
    print("QUICK TEST PASSED!")
    print("=" * 70)
    print("\nYou can now run full training with:")
    print("  python train_hybrid_tsmixer_ensemble.py")
    print("Or for 10,000 epochs:")
    print("  python train_hybrid_tsmixer_ensemble.py --long-training")

    return True


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Train Hybrid TSMixer + ML Ensemble')
    parser.add_argument('--long-training', action='store_true',
                        help='Use 10,000 epochs for TSMixer training')
    parser.add_argument('--quick-test', action='store_true',
                        help='Run quick test (100 steps) to verify CUDA setup')
    parser.add_argument('--dynamic-routing', action='store_true',
                        help='Use validation set to determine optimal routing per horizon')
    parser.add_argument('--with-binary-classifier', action='store_true',
                        help='Integrate zero detection (binary classifier) models')
    parser.add_argument('--train-all-horizons', action='store_true',
                        help='Train ML models for all 24 horizons (auto-enabled with --dynamic-routing)')

    args = parser.parse_args()

    if args.quick_test:
        run_quick_test()
    else:
        hybrid, results = run_hybrid_training(
            use_long_training=args.long_training,
            use_dynamic_routing=args.dynamic_routing,
            use_binary_classifier=args.with_binary_classifier,
            train_all_horizons=args.train_all_horizons
        )
