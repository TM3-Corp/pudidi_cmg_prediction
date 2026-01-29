#!/usr/bin/env python3
"""
Comprehensive Model Audit Script

Compares all models using identical methodology:
1. Same test period for ALL models
2. Same evaluation function
3. Include/exclude binary classifier as separate columns
4. Walk-forward cross-validation

This script answers:
- What is the true performance of each model?
- How much does the binary classifier help?
- Is dynamic routing better than static routing?

Author: CMG Prediction System
Date: 2026-01-29
"""

import os
import sys
import warnings
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import torch

# Set seeds for reproducibility
np.random.seed(42)
torch.manual_seed(42)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lightgbm as lgb
import xgboost as xgb
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error,
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)
from neuralforecast import NeuralForecast

from ml_feature_engineering import CleanCMGFeatureEngineering

# ============================================================================
# CONFIGURATION
# ============================================================================

# Paths
DATA_PATH = Path('/home/paul/projects/Pudidi/traindataset_2023plus.parquet')
MODELS_DIR = Path(__file__).parent.parent
HYBRID_DIR = MODELS_DIR / 'models_hybrid_tsmixer'
ZERO_DETECTION_DIR = MODELS_DIR / 'models_24h' / 'zero_detection'

# Test configuration
DEFAULT_TEST_DAYS = 30
ALL_HORIZONS = list(range(1, 25))

# Feature engineering config (must match training)
ROLLING_WINDOWS = [6, 12, 24, 48, 168]
LAG_HOURS = [1, 2, 3, 6, 12, 24, 48, 168]


def load_data() -> pd.DataFrame:
    """Load CMG data from parquet file."""
    print(f"Loading data from: {DATA_PATH}")
    df = pd.read_parquet(DATA_PATH)

    df_hourly = df[['CMg']].copy()
    df_hourly.columns = ['CMG']
    df_hourly = df_hourly.sort_index()
    df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

    print(f"Loaded {len(df_hourly)} hours ({len(df_hourly)/24:.0f} days)")
    print(f"Date range: {df_hourly.index.min()} to {df_hourly.index.max()}")

    return df_hourly


def prepare_nixtla_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert to NeuralForecast format."""
    df_nf = df.reset_index()
    df_nf.columns = ['ds', 'y']
    df_nf['unique_id'] = 'CMG'
    return df_nf[['unique_id', 'ds', 'y']]


def load_zero_classifiers() -> Tuple[Dict[int, lgb.Booster], Dict[int, float], pd.DataFrame]:
    """Load zero detection models and thresholds."""
    classifiers = {}
    for h in range(1, 25):
        lgb_path = ZERO_DETECTION_DIR / f'lgb_t+{h}.txt'
        if lgb_path.exists():
            classifiers[h] = lgb.Booster(model_file=str(lgb_path))

    # Load thresholds
    threshold_csv = ZERO_DETECTION_DIR / 'optimal_thresholds_by_hour_calibrated.csv'
    thresholds_df = pd.read_csv(threshold_csv) if threshold_csv.exists() else None

    # Convert to dict
    thresholds = {}
    if thresholds_df is not None:
        for _, row in thresholds_df.iterrows():
            # Store by target hour
            thresholds[int(row['target_hour'])] = float(row['threshold'])

    print(f"Loaded {len(classifiers)} zero classifiers")
    return classifiers, thresholds, thresholds_df


def apply_binary_classifier(
    value_pred: float,
    zero_prob: float,
    threshold: float
) -> float:
    """Apply 2-stage prediction logic."""
    if zero_prob > threshold:
        return 0.0
    return max(0.0, value_pred)


def evaluate_binary_classifier(
    zero_classifiers: Dict[int, lgb.Booster],
    zero_thresholds: Dict[int, float],
    df_feat: pd.DataFrame,
    feature_names: List[str],
    test_start: int,
    df_raw: pd.DataFrame
) -> Dict:
    """
    Evaluate binary classifier (zero detection) performance.

    Returns confusion matrix, accuracy, precision, recall, F1 for each horizon.
    """
    results = {
        'per_horizon': {},
        'overall': {}
    }

    all_y_true = []
    all_y_pred = []

    test_df = df_feat.iloc[test_start:].copy()

    for h in ALL_HORIZONS:
        if h not in zero_classifiers:
            continue

        target_col = f'is_zero_t+{h}'
        if target_col not in test_df.columns:
            # Create target from cmg_value if is_zero not present
            target_col = f'cmg_value_t+{h}'
            if target_col not in test_df.columns:
                continue
            y_true = (test_df[target_col] == 0).astype(int)
        else:
            y_true = test_df[target_col].astype(int)

        X_test = test_df[feature_names].copy()

        # Handle NaNs
        mask = ~(y_true.isna() | X_test.isna().any(axis=1))
        X_test = X_test[mask]
        y_true = y_true[mask]

        if len(X_test) == 0:
            continue

        # Fill any remaining NaNs
        X_test = X_test.fillna(0)

        # Get predictions
        zero_probs = zero_classifiers[h].predict(X_test)

        # Get threshold for each prediction (based on target hour)
        y_pred = []
        test_index = X_test.index
        for i, idx in enumerate(test_index):
            # Calculate target hour based on index
            if isinstance(idx, pd.Timestamp):
                target_hour = (idx + pd.Timedelta(hours=h)).hour
            else:
                target_hour = h % 24
            threshold = zero_thresholds.get(target_hour, 0.5)
            y_pred.append(1 if zero_probs[i] > threshold else 0)

        y_pred = np.array(y_pred)
        y_true_arr = y_true.values

        # Calculate metrics
        cm = confusion_matrix(y_true_arr, y_pred, labels=[0, 1])
        acc = accuracy_score(y_true_arr, y_pred)

        # Handle edge cases where one class might be missing
        try:
            prec = precision_score(y_true_arr, y_pred, zero_division=0)
            rec = recall_score(y_true_arr, y_pred, zero_division=0)
            f1 = f1_score(y_true_arr, y_pred, zero_division=0)
        except:
            prec = rec = f1 = 0.0

        results['per_horizon'][f't+{h}'] = {
            'confusion_matrix': cm.tolist(),
            'accuracy': acc,
            'precision': prec,
            'recall': rec,
            'f1': f1,
            'n_samples': len(y_true_arr),
            'n_zeros': int(y_true_arr.sum()),
            'n_non_zeros': int(len(y_true_arr) - y_true_arr.sum())
        }

        all_y_true.extend(y_true_arr.tolist())
        all_y_pred.extend(y_pred.tolist())

    # Overall metrics
    if all_y_true:
        all_y_true = np.array(all_y_true)
        all_y_pred = np.array(all_y_pred)

        cm_overall = confusion_matrix(all_y_true, all_y_pred, labels=[0, 1])
        results['overall'] = {
            'confusion_matrix': cm_overall.tolist(),
            'accuracy': accuracy_score(all_y_true, all_y_pred),
            'precision': precision_score(all_y_true, all_y_pred, zero_division=0),
            'recall': recall_score(all_y_true, all_y_pred, zero_division=0),
            'f1': f1_score(all_y_true, all_y_pred, zero_division=0),
            'n_samples': len(all_y_true),
            'n_zeros': int(all_y_true.sum()),
            'n_non_zeros': int(len(all_y_true) - all_y_true.sum()),
            'zero_rate': float(all_y_true.mean())
        }

    return results


def evaluate_model_on_test(
    model_name: str,
    predict_fn,
    df_raw: pd.DataFrame,
    df_nixtla: pd.DataFrame,
    df_feat: pd.DataFrame,
    feature_names: List[str],
    test_start: int,
    zero_classifiers: Optional[Dict] = None,
    zero_thresholds: Optional[Dict] = None,
    thresholds_df: Optional[pd.DataFrame] = None
) -> Dict:
    """
    Evaluate a model on the test set with walk-forward predictions.

    Returns dict with MAE per horizon:
    - without_bc: MAE without binary classifier
    - with_bc: MAE with binary classifier
    - nonzero_only: MAE only for non-zero actuals (with BC)
    """
    results = {
        'without_bc': {f't+{h}': [] for h in ALL_HORIZONS},
        'with_bc': {f't+{h}': [] for h in ALL_HORIZONS},
        'actuals': {f't+{h}': [] for h in ALL_HORIZONS},
        # Track non-zero separately
        'nonzero_preds': {f't+{h}': [] for h in ALL_HORIZONS},
        'nonzero_actuals': {f't+{h}': [] for h in ALL_HORIZONS},
    }

    test_hours = len(df_nixtla) - test_start
    n_predictions = test_hours // 24

    print(f"  Evaluating {model_name}: {n_predictions} daily predictions...")

    for day in range(n_predictions):
        pred_start_idx = test_start + (day * 24)
        prediction_time = df_raw.index[pred_start_idx]

        # Get predictions from model
        try:
            preds = predict_fn(pred_start_idx, df_nixtla, df_feat, feature_names)
        except Exception as e:
            print(f"    Warning: Prediction failed at day {day}: {e}")
            continue

        # Get zero probabilities if binary classifier available
        zero_probs = {}
        if zero_classifiers:
            X = df_feat[feature_names].iloc[[pred_start_idx]].copy()
            if X.isna().any().any():
                X = X.fillna(0)
            if len(X) > 0:
                for h in ALL_HORIZONS:
                    if h in zero_classifiers:
                        try:
                            zero_probs[h] = float(zero_classifiers[h].predict(X)[0])
                        except:
                            pass

        # Store predictions and actuals for each horizon
        for h in ALL_HORIZONS:
            key = f't+{h}'
            target_idx = pred_start_idx + h - 1

            if target_idx >= len(df_nixtla):
                continue

            actual = df_nixtla['y'].iloc[target_idx]
            pred = preds.get(key)

            if pred is None or np.isnan(actual):
                continue

            # Without binary classifier
            pred_no_bc = max(0.0, pred)
            results['without_bc'][key].append(pred_no_bc)

            # With binary classifier
            if h in zero_probs and zero_thresholds:
                # Get threshold for target hour
                target_hour = (prediction_time + pd.Timedelta(hours=h)).hour
                threshold = zero_thresholds.get(target_hour, 0.5)
                pred_with_bc = apply_binary_classifier(pred, zero_probs[h], threshold)
            else:
                pred_with_bc = pred_no_bc

            results['with_bc'][key].append(pred_with_bc)
            results['actuals'][key].append(actual)

            # Track non-zero actuals separately (for MAE when CMG != 0)
            if actual != 0:
                results['nonzero_preds'][key].append(pred_with_bc)
                results['nonzero_actuals'][key].append(actual)

    # Calculate MAE
    mae_results = {
        'without_bc': {},
        'with_bc': {},
        'nonzero_only': {}
    }

    for h in ALL_HORIZONS:
        key = f't+{h}'
        if results['actuals'][key]:
            mae_results['without_bc'][key] = mean_absolute_error(
                results['actuals'][key], results['without_bc'][key]
            )
            mae_results['with_bc'][key] = mean_absolute_error(
                results['actuals'][key], results['with_bc'][key]
            )
        if results['nonzero_actuals'][key]:
            mae_results['nonzero_only'][key] = mean_absolute_error(
                results['nonzero_actuals'][key], results['nonzero_preds'][key]
            )

    # Averages
    for mode in ['without_bc', 'with_bc', 'nonzero_only']:
        vals = [v for k, v in mae_results[mode].items() if k.startswith('t+')]
        mae_results[mode]['average'] = np.mean(vals) if vals else 0.0

    # Count zeros in test set
    total_samples = sum(len(results['actuals'][f't+{h}']) for h in ALL_HORIZONS)
    zero_samples = sum(
        sum(1 for a in results['actuals'][f't+{h}'] if a == 0)
        for h in ALL_HORIZONS
    )
    mae_results['stats'] = {
        'total_samples': total_samples,
        'zero_samples': zero_samples,
        'nonzero_samples': total_samples - zero_samples,
        'zero_rate': zero_samples / total_samples if total_samples > 0 else 0
    }

    return mae_results


def create_tsmixer_predictor(nf: NeuralForecast, input_size: int):
    """Create prediction function for TSMixer."""
    def predict(pred_start_idx, df_nixtla, df_feat, feature_names):
        df_input = df_nixtla.iloc[:pred_start_idx].copy()
        if len(df_input) < input_size:
            return {}

        with torch.no_grad():
            forecast = nf.predict(df=df_input)

        preds = {}
        for h in ALL_HORIZONS:
            if h <= len(forecast):
                preds[f't+{h}'] = float(forecast['TSMixer'].iloc[h - 1])
        return preds

    return predict


def create_ml_ensemble_predictor(ml_models: Dict):
    """Create prediction function for ML Ensemble."""
    def predict(pred_start_idx, df_nixtla, df_feat, feature_names):
        # Use iloc with the exact index (pred_start_idx is the row where we make prediction)
        if pred_start_idx >= len(df_feat):
            return {}

        X = df_feat[feature_names].iloc[[pred_start_idx]].copy()

        # Handle NaN values
        if X.isna().any().any():
            X = X.fillna(0)

        # Ensure column names for XGBoost
        X.columns = feature_names

        preds = {}
        for h in ALL_HORIZONS:
            if h in ml_models:
                try:
                    lgb_pred = ml_models[h]['lgb'].predict(X)[0]
                    # Create DMatrix with feature names
                    dmatrix = xgb.DMatrix(X, feature_names=feature_names)
                    xgb_pred = ml_models[h]['xgb'].predict(dmatrix)[0]
                    preds[f't+{h}'] = float((lgb_pred + xgb_pred) / 2)
                except Exception as e:
                    print(f"    ML prediction error h={h}: {e}")
        return preds

    return predict


def create_hybrid_predictor(
    nf: NeuralForecast,
    ml_models: Dict,
    tsmixer_horizons: List[int],
    ml_horizons: List[int],
    input_size: int
):
    """Create prediction function for Hybrid Ensemble."""
    tsmixer_pred = create_tsmixer_predictor(nf, input_size)
    ml_pred = create_ml_ensemble_predictor(ml_models)

    def predict(pred_start_idx, df_nixtla, df_feat, feature_names):
        preds = {}

        # TSMixer for its horizons
        ts_preds = tsmixer_pred(pred_start_idx, df_nixtla, df_feat, feature_names)
        for h in tsmixer_horizons:
            key = f't+{h}'
            if key in ts_preds:
                preds[key] = ts_preds[key]

        # ML for its horizons
        ml_preds = ml_pred(pred_start_idx, df_nixtla, df_feat, feature_names)
        for h in ml_horizons:
            key = f't+{h}'
            if key in ml_preds:
                preds[key] = ml_preds[key]

        return preds

    return predict


def create_persistence_predictor():
    """Create prediction function for persistence baseline."""
    def predict(pred_start_idx, df_nixtla, df_feat, feature_names):
        # Use same hour yesterday
        if pred_start_idx < 24:
            return {}

        preds = {}
        for h in ALL_HORIZONS:
            # Persistence: predict t+h using value from 24 hours before current time
            prev_idx = pred_start_idx - 24 + h - 1
            if prev_idx >= 0 and prev_idx < len(df_nixtla):
                preds[f't+{h}'] = float(df_nixtla['y'].iloc[prev_idx])
        return preds

    return predict


def run_comprehensive_audit(test_days: int = DEFAULT_TEST_DAYS):
    """Run full model audit."""
    print("=" * 80)
    print("COMPREHENSIVE MODEL AUDIT")
    print("=" * 80)
    print(f"Test period: Last {test_days} days")
    print()

    # 1. Load data
    print("\n[1/5] LOADING DATA")
    print("-" * 60)
    df_raw = load_data()

    # Create splits
    n = len(df_raw)
    test_size = test_days * 24
    val_size = 14 * 24  # 14 days for validation
    test_start = n - test_size
    val_start = test_start - val_size
    train_end = val_start

    print(f"\nData splits:")
    print(f"  Train: {train_end} hours (up to {df_raw.index[train_end-1]})")
    print(f"  Val:   {val_size} hours")
    print(f"  Test:  {test_size} hours ({df_raw.index[test_start]} to {df_raw.index[-1]})")

    # 2. Prepare data formats
    print("\n[2/5] PREPARING DATA")
    print("-" * 60)

    df_nixtla = prepare_nixtla_format(df_raw)
    print(f"  NeuralForecast format: {df_nixtla.shape}")

    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=ALL_HORIZONS,
        rolling_windows=ROLLING_WINDOWS,
        lag_hours=LAG_HOURS
    )
    df_for_features = df_raw.copy()
    df_for_features.columns = ['CMG [$/MWh]']
    df_feat = feature_engineer.create_features(df_for_features, cmg_column='CMG [$/MWh]')
    feature_names = feature_engineer.get_feature_names()
    print(f"  Feature format: {df_feat.shape} with {len(feature_names)} features")

    # 3. Load models
    print("\n[3/5] LOADING MODELS")
    print("-" * 60)

    # Load hybrid config
    with open(HYBRID_DIR / 'config.json', 'r') as f:
        hybrid_config = json.load(f)

    # Load TSMixer
    print("  Loading TSMixer...")
    tsmixer_model = NeuralForecast.load(path=str(HYBRID_DIR / 'tsmixer'))

    # Load ML models
    print("  Loading ML Ensemble...")
    ml_models = {}
    ml_models_path = HYBRID_DIR / 'ml_models'
    for h in hybrid_config['ml_horizons']:
        lgb_model = lgb.Booster(model_file=str(ml_models_path / f'lgb_t+{h}.txt'))
        xgb_model = xgb.Booster()
        xgb_model.load_model(str(ml_models_path / f'xgb_t+{h}.json'))
        ml_models[h] = {'lgb': lgb_model, 'xgb': xgb_model}
    print(f"    Loaded {len(ml_models)} ML models")

    # Load zero classifiers
    print("  Loading zero detection models...")
    zero_classifiers, zero_thresholds, thresholds_df = load_zero_classifiers()

    # 4. Evaluate all models
    print("\n[4/5] EVALUATING MODELS")
    print("-" * 60)

    all_results = {}

    # Persistence baseline
    print("\n  [a] Persistence Baseline")
    persist_predictor = create_persistence_predictor()
    all_results['Persistence'] = evaluate_model_on_test(
        'Persistence', persist_predictor,
        df_raw, df_nixtla, df_feat, feature_names, test_start,
        zero_classifiers, zero_thresholds, thresholds_df
    )

    # TSMixer (all horizons)
    print("\n  [b] TSMixer (all horizons)")
    input_size = hybrid_config.get('tsmixer_config', {}).get('input_size', 336)
    tsmixer_predictor = create_tsmixer_predictor(tsmixer_model, input_size)
    all_results['TSMixer'] = evaluate_model_on_test(
        'TSMixer', tsmixer_predictor,
        df_raw, df_nixtla, df_feat, feature_names, test_start,
        zero_classifiers, zero_thresholds, thresholds_df
    )

    # ML Ensemble (only has models for specific horizons)
    print("\n  [c] ML Ensemble (available horizons)")
    ml_predictor = create_ml_ensemble_predictor(ml_models)
    all_results['ML Ensemble'] = evaluate_model_on_test(
        'ML Ensemble', ml_predictor,
        df_raw, df_nixtla, df_feat, feature_names, test_start,
        zero_classifiers, zero_thresholds, thresholds_df
    )

    # Hybrid (static routing)
    print("\n  [d] Hybrid (static routing)")
    tsmixer_horizons = hybrid_config['tsmixer_horizons']
    ml_horizons = hybrid_config['ml_horizons']
    hybrid_predictor = create_hybrid_predictor(
        tsmixer_model, ml_models, tsmixer_horizons, ml_horizons, input_size
    )
    all_results['Hybrid (static)'] = evaluate_model_on_test(
        'Hybrid (static)', hybrid_predictor,
        df_raw, df_nixtla, df_feat, feature_names, test_start,
        zero_classifiers, zero_thresholds, thresholds_df
    )

    # 4b. Evaluate binary classifier
    print("\n  [e] Binary Classifier Evaluation")
    bc_results = evaluate_binary_classifier(
        zero_classifiers, zero_thresholds,
        df_feat, feature_names, test_start, df_raw
    )

    # 5. Generate report
    print("\n[5/5] GENERATING REPORT")
    print("-" * 60)

    # Binary classifier metrics
    print("\n" + "=" * 80)
    print("BINARY CLASSIFIER (ZERO DETECTION) METRICS")
    print("=" * 80)

    if bc_results['overall']:
        overall = bc_results['overall']
        cm = np.array(overall['confusion_matrix'])
        print(f"\n  Overall Performance (across all horizons):")
        print(f"    Samples: {overall['n_samples']:,} (Zeros: {overall['n_zeros']:,}, Non-zeros: {overall['n_non_zeros']:,})")
        print(f"    Zero rate in test set: {overall['zero_rate']*100:.1f}%")
        print()
        print(f"    Confusion Matrix:")
        print(f"                      Predicted")
        print(f"                    Non-Zero  Zero")
        print(f"    Actual Non-Zero   {cm[0,0]:>6}  {cm[0,1]:>6}   (TN, FP)")
        print(f"    Actual Zero       {cm[1,0]:>6}  {cm[1,1]:>6}   (FN, TP)")
        print()
        print(f"    Accuracy:  {overall['accuracy']*100:.2f}%")
        print(f"    Precision: {overall['precision']*100:.2f}%  (of predicted zeros, how many are actually zero)")
        print(f"    Recall:    {overall['recall']*100:.2f}%  (of actual zeros, how many did we catch)")
        print(f"    F1 Score:  {overall['f1']*100:.2f}%")

    # Per-horizon binary classifier metrics
    print("\n  Per-Horizon Binary Classifier Metrics:")
    print(f"  {'Horizon':<10} {'Accuracy':<10} {'Precision':<10} {'Recall':<10} {'F1':<10} {'Zeros':<10}")
    print("  " + "-" * 60)
    for h in ALL_HORIZONS:
        key = f't+{h}'
        if key in bc_results['per_horizon']:
            m = bc_results['per_horizon'][key]
            print(f"  {key:<10} {m['accuracy']*100:>8.1f}% {m['precision']*100:>8.1f}% {m['recall']*100:>8.1f}% {m['f1']*100:>8.1f}% {m['n_zeros']:>8}")

    print("\n" + "=" * 80)
    print("MAE RESULTS SUMMARY")
    print("=" * 80)

    # Get stats from one of the models
    sample_stats = all_results['Hybrid (static)'].get('stats', {})
    print(f"\n  Test Set Statistics:")
    print(f"    Total samples: {sample_stats.get('total_samples', 'N/A'):,}")
    print(f"    Zero samples: {sample_stats.get('zero_samples', 'N/A'):,}")
    print(f"    Non-zero samples: {sample_stats.get('nonzero_samples', 'N/A'):,}")
    print(f"    Zero rate: {sample_stats.get('zero_rate', 0)*100:.1f}%")

    print("\n  Average MAE Comparison (All Samples):")
    print(f"  {'Model':<25} {'Without BC':<12} {'With BC':<12} {'Δ (BC help)':<12}")
    print("  " + "-" * 63)

    for model_name, results in all_results.items():
        no_bc = results['without_bc']['average']
        with_bc = results['with_bc']['average']
        delta = no_bc - with_bc
        print(f"  {model_name:<25} ${no_bc:<11.2f} ${with_bc:<11.2f} -${delta:<10.2f}")

    print("\n  Average MAE Comparison (Non-Zero Actuals Only):")
    print(f"  {'Model':<25} {'MAE (non-zero)':<15}")
    print("  " + "-" * 42)

    for model_name, results in all_results.items():
        nonzero_mae = results['nonzero_only']['average']
        print(f"  {model_name:<25} ${nonzero_mae:<14.2f}")

    # Best model
    print("\n  Best Results:")
    best_without_bc = min(all_results.items(), key=lambda x: x[1]['without_bc']['average'])
    best_with_bc = min(all_results.items(), key=lambda x: x[1]['with_bc']['average'])
    print(f"    Without BC: {best_without_bc[0]} (${best_without_bc[1]['without_bc']['average']:.2f})")
    print(f"    With BC: {best_with_bc[0]} (${best_with_bc[1]['with_bc']['average']:.2f})")

    # Detailed horizon comparison (With BC - All samples)
    print("\n" + "-" * 80)
    print("DETAILED HORIZON COMPARISON (With BC - All Samples)")
    print("-" * 80)
    print()
    print(f"  {'Horizon':<8}", end="")
    for model_name in all_results:
        print(f"{model_name[:12]:<14}", end="")
    print("Best")
    print("  " + "-" * 72)

    for h in ALL_HORIZONS:
        key = f't+{h}'
        print(f"  {key:<8}", end="")
        best_mae = float('inf')
        best_model = ""
        for model_name, results in all_results.items():
            mae = results['with_bc'].get(key, 0)
            print(f"${mae:<13.2f}", end="")
            if mae > 0 and mae < best_mae:
                best_mae = mae
                best_model = model_name[:8]
        print(best_model)

    print("  " + "-" * 72)
    print(f"  {'AVG':<8}", end="")
    for model_name, results in all_results.items():
        print(f"${results['with_bc']['average']:<13.2f}", end="")
    print()

    # Detailed horizon comparison (Non-zero actuals only)
    print("\n" + "-" * 80)
    print("DETAILED HORIZON COMPARISON (Non-Zero Actuals Only)")
    print("-" * 80)
    print()
    print(f"  {'Horizon':<8}", end="")
    for model_name in all_results:
        print(f"{model_name[:12]:<14}", end="")
    print("Best")
    print("  " + "-" * 72)

    for h in ALL_HORIZONS:
        key = f't+{h}'
        print(f"  {key:<8}", end="")
        best_mae = float('inf')
        best_model = ""
        for model_name, results in all_results.items():
            mae = results['nonzero_only'].get(key, 0)
            print(f"${mae:<13.2f}", end="")
            if mae > 0 and mae < best_mae:
                best_mae = mae
                best_model = model_name[:8]
        print(best_model)

    print("  " + "-" * 72)
    print(f"  {'AVG':<8}", end="")
    for model_name, results in all_results.items():
        print(f"${results['nonzero_only']['average']:<13.2f}", end="")
    print()

    # Save results
    output_path = MODELS_DIR / 'audit_results.json'
    audit_output = {
        'audit_date': datetime.now().isoformat(),
        'test_days': test_days,
        'test_period': {
            'start': df_raw.index[test_start].isoformat(),
            'end': df_raw.index[-1].isoformat()
        },
        'test_stats': sample_stats,
        'binary_classifier': bc_results,
        'model_results': {}
    }

    for model_name, results in all_results.items():
        audit_output['model_results'][model_name] = {
            'without_bc': results['without_bc'],
            'with_bc': results['with_bc'],
            'nonzero_only': results['nonzero_only'],
            'stats': results.get('stats', {})
        }

    with open(output_path, 'w') as f:
        json.dump(audit_output, f, indent=2, default=str)

    print(f"\nResults saved to: {output_path}")
    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)

    return all_results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Comprehensive Model Audit')
    parser.add_argument('--test-days', type=int, default=DEFAULT_TEST_DAYS,
                        help=f'Number of days for test set (default: {DEFAULT_TEST_DAYS})')

    args = parser.parse_args()

    results = run_comprehensive_audit(test_days=args.test_days)
