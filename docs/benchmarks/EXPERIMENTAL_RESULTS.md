# Experimental Results Log

This document tracks all model experiments with dates, configurations, and results.

## Summary Table

| Date | Model | Script | Test Period | MAE | Status | Notes |
|------|-------|--------|-------------|-----|--------|-------|
| 2026-01-29 | Enhanced Hybrid TSMixer | train_enhanced_tsmixer.py | Dec 2025 | **$34.85** | Best | Dynamic regime detection |
| 2026-01-29 | Hybrid TSMixer+ML | train_hybrid_tsmixer_ensemble.py | Dec 2025 | $35.66 | Experimental | Dynamic routing between TSMixer/ML |
| 2026-01-29 | TSMixer (Optuna) | optuna_tsmixer_search.py | Dec 2025 | $36.29 | Experimental | Hyperparameter-optimized TSMixer |
| 2026-01-29 | Stacked Ensemble | train_stacked_ensemble.py | Dec 2025 | $41.10 | Archived | Meta-learner overfitted |
| 2025-11 | LightGBM + XGBoost | ml_model_training.py | Nov 2025 | ~$40 | Production | Current production ensemble |
| Baseline | Persistence | - | - | $63.57 | Baseline | CMG[t+h] = CMG[t-24] |

## Detailed Experiment Notes

### Enhanced Hybrid TSMixer (Best: $34.85)
**Date**: 2026-01-29
**Script**: `scripts/training/train_enhanced_tsmixer.py`
**Status**: Best experimental result

**Key Features**:
- Dynamic regime detection (high volatility vs stable)
- Adaptive blending between TSMixer and ML predictions
- Enhanced feature engineering with regime indicators

**Results**:
```
MAE: $34.85 (13% improvement over production)
Test Period: December 2025
```

**Path Forward**: Consider deploying after extended validation period

---

### Hybrid TSMixer+ML ($35.66)
**Date**: 2026-01-29
**Script**: `scripts/training/train_hybrid_tsmixer_ensemble.py`
**Status**: Experimental

**Architecture**:
- TSMixer for sequence modeling
- ML (LightGBM/XGBoost) for tabular features
- Dynamic routing based on prediction confidence

**Results**:
```
MAE: $35.66
Test Period: December 2025
```

---

### TSMixer with Optuna ($36.29)
**Date**: 2026-01-29
**Script**: `scripts/training/optuna_tsmixer_search.py`
**Status**: Experimental

**Hyperparameters Found**:
- See `optuna_tsmixer_results.json` for details
- Extensive search over learning rate, layers, hidden dims

**Results**:
```
MAE: $36.29
Trials: 100 Optuna trials
Test Period: December 2025
```

---

### Stacked Ensemble ($41.10) - ARCHIVED
**Date**: 2026-01-29
**Script**: Archived to `archive/scripts/train_stacked_ensemble.py`
**Status**: Archived - Underperformed

**Why It Failed**:
- Meta-learner overfit to training patterns
- Added complexity without benefit
- Worse than simple averaging

**Results**:
```
MAE: $41.10 (worse than base models)
Conclusion: Simple averaging > complex stacking
```

---

### Production LightGBM + XGBoost (~$40)
**Date**: November 2025
**Script**: `scripts/training/ml_model_training.py`
**Status**: Current Production

**Architecture**:
- 24 LightGBM models (one per horizon)
- 24 XGBoost models (one per horizon)
- Simple averaging of predictions

**Why It Works**:
- Robust to outliers
- Fast inference
- Well-calibrated for most hours

---

## Key Learnings

1. **Simple averaging beats complex stacking** - The meta-learner experiment showed that complex stacking can overfit

2. **Regime detection helps** - The enhanced hybrid with regime detection achieved best results

3. **Deep learning viable but marginal** - TSMixer shows promise but gains are incremental over well-tuned ML

4. **Test period matters** - December 2025 was used for fair comparison; results may vary by season

## Future Experiments

- [ ] Seasonal model variants (summer vs winter)
- [ ] Extended test period validation for enhanced hybrid
- [ ] Real-time model performance monitoring
- [ ] Ensemble with NeuralProphet for trend/seasonality
