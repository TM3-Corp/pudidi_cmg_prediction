# Model Evaluation Methodology

This document describes the methodology used to evaluate and compare CMG prediction models.

## Core Principles

### 1. Walk-Forward Validation
All models are evaluated using walk-forward (expanding window) validation:
- Train on data up to time T
- Predict for time T+1 to T+24
- Expand training window and repeat
- Never look ahead - predictions only use past data

### 2. Same Test Period
For fair comparison, all models must be evaluated on the **same test period**:
- Current benchmark period: **December 2025**
- Future comparisons should use the same period or clearly state differences

### 3. Consistent Metrics
Primary metrics for each task:

**CMG Price Prediction**:
- **Primary**: Mean Absolute Error (MAE) in $/MWh
- **Secondary**: RMSE, R-squared

**CMG Zero Detection**:
- **Primary**: Recall (prioritize catching zeros)
- **Secondary**: Precision, F1, AUC-ROC

## Evaluation Protocol

### Step 1: Data Split
```
|-------- Training --------|--- Test ---|
                           ^
                     Dec 1, 2025
```
- Training: All data before December 2025
- Test: December 2025 (31 days, 744 hours)

### Step 2: Feature Engineering
- All features computed only from past data
- No future leakage (e.g., same-day values)
- Lag features start from t-1 minimum

### Step 3: Model Training
- Train on expanding window up to start of test
- Hyperparameters tuned on validation set (last 30 days of training)
- Final model trained on full training set

### Step 4: Prediction Generation
For each hour in test period:
1. Create features from available data (up to previous hour)
2. Generate 24-hour forecast (t+1 to t+24)
3. Store predictions for later analysis

### Step 5: Metric Calculation
```python
# Price Prediction
mae = np.mean(np.abs(y_true - y_pred))

# Zero Detection
recall = true_positives / (true_positives + false_negatives)
precision = true_positives / (true_positives + false_positives)
```

## Baselines

### Persistence Baseline (CMG Price)
- Predict tomorrow's value equals today's value at same hour
- Formula: `CMG[t+h] = CMG[t-24+h]`
- December 2025 MAE: **$63.57**

### Majority Class Baseline (Zero Detection)
- Always predict the majority class
- Varies by hour and season

## Reporting Standards

When reporting new model results:

1. **Required Information**:
   - Date of experiment
   - Script used (with path)
   - Test period used
   - MAE or primary metric
   - Comparison to baseline

2. **Optional but Recommended**:
   - Training time
   - Inference time per prediction
   - Model size (MB)
   - Hyperparameters used

3. **Log Format**:
```markdown
| Date | Model | Script | Test Period | MAE | Notes |
|------|-------|--------|-------------|-----|-------|
| YYYY-MM-DD | Model Name | script.py | Mon YYYY | $XX.XX | Brief notes |
```

## Common Pitfalls

### Avoid These Mistakes

1. **Future Leakage**
   - Using same-day actual values in features
   - Using future data in rolling calculations

2. **Inconsistent Test Periods**
   - Comparing models on different time ranges
   - Cherry-picking favorable test periods

3. **Overfitting to Test Set**
   - Repeatedly tuning on test data
   - Using test set for hyperparameter selection

4. **Missing Baseline Comparison**
   - Always compare to persistence baseline
   - Report improvement percentage

## Seasonal Considerations

CMG patterns vary by season:
- **Summer (Dec-Feb)**: More CMG=0 hours (solar)
- **Winter (Jun-Aug)**: Higher average CMG
- **Transition (Mar-May, Sep-Nov)**: Variable patterns

When comparing models across seasons, normalize for seasonal effects or use matched periods.
