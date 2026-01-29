#!/usr/bin/env python3
"""
ML Model Training Script
========================

Trains CMG forecasting models with fresh data from Supabase.

Features:
1. Fetches latest data from Supabase
2. Creates features including CMG Programado (optional)
3. Uses time-series cross-validation
4. Trains LightGBM and XGBoost models for each horizon
5. Saves models in production format
6. Logs training metrics

Usage:
    python scripts/ml_model_training.py [--include-programado] [--horizons 1-24]

Requirements:
    - SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables
    - lightgbm, xgboost, scikit-learn, pandas, numpy

Author: Pudidi CMG Prediction System
Date: 2026-01
"""

import sys
import os
import json
import pickle
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import lightgbm as lgb
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ml_feature_engineering import CleanCMGFeatureEngineering

# Configuration
MODELS_DIR = Path(__file__).parent.parent / "models_24h"
DATA_DIR = Path(__file__).parent.parent / "data"
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


def fetch_training_data(supabase, days: int = 365) -> pd.DataFrame:
    """
    Fetch CMG Online (actuals) data from Supabase for training.

    Args:
        supabase: SupabaseClient instance
        days: Number of days of history to fetch

    Returns:
        DataFrame with datetime index and CMG values
    """
    print(f"Fetching {days} days of CMG Online data from Supabase...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    records = supabase.get_cmg_online(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        limit=days * 24 * 3  # 3 nodes per hour
    )

    if not records:
        raise ValueError("No CMG Online data found in Supabase")

    print(f"  Fetched {len(records)} records")

    # Convert to DataFrame
    df = pd.DataFrame(records)
    df['datetime'] = pd.to_datetime(df['datetime'])

    # Average across nodes for each hour
    df_hourly = df.groupby('datetime')['cmg_usd'].mean().reset_index()
    df_hourly.columns = ['fecha_hora', 'CMG [$/MWh]']
    df_hourly = df_hourly.set_index('fecha_hora').sort_index()

    # Remove duplicates
    df_hourly = df_hourly[~df_hourly.index.duplicated(keep='last')]

    print(f"  Processed {len(df_hourly)} unique hours")
    print(f"  Date range: {df_hourly.index.min()} to {df_hourly.index.max()}")

    return df_hourly


def fetch_cmg_programado(supabase, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch CMG Programado data from Supabase.

    Args:
        supabase: SupabaseClient instance
        start_date: Start date string
        end_date: End date string

    Returns:
        DataFrame with CMG Programado forecasts
    """
    print(f"Fetching CMG Programado data...")

    records = supabase.get_cmg_programado(
        start_date=start_date,
        end_date=end_date,
        latest_forecast_only=False,
        limit=100000
    )

    if not records:
        print("  Warning: No CMG Programado data found")
        return None

    print(f"  Fetched {len(records)} programado records")

    df = pd.DataFrame(records)
    df['target_datetime'] = pd.to_datetime(df['target_datetime'])

    return df


def train_value_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    horizon: int,
    model_type: str = 'lgb'
) -> Tuple[any, Dict]:
    """
    Train a value prediction model.

    Args:
        X_train, y_train: Training data
        X_val, y_val: Validation data
        horizon: Forecast horizon (1-24)
        model_type: 'lgb' or 'xgb'

    Returns:
        Trained model and metrics dict
    """
    # Handle NaN values
    mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
    mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))

    X_train_clean = X_train[mask_train]
    y_train_clean = y_train[mask_train]
    X_val_clean = X_val[mask_val]
    y_val_clean = y_val[mask_val]

    if len(X_train_clean) < 100:
        print(f"    Warning: Only {len(X_train_clean)} training samples")
        return None, {}

    if model_type == 'lgb':
        # LightGBM parameters
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

    else:  # XGBoost
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

    # Calculate metrics
    if model_type == 'lgb':
        y_pred = model.predict(X_val_clean)
    else:
        y_pred = model.predict(xgb.DMatrix(X_val_clean))

    metrics = {
        'mae': mean_absolute_error(y_val_clean, y_pred),
        'rmse': np.sqrt(mean_squared_error(y_val_clean, y_pred)),
        'r2': r2_score(y_val_clean, y_pred),
        'train_samples': len(X_train_clean),
        'val_samples': len(X_val_clean)
    }

    return model, metrics


def train_zero_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    horizon: int,
    model_type: str = 'lgb'
) -> Tuple[any, Dict]:
    """
    Train a zero detection (classification) model.

    Args:
        X_train, y_train: Training data (y is binary)
        X_val, y_val: Validation data
        horizon: Forecast horizon (1-24)
        model_type: 'lgb' or 'xgb'

    Returns:
        Trained model and metrics dict
    """
    # Handle NaN values
    mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
    mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))

    X_train_clean = X_train[mask_train]
    y_train_clean = y_train[mask_train]
    X_val_clean = X_val[mask_val]
    y_val_clean = y_val[mask_val]

    if len(X_train_clean) < 100:
        return None, {}

    # Calculate scale_pos_weight for imbalanced classes
    n_pos = y_train_clean.sum()
    n_neg = len(y_train_clean) - n_pos
    scale_pos_weight = n_neg / (n_pos + 1e-6)

    if model_type == 'lgb':
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.8,
            'scale_pos_weight': scale_pos_weight,
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

        y_prob = model.predict(X_val_clean)

    else:  # XGBoost
        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 6,
            'learning_rate': 0.05,
            'scale_pos_weight': scale_pos_weight,
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

        y_prob = model.predict(xgb.DMatrix(X_val_clean))

    # Calculate metrics
    from sklearn.metrics import roc_auc_score, precision_recall_fscore_support

    y_pred = (y_prob > 0.5).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_val_clean, y_pred, average='binary', zero_division=0
    )

    metrics = {
        'auc': roc_auc_score(y_val_clean, y_prob) if len(np.unique(y_val_clean)) > 1 else 0,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'train_samples': len(X_train_clean),
        'zero_rate_train': y_train_clean.mean(),
        'zero_rate_val': y_val_clean.mean()
    }

    return model, metrics


def save_models(
    models: Dict,
    feature_names: List[str],
    metrics: Dict,
    output_dir: Path
):
    """
    Save trained models to disk.

    Args:
        models: Dict with model objects
        feature_names: List of feature names
        metrics: Training metrics
        output_dir: Output directory
    """
    # Create directories
    value_dir = output_dir / "value_prediction"
    zero_dir = output_dir / "zero_detection"
    value_dir.mkdir(parents=True, exist_ok=True)
    zero_dir.mkdir(parents=True, exist_ok=True)

    # Save value prediction models
    for key, model in models.items():
        if model is None:
            continue

        if 'value' in key:
            model_type, horizon = key.split('_value_t+')
            if model_type == 'lgb':
                model.save_model(str(value_dir / f"lgb_median_t+{horizon}.txt"))
            else:
                model.save_model(str(value_dir / f"xgb_t+{horizon}.json"))

        elif 'zero' in key:
            model_type, horizon = key.split('_zero_t+')
            if model_type == 'lgb':
                model.save_model(str(zero_dir / f"lgb_t+{horizon}.txt"))
            else:
                model.save_model(str(zero_dir / f"xgb_t+{horizon}.json"))

    # Save feature names
    with open(value_dir / "feature_names.pkl", 'wb') as f:
        pickle.dump(feature_names, f)

    # Save metrics
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(LOGS_DIR / f"training_metrics_{timestamp}.json", 'w') as f:
        json.dump(metrics, f, indent=2, default=str)

    print(f"\nModels saved to {output_dir}")
    print(f"Metrics saved to {LOGS_DIR}/training_metrics_{timestamp}.json")


def main():
    parser = argparse.ArgumentParser(description='Train CMG forecasting models')
    parser.add_argument('--include-programado', action='store_true',
                        help='Include CMG Programado as input feature')
    parser.add_argument('--horizons', type=str, default='1-24',
                        help='Horizons to train (e.g., "1-24" or "1,6,12,24")')
    parser.add_argument('--days', type=int, default=365,
                        help='Days of history to use for training')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for models')
    args = parser.parse_args()

    # Parse horizons
    if '-' in args.horizons:
        start, end = map(int, args.horizons.split('-'))
        horizons = list(range(start, end + 1))
    else:
        horizons = [int(h) for h in args.horizons.split(',')]

    print("="*80)
    print("ML MODEL TRAINING SCRIPT")
    print("="*80)
    print(f"Horizons: {horizons}")
    print(f"Include CMG Programado: {args.include_programado}")
    print(f"Training days: {args.days}")
    print()

    # Initialize Supabase
    supabase = get_supabase_client()
    if supabase is None:
        print("Error: Could not initialize Supabase client")
        print("Make sure SUPABASE_URL and SUPABASE_SERVICE_KEY are set")
        sys.exit(1)

    # Fetch training data
    try:
        df = fetch_training_data(supabase, days=args.days)
    except Exception as e:
        print(f"Error fetching training data: {e}")
        sys.exit(1)

    # Fetch CMG Programado if requested
    prog_df = None
    if args.include_programado:
        try:
            prog_df = fetch_cmg_programado(
                supabase,
                start_date=df.index.min().strftime('%Y-%m-%d'),
                end_date=df.index.max().strftime('%Y-%m-%d')
            )
        except Exception as e:
            print(f"Warning: Could not fetch CMG Programado: {e}")

    # Create features
    print("\nCreating features...")
    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=horizons,
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168]
    )

    df_feat = feature_engineer.create_features(
        df,
        cmg_column='CMG [$/MWh]',
        cmg_programado_df=prog_df
    )

    feature_names = feature_engineer.get_feature_names()
    print(f"Created {len(feature_names)} features")

    # Create train/val split (time-series aware)
    # Use 80% train, 20% validation
    n = len(df_feat)
    train_end = int(n * 0.8)

    train_df = df_feat.iloc[:train_end]
    val_df = df_feat.iloc[train_end:]

    print(f"\nTrain: {len(train_df)} samples ({train_df.index.min()} to {train_df.index.max()})")
    print(f"Val: {len(val_df)} samples ({val_df.index.min()} to {val_df.index.max()})")

    # Train models for each horizon
    all_models = {}
    all_metrics = {'value': {}, 'zero': {}}

    for h in horizons:
        print(f"\n{'='*60}")
        print(f"Training models for horizon t+{h}")
        print('='*60)

        # Prepare data
        X_train = train_df[feature_names]
        X_val = val_df[feature_names]

        y_train_value = train_df[f'cmg_value_t+{h}']
        y_val_value = val_df[f'cmg_value_t+{h}']

        y_train_zero = train_df[f'is_zero_t+{h}']
        y_val_zero = val_df[f'is_zero_t+{h}']

        # Train value prediction models (LGB and XGB)
        print(f"  Training LightGBM value model...")
        lgb_model, lgb_metrics = train_value_model(
            X_train, y_train_value, X_val, y_val_value, h, 'lgb'
        )
        if lgb_model:
            all_models[f'lgb_value_t+{h}'] = lgb_model
            all_metrics['value'][f'lgb_t+{h}'] = lgb_metrics
            print(f"    MAE: ${lgb_metrics['mae']:.2f}")

        print(f"  Training XGBoost value model...")
        xgb_model, xgb_metrics = train_value_model(
            X_train, y_train_value, X_val, y_val_value, h, 'xgb'
        )
        if xgb_model:
            all_models[f'xgb_value_t+{h}'] = xgb_model
            all_metrics['value'][f'xgb_t+{h}'] = xgb_metrics
            print(f"    MAE: ${xgb_metrics['mae']:.2f}")

        # Train zero detection models
        print(f"  Training LightGBM zero detection model...")
        lgb_zero, lgb_zero_metrics = train_zero_model(
            X_train, y_train_zero, X_val, y_val_zero, h, 'lgb'
        )
        if lgb_zero:
            all_models[f'lgb_zero_t+{h}'] = lgb_zero
            all_metrics['zero'][f'lgb_t+{h}'] = lgb_zero_metrics
            print(f"    AUC: {lgb_zero_metrics['auc']:.3f}, F1: {lgb_zero_metrics['f1']:.3f}")

        print(f"  Training XGBoost zero detection model...")
        xgb_zero, xgb_zero_metrics = train_zero_model(
            X_train, y_train_zero, X_val, y_val_zero, h, 'xgb'
        )
        if xgb_zero:
            all_models[f'xgb_zero_t+{h}'] = xgb_zero
            all_metrics['zero'][f'xgb_t+{h}'] = xgb_zero_metrics
            print(f"    AUC: {xgb_zero_metrics['auc']:.3f}, F1: {xgb_zero_metrics['f1']:.3f}")

    # Save models
    output_dir = Path(args.output_dir) if args.output_dir else MODELS_DIR
    save_models(all_models, feature_names, all_metrics, output_dir)

    # Print summary
    print("\n" + "="*80)
    print("TRAINING COMPLETE - SUMMARY")
    print("="*80)

    # Calculate average metrics
    value_maes = [m['mae'] for m in all_metrics['value'].values() if 'mae' in m]
    zero_aucs = [m['auc'] for m in all_metrics['zero'].values() if 'auc' in m]

    print(f"\nValue Prediction:")
    print(f"  Average MAE: ${np.mean(value_maes):.2f}")
    print(f"  Best MAE: ${min(value_maes):.2f}")
    print(f"  Worst MAE: ${max(value_maes):.2f}")

    print(f"\nZero Detection:")
    print(f"  Average AUC: {np.mean(zero_aucs):.3f}")
    print(f"  Average F1: {np.mean([m['f1'] for m in all_metrics['zero'].values() if 'f1' in m]):.3f}")

    print(f"\nModels saved to: {output_dir}")
    print("\nDone!")


if __name__ == "__main__":
    main()
