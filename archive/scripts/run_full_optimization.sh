#!/bin/bash
# Full optimization pipeline: Optuna search + Stacked ensemble training
# This script runs sequentially to avoid GPU memory conflicts

set -e

VENV="/home/paul/projects/Pudidi/.venv/bin/python"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../logs"
TIMESTAMP=$(date +%Y%m%d_%H%M)

mkdir -p "$LOG_DIR"

echo "=============================================="
echo "FULL OPTIMIZATION PIPELINE"
echo "=============================================="
echo "Started at: $(date)"
echo ""

# Step 1: Optuna Hyperparameter Search
echo "[1/2] OPTUNA HYPERPARAMETER SEARCH"
echo "----------------------------------------------"
OPTUNA_LOG="${LOG_DIR}/optuna_search_${TIMESTAMP}.log"
echo "Log: $OPTUNA_LOG"
echo ""

$VENV "${SCRIPT_DIR}/optuna_tsmixer_search.py" \
    --n-trials 30 \
    --timeout 7200 \
    --steps-per-trial 500 \
    2>&1 | tee "$OPTUNA_LOG"

echo ""
echo "Optuna search completed at: $(date)"
echo ""

# Step 2: Stacked Ensemble Training
echo "[2/2] STACKED ENSEMBLE TRAINING"
echo "----------------------------------------------"
STACKED_LOG="${LOG_DIR}/stacked_ensemble_${TIMESTAMP}.log"
echo "Log: $STACKED_LOG"
echo ""

$VENV "${SCRIPT_DIR}/train_stacked_ensemble.py" \
    --tsmixer-steps 2000 \
    --meta-type ridge \
    2>&1 | tee "$STACKED_LOG"

echo ""
echo "=============================================="
echo "PIPELINE COMPLETED"
echo "=============================================="
echo "Finished at: $(date)"
echo ""
echo "Results:"
echo "  - Optuna results: ${LOG_DIR}/optuna_tsmixer_results.json"
echo "  - Stacked model: models_stacked_ensemble/"
echo ""
