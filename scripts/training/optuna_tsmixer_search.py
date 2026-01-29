#!/usr/bin/env python3
"""
Optuna Hyperparameter Search for TSMixer

Uses Bayesian optimization to find optimal TSMixer hyperparameters.
Searches over:
- n_block: Number of mixing layers
- ff_dim: Feed-forward dimension
- dropout: Dropout rate
- learning_rate: Learning rate
- input_size: Context window size
- batch_size: Training batch size

Optimization target: Average MAE across all 24 horizons on validation set.

Author: CMG Prediction System
Date: 2026-01-29
"""

import os
import sys
import warnings
import json
import gc
from datetime import datetime
from typing import Dict, List, Tuple
from pathlib import Path

warnings.filterwarnings('ignore')

os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'

import numpy as np
import pandas as pd
import torch
import optuna
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

np.random.seed(42)
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed(42)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = True

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from neuralforecast import NeuralForecast
from neuralforecast.models import TSMixer
from neuralforecast.losses.pytorch import MAE
from sklearn.metrics import mean_absolute_error

torch.set_float32_matmul_precision('high')

# ============================================================================
# CONFIGURATION
# ============================================================================

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Device: {DEVICE}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# Data split - use smaller validation for faster trials
VAL_DAYS = 14
TEST_DAYS = 30

# Optuna settings
N_TRIALS = 50  # Number of trials
TIMEOUT = 3600 * 3  # 3 hours max
N_STARTUP_TRIALS = 10  # Random trials before Bayesian optimization

# Training steps per trial (smaller for faster search)
TRIAL_MAX_STEPS = 1000

ALL_HORIZONS = list(range(1, 25))


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

    return df_hourly


def prepare_nixtla_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert to NeuralForecast format."""
    df_nf = df.reset_index()
    df_nf.columns = ['ds', 'y']
    df_nf['unique_id'] = 'CMG'
    return df_nf[['unique_id', 'ds', 'y']]


class TSMixerObjective:
    """Optuna objective for TSMixer hyperparameter optimization."""

    def __init__(self, df_nixtla: pd.DataFrame, train_end: int, val_end: int):
        self.df_nixtla = df_nixtla
        self.train_end = train_end
        self.val_end = val_end
        self.best_mae = float('inf')
        self.best_config = None

    def __call__(self, trial: optuna.Trial) -> float:
        """Evaluate a single trial."""
        clear_gpu_memory()

        # Sample hyperparameters
        config = {
            'input_size': trial.suggest_categorical('input_size', [96, 168, 336]),
            'n_block': trial.suggest_int('n_block', 2, 12),
            'ff_dim': trial.suggest_categorical('ff_dim', [32, 64, 128, 256]),
            'dropout': trial.suggest_float('dropout', 0.1, 0.7),
            'learning_rate': trial.suggest_float('learning_rate', 1e-5, 1e-3, log=True),
            'batch_size': trial.suggest_categorical('batch_size', [16, 32, 64]),
            'revin': trial.suggest_categorical('revin', [True, False]),
        }

        print(f"\nTrial {trial.number}: {config}")

        try:
            # Create model
            model = TSMixer(
                h=24,
                input_size=config['input_size'],
                n_series=1,
                n_block=config['n_block'],
                ff_dim=config['ff_dim'],
                dropout=config['dropout'],
                revin=config['revin'],
                max_steps=TRIAL_MAX_STEPS,
                val_check_steps=50,
                early_stop_patience_steps=5,
                scaler_type='standard',
                learning_rate=config['learning_rate'],
                batch_size=config['batch_size'],
                valid_loss=MAE(),
                random_seed=42,
                accelerator='gpu' if DEVICE == 'cuda' else 'cpu',
                devices=1,
            )

            nf = NeuralForecast(models=[model], freq='h')

            # Train on training data
            df_train = self.df_nixtla.iloc[:self.train_end].copy()
            nf.fit(df=df_train, val_size=48)

            # Evaluate on validation set
            val_mae = self._evaluate_on_validation(nf, config['input_size'])

            # Track best
            if val_mae < self.best_mae:
                self.best_mae = val_mae
                self.best_config = config.copy()
                print(f"  NEW BEST: ${val_mae:.2f}")

            # Report intermediate value for pruning
            trial.report(val_mae, step=0)

            if trial.should_prune():
                raise optuna.TrialPruned()

            # Clean up
            del nf, model
            clear_gpu_memory()

            return val_mae

        except Exception as e:
            print(f"  Trial failed: {e}")
            clear_gpu_memory()
            return float('inf')

    def _evaluate_on_validation(self, nf: NeuralForecast, input_size: int) -> float:
        """Evaluate model on validation set with rolling predictions."""
        results = {f't+{h}': [] for h in ALL_HORIZONS}
        actuals = {f't+{h}': [] for h in ALL_HORIZONS}

        val_hours = self.val_end - self.train_end
        n_predictions = val_hours // 24

        for day in range(n_predictions):
            pred_start_idx = self.train_end + (day * 24)

            df_input = self.df_nixtla.iloc[:pred_start_idx].copy()

            if len(df_input) < input_size:
                continue

            with torch.no_grad():
                forecast = nf.predict(df=df_input)

            for h in ALL_HORIZONS:
                target_idx = pred_start_idx + h - 1

                if target_idx < self.val_end and h <= len(forecast):
                    pred_value = forecast['TSMixer'].iloc[h - 1]
                    actual_value = self.df_nixtla['y'].iloc[target_idx]

                    results[f't+{h}'].append(pred_value)
                    actuals[f't+{h}'].append(actual_value)

        # Calculate average MAE
        maes = []
        for h in ALL_HORIZONS:
            key = f't+{h}'
            if results[key]:
                mae = mean_absolute_error(actuals[key], results[key])
                maes.append(mae)

        return np.mean(maes) if maes else float('inf')


def run_optuna_search(n_trials: int = N_TRIALS, timeout: int = TIMEOUT):
    """Run Optuna hyperparameter search."""
    print("=" * 70)
    print("OPTUNA HYPERPARAMETER SEARCH FOR TSMIXER")
    print("=" * 70)
    print()
    print(f"Trials: {n_trials}")
    print(f"Timeout: {timeout}s ({timeout/3600:.1f} hours)")
    print(f"Steps per trial: {TRIAL_MAX_STEPS}")
    print()

    # Load data
    print("Loading data...")
    df_raw = load_data()

    n = len(df_raw)
    test_size = TEST_DAYS * 24
    val_size = VAL_DAYS * 24

    val_end = n - test_size
    train_end = val_end - val_size

    print(f"Train: {train_end} hours, Val: {val_size} hours, Test: {test_size} hours")

    df_nixtla = prepare_nixtla_format(df_raw)

    # Create objective
    objective = TSMixerObjective(df_nixtla, train_end, val_end)

    # Create study with TPE sampler
    sampler = TPESampler(
        n_startup_trials=N_STARTUP_TRIALS,
        seed=42,
    )

    pruner = MedianPruner(
        n_startup_trials=5,
        n_warmup_steps=0,
    )

    study = optuna.create_study(
        direction='minimize',
        sampler=sampler,
        pruner=pruner,
        study_name='tsmixer_optimization',
    )

    # Run optimization
    print("\n" + "=" * 70)
    print("STARTING OPTIMIZATION")
    print("=" * 70)

    study.optimize(
        objective,
        n_trials=n_trials,
        timeout=timeout,
        show_progress_bar=True,
        gc_after_trial=True,
    )

    # Results
    print("\n" + "=" * 70)
    print("OPTIMIZATION RESULTS")
    print("=" * 70)

    print(f"\nBest trial: {study.best_trial.number}")
    print(f"Best MAE: ${study.best_value:.2f}")
    print(f"\nBest hyperparameters:")
    for key, value in study.best_params.items():
        print(f"  {key}: {value}")

    # Compare to baseline
    print("\n" + "-" * 70)
    print("COMPARISON TO BASELINE CONFIGS")
    print("-" * 70)

    baseline_configs = {
        'Original (dropout=0.9)': 44.58,
        'Deep (8 blocks)': 43.56,
        'Wide (128 ff_dim)': 44.08,
        'Previous best': 43.25,  # From long training
    }

    for name, mae in baseline_configs.items():
        improvement = (mae - study.best_value) / mae * 100
        print(f"  vs {name}: {improvement:+.1f}%")

    # Top 5 trials
    print("\n" + "-" * 70)
    print("TOP 5 TRIALS")
    print("-" * 70)

    trials_df = study.trials_dataframe()
    trials_df = trials_df.sort_values('value').head(5)

    for idx, row in trials_df.iterrows():
        print(f"\n  Trial {int(row['number'])}: ${row['value']:.2f}")
        for col in trials_df.columns:
            if col.startswith('params_'):
                param_name = col.replace('params_', '')
                print(f"    {param_name}: {row[col]}")

    # Save results
    output_dir = Path(__file__).parent.parent / 'logs'
    output_dir.mkdir(exist_ok=True)

    results = {
        'study_name': 'tsmixer_optimization',
        'n_trials': len(study.trials),
        'best_trial': study.best_trial.number,
        'best_value': float(study.best_value),
        'best_params': study.best_params,
        'optimization_date': datetime.now().isoformat(),
        'device': DEVICE,
        'trial_max_steps': TRIAL_MAX_STEPS,
        'all_trials': [
            {
                'number': t.number,
                'value': float(t.value) if t.value is not None else None,
                'params': t.params,
                'state': str(t.state),
            }
            for t in study.trials
        ],
    }

    output_path = output_dir / 'optuna_tsmixer_results.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_path}")

    # Generate best config for training
    print("\n" + "=" * 70)
    print("RECOMMENDED TSMIXER CONFIG")
    print("=" * 70)

    best_config = {
        'input_size': study.best_params['input_size'],
        'horizon': 24,
        'n_block': study.best_params['n_block'],
        'ff_dim': study.best_params['ff_dim'],
        'dropout': study.best_params['dropout'],
        'revin': study.best_params['revin'],
        'learning_rate': study.best_params['learning_rate'],
        'batch_size': study.best_params['batch_size'],
        'max_steps': 10000,  # For final training
        'val_check_steps': 100,
        'early_stop_patience': 20,
    }

    print("\nTSMIXER_CONFIG = {")
    for key, value in best_config.items():
        if isinstance(value, str):
            print(f"    '{key}': '{value}',")
        elif isinstance(value, bool):
            print(f"    '{key}': {value},")
        elif isinstance(value, float):
            print(f"    '{key}': {value:.6f},")
        else:
            print(f"    '{key}': {value},")
    print("}")

    # Save best config
    config_path = output_dir / 'optuna_best_tsmixer_config.json'
    with open(config_path, 'w') as f:
        json.dump(best_config, f, indent=2)

    print(f"\nBest config saved to: {config_path}")

    return study, results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Optuna TSMixer Hyperparameter Search')
    parser.add_argument('--n-trials', type=int, default=N_TRIALS,
                        help=f'Number of trials (default: {N_TRIALS})')
    parser.add_argument('--timeout', type=int, default=TIMEOUT,
                        help=f'Timeout in seconds (default: {TIMEOUT})')
    parser.add_argument('--steps-per-trial', type=int, default=TRIAL_MAX_STEPS,
                        help=f'Training steps per trial (default: {TRIAL_MAX_STEPS})')

    args = parser.parse_args()

    # Update global
    TRIAL_MAX_STEPS = args.steps_per_trial

    study, results = run_optuna_search(
        n_trials=args.n_trials,
        timeout=args.timeout,
    )
