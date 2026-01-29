#!/usr/bin/env python3
"""
Stacked Ensemble: TSMixer + LightGBM + XGBoost with Learned Weights

This script creates a meta-ensemble that learns optimal weights for each model
at each horizon. This can potentially beat any single model by:

1. Generating out-of-fold (OOF) predictions from all base models
2. Training a meta-learner that learns optimal combination weights per horizon
3. Using the meta-learner for final predictions

The key insight: different models excel at different horizons and conditions.
A smart meta-learner can dynamically weight models based on the situation.

Base Models:
- TSMixer: Deep learning time-series model (good at short-term patterns)
- LightGBM: Gradient boosting with engineered features
- XGBoost: Gradient boosting with different regularization

Meta-Learner Options:
- Ridge Regression: Simple, interpretable weights
- LightGBM: Can learn non-linear combinations and feature interactions

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

os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'

import numpy as np
import pandas as pd
import torch

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
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.model_selection import TimeSeriesSplit
import pickle

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
N_FOLDS = 5  # For time-series cross-validation

ALL_HORIZONS = list(range(1, 25))

# TSMixer config (OPTUNA-OPTIMIZED - Trial 10, $36.29 MAE)
TSMIXER_CONFIG = {
    'input_size': 336,        # 2 weeks (was 168)
    'horizon': 24,
    'n_block': 10,            # More layers (was 8)
    'ff_dim': 128,            # Wider (was 64)
    'dropout': 0.308,         # Similar
    'revin': True,
    'learning_rate': 5.9e-4,  # Higher (was 1e-4)
    'max_steps': 2000,        # Will be overridden by command line
    'batch_size': 64,         # Larger (was 32)
    'val_check_steps': 50,
    'early_stop_patience': 10,
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


def generate_tsmixer_oof_predictions(
    df_nixtla: pd.DataFrame,
    train_indices: List[Tuple[int, int]],
    config: dict
) -> pd.DataFrame:
    """
    Generate out-of-fold predictions from TSMixer using time-series CV.

    For each fold:
    1. Train TSMixer on training portion
    2. Generate predictions on validation portion
    3. Store predictions with their indices

    Returns DataFrame with columns: index, horizon, tsmixer_pred, actual
    """
    print("\n  Generating TSMixer OOF predictions...")

    all_predictions = []

    for fold_idx, (train_end, val_start, val_end) in enumerate(train_indices):
        print(f"    Fold {fold_idx + 1}/{len(train_indices)}: "
              f"train={train_end}, val=[{val_start}:{val_end}]")

        clear_gpu_memory()

        # Train data
        df_train = df_nixtla.iloc[:train_end].copy()

        # Create and train model
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
            accelerator='gpu' if DEVICE == 'cuda' else 'cpu',
            devices=1,
        )

        nf = NeuralForecast(models=[model], freq='h')
        nf.fit(df=df_train, val_size=48)

        # Generate predictions for validation period
        # We predict in rolling fashion, 24 hours at a time
        val_hours = val_end - val_start
        n_predictions = val_hours // 24

        for day in range(n_predictions):
            pred_start_idx = val_start + (day * 24)

            # Use data up to prediction point
            df_input = df_nixtla.iloc[:pred_start_idx].copy()

            if len(df_input) < config['input_size']:
                continue

            with torch.no_grad():
                forecast = nf.predict(df=df_input)

            # Extract predictions for each horizon
            for h in range(1, 25):
                target_idx = pred_start_idx + h - 1

                if target_idx < len(df_nixtla) and target_idx < val_end:
                    pred_value = forecast['TSMixer'].iloc[h - 1]
                    actual_value = df_nixtla['y'].iloc[target_idx]

                    all_predictions.append({
                        'index': target_idx,
                        'horizon': h,
                        'tsmixer_pred': float(pred_value),
                        'actual': float(actual_value),
                        'fold': fold_idx,
                    })

        # Clean up
        del nf, model
        clear_gpu_memory()

    return pd.DataFrame(all_predictions)


def generate_gb_oof_predictions(
    df_feat: pd.DataFrame,
    feature_names: List[str],
    train_indices: List[Tuple[int, int]],
) -> pd.DataFrame:
    """
    Generate out-of-fold predictions from LightGBM and XGBoost.
    """
    print("\n  Generating LightGBM/XGBoost OOF predictions...")

    all_predictions = []

    for fold_idx, (train_end, val_start, val_end) in enumerate(train_indices):
        print(f"    Fold {fold_idx + 1}/{len(train_indices)}")

        train_df = df_feat.iloc[:train_end]
        val_df = df_feat.iloc[val_start:val_end]

        for h in ALL_HORIZONS:
            target_col = f'cmg_value_t+{h}'

            if target_col not in df_feat.columns:
                continue

            X_train = train_df[feature_names]
            y_train = train_df[target_col]
            X_val = val_df[feature_names]
            y_val = val_df[target_col]

            # Handle NaNs
            mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
            mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))

            X_train, y_train = X_train[mask_train], y_train[mask_train]
            X_val_clean, y_val_clean = X_val[mask_val], y_val[mask_val]

            if len(X_train) == 0 or len(X_val_clean) == 0:
                continue

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
            lgb_model = lgb.train(lgb_params, train_data, num_boost_round=300)

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
            xgb_model = xgb.train(xgb_params, train_dmatrix, num_boost_round=300)

            # Generate predictions
            lgb_pred = lgb_model.predict(X_val_clean)
            xgb_pred = xgb_model.predict(xgb.DMatrix(X_val_clean))

            # Store predictions with original indices
            val_indices = y_val_clean.index
            for i, idx in enumerate(val_indices):
                # Convert pandas index to integer position
                int_idx = df_feat.index.get_loc(idx)

                all_predictions.append({
                    'index': int_idx,
                    'horizon': h,
                    'lgb_pred': float(lgb_pred[i]),
                    'xgb_pred': float(xgb_pred[i]),
                    'actual': float(y_val_clean.iloc[i]),
                    'fold': fold_idx,
                })

    return pd.DataFrame(all_predictions)


def train_meta_learner(
    oof_predictions: pd.DataFrame,
    meta_type: str = 'ridge'
) -> Dict:
    """
    Train meta-learner that combines base model predictions.

    Args:
        oof_predictions: DataFrame with columns [tsmixer_pred, lgb_pred, xgb_pred, actual, horizon]
        meta_type: 'ridge' for linear combination, 'lgb' for non-linear

    Returns:
        Dict of meta-learners per horizon
    """
    print(f"\n  Training {meta_type} meta-learner for each horizon...")

    meta_learners = {}
    weights_per_horizon = {}

    for h in ALL_HORIZONS:
        h_data = oof_predictions[oof_predictions['horizon'] == h].copy()

        if len(h_data) < 10:
            print(f"    Horizon {h}: insufficient data ({len(h_data)} samples)")
            continue

        # Prepare features (base model predictions)
        X = h_data[['tsmixer_pred', 'lgb_pred', 'xgb_pred']].values
        y = h_data['actual'].values

        # Handle any NaNs
        mask = ~(np.isnan(X).any(axis=1) | np.isnan(y))
        X, y = X[mask], y[mask]

        if len(X) < 10:
            continue

        if meta_type == 'ridge':
            # Ridge regression with cross-validation to find best alpha
            meta = RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0], cv=3)
            meta.fit(X, y)

            # Store weights for interpretability
            weights = meta.coef_ / meta.coef_.sum()  # Normalize to sum to 1
            weights_per_horizon[h] = {
                'tsmixer': float(weights[0]),
                'lgb': float(weights[1]),
                'xgb': float(weights[2]),
                'alpha': float(meta.alpha_),
            }

        elif meta_type == 'lgb':
            # LightGBM can learn non-linear combinations
            meta_params = {
                'objective': 'regression',
                'metric': 'mae',
                'num_leaves': 8,  # Keep simple to avoid overfitting
                'learning_rate': 0.1,
                'verbose': -1,
            }
            train_data = lgb.Dataset(X, label=y)
            meta = lgb.train(meta_params, train_data, num_boost_round=100)

            weights_per_horizon[h] = {'type': 'lgb'}

        meta_learners[h] = meta

        # Evaluate meta-learner
        meta_pred = meta.predict(X)
        meta_mae = mean_absolute_error(y, meta_pred)

        # Compare to simple average
        simple_avg = X.mean(axis=1)
        simple_mae = mean_absolute_error(y, simple_avg)

        # Compare to best single model
        best_single_mae = min(
            mean_absolute_error(y, X[:, 0]),  # tsmixer
            mean_absolute_error(y, X[:, 1]),  # lgb
            mean_absolute_error(y, X[:, 2]),  # xgb
        )

        improvement = (simple_mae - meta_mae) / simple_mae * 100
        vs_best = (best_single_mae - meta_mae) / best_single_mae * 100

        print(f"    t+{h}: Meta=${meta_mae:.2f}, Simple=${simple_mae:.2f}, "
              f"Best=${best_single_mae:.2f} | Meta vs Simple: {improvement:+.1f}%, "
              f"vs Best: {vs_best:+.1f}%")

    return {
        'meta_learners': meta_learners,
        'weights': weights_per_horizon,
        'meta_type': meta_type,
    }


class StackedEnsemble:
    """
    Stacked ensemble combining TSMixer, LightGBM, and XGBoost
    with learned meta-weights per horizon.
    """

    def __init__(
        self,
        tsmixer_model: NeuralForecast,
        lgb_models: Dict,
        xgb_models: Dict,
        meta_learners: Dict,
        feature_names: List[str],
        weights: Dict = None,
    ):
        self.tsmixer_model = tsmixer_model
        self.lgb_models = lgb_models
        self.xgb_models = xgb_models
        self.meta_learners = meta_learners
        self.feature_names = feature_names
        self.weights = weights or {}

    def predict(
        self,
        df_nixtla: pd.DataFrame,
        df_features: pd.DataFrame,
    ) -> Dict[str, float]:
        """Generate predictions using stacked ensemble."""
        predictions = {}

        # Get TSMixer predictions
        with torch.no_grad():
            tsmixer_forecast = self.tsmixer_model.predict(df=df_nixtla)

        # Get latest features for GB models
        X = df_features[self.feature_names].iloc[-1:].values

        for h in ALL_HORIZONS:
            # Get base predictions
            tsmixer_pred = float(tsmixer_forecast['TSMixer'].iloc[h - 1])

            if h in self.lgb_models:
                lgb_pred = float(self.lgb_models[h].predict(X)[0])
                xgb_pred = float(self.xgb_models[h].predict(xgb.DMatrix(X))[0])
            else:
                lgb_pred = tsmixer_pred
                xgb_pred = tsmixer_pred

            # Combine using meta-learner
            if h in self.meta_learners:
                X_meta = np.array([[tsmixer_pred, lgb_pred, xgb_pred]])
                predictions[f't+{h}'] = float(self.meta_learners[h].predict(X_meta)[0])
            else:
                # Fallback to simple average
                predictions[f't+{h}'] = (tsmixer_pred + lgb_pred + xgb_pred) / 3

        return predictions

    def save(self, output_dir: Path):
        """Save stacked ensemble."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save TSMixer
        self.tsmixer_model.save(path=str(output_dir / 'tsmixer'), overwrite=True)

        # Save GB models
        lgb_dir = output_dir / 'lgb_models'
        lgb_dir.mkdir(exist_ok=True)
        for h, model in self.lgb_models.items():
            model.save_model(str(lgb_dir / f't+{h}.txt'))

        xgb_dir = output_dir / 'xgb_models'
        xgb_dir.mkdir(exist_ok=True)
        for h, model in self.xgb_models.items():
            model.save_model(str(xgb_dir / f't+{h}.json'))

        # Save meta-learners
        meta_dir = output_dir / 'meta_learners'
        meta_dir.mkdir(exist_ok=True)
        for h, meta in self.meta_learners.items():
            with open(meta_dir / f't+{h}.pkl', 'wb') as f:
                pickle.dump(meta, f)

        # Save config
        config = {
            'feature_names': self.feature_names,
            'weights': self.weights,
            'horizons': list(self.meta_learners.keys()),
            'created_at': datetime.now().isoformat(),
        }
        with open(output_dir / 'config.json', 'w') as f:
            json.dump(config, f, indent=2)

        print(f"Saved stacked ensemble to: {output_dir}")

    @classmethod
    def load(cls, model_dir: Path) -> 'StackedEnsemble':
        """Load stacked ensemble from disk."""
        with open(model_dir / 'config.json', 'r') as f:
            config = json.load(f)

        # Load TSMixer
        tsmixer_model = NeuralForecast.load(path=str(model_dir / 'tsmixer'))

        # Load GB models
        lgb_models = {}
        lgb_dir = model_dir / 'lgb_models'
        for h in config['horizons']:
            lgb_models[h] = lgb.Booster(model_file=str(lgb_dir / f't+{h}.txt'))

        xgb_models = {}
        xgb_dir = model_dir / 'xgb_models'
        for h in config['horizons']:
            xgb_models[h] = xgb.Booster()
            xgb_models[h].load_model(str(xgb_dir / f't+{h}.json'))

        # Load meta-learners
        meta_learners = {}
        meta_dir = model_dir / 'meta_learners'
        for h in config['horizons']:
            with open(meta_dir / f't+{h}.pkl', 'rb') as f:
                meta_learners[h] = pickle.load(f)

        return cls(
            tsmixer_model=tsmixer_model,
            lgb_models=lgb_models,
            xgb_models=xgb_models,
            meta_learners=meta_learners,
            feature_names=config['feature_names'],
            weights=config.get('weights', {}),
        )


def run_stacked_ensemble_training(
    tsmixer_steps: int = 2000,
    meta_type: str = 'ridge',
):
    """
    Train the full stacked ensemble pipeline.
    """
    print("=" * 70)
    print("STACKED ENSEMBLE TRAINING")
    print("TSMixer + LightGBM + XGBoost with Learned Meta-Weights")
    print("=" * 70)
    print()
    print(f"TSMixer steps: {tsmixer_steps}")
    print(f"Meta-learner type: {meta_type}")
    print()

    # 1. Load data
    print("\n[1/7] LOADING DATA")
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
    print("\n[2/7] PREPARING DATA")
    print("-" * 50)

    df_nixtla = prepare_nixtla_format(df_raw)

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

    # 3. Create CV folds for OOF predictions
    print("\n[3/7] CREATING CV FOLDS")
    print("-" * 50)

    # Use expanding window for time series
    fold_size = train_end // (N_FOLDS + 1)
    train_indices = []

    for fold in range(N_FOLDS):
        fold_train_end = fold_size * (fold + 2)  # Expanding window
        fold_val_start = fold_train_end
        fold_val_end = min(fold_val_start + fold_size, train_end)

        if fold_val_end > fold_val_start:
            train_indices.append((fold_train_end, fold_val_start, fold_val_end))
            print(f"  Fold {fold + 1}: train={fold_train_end}, val=[{fold_val_start}:{fold_val_end}]")

    # 4. Generate OOF predictions
    print("\n[4/7] GENERATING OUT-OF-FOLD PREDICTIONS")
    print("-" * 50)

    # Update config with steps
    config = TSMIXER_CONFIG.copy()
    config['max_steps'] = tsmixer_steps

    tsmixer_oof = generate_tsmixer_oof_predictions(df_nixtla, train_indices, config)
    gb_oof = generate_gb_oof_predictions(df_feat, feature_names, train_indices)

    # Merge OOF predictions
    print("\n  Merging OOF predictions...")
    oof_merged = pd.merge(
        tsmixer_oof[['index', 'horizon', 'tsmixer_pred', 'actual']],
        gb_oof[['index', 'horizon', 'lgb_pred', 'xgb_pred']],
        on=['index', 'horizon'],
        how='inner'
    )
    print(f"  Merged OOF samples: {len(oof_merged)}")

    # 5. Train meta-learner
    print("\n[5/7] TRAINING META-LEARNER")
    print("-" * 50)

    meta_result = train_meta_learner(oof_merged, meta_type=meta_type)

    # 6. Train final base models on full training data
    print("\n[6/7] TRAINING FINAL BASE MODELS")
    print("-" * 50)

    # Train TSMixer on full training data
    print("  Training final TSMixer...")
    clear_gpu_memory()

    df_train_nixtla = df_nixtla.iloc[:train_end].copy()

    final_tsmixer = TSMixer(
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
        accelerator='gpu' if DEVICE == 'cuda' else 'cpu',
        devices=1,
    )

    nf_final = NeuralForecast(models=[final_tsmixer], freq='h')
    nf_final.fit(df=df_train_nixtla, val_size=48)

    # Train final GB models
    print("  Training final LightGBM/XGBoost models...")

    train_df = df_feat.iloc[:train_end]
    val_df = df_feat.iloc[val_start:test_start]

    lgb_models = {}
    xgb_models = {}

    for h in ALL_HORIZONS:
        target_col = f'cmg_value_t+{h}'

        if target_col not in df_feat.columns:
            continue

        X_train = train_df[feature_names]
        y_train = train_df[target_col]
        X_val = val_df[feature_names]
        y_val = val_df[target_col]

        mask_train = ~(y_train.isna() | X_train.isna().any(axis=1))
        mask_val = ~(y_val.isna() | X_val.isna().any(axis=1))

        X_train, y_train = X_train[mask_train], y_train[mask_train]
        X_val, y_val = X_val[mask_val], y_val[mask_val]

        # LightGBM
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

        lgb_models[h] = lgb.train(
            lgb_params, train_data, num_boost_round=500,
            valid_sets=[val_data],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )

        # XGBoost
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

        xgb_models[h] = xgb.train(
            xgb_params, train_dmatrix, num_boost_round=500,
            evals=[(val_dmatrix, 'val')],
            early_stopping_rounds=50, verbose_eval=False
        )

    # 7. Evaluate on test set
    print("\n[7/7] EVALUATING ON TEST SET")
    print("-" * 50)

    # Create ensemble
    stacked = StackedEnsemble(
        tsmixer_model=nf_final,
        lgb_models=lgb_models,
        xgb_models=xgb_models,
        meta_learners=meta_result['meta_learners'],
        feature_names=feature_names,
        weights=meta_result['weights'],
    )

    # Evaluate
    test_df = df_feat.iloc[test_start:]
    test_results = {
        'stacked': {},
        'tsmixer': {},
        'lgb': {},
        'xgb': {},
        'simple_avg': {},
    }

    # Rolling evaluation
    test_hours = len(df_nixtla) - test_start
    n_predictions = test_hours // 24

    print(f"  Running {n_predictions} rolling predictions...")

    all_preds = {key: {f't+{h}': [] for h in ALL_HORIZONS} for key in test_results}
    all_actuals = {f't+{h}': [] for h in ALL_HORIZONS}

    for day in range(n_predictions):
        pred_start_idx = test_start + (day * 24)

        # TSMixer prediction
        df_input = df_nixtla.iloc[:pred_start_idx].copy()

        if len(df_input) < TSMIXER_CONFIG['input_size']:
            continue

        with torch.no_grad():
            tsmixer_forecast = nf_final.predict(df=df_input)

        # Features for this prediction point
        feat_idx = pred_start_idx - 1
        if feat_idx >= len(df_feat):
            continue

        X_pred = df_feat[feature_names].iloc[feat_idx:feat_idx+1]

        for h in ALL_HORIZONS:
            target_idx = pred_start_idx + h - 1

            if target_idx >= len(df_nixtla):
                continue

            actual = df_nixtla['y'].iloc[target_idx]
            all_actuals[f't+{h}'].append(actual)

            # TSMixer prediction
            ts_pred = float(tsmixer_forecast['TSMixer'].iloc[h - 1])
            all_preds['tsmixer'][f't+{h}'].append(ts_pred)

            # GB predictions
            if h in lgb_models:
                lgb_pred = float(lgb_models[h].predict(X_pred)[0])
                xgb_pred = float(xgb_models[h].predict(xgb.DMatrix(X_pred))[0])
            else:
                lgb_pred = ts_pred
                xgb_pred = ts_pred

            all_preds['lgb'][f't+{h}'].append(lgb_pred)
            all_preds['xgb'][f't+{h}'].append(xgb_pred)

            # Simple average
            all_preds['simple_avg'][f't+{h}'].append((ts_pred + lgb_pred + xgb_pred) / 3)

            # Stacked ensemble
            if h in meta_result['meta_learners']:
                X_meta = np.array([[ts_pred, lgb_pred, xgb_pred]])
                stacked_pred = float(meta_result['meta_learners'][h].predict(X_meta)[0])
            else:
                stacked_pred = (ts_pred + lgb_pred + xgb_pred) / 3

            all_preds['stacked'][f't+{h}'].append(stacked_pred)

    # Calculate MAE for each model and horizon
    print("\n" + "=" * 80)
    print("RESULTS COMPARISON")
    print("=" * 80)

    print(f"\n{'Horizon':<10} {'TSMixer':<12} {'LightGBM':<12} {'XGBoost':<12} "
          f"{'Simple Avg':<12} {'STACKED':<12} {'Best':<10}")
    print("-" * 80)

    for h in ALL_HORIZONS:
        key = f't+{h}'

        if not all_actuals[key]:
            continue

        actuals = all_actuals[key]

        maes = {}
        for model_name in test_results:
            preds = all_preds[model_name][key]
            if preds:
                maes[model_name] = mean_absolute_error(actuals, preds)

        best_model = min(maes, key=maes.get)

        print(f"{key:<10} ${maes.get('tsmixer', 0):<11.2f} ${maes.get('lgb', 0):<11.2f} "
              f"${maes.get('xgb', 0):<11.2f} ${maes.get('simple_avg', 0):<11.2f} "
              f"${maes.get('stacked', 0):<11.2f} {best_model}")

        for model_name in test_results:
            test_results[model_name][key] = maes.get(model_name, 0)

    # Calculate averages
    print("-" * 80)

    avg_results = {}
    for model_name in test_results:
        vals = [v for k, v in test_results[model_name].items() if k.startswith('t+')]
        if vals:
            avg_results[model_name] = np.mean(vals)

    best_overall = min(avg_results, key=avg_results.get)

    print(f"{'AVERAGE':<10} ${avg_results.get('tsmixer', 0):<11.2f} "
          f"${avg_results.get('lgb', 0):<11.2f} ${avg_results.get('xgb', 0):<11.2f} "
          f"${avg_results.get('simple_avg', 0):<11.2f} "
          f"${avg_results.get('stacked', 0):<11.2f} {best_overall}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for model_name, mae in sorted(avg_results.items(), key=lambda x: x[1]):
        print(f"  {model_name:<15}: ${mae:.2f}")

    improvement = (avg_results['simple_avg'] - avg_results['stacked']) / avg_results['simple_avg'] * 100
    print(f"\n  Stacked vs Simple Average: {improvement:+.1f}%")

    # Count wins per horizon
    wins = {m: 0 for m in test_results}
    for h in ALL_HORIZONS:
        key = f't+{h}'
        if key in test_results['stacked']:
            best = min(test_results, key=lambda m: test_results[m].get(key, float('inf')))
            wins[best] += 1

    print(f"\n  Wins per model: {wins}")

    # Show learned weights
    if meta_result['weights']:
        print("\n" + "=" * 80)
        print("LEARNED WEIGHTS PER HORIZON")
        print("=" * 80)

        print(f"\n{'Horizon':<10} {'TSMixer':<12} {'LightGBM':<12} {'XGBoost':<12}")
        print("-" * 50)

        for h in ALL_HORIZONS:
            if h in meta_result['weights']:
                w = meta_result['weights'][h]
                print(f"t+{h:<8} {w.get('tsmixer', 0):<12.3f} "
                      f"{w.get('lgb', 0):<12.3f} {w.get('xgb', 0):<12.3f}")

    # Save ensemble
    output_dir = Path(__file__).parent.parent / 'models_stacked_ensemble'
    stacked.save(output_dir)

    # Save results
    results_summary = {
        'training_date': datetime.now().isoformat(),
        'tsmixer_steps': tsmixer_steps,
        'meta_type': meta_type,
        'test_results': test_results,
        'average_results': avg_results,
        'wins_per_model': wins,
        'weights': meta_result['weights'],
    }

    with open(output_dir / 'training_results.json', 'w') as f:
        json.dump(results_summary, f, indent=2, default=str)

    print(f"\nResults saved to: {output_dir}")

    return stacked, results_summary


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Train Stacked Ensemble')
    parser.add_argument('--tsmixer-steps', type=int, default=2000,
                        help='Training steps for TSMixer')
    parser.add_argument('--meta-type', choices=['ridge', 'lgb'], default='ridge',
                        help='Meta-learner type')

    args = parser.parse_args()

    stacked, results = run_stacked_ensemble_training(
        tsmixer_steps=args.tsmixer_steps,
        meta_type=args.meta_type,
    )
