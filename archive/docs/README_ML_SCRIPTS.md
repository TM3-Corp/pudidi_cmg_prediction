# ML Scripts for CMG Price Prediction

This directory contains all scripts used for training and evaluating the CMG price prediction models.

## Quick Start

```bash
# Activate virtual environment
source /home/paul/projects/Pudidi/.venv/bin/activate

# Run the best performing model (Enhanced Hybrid Ensemble)
python train_enhanced_tsmixer.py --n-ensemble 3 --aggregation mean
```

---

## Script Inventory

### 1. Core Training Scripts

#### `train_enhanced_tsmixer.py` ⭐ BEST RESULTS
**Purpose**: Train the enhanced hybrid ensemble with SOTA techniques.
**Result**: $34.85 MAE (45.2% improvement)

```bash
python train_enhanced_tsmixer.py --n-ensemble 3 --aggregation mean
```

**Features**:
- Deep ensemble (multiple TSMixer models with different seeds)
- Data augmentation (jittering, scaling)
- Stochastic Weight Averaging
- Hybrid routing (TSMixer for short-term, ML for medium-term)

---

#### `train_hybrid_tsmixer_ensemble.py`
**Purpose**: Train hybrid ensemble combining TSMixer and ML models.
**Result**: $35.66 MAE (43.9% improvement)

```bash
# Standard training (2000 steps)
python train_hybrid_tsmixer_ensemble.py

# Long training (10000 steps)
python train_hybrid_tsmixer_ensemble.py --long-training

# Quick test (100 steps)
python train_hybrid_tsmixer_ensemble.py --quick-test
```

**Configuration** (Optuna-optimized):
```python
TSMIXER_CONFIG = {
    'input_size': 336,      # 2 weeks
    'n_block': 10,          # 10 mixing layers
    'ff_dim': 128,          # Feed-forward dimension
    'dropout': 0.308,       # Dropout rate
    'learning_rate': 5.9e-4,
    'batch_size': 64,
}
```

---

#### `train_stacked_ensemble.py`
**Purpose**: Train stacked ensemble with meta-learner for learned weights.
**Result**: $41.10 MAE (simple average was better than meta-learner)

```bash
python train_stacked_ensemble.py --tsmixer-steps 2000 --meta-type ridge
```

**Note**: This approach underperformed compared to hybrid routing due to meta-learner overfitting.

---

### 2. Hyperparameter Optimization

#### `optuna_tsmixer_search.py` ⭐ CRITICAL
**Purpose**: Bayesian hyperparameter optimization using Optuna.
**Result**: Found optimal config with $36.29 MAE

```bash
# Full search (30 trials, 2 hours)
python optuna_tsmixer_search.py --n-trials 30 --timeout 7200

# Quick search (10 trials)
python optuna_tsmixer_search.py --n-trials 10 --timeout 3600
```

**Search Space**:
| Parameter | Search Range | Best Value |
|-----------|--------------|------------|
| input_size | [96, 168, 336] | 336 |
| n_block | [2, 12] | 10 |
| ff_dim | [32, 64, 128, 256] | 128 |
| dropout | [0.1, 0.7] | 0.308 |
| learning_rate | [1e-5, 1e-3] | 5.9e-4 |
| batch_size | [16, 32, 64] | 64 |

---

#### `tsmixer_hyperparameter_search.py`
**Purpose**: Manual grid search over TSMixer configurations.
**Result**: Found "Deep (8 blocks)" as best manual config

```bash
python tsmixer_hyperparameter_search.py
```

**Configurations tested**:
- Original (notebook): n_block=2, dropout=0.9
- Optimized: n_block=4, dropout=0.5
- Deep: n_block=8, dropout=0.3
- Wide: ff_dim=128
- Long input: input_size=336
- No RevIN: revin=False

---

### 3. Model Comparison Scripts

#### `compare_tsmixer_vs_xgboost.py`
**Purpose**: Fair comparison between TSMixer and gradient boosting models.

```bash
python compare_tsmixer_vs_xgboost.py --test-days 30
```

**Ensures**:
- Same test period for all models
- No data leakage
- Proper temporal split

---

### 4. Feature Engineering

#### `ml_feature_engineering.py`
**Purpose**: Create features for gradient boosting models.

**Features created** (78 total):
- **Lag features**: [1, 2, 3, 6, 12, 24, 48, 168] hours
- **Rolling statistics**: mean, std, min, max, range for windows [6, 12, 24, 48, 168]
- **Time features**: hour, day_of_week, month (cyclical encoding)
- **Zero patterns**: count, ratio, hours_since_zero
- **Trend features**: 1h, 24h, 48h changes

**Usage**:
```python
from ml_feature_engineering import CleanCMGFeatureEngineering

engineer = CleanCMGFeatureEngineering(
    target_horizons=list(range(1, 25)),
    rolling_windows=[6, 12, 24, 48, 168],
    lag_hours=[1, 2, 3, 6, 12, 24, 48, 168]
)

df_features = engineer.create_features(df, cmg_column='CMG [$/MWh]')
feature_names = engineer.get_feature_names()
```

---

### 5. Production Inference

#### `ml_hourly_forecast.py`
**Purpose**: Generate hourly forecasts for production deployment.

```bash
python ml_hourly_forecast.py
```

**Pipeline stages**:
1. Load latest CMG data (168 hours)
2. Create features
3. Load trained models
4. Generate 24-hour forecast
5. Save predictions

---

### 6. Utility Scripts

#### `run_full_optimization.sh`
**Purpose**: Run complete optimization pipeline sequentially.

```bash
chmod +x run_full_optimization.sh
./run_full_optimization.sh
```

**Steps**:
1. Optuna hyperparameter search
2. Stacked ensemble training

---

## Directory Structure

```
scripts/
├── train_enhanced_tsmixer.py      # ⭐ Best model
├── train_hybrid_tsmixer_ensemble.py
├── train_stacked_ensemble.py
├── optuna_tsmixer_search.py       # ⭐ Hyperparameter optimization
├── tsmixer_hyperparameter_search.py
├── compare_tsmixer_vs_xgboost.py
├── ml_feature_engineering.py
├── ml_hourly_forecast.py
├── run_full_optimization.sh
└── README_ML_SCRIPTS.md           # This file
```

---

## Model Outputs

### Saved Models Location

| Model Type | Directory |
|------------|-----------|
| Hybrid Ensemble | `models_hybrid_tsmixer/` |
| Enhanced Ensemble | `models_enhanced_tsmixer/` |
| Stacked Ensemble | `models_stacked_ensemble/` |
| Production Models | `models_24h/` |

### Results Logs

| Log Type | Directory |
|----------|-----------|
| Training logs | `logs/` |
| Optuna results | `logs/optuna_tsmixer_results.json` |
| Best config | `logs/optuna_best_tsmixer_config.json` |

---

## Performance Summary

| Script | Model | MAE | Improvement |
|--------|-------|-----|-------------|
| `train_enhanced_tsmixer.py` | Hybrid Enhanced | **$34.85** | **45.2%** |
| `train_hybrid_tsmixer_ensemble.py` | Hybrid (Optuna) | $35.66 | 43.9% |
| `train_stacked_ensemble.py` | Simple Average | $41.10 | 35.3% |
| Baseline | Persistence | $63.57 | 0% |

---

## Hardware Requirements

- **GPU**: NVIDIA GPU with 8GB+ VRAM (RTX 4060 or better)
- **RAM**: 16GB minimum
- **CUDA**: 12.x

Check GPU availability:
```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
```

---

## Common Issues

### 1. Out of Memory (OOM)
Reduce batch size:
```python
TSMIXER_CONFIG['batch_size'] = 32  # Instead of 64
```

### 2. CUDA Not Found
Install PyTorch with CUDA:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

### 3. Training Too Slow
- Use GPU (10x faster than CPU)
- Reduce `max_steps` for quick tests
- Use `--quick-test` flag

---

*Last updated: 2026-01-29*
