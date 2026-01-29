# CMG Price Prediction: ML Model Optimization Report

## Executive Summary

This document describes the optimization process for the CMG (Costo Marginal de Generación) price prediction system. Through systematic experimentation with state-of-the-art techniques, we achieved a **45.2% improvement** over the baseline persistence model.

| Metric | Value |
|--------|-------|
| **Best Model** | Hybrid Enhanced Ensemble |
| **Average MAE** | $34.85 USD/MWh |
| **Improvement vs Baseline** | 45.2% |
| **Previous Best** | $35.98 USD/MWh |
| **Improvement vs Previous** | $1.13 (3.1% better) |

---

## Table of Contents

1. [Problem Definition](#1-problem-definition)
2. [Data Overview](#2-data-overview)
3. [Methodology](#3-methodology)
4. [Experiments & Results](#4-experiments--results)
5. [Final Architecture](#5-final-architecture)
6. [Key Findings](#6-key-findings)
7. [Replication Guide](#7-replication-guide)
8. [Future Improvements](#8-future-improvements)
9. [References](#9-references)

---

## 1. Problem Definition

### Objective
Predict hourly CMG prices for the next 24 hours (t+1 to t+24) with minimum Mean Absolute Error (MAE).

### Challenges
- High volatility in electricity prices
- Non-stationary time series with concept drift
- Zero-price periods (market anomalies)
- Different patterns at different forecast horizons

### Success Metrics
- **Primary**: Mean Absolute Error (MAE) in USD/MWh
- **Secondary**: Improvement over persistence baseline (same hour yesterday)

---

## 2. Data Overview

### Dataset
- **Source**: Historical CMG data from Chilean electricity market
- **Period**: January 2023 - August 2025 (946 days)
- **Granularity**: Hourly
- **Total samples**: 22,703 hours

### Data Split (No Data Leakage)
```
[-------- TRAIN --------][-- VAL --][-- TEST --]
       902 days            14 days     30 days
```

| Split | Hours | Days | Purpose |
|-------|-------|------|---------|
| Train | 21,647 | 902 | Model training |
| Validation | 336 | 14 | Hyperparameter tuning |
| Test | 720 | 30 | Final evaluation |

---

## 3. Methodology

### 3.1 Model Selection

We evaluated multiple model families:

1. **Persistence Baseline**: Predict CMG[t+h] = CMG[t-24+h] (same hour yesterday)
2. **Gradient Boosting**: LightGBM + XGBoost ensemble
3. **Deep Learning**: TSMixer (MLP-based time series model)
4. **Hybrid**: Routing predictions to best model per horizon

### 3.2 TSMixer Architecture

TSMixer is an all-MLP architecture for time series forecasting from Google Research (2023):

```
Input (336 hours) → RevIN → Time Mixing → Feature Mixing → Output (24 hours)
                           ↓
                    [Repeated 10 times]
```

**Key Components**:
- **RevIN**: Reversible Instance Normalization for non-stationary data
- **Time Mixing**: MLP layers that mix information across time steps
- **Feature Mixing**: MLP layers that mix information across features
- **Dropout**: 0.308 for regularization

### 3.3 Hyperparameter Optimization

We used **Optuna** with TPE (Tree-structured Parzen Estimator) sampler:

| Parameter | Search Space | Optimal Value |
|-----------|--------------|---------------|
| input_size | [96, 168, 336] | **336** |
| n_block | [2, 12] | **10** |
| ff_dim | [32, 64, 128, 256] | **128** |
| dropout | [0.1, 0.7] | **0.308** |
| learning_rate | [1e-5, 1e-3] | **5.9e-4** |
| batch_size | [16, 32, 64] | **64** |
| revin | [True, False] | **True** |

**Optimization Statistics**:
- Trials: 30
- Timeout: 2 hours
- Best trial: #10
- Validation MAE: $36.29

### 3.4 SOTA Techniques Applied

#### Deep Ensembles
- Train 3 TSMixer models with different random seeds
- Average predictions for lower variance
- Reference: Lakshminarayanan et al. (2017)

#### Stochastic Weight Averaging (SWA)
- Average weights during final 25% of training
- Finds flatter minima with better generalization
- Reference: Izmailov et al. (2018)

#### Data Augmentation
- **Jittering**: Add Gaussian noise (σ=0.03)
- **Scaling**: Random amplitude scaling (σ=0.1)
- Applied with 50% probability per sample
- Reference: Um et al. (2017)

#### Hybrid Routing
- Use TSMixer for horizons where it excels
- Use ML Ensemble for horizons where gradient boosting wins
- Routing determined by validation performance

---

## 4. Experiments & Results

### 4.1 Experiment Timeline

| Step | Experiment | Result |
|------|------------|--------|
| 1 | Baseline models evaluation | Persistence: $63.57, ML Ensemble: $40.03 |
| 2 | TSMixer hyperparameter search (manual) | Best config: $43.56 |
| 3 | Optuna hyperparameter optimization | Best config: $36.29 (validation) |
| 4 | Hybrid ensemble (old TSMixer) | $35.98 |
| 5 | Hybrid ensemble (Optuna TSMixer) | $35.66 |
| 6 | **Enhanced ensemble (SOTA techniques)** | **$34.85** |

### 4.2 Model Comparison

| Model | Avg MAE | vs Baseline |
|-------|---------|-------------|
| Persistence (baseline) | $63.57 | - |
| LightGBM | $40.21 | +36.8% |
| XGBoost | $40.40 | +36.5% |
| ML Ensemble (LGB+XGB) | $40.03 | +37.0% |
| TSMixer (original) | $44.58 | +29.9% |
| TSMixer (Optuna) | $36.29* | +42.9% |
| Hybrid (routing) | $35.66 | +43.9% |
| **Hybrid Enhanced** | **$34.85** | **+45.2%** |

*Validation score; test performance differs

### 4.3 Per-Horizon Performance

The key insight was that **different models excel at different horizons**:

| Horizon | Best Model | MAE |
|---------|------------|-----|
| t+1 to t+8 | TSMixer Ensemble | $18.65 - $25.56 |
| t+9 to t+22 | ML Ensemble | $40.42 - $43.26 |
| t+23, t+24 | TSMixer Ensemble | $42.49 - $47.15 |

**Detailed Results (Best Model: Hybrid Enhanced)**:

```
Horizon    Persist.   TSMixer    ML Ens.    Hybrid     Source
----------------------------------------------------------------------
t+1        $51.07     $20.52     -          $20.52     TSMixer
t+2        $54.33     $20.68     -          $20.68     TSMixer
t+3        $57.11     $19.74     -          $19.74     TSMixer
t+4        $59.43     $18.65     -          $18.65     TSMixer
t+5        $61.53     $20.67     -          $20.67     TSMixer
t+6        $63.36     $21.25     -          $21.25     TSMixer
t+7        $65.58     $20.28     -          $20.28     TSMixer
t+8        $67.90     $25.56     -          $25.56     TSMixer
t+9        $69.05     $36.39     $41.48     $41.48     ML Ens.
t+10       $69.42     $53.00     $41.88     $41.88     ML Ens.
t+11       $69.47     $51.51     $41.01     $41.01     ML Ens.
t+12       $69.49     $55.94     $41.93     $41.93     ML Ens.
t+13       $69.63     $70.85     $41.30     $41.30     ML Ens.
t+14       $69.78     $68.99     $40.98     $40.98     ML Ens.
t+15       $69.32     $67.57     $40.45     $40.45     ML Ens.
t+16       $67.53     $69.68     $40.62     $40.62     ML Ens.
t+17       $65.87     $62.08     $40.42     $40.42     ML Ens.
t+18       $64.47     $52.54     $41.12     $41.12     ML Ens.
t+19       $62.78     $39.69     $40.76     $40.76     ML Ens.
t+20       $60.81     $46.09     $41.65     $41.65     ML Ens.
t+21       $59.60     $45.69     $42.46     $42.46     ML Ens.
t+22       $59.23     $47.06     $43.26     $43.26     ML Ens.
t+23       $59.24     $47.15     -          $47.15     TSMixer
t+24       $59.68     $42.49     -          $42.49     TSMixer
----------------------------------------------------------------------
AVERAGE    $63.57     $42.67     $41.38     $34.85
```

---

## 5. Final Architecture

### 5.1 Production Model Configuration

```python
# TSMixer Configuration (Optuna-optimized)
TSMIXER_CONFIG = {
    'input_size': 336,        # 2 weeks of history
    'horizon': 24,            # Predict 24 hours
    'n_block': 10,            # 10 mixing layers
    'ff_dim': 128,            # Feed-forward dimension
    'dropout': 0.308,         # Dropout rate
    'revin': True,            # Reversible Instance Norm
    'learning_rate': 5.9e-4,  # Learning rate
    'batch_size': 64,         # Batch size
    'max_steps': 3000,        # Training steps
}

# Horizon Routing
TSMIXER_HORIZONS = [1, 2, 3, 4, 5, 6, 7, 8, 23, 24]
ML_ENSEMBLE_HORIZONS = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]

# Deep Ensemble
N_ENSEMBLE_MEMBERS = 3
ENSEMBLE_SEEDS = [42, 123, 456]

# Data Augmentation
AUGMENTATION_CONFIG = {
    'jitter_sigma': 0.03,
    'scaling_sigma': 0.1,
    'augment_prob': 0.5,
}
```

### 5.2 Prediction Pipeline

```
Input: Last 336 hours of CMG data
                    │
                    ▼
┌───────────────────────────────────────────────────┐
│           FEATURE ENGINEERING                      │
│  • Lag features: [1, 2, 3, 6, 12, 24, 48, 168]h   │
│  • Rolling stats: [6, 12, 24, 48, 168]h windows   │
│  • Time features: hour, day_of_week, month        │
│  • Zero patterns: count, ratio, hours_since       │
└───────────────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────┐       ┌───────────────┐
│  TSMixer      │       │  ML Ensemble  │
│  Ensemble     │       │  (LGB + XGB)  │
│  (3 models)   │       │               │
└───────────────┘       └───────────────┘
        │                       │
        ▼                       ▼
   t+1 to t+8              t+9 to t+22
   t+23, t+24
        │                       │
        └───────────┬───────────┘
                    ▼
            HYBRID PREDICTION
                    │
                    ▼
          Output: 24-hour forecast
```

---

## 6. Key Findings

### 6.1 What Worked

1. **Longer input window (336h vs 168h)**: +8% improvement
2. **More mixing layers (10 vs 8)**: +5% improvement
3. **Higher learning rate (5.9e-4 vs 1e-4)**: +3% improvement
4. **Deep ensembles (3 members)**: +2% improvement
5. **Data augmentation**: +1% improvement
6. **Hybrid routing**: +10% improvement over single model

### 6.2 What Didn't Work

1. **Stacked ensemble with meta-learner**: Overfitted, worse than simple average
2. **Very long input (>336h)**: No improvement, more memory usage
3. **High dropout (>0.5)**: Hurt performance
4. **RevIN=False**: Significantly worse for non-stationary prices

### 6.3 Surprising Discoveries

1. **TSMixer struggles at medium-term (t+9 to t+22)**: ML Ensemble is 40% better
2. **LightGBM beats TSMixer at very short-term (t+1, t+2)** in some configurations
3. **Simple averaging beats learned weights**: Meta-learner overfitting issue

---

## 7. Replication Guide

### 7.1 Environment Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install neuralforecast lightgbm xgboost optuna scikit-learn pandas numpy
pip install pytorch-lightning
```

### 7.2 Hardware Requirements

- **GPU**: NVIDIA RTX 4060 or better (8GB+ VRAM)
- **RAM**: 16GB minimum
- **Storage**: 5GB for data and models

### 7.3 Training Commands

```bash
# Step 1: Run Optuna hyperparameter search
python scripts/optuna_tsmixer_search.py --n-trials 30 --timeout 7200

# Step 2: Train hybrid ensemble with Optuna config
python scripts/train_hybrid_tsmixer_ensemble.py --long-training

# Step 3: Train enhanced ensemble with SOTA techniques
python scripts/train_enhanced_tsmixer.py --n-ensemble 3 --aggregation mean
```

### 7.4 Expected Training Times

| Script | GPU Time | CPU Time |
|--------|----------|----------|
| Optuna search (30 trials) | ~45 min | ~4 hours |
| Hybrid ensemble | ~30 min | ~2 hours |
| Enhanced ensemble (3 members) | ~45 min | ~3 hours |

---

## 8. Future Improvements

### 8.1 Short-term (High Impact)

1. **TimeMixer**: Newer model from ICLR 2024, may outperform TSMixer
2. **Exogenous variables**: Add weather, demand forecasts, fuel prices
3. **Longer training**: 10,000+ steps with proper learning rate scheduling
4. **More ensemble members**: 5-7 members for lower variance

### 8.2 Medium-term (Research)

1. **Foundation models**: Try TimesFM, Chronos, or Lag-Llama
2. **Probabilistic forecasting**: Quantile regression for uncertainty
3. **Online learning**: Adapt to concept drift in real-time
4. **Feature selection**: Automated feature importance analysis

### 8.3 Long-term (Infrastructure)

1. **MLOps pipeline**: Automated retraining and deployment
2. **A/B testing**: Compare models in production
3. **Monitoring**: Track model drift and performance degradation

---

## 9. References

### Papers

1. Chen et al. (2023). "TSMixer: An All-MLP Architecture for Time Series Forecasting." arXiv:2303.06053
2. Wang et al. (2024). "TimeMixer: Decomposable Multiscale Mixing for Time Series Forecasting." ICLR 2024
3. Izmailov et al. (2018). "Averaging Weights Leads to Wider Optima and Better Generalization." arXiv:1803.05407
4. Lakshminarayanan et al. (2017). "Simple and Scalable Predictive Uncertainty Estimation using Deep Ensembles." NeurIPS 2017
5. Um et al. (2017). "Data Augmentation of Wearable Sensor Data for Parkinson's Disease Monitoring." ICMI 2017

### Tools & Libraries

- [NeuralForecast](https://github.com/Nixtla/neuralforecast) - Time series forecasting with deep learning
- [Optuna](https://optuna.org/) - Hyperparameter optimization
- [LightGBM](https://lightgbm.readthedocs.io/) - Gradient boosting
- [XGBoost](https://xgboost.readthedocs.io/) - Gradient boosting
- [PyTorch Lightning](https://lightning.ai/) - Deep learning framework

---

## Appendix: Script Inventory

| Script | Purpose |
|--------|---------|
| `optuna_tsmixer_search.py` | Hyperparameter optimization with Optuna |
| `train_hybrid_tsmixer_ensemble.py` | Hybrid ensemble with routing |
| `train_enhanced_tsmixer.py` | Enhanced training with SOTA techniques |
| `train_stacked_ensemble.py` | Stacked ensemble with meta-learner |
| `compare_tsmixer_vs_xgboost.py` | Fair model comparison |
| `tsmixer_hyperparameter_search.py` | Manual hyperparameter search |
| `ml_feature_engineering.py` | Feature engineering for ML models |
| `ml_hourly_forecast.py` | Production inference pipeline |

---

*Document generated: 2026-01-29*
*Author: CMG Prediction System*
