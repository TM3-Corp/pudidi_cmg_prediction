#!/usr/bin/env python3
"""
Evaluacion: Weighted Ensemble + Zero Detection de Produccion
=============================================================

Combina:
- Stage 1 (produccion): Clasificador LGB+XGB de zeros con thresholds calibrados
- Stage 2 (weighted ensemble): TiDE*w + Prod*(1-w) para prediccion de valor

Compara MAE y metricas de deteccion de zeros contra:
- Produccion actual (Stage 1 + Stage 2 LGB+XGB)
- Weighted ensemble sin zero detection (continuo)
- TiDE solo (continuo)

Uso:
    python proposal/evaluation/eval_zero_detection.py
"""

import sys
import os
import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

MODELS_DIR = PROJECT_ROOT / "models_24h"
RESULTS_DIR = PROJECT_ROOT / "proposal" / "results"

import lightgbm as lgb
import xgboost as xgb


# ============================================================================
# ZERO DETECTION (reutiliza Stage 1 de produccion)
# ============================================================================

class ZeroDetector:
    """Wrapper del Stage 1 de produccion para deteccion de zeros."""

    def __init__(self):
        self.models = {}
        self.thresholds = {}
        self.threshold_type = None
        self.stage1_feature_names = None

    def load(self):
        """Carga modelos de zero detection y thresholds calibrados."""
        print("Cargando Stage 1 (zero detection)...")

        # Feature names
        with open(MODELS_DIR / "zero_detection" / "feature_names.pkl", 'rb') as f:
            self.stage1_feature_names = pickle.load(f)
        print(f"  Features: {len(self.stage1_feature_names)}")

        # Thresholds
        npy_path = MODELS_DIR / "zero_detection" / "optimal_thresholds_by_hour_calibrated.npy"
        csv_path = MODELS_DIR / "zero_detection" / "optimal_thresholds_by_hour_calibrated.csv"

        if npy_path.exists():
            arr = np.load(npy_path)
            self.thresholds = {h: float(arr[h]) for h in range(24)}
            self.threshold_type = 'hour-based'
        elif csv_path.exists():
            df = pd.read_csv(csv_path)
            self.thresholds = {int(row['target_hour']): row['threshold'] for _, row in df.iterrows()}
            self.threshold_type = 'hour-based'
        else:
            self.thresholds = {h: 0.5 for h in range(24)}
            self.threshold_type = 'fixed'

        print(f"  Thresholds ({self.threshold_type}): {min(self.thresholds.values()):.3f}-{max(self.thresholds.values()):.3f}")

        # Modelos
        for h in range(1, 25):
            lgb_path = MODELS_DIR / "zero_detection" / f"lgb_t+{h}.txt"
            xgb_path = MODELS_DIR / "zero_detection" / f"xgb_t+{h}.json"
            if lgb_path.exists() and xgb_path.exists():
                self.models[h] = {
                    'lgb': lgb.Booster(model_file=str(lgb_path)),
                    'xgb': xgb.Booster(model_file=str(xgb_path)),
                }

        print(f"  Modelos: {len(self.models)}/24 horizontes")

    def predict_zero_prob(self, X_stage1: pd.DataFrame, horizon: int) -> float:
        """Predice P(CMG=0) para un horizonte dado."""
        if horizon not in self.models:
            return 0.0

        X = X_stage1.reindex(columns=self.stage1_feature_names, fill_value=0)
        lgb_pred = self.models[horizon]['lgb'].predict(X)[0]
        xgb_pred = self.models[horizon]['xgb'].predict(xgb.DMatrix(X))[0]
        return (lgb_pred + xgb_pred) / 2

    def should_be_zero(self, zero_prob: float, target_hour: int) -> bool:
        """Decide si predecir zero basado en threshold calibrado."""
        threshold = self.thresholds.get(target_hour, 0.5)
        return zero_prob > threshold


# ============================================================================
# BACKTESTING CON ZERO DETECTION
# ============================================================================

def run_full_backtesting(test_days: int = 45):
    """
    Ejecuta backtesting completo comparando:
    1. Produccion actual (ya tiene zero detection)
    2. Weighted ensemble SIN zero detection (continuo)
    3. Weighted ensemble CON zero detection (Stage 1 produccion)
    4. TiDE solo SIN zero detection
    5. TiDE solo CON zero detection
    """
    from proposal.utils.data_loader import CMGDataLoader
    from proposal.utils.benchmark import ProductionModelEvaluator
    from ml_feature_engineering import CleanCMGFeatureEngineering

    # Cargar datos
    print("=" * 90)
    print("BACKTESTING: ENSEMBLE + ZERO DETECTION")
    print("=" * 90)

    print("\n[1/5] CARGANDO DATOS")
    loader = CMGDataLoader()
    df_raw = loader.load_cmg_online()
    series = loader.build_averaged_series(df_raw)

    # Cargar predicciones neurales del CV
    cv = pd.read_csv(RESULTS_DIR / "cv_neural_models.csv")
    cv['ds'] = pd.to_datetime(cv['ds'])
    cv = cv.sort_values(['cutoff', 'ds'])
    cv['horizon'] = cv.groupby('cutoff').cumcount() + 1

    # Crear lookup: datetime -> predicciones neurales
    neural_lookup = {}
    for _, row in cv.iterrows():
        neural_lookup[row['ds']] = {
            'TiDE': max(0, row['TiDE']),
            'NHITS': max(0, row['NHITS']),
            'NBEATSx': max(0, row['NBEATSx']),
            'horizon': int(row['horizon']),
        }

    # Cargar modelos
    print("\n[2/5] CARGANDO MODELOS")
    prod_model = ProductionModelEvaluator()
    prod_model.load_models()

    zero_detector = ZeroDetector()
    zero_detector.load()

    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168],
    )

    # Definir periodo test
    cmg = series['CMG [$/MWh]'].dropna()
    test_start = cmg.index.max() - timedelta(days=test_days)

    window_starts = []
    current = cmg.index[cmg.index > test_start][0]
    while current + timedelta(hours=24) <= cmg.index.max():
        if current - timedelta(hours=168) >= cmg.index.min():
            window_starts.append(current)
        current += timedelta(hours=24)

    print(f"\n[3/5] BACKTESTING ({len(window_starts)} ventanas)")

    all_preds = []

    for i, window_start in enumerate(window_starts):
        # Ventana de historia
        history_end = window_start
        history_start = history_end - timedelta(hours=168)
        window_data = series.loc[history_start:history_end].copy()

        if len(window_data) < 140:
            continue

        window_data['CMG [$/MWh]'] = window_data['CMG [$/MWh]'].ffill().fillna(0)

        # Crear features para zero detection
        try:
            df_feat = feature_engineer.create_features(window_data)
            base_cols = [c for c in df_feat.columns
                         if not c.startswith(('is_zero_t+', 'cmg_value_t+'))
                         and c != 'CMG [$/MWh]']
            latest_idx = df_feat.index[-1]
            X_base = df_feat.loc[[latest_idx], base_cols]
        except Exception:
            continue

        # Produccion: generar predicciones completas
        try:
            prod_preds = prod_model.predict_window(window_data)
        except Exception:
            continue

        base_time = latest_idx

        for p in prod_preds:
            h = p['horizon']
            target_dt = p['target_datetime']
            target_hour = target_dt.hour

            # Valor real
            if target_dt not in cmg.index:
                continue
            actual = cmg.loc[target_dt]
            if np.isnan(actual):
                continue

            # Zero detection
            zero_prob = zero_detector.predict_zero_prob(X_base, h)
            is_zero = zero_detector.should_be_zero(zero_prob, target_hour)
            threshold = zero_detector.thresholds.get(target_hour, 0.5)

            # Prediccion produccion (ya tiene zero detection integrado)
            prod_pred = p['predicted_cmg']

            # Predicciones neurales
            neural = neural_lookup.get(target_dt)
            if neural is None:
                continue

            tide_raw = neural['TiDE']
            nhits_raw = neural['NHITS']

            # Weighted ensemble (sin zero detection)
            w = max(0, 1 - (h - 1) / 24)
            weighted_raw = w * tide_raw + (1 - w) * prod_pred

            # Weighted ensemble CON zero detection
            # Usa valor del ensemble pero respeta decision de Stage 1
            value_for_weighted = w * tide_raw + (1 - w) * p['value_prediction']
            weighted_with_zd = 0.0 if is_zero else max(0, value_for_weighted)

            # TiDE con zero detection
            tide_with_zd = 0.0 if is_zero else tide_raw

            all_preds.append({
                'window': i,
                'target_datetime': target_dt,
                'horizon': h,
                'target_hour': target_hour,
                'actual': actual,
                'actual_is_zero': actual == 0,
                # Predicciones
                'prod': prod_pred,
                'tide_raw': tide_raw,
                'tide_zd': tide_with_zd,
                'weighted_raw': weighted_raw,
                'weighted_zd': weighted_with_zd,
                # Zero detection info
                'zero_prob': zero_prob,
                'threshold': threshold,
                'predicted_zero': is_zero,
            })

        if (i + 1) % 10 == 0:
            print(f"  Ventana {i+1}/{len(window_starts)}")

    df = pd.DataFrame(all_preds)
    print(f"\n  Total: {len(df)} predicciones, {df['window'].nunique()} ventanas")

    # ================================================================
    # METRICAS
    # ================================================================
    print("\n[4/5] CALCULANDO METRICAS")

    models = {
        'Produccion (LGB+XGB)': df['prod'],
        'TiDE continuo': df['tide_raw'],
        'TiDE + Zero Detection': df['tide_zd'],
        'Weighted continuo': df['weighted_raw'],
        'Weighted + Zero Detection': df['weighted_zd'],
    }

    results = {}
    for name, preds in models.items():
        results[name] = compute_full_metrics(df['actual'], preds, df, name)

    # ================================================================
    # REPORTE
    # ================================================================
    print("\n[5/5] REPORTE")
    print_full_report(results, df)

    # Guardar
    df.to_csv(RESULTS_DIR / "ensemble_zero_detection_predictions.csv", index=False)

    summary = {}
    for name, m in results.items():
        summary[name] = {k: v for k, v in m.items() if k not in ('h_mae', 'h_zero')}
        summary[name]['horizon_mae'] = {str(k): v for k, v in m.get('h_mae', {}).items()}

    with open(RESULTS_DIR / "ensemble_zero_detection_comparison.json", 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nResultados guardados en {RESULTS_DIR}/")
    return results


def compute_full_metrics(actual, predicted, df, name):
    """Calcula MAE + metricas de zero detection."""
    y = actual.values
    p = predicted.values

    errors = np.abs(y - p)
    sq = (y - p) ** 2
    nonzero = y != 0
    mape = np.mean(errors[nonzero] / y[nonzero]) * 100 if nonzero.sum() > 0 else np.nan

    # Bloques horizonte
    h = df['horizon'].values
    short = errors[h <= 6].mean()
    mid = errors[(h > 6) & (h <= 12)].mean()
    long_ = errors[h > 12].mean()

    # MAE por horizonte
    h_mae = {}
    for hi in range(1, 25):
        mask = h == hi
        if mask.sum() > 0:
            h_mae[hi] = float(errors[mask].mean())

    # Zero detection
    true_zero = y == 0
    pred_zero = p == 0

    tp = int((true_zero & pred_zero).sum())
    fp = int((~true_zero & pred_zero).sum())
    fn = int((true_zero & ~pred_zero).sum())
    tn = int((~true_zero & ~pred_zero).sum())

    n_actual_zeros = int(true_zero.sum())
    n_pred_zeros = int(pred_zero.sum())

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    acc = (tp + tn) / len(y)

    # MAE solo en horas zero vs no-zero
    mae_when_zero = errors[true_zero].mean() if true_zero.sum() > 0 else np.nan
    mae_when_nonzero = errors[~true_zero].mean() if (~true_zero).sum() > 0 else np.nan

    # Zero F1 por horizonte
    h_zero = {}
    for hi in range(1, 25):
        mask = h == hi
        if mask.sum() == 0:
            continue
        tz = true_zero[mask]
        pz = pred_zero[mask]
        tp_h = (tz & pz).sum()
        fp_h = (~tz & pz).sum()
        fn_h = (tz & ~pz).sum()
        p_h = tp_h / (tp_h + fp_h) if (tp_h + fp_h) > 0 else 0
        r_h = tp_h / (tp_h + fn_h) if (tp_h + fn_h) > 0 else 0
        f1_h = 2 * p_h * r_h / (p_h + r_h) if (p_h + r_h) > 0 else 0
        h_zero[hi] = {'f1': f1_h, 'precision': p_h, 'recall': r_h}

    return {
        'mae': float(errors.mean()),
        'rmse': float(np.sqrt(sq.mean())),
        'mape': float(mape),
        'short': float(short),
        'mid': float(mid),
        'long': float(long_),
        'h_mae': h_mae,
        # Zero metrics
        'zero_precision': float(prec),
        'zero_recall': float(rec),
        'zero_f1': float(f1),
        'zero_accuracy': float(acc),
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'n_actual_zeros': n_actual_zeros,
        'n_pred_zeros': n_pred_zeros,
        'mae_when_zero': float(mae_when_zero),
        'mae_when_nonzero': float(mae_when_nonzero),
        'h_zero': h_zero,
        'n': len(y),
    }


def print_full_report(results, df):
    """Imprime reporte comparativo completo: MAE + Zero Detection."""

    print("\n" + "=" * 100)
    print("COMPARATIVA: MAE + DETECCION DE ZEROS")
    print("=" * 100)

    # Contexto
    n_actual_zeros = (df['actual'] == 0).sum()
    n_total = len(df)
    print(f"\nDataset: {n_total} predicciones, {n_actual_zeros} zeros reales ({n_actual_zeros/n_total*100:.1f}%)")

    # Tabla MAE
    print(f"\n{'─' * 100}")
    print("MAE")
    print(f"{'─' * 100}")
    print(f"{'Modelo':<35} {'MAE':>7} {'RMSE':>7} {'Corto':>9} {'Medio':>9} {'Largo':>9} {'MAE(0)':>9} {'MAE(>0)':>9}")
    print(f"{'':35} {'':>7} {'':>7} {'(t+1..6)':>9} {'(t+7..12)':>9} {'(t+13..24)':>9} {'(real=0)':>9} {'(real>0)':>9}")
    print("-" * 100)

    for name in sorted(results, key=lambda x: results[x]['mae']):
        m = results[name]
        print(
            f"{name:<35} "
            f"{m['mae']:>7.2f} "
            f"{m['rmse']:>7.2f} "
            f"${m['short']:>8.2f} "
            f"${m['mid']:>8.2f} "
            f"${m['long']:>8.2f} "
            f"${m['mae_when_zero']:>8.2f} "
            f"${m['mae_when_nonzero']:>8.2f}"
        )

    # Tabla Zero Detection
    print(f"\n{'─' * 100}")
    print("DETECCION DE ZEROS")
    print(f"{'─' * 100}")
    print(f"{'Modelo':<35} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Accuracy':>10} {'Pred 0s':>10} {'Real 0s':>10}")
    print("-" * 100)

    for name in sorted(results, key=lambda x: -results[x]['zero_f1']):
        m = results[name]
        print(
            f"{name:<35} "
            f"{m['zero_precision']:>10.3f} "
            f"{m['zero_recall']:>10.3f} "
            f"{m['zero_f1']:>10.3f} "
            f"{m['zero_accuracy']:>10.3f} "
            f"{m['n_pred_zeros']:>10d} "
            f"{m['n_actual_zeros']:>10d}"
        )

    # Confusion matrix del mejor modelo con ZD
    print(f"\n{'─' * 100}")
    print("MATRIZ DE CONFUSION")
    print(f"{'─' * 100}")

    for name in ['Produccion (LGB+XGB)', 'Weighted + Zero Detection']:
        m = results[name]
        print(f"\n  {name}:")
        print(f"                    Pred=0    Pred>0")
        print(f"    Real=0    {m['tp']:>10d} {m['fn']:>10d}")
        print(f"    Real>0    {m['fp']:>10d} {m['tn']:>10d}")

    # Zero F1 por horizonte
    print(f"\n{'─' * 100}")
    print("ZERO F1 POR HORIZONTE")
    print(f"{'─' * 100}")

    zd_models = ['Produccion (LGB+XGB)', 'Weighted + Zero Detection', 'TiDE + Zero Detection']
    header = f"{'h':<6}" + "".join(f"{n[:25]:>28}" for n in zd_models)
    print(header)
    print("-" * (6 + 28 * len(zd_models)))

    for h in range(1, 25):
        row = f"t+{h:<4}"
        for name in zd_models:
            hz = results[name]['h_zero'].get(h, {})
            f1 = hz.get('f1', 0)
            row += f"{f1:>28.3f}"
        print(row)

    # MAE por horizonte: modelos clave
    print(f"\n{'─' * 100}")
    print("MAE POR HORIZONTE")
    print(f"{'─' * 100}")

    key_models = ['Produccion (LGB+XGB)', 'Weighted continuo', 'Weighted + Zero Detection']
    header = f"{'h':<6}" + "".join(f"{n[:25]:>28}" for n in key_models)
    print(header)
    print("-" * (6 + 28 * len(key_models)))

    for h in range(1, 25):
        row = f"t+{h:<4}"
        for name in key_models:
            v = results[name]['h_mae'].get(h, np.nan)
            row += f"${v:>26.2f}"
        print(row)

    # Resumen final
    prod = results['Produccion (LGB+XGB)']
    wzd = results['Weighted + Zero Detection']
    wraw = results['Weighted continuo']

    print(f"\n{'=' * 100}")
    print("RESUMEN")
    print(f"{'=' * 100}")

    print(f"\n  Weighted + Zero Detection vs Produccion:")
    print(f"    MAE:       ${wzd['mae']:.2f} vs ${prod['mae']:.2f} ({(wzd['mae']-prod['mae'])/prod['mae']*100:+.1f}%)")
    print(f"    Corto:     ${wzd['short']:.2f} vs ${prod['short']:.2f} ({(wzd['short']-prod['short'])/prod['short']*100:+.1f}%)")
    print(f"    Medio:     ${wzd['mid']:.2f} vs ${prod['mid']:.2f} ({(wzd['mid']-prod['mid'])/prod['mid']*100:+.1f}%)")
    print(f"    Largo:     ${wzd['long']:.2f} vs ${prod['long']:.2f} ({(wzd['long']-prod['long'])/prod['long']*100:+.1f}%)")
    print(f"    Zero F1:   {wzd['zero_f1']:.3f} vs {prod['zero_f1']:.3f} ({(wzd['zero_f1']-prod['zero_f1'])/max(prod['zero_f1'],1e-6)*100:+.1f}%)")
    print(f"    MAE(real=0): ${wzd['mae_when_zero']:.2f} vs ${prod['mae_when_zero']:.2f}")

    print(f"\n  Efecto de agregar Zero Detection al Weighted:")
    print(f"    MAE:       ${wzd['mae']:.2f} vs ${wraw['mae']:.2f} ({(wzd['mae']-wraw['mae'])/wraw['mae']*100:+.1f}%)")
    print(f"    Zero F1:   {wzd['zero_f1']:.3f} vs {wraw['zero_f1']:.3f}")
    print(f"    MAE(real=0): ${wzd['mae_when_zero']:.2f} vs ${wraw['mae_when_zero']:.2f}")

    print(f"\n{'=' * 100}")


if __name__ == '__main__':
    results = run_full_backtesting(test_days=45)
