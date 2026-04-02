"""
Benchmark con Backtesting Rolling - CMG Prediction
====================================================

Evalua el modelo de produccion (LightGBM+XGBoost two-stage ensemble)
usando backtesting rolling sobre datos locales.

## Que es el backtesting rolling?

Simula como el modelo hubiera funcionado en produccion dia a dia:

    Serie temporal completa:
    |------- train (168h minimo) -------| pred 24h | real 24h |
                                        t          t+1...t+24

    Ventana 1: Usa datos hasta hora t=168, predice t+1..t+24, compara con real
    Ventana 2: Avanza 24h, usa datos hasta t=192, predice t+193..t+216, compara
    Ventana 3: Avanza 24h, usa datos hasta t=216, predice t+217..t+240, compara
    ...

    Cada ventana:
    1. Toma las ultimas 168 horas como input (igual que produccion)
    2. Genera features con CleanCMGFeatureEngineering
    3. Corre Stage 1 (zero detection) + Stage 2 (value prediction)
    4. Obtiene 24 predicciones (t+1 a t+24)
    5. Compara con los 24 valores reales

    Esto da una evaluacion REALISTA porque:
    - El modelo nunca ve datos futuros
    - Replica exactamente el pipeline de produccion
    - Mide performance por horizonte (t+1 es mas facil que t+24)
    - Captura degradacion del modelo en el tiempo

Uso:
    python proposal/utils/benchmark.py
"""

import sys
import os
import json
import pickle
import numpy as np
import pandas as pd
from datetime import timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

MODELS_DIR = PROJECT_ROOT / "models_24h"


# ============================================================================
# RESULT STRUCTURES
# ============================================================================

@dataclass
class HorizonMetrics:
    """Metricas para un horizonte especifico."""
    horizon: int
    mae: float
    rmse: float
    n_samples: int
    zero_f1: float = 0.0
    zero_precision: float = 0.0
    zero_recall: float = 0.0


@dataclass
class BacktestResult:
    """Resultado completo del backtesting."""
    model_name: str
    mae_global: float
    rmse_global: float
    mape_global: float
    n_windows: int
    n_predictions: int
    horizon_metrics: List[HorizonMetrics] = field(default_factory=list)
    hourly_mae: Dict[int, float] = field(default_factory=dict)
    daily_mae: List[dict] = field(default_factory=list)
    all_predictions: Optional[pd.DataFrame] = None


# ============================================================================
# PRODUCTION MODEL WRAPPER
# ============================================================================

class ProductionModelEvaluator:
    """
    Wrapper del modelo de produccion para backtesting.
    Replica exactamente el pipeline de ml_hourly_forecast.py.
    """

    def __init__(self):
        self.models_loaded = False
        self.models = None
        self.feature_engineer = None
        self.stage1_feature_names = None
        self.stage2_feature_names = None
        self.thresholds = None
        self.threshold_type = None

    def load_models(self):
        """Carga todos los modelos una sola vez."""
        import lightgbm as lgb
        import xgboost as xgb

        print("Cargando modelos de produccion...")

        # Feature names
        with open(MODELS_DIR / "zero_detection" / "feature_names.pkl", 'rb') as f:
            self.stage1_feature_names = pickle.load(f)
        with open(MODELS_DIR / "value_prediction" / "feature_names.pkl", 'rb') as f:
            self.stage2_feature_names = pickle.load(f)

        print(f"  Stage 1 features: {len(self.stage1_feature_names)}")
        print(f"  Stage 2 features: {len(self.stage2_feature_names)}")

        # Thresholds
        self.thresholds, self.threshold_type = self._load_thresholds()

        # Models
        self.models = {'zero_detection': {}, 'value_prediction': {}}

        for h in range(1, 25):
            # Zero detection
            lgb_path = MODELS_DIR / "zero_detection" / f"lgb_t+{h}.txt"
            xgb_path = MODELS_DIR / "zero_detection" / f"xgb_t+{h}.json"
            if lgb_path.exists() and xgb_path.exists():
                self.models['zero_detection'][h] = {
                    'lgb': lgb.Booster(model_file=str(lgb_path)),
                    'xgb': xgb.Booster(model_file=str(xgb_path)),
                }

            # Value prediction
            lgb_med = MODELS_DIR / "value_prediction" / f"lgb_median_t+{h}.txt"
            lgb_q10 = MODELS_DIR / "value_prediction" / f"lgb_q10_t+{h}.txt"
            lgb_q90 = MODELS_DIR / "value_prediction" / f"lgb_q90_t+{h}.txt"
            xgb_val = MODELS_DIR / "value_prediction" / f"xgb_t+{h}.json"
            if all(p.exists() for p in [lgb_med, lgb_q10, lgb_q90, xgb_val]):
                xgb_model = xgb.Booster()
                xgb_model.load_model(str(xgb_val))
                self.models['value_prediction'][h] = {
                    'lgb_median': lgb.Booster(model_file=str(lgb_med)),
                    'lgb_q10': lgb.Booster(model_file=str(lgb_q10)),
                    'lgb_q90': lgb.Booster(model_file=str(lgb_q90)),
                    'xgb': xgb_model,
                }

        print(f"  Zero detection: {len(self.models['zero_detection'])}/24 horizontes")
        print(f"  Value prediction: {len(self.models['value_prediction'])}/24 horizontes")

        # Feature engineer
        from ml_feature_engineering import CleanCMGFeatureEngineering
        self.feature_engineer = CleanCMGFeatureEngineering(
            target_horizons=list(range(1, 25)),
            rolling_windows=[6, 12, 24, 48, 168],
            lag_hours=[1, 2, 3, 6, 12, 24, 48, 168],
        )

        self.models_loaded = True
        print("Modelos cargados.\n")

    def predict_window(self, cmg_window: pd.DataFrame) -> List[dict]:
        """
        Genera prediccion de 24 horas a partir de una ventana de datos.
        Replica exactamente el pipeline de produccion.

        Args:
            cmg_window: DataFrame con DatetimeIndex y columna 'CMG [$/MWh]'
                        Debe tener al menos 168 filas (1 semana)

        Returns:
            Lista de 24 dicts con: horizon, target_datetime, predicted_cmg,
                                    zero_probability, value_prediction,
                                    confidence_lower, confidence_upper
        """
        import xgboost as xgb

        if not self.models_loaded:
            self.load_models()

        # 1. Crear features base (78 features)
        df_feat = self.feature_engineer.create_features(cmg_window)
        base_feature_cols = [c for c in df_feat.columns
                             if not c.startswith(('is_zero_t+', 'cmg_value_t+'))
                             and c != 'CMG [$/MWh]']

        latest_idx = df_feat.index[-1]
        X_base = df_feat.loc[[latest_idx], base_feature_cols]

        # 2. Reordenar para Stage 1
        X_stage1 = X_base.reindex(columns=self.stage1_feature_names, fill_value=0)

        # 3. Generar meta-features de Stage 1
        meta = pd.DataFrame(index=X_base.index)
        for h in range(1, 25):
            if h not in self.models['zero_detection']:
                continue
            lgb_pred = self.models['zero_detection'][h]['lgb'].predict(X_stage1)[0]
            xgb_pred = self.models['zero_detection'][h]['xgb'].predict(
                xgb.DMatrix(X_stage1)
            )[0]
            meta[f'zero_risk_lgb_t+{h}'] = lgb_pred
            meta[f'zero_risk_xgb_t+{h}'] = xgb_pred
            meta[f'zero_risk_avg_t+{h}'] = (lgb_pred + xgb_pred) / 2

        # 4. Combinar base + meta para Stage 2
        X_full = pd.concat([X_base, meta], axis=1)
        X_full = X_full.replace([np.inf, -np.inf], np.nan).fillna(0).clip(-1e6, 1e6)
        X_stage2 = X_full.reindex(columns=self.stage2_feature_names, fill_value=0)

        # 5. Predecir cada horizonte
        base_time = latest_idx
        predictions = []

        for h in range(1, 25):
            if h not in self.models['zero_detection'] or h not in self.models['value_prediction']:
                continue

            target_time = base_time + timedelta(hours=h)

            # Stage 1: Zero probability
            lgb_zero = self.models['zero_detection'][h]['lgb'].predict(X_stage1)[0]
            xgb_zero = self.models['zero_detection'][h]['xgb'].predict(
                xgb.DMatrix(X_stage1)
            )[0]
            zero_prob = (lgb_zero + xgb_zero) / 2

            # Stage 2: Value prediction
            lgb_val = self.models['value_prediction'][h]['lgb_median'].predict(X_stage2)[0]
            xgb_val_pred = self.models['value_prediction'][h]['xgb'].predict(
                xgb.DMatrix(X_stage2)
            )[0]
            value_median = (lgb_val + xgb_val_pred) / 2

            # Quantiles
            val_q10 = self.models['value_prediction'][h]['lgb_q10'].predict(X_stage2)[0]
            val_q90 = self.models['value_prediction'][h]['lgb_q90'].predict(X_stage2)[0]

            # Decision con threshold
            if self.threshold_type == 'hour-based':
                threshold = self.thresholds.get(target_time.hour, 0.5)
            else:
                threshold = self.thresholds.get(h, 0.5)

            final_cmg = 0.0 if zero_prob > threshold else max(0.0, value_median)

            predictions.append({
                'horizon': h,
                'target_datetime': target_time,
                'predicted_cmg': round(final_cmg, 2),
                'zero_probability': round(zero_prob, 4),
                'decision_threshold': round(threshold, 4),
                'value_prediction': round(value_median, 2),
                'confidence_lower': round(val_q10, 2),
                'confidence_upper': round(val_q90, 2),
            })

        return predictions

    def _load_thresholds(self):
        """Carga thresholds de decision."""
        npy_path = MODELS_DIR / "zero_detection" / "optimal_thresholds_by_hour_calibrated.npy"
        csv_path = MODELS_DIR / "zero_detection" / "optimal_thresholds_by_hour_calibrated.csv"

        if npy_path.exists():
            arr = np.load(npy_path)
            d = {h: float(arr[h]) for h in range(24)}
            print(f"  Thresholds hour-based: {min(d.values()):.3f}-{max(d.values()):.3f}")
            return d, 'hour-based'

        if csv_path.exists():
            df = pd.read_csv(csv_path)
            d = {int(row['target_hour']): row['threshold'] for _, row in df.iterrows()}
            print(f"  Thresholds hour-based (csv): {min(d.values()):.3f}-{max(d.values()):.3f}")
            return d, 'hour-based'

        print("  Thresholds: usando 0.5 por defecto")
        return {h: 0.5 for h in range(24)}, 'fixed'


# ============================================================================
# BASELINES
# ============================================================================

def persistence_baseline_24h(series: pd.Series) -> pd.Series:
    """Baseline: CMG sera igual que hace 24h (ayer a la misma hora)."""
    return series.shift(24)


def persistence_baseline_168h(series: pd.Series) -> pd.Series:
    """Baseline: CMG sera igual que hace 168h (semana pasada misma hora)."""
    return series.shift(168)


def mean_baseline(series: pd.Series, window: int = 168) -> pd.Series:
    """Baseline: media movil de las ultimas `window` horas."""
    return series.shift(1).rolling(window, min_periods=24).mean()


# ============================================================================
# BACKTESTING ENGINE
# ============================================================================

def run_backtesting(
    series: pd.DataFrame,
    model: ProductionModelEvaluator,
    test_days: int = 30,
    step_hours: int = 24,
    min_history: int = 168,
    verbose: bool = True,
) -> BacktestResult:
    """
    Ejecuta backtesting rolling del modelo de produccion.

    Proceso:
    1. Define periodo de test (ultimos `test_days` dias)
    2. Para cada ventana de 24h en el test:
       a. Toma las ultimas `min_history` horas como input
       b. Genera 24 predicciones con el modelo
       c. Compara con valores reales
    3. Calcula metricas globales, por horizonte y por hora

    Args:
        series: DataFrame con DatetimeIndex y columna 'CMG [$/MWh]'
        model: ProductionModelEvaluator con modelos cargados
        test_days: Dias de test (los mas recientes)
        step_hours: Avance entre ventanas (24 = una ventana por dia)
        min_history: Horas minimas de historia requeridas (168 = 1 semana)
        verbose: Mostrar progreso

    Returns:
        BacktestResult con todas las metricas
    """
    cmg_col = 'CMG [$/MWh]'
    cmg_series = series[cmg_col].dropna()

    # Definir periodo de test
    test_start = cmg_series.index.max() - timedelta(days=test_days)
    test_mask = cmg_series.index > test_start

    # Encontrar indices de inicio de cada ventana
    test_indices = cmg_series.index[test_mask]
    window_starts = []
    current = test_indices[0]
    while current + timedelta(hours=24) <= cmg_series.index.max():
        # Verificar que hay suficiente historia
        history_start = current - timedelta(hours=min_history)
        if history_start >= cmg_series.index.min():
            window_starts.append(current)
        current += timedelta(hours=step_hours)

    if verbose:
        print(f"\nBACKTESTING ROLLING")
        print(f"  Periodo test: {test_start} -> {cmg_series.index.max()}")
        print(f"  Ventanas: {len(window_starts)}")
        print(f"  Step: {step_hours}h | Historia minima: {min_history}h")
        print()

    # Ejecutar cada ventana
    all_preds = []

    for i, window_start in enumerate(window_starts):
        # Extraer ventana de historia
        history_end = window_start
        history_start = history_end - timedelta(hours=min_history)
        window_data = series.loc[history_start:history_end].copy()

        if len(window_data) < min_history * 0.8:
            if verbose:
                print(f"  Ventana {i+1}: SKIP (datos insuficientes: {len(window_data)}/{min_history})")
            continue

        # Rellenar NaN para que el modelo no falle
        window_data[cmg_col] = window_data[cmg_col].ffill().fillna(0)

        try:
            # Generar predicciones
            preds = model.predict_window(window_data)

            # Comparar con reales
            for p in preds:
                target_dt = p['target_datetime']
                if target_dt in cmg_series.index:
                    actual = cmg_series.loc[target_dt]
                    if not np.isnan(actual):
                        all_preds.append({
                            'window': i,
                            'base_datetime': history_end,
                            'target_datetime': target_dt,
                            'horizon': p['horizon'],
                            'target_hour': target_dt.hour,
                            'predicted': p['predicted_cmg'],
                            'actual': actual,
                            'zero_prob': p['zero_probability'],
                            'value_pred': p['value_prediction'],
                            'ci_lower': p['confidence_lower'],
                            'ci_upper': p['confidence_upper'],
                            'error': actual - p['predicted_cmg'],
                            'abs_error': abs(actual - p['predicted_cmg']),
                        })

            if verbose and (i + 1) % 5 == 0:
                print(f"  Ventana {i+1}/{len(window_starts)} completada")

        except Exception as e:
            if verbose:
                print(f"  Ventana {i+1}: ERROR - {e}")
            continue

    if not all_preds:
        raise ValueError("No se generaron predicciones. Verificar datos y modelos.")

    df_preds = pd.DataFrame(all_preds)

    # Calcular metricas
    result = _compute_backtest_metrics(df_preds, "Produccion (LGB+XGB)")
    result.all_predictions = df_preds

    if verbose:
        print(f"\n  Total predicciones: {len(df_preds)}")
        print(f"  Ventanas exitosas: {df_preds['window'].nunique()}")

    return result


def run_baseline_backtesting(
    series: pd.DataFrame,
    test_days: int = 30,
) -> List[BacktestResult]:
    """
    Evalua baselines simples con el mismo periodo de test.

    Returns:
        Lista de BacktestResult para cada baseline
    """
    cmg = series['CMG [$/MWh]'].dropna()
    test_start = cmg.index.max() - timedelta(days=test_days)

    results = []

    baselines = {
        'Persistencia 24h': persistence_baseline_24h(cmg),
        'Persistencia 168h': persistence_baseline_168h(cmg),
        'Media Movil 168h': mean_baseline(cmg, 168),
    }

    for name, pred_series in baselines.items():
        # Filtrar periodo de test
        mask = (cmg.index > test_start) & pred_series.notna() & cmg.notna()
        y_true = cmg[mask].values
        y_pred = pred_series[mask].values
        hours = cmg.index[mask].hour

        if len(y_true) == 0:
            continue

        errors = np.abs(y_true - y_pred)
        sq_errors = (y_true - y_pred) ** 2

        # MAPE (evitar div/0)
        nonzero = y_true != 0
        mape = np.mean(np.abs((y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero])) * 100 if nonzero.sum() > 0 else np.nan

        # Zero metrics
        true_zero = y_true == 0
        pred_zero = y_pred == 0
        tp = np.sum(true_zero & pred_zero)
        fp = np.sum(~true_zero & pred_zero)
        fn = np.sum(true_zero & ~pred_zero)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

        # MAE por hora
        hourly_mae = {}
        for hr in range(24):
            hr_mask = hours == hr
            if hr_mask.sum() > 0:
                hourly_mae[hr] = float(np.mean(errors[hr_mask]))

        result = BacktestResult(
            model_name=name,
            mae_global=float(np.mean(errors)),
            rmse_global=float(np.sqrt(np.mean(sq_errors))),
            mape_global=mape,
            n_windows=0,
            n_predictions=len(y_true),
            horizon_metrics=[],
            hourly_mae=hourly_mae,
        )
        results.append(result)

    return results


# ============================================================================
# METRICS
# ============================================================================

def _compute_backtest_metrics(df: pd.DataFrame, model_name: str) -> BacktestResult:
    """Calcula metricas a partir del DataFrame de predicciones."""

    errors = df['abs_error'].values
    sq_errors = (df['actual'] - df['predicted']).values ** 2

    # MAPE
    nonzero = df['actual'] != 0
    if nonzero.sum() > 0:
        mape = np.mean(np.abs(df.loc[nonzero, 'error'] / df.loc[nonzero, 'actual'])) * 100
    else:
        mape = np.nan

    # Metricas por horizonte
    horizon_metrics = []
    for h in range(1, 25):
        h_df = df[df['horizon'] == h]
        if h_df.empty:
            continue

        h_errors = h_df['abs_error'].values
        h_sq = (h_df['actual'] - h_df['predicted']).values ** 2

        # Zero F1
        tz = h_df['actual'] == 0
        pz = h_df['predicted'] == 0
        tp = (tz & pz).sum()
        fp = (~tz & pz).sum()
        fn = (tz & ~pz).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

        horizon_metrics.append(HorizonMetrics(
            horizon=h,
            mae=float(np.mean(h_errors)),
            rmse=float(np.sqrt(np.mean(h_sq))),
            n_samples=len(h_df),
            zero_f1=f1,
            zero_precision=prec,
            zero_recall=rec,
        ))

    # MAE por hora del dia
    hourly_mae = {}
    for hr in range(24):
        hr_df = df[df['target_hour'] == hr]
        if not hr_df.empty:
            hourly_mae[hr] = float(hr_df['abs_error'].mean())

    # MAE por dia (para tracking temporal)
    daily_mae = []
    df_copy = df.copy()
    df_copy['date'] = df_copy['target_datetime'].dt.date if hasattr(df_copy['target_datetime'], 'dt') else pd.to_datetime(df_copy['target_datetime']).dt.date
    for date, day_df in df_copy.groupby('date'):
        daily_mae.append({
            'date': str(date),
            'mae': float(day_df['abs_error'].mean()),
            'n': len(day_df),
        })

    return BacktestResult(
        model_name=model_name,
        mae_global=float(np.mean(errors)),
        rmse_global=float(np.sqrt(np.mean(sq_errors))),
        mape_global=mape,
        n_windows=df['window'].nunique(),
        n_predictions=len(df),
        horizon_metrics=horizon_metrics,
        hourly_mae=hourly_mae,
        daily_mae=daily_mae,
    )


# ============================================================================
# REPORTING
# ============================================================================

def print_report(model_result: BacktestResult, baseline_results: List[BacktestResult]):
    """Imprime reporte comparativo completo."""

    all_results = [model_result] + baseline_results

    print("\n" + "=" * 80)
    print("BENCHMARK BACKTESTING ROLLING - CMG PREDICTION")
    print("=" * 80)

    # Tabla resumen
    print(f"\n{'Modelo':<25} {'MAE':>8} {'RMSE':>8} {'MAPE%':>8} {'N':>8}")
    print("-" * 60)
    for r in sorted(all_results, key=lambda x: x.mae_global):
        print(f"{r.model_name:<25} {r.mae_global:>8.2f} {r.rmse_global:>8.2f} {r.mape_global:>8.1f} {r.n_predictions:>8d}")

    # Mejor baseline
    if baseline_results:
        best_baseline = min(baseline_results, key=lambda x: x.mae_global)
        improvement = (best_baseline.mae_global - model_result.mae_global) / best_baseline.mae_global * 100
        print(f"\nMejora vs mejor baseline ({best_baseline.model_name}): {improvement:+.1f}%")

    # MAE por horizonte (solo modelo principal)
    if model_result.horizon_metrics:
        print(f"\n{'─' * 80}")
        print("MAE POR HORIZONTE (modelo de produccion)")
        print(f"{'─' * 80}")
        print(f"{'Horizonte':<12} {'MAE':>8} {'RMSE':>8} {'Zero F1':>8} {'N':>6}")
        print("-" * 45)
        for hm in model_result.horizon_metrics:
            print(f"  t+{hm.horizon:<8} {hm.mae:>8.2f} {hm.rmse:>8.2f} {hm.zero_f1:>8.3f} {hm.n_samples:>6d}")

        # Resumen por bloques
        short = [hm for hm in model_result.horizon_metrics if hm.horizon <= 6]
        mid = [hm for hm in model_result.horizon_metrics if 7 <= hm.horizon <= 12]
        long_ = [hm for hm in model_result.horizon_metrics if hm.horizon > 12]

        if short and mid and long_:
            print(f"\n  Corto plazo (t+1..t+6):   MAE = ${np.mean([h.mae for h in short]):.2f}")
            print(f"  Medio plazo (t+7..t+12):  MAE = ${np.mean([h.mae for h in mid]):.2f}")
            print(f"  Largo plazo (t+13..t+24): MAE = ${np.mean([h.mae for h in long_]):.2f}")

    # MAE por hora del dia
    if model_result.hourly_mae:
        print(f"\n{'─' * 80}")
        print("MAE POR HORA DEL DIA")
        print(f"{'─' * 80}")
        for hr in range(24):
            val = model_result.hourly_mae.get(hr, np.nan)
            bar = '#' * int(val / 2) if not np.isnan(val) else ''
            print(f"  {hr:02d}:00  ${val:>7.2f}  {bar}")

    print("\n" + "=" * 80)


def save_results(result: BacktestResult, output_dir: Optional[Path] = None):
    """Guarda resultados del backtesting a JSON."""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "proposal" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Summary JSON
    summary = {
        'model_name': result.model_name,
        'mae_global': result.mae_global,
        'rmse_global': result.rmse_global,
        'mape_global': result.mape_global,
        'n_windows': result.n_windows,
        'n_predictions': result.n_predictions,
        'horizon_metrics': [
            {'horizon': hm.horizon, 'mae': hm.mae, 'rmse': hm.rmse,
             'zero_f1': hm.zero_f1, 'n_samples': hm.n_samples}
            for hm in result.horizon_metrics
        ],
        'hourly_mae': result.hourly_mae,
        'daily_mae': result.daily_mae,
    }

    out_file = output_dir / f"backtest_{result.model_name.lower().replace(' ', '_')}.json"
    with open(out_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResultados guardados en: {out_file}")

    # Predictions CSV
    if result.all_predictions is not None:
        csv_file = output_dir / f"predictions_{result.model_name.lower().replace(' ', '_')}.csv"
        result.all_predictions.to_csv(csv_file, index=False)
        print(f"Predicciones guardadas en: {csv_file}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Ejecuta benchmark completo: modelo de produccion + baselines."""
    from proposal.utils.data_loader import CMGDataLoader

    print("=" * 80)
    print("BENCHMARK CMG PREDICTION - BACKTESTING ROLLING")
    print("=" * 80)

    # 1. Cargar datos
    print("\n[1/4] CARGANDO DATOS")
    print("-" * 40)
    loader = CMGDataLoader()
    df_raw = loader.load_cmg_online()

    # Usar serie promediada (como produccion)
    series = loader.build_averaged_series(df_raw)

    TEST_DAYS = 45

    # 2. Cargar modelo y correr backtesting
    print("\n[2/4] BACKTESTING MODELO DE PRODUCCION")
    print("-" * 40)
    model = ProductionModelEvaluator()
    model.load_models()

    model_result = run_backtesting(
        series=series,
        model=model,
        test_days=TEST_DAYS,
        step_hours=24,
        verbose=True,
    )

    # 3. Baselines
    print("\n[3/4] EVALUANDO BASELINES")
    print("-" * 40)
    baseline_results = run_baseline_backtesting(series, test_days=TEST_DAYS)
    for br in baseline_results:
        print(f"  {br.model_name}: MAE = ${br.mae_global:.2f}")

    # 4. Reporte
    print("\n[4/4] GENERANDO REPORTE")
    print_report(model_result, baseline_results)

    # Guardar
    save_results(model_result)

    return model_result, baseline_results


if __name__ == '__main__':
    model_result, baseline_results = main()
