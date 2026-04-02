#!/usr/bin/env python3
"""
Entrenamiento y Evaluacion: NHITS, NBEATSx, TiDE
==================================================

Entrena 3 modelos SOTA de NeuralForecast y los compara contra
el modelo de produccion usando backtesting rolling identico.

Foco: horizontes cercanos (t+1 a t+12) donde el modelo actual falla.

Resultado del benchmark actual (produccion LGB+XGB):
  - Corto plazo (t+1..t+6):   MAE = $85.30  <-- FALLA
  - Medio plazo (t+7..t+12):  MAE = $74.24  <-- FALLA
  - Largo plazo (t+13..t+24): MAE = $36.54

Uso:
    python proposal/training/train_neural_models.py
"""

import sys
import os
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from proposal.utils.data_loader import CMGDataLoader

# NeuralForecast
from neuralforecast import NeuralForecast
from neuralforecast.models import NHITS, NBEATSx, TiDE
from neuralforecast.losses.pytorch import MAE, MSE

import torch
torch.set_num_threads(4)

# Constants
HORIZON = 24
INPUT_SIZE = 168  # 1 semana
TEST_DAYS = 45
RESULTS_DIR = PROJECT_ROOT / "proposal" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Features futuras conocidas (deterministas, calculables para cualquier fecha)
FUTR_FEATURES = [
    'hour_sin', 'hour_cos',
    'dow_sin', 'dow_cos',
    'month_sin', 'month_cos',
    'is_weekend',
    'is_night', 'is_morning', 'is_afternoon', 'is_evening',
]

# Features historicas (computadas de la serie, solo conocidas para el pasado)
HIST_FEATURES = [
    'cmg_mean_24h', 'cmg_std_24h',
    'cmg_mean_168h', 'cmg_std_168h',
    'zeros_ratio_24h', 'zeros_ratio_168h',
    'cmg_change_1h', 'cmg_change_24h',
]


# ============================================================================
# DATA PREPARATION
# ============================================================================

def prepare_nixtla_data(series: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte serie horaria al formato Nixtla:
    unique_id | ds | y | futr_exog_1 | ... | hist_exog_1 | ...

    Tambien agrega features temporales y estadisticas rolling.
    """
    df = pd.DataFrame({
        'unique_id': 'CMG',
        'ds': series.index,
        'y': series['CMG [$/MWh]'].values,
    })

    # Features futuras (deterministas - se pueden calcular para cualquier fecha)
    df['hour_sin'] = np.sin(2 * np.pi * df['ds'].dt.hour / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['ds'].dt.hour / 24)
    df['dow_sin'] = np.sin(2 * np.pi * df['ds'].dt.dayofweek / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['ds'].dt.dayofweek / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['ds'].dt.month / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['ds'].dt.month / 12)
    df['is_weekend'] = (df['ds'].dt.dayofweek >= 5).astype(float)
    df['is_night'] = ((df['ds'].dt.hour >= 0) & (df['ds'].dt.hour < 6)).astype(float)
    df['is_morning'] = ((df['ds'].dt.hour >= 6) & (df['ds'].dt.hour < 12)).astype(float)
    df['is_afternoon'] = ((df['ds'].dt.hour >= 12) & (df['ds'].dt.hour < 18)).astype(float)
    df['is_evening'] = ((df['ds'].dt.hour >= 18) & (df['ds'].dt.hour < 24)).astype(float)

    # Features historicas (rolling stats - solo conocidas para datos pasados)
    shifted = df['y'].shift(1)
    df['cmg_mean_24h'] = shifted.rolling(24, min_periods=1).mean()
    df['cmg_std_24h'] = shifted.rolling(24, min_periods=1).std().fillna(0)
    df['cmg_mean_168h'] = shifted.rolling(168, min_periods=1).mean()
    df['cmg_std_168h'] = shifted.rolling(168, min_periods=1).std().fillna(0)

    is_zero = (shifted == 0).astype(float)
    df['zeros_ratio_24h'] = is_zero.rolling(24, min_periods=1).mean()
    df['zeros_ratio_168h'] = is_zero.rolling(168, min_periods=1).mean()

    df['cmg_change_1h'] = shifted - shifted.shift(1)
    df['cmg_change_24h'] = shifted - shifted.shift(24)

    # Fill NaN de features (primeras filas sin historia suficiente)
    for col in HIST_FEATURES:
        df[col] = df[col].fillna(0)

    # NeuralForecast necesita y sin NaN
    df['y'] = df['y'].fillna(method='ffill').fillna(0)

    return df


def create_future_exog(last_ds: pd.Timestamp, horizon: int = HORIZON) -> pd.DataFrame:
    """Crea features futuras para prediccion (conocidas a priori)."""
    future_dates = pd.date_range(start=last_ds + timedelta(hours=1), periods=horizon, freq='h')

    df = pd.DataFrame({
        'unique_id': 'CMG',
        'ds': future_dates,
    })

    df['hour_sin'] = np.sin(2 * np.pi * df['ds'].dt.hour / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['ds'].dt.hour / 24)
    df['dow_sin'] = np.sin(2 * np.pi * df['ds'].dt.dayofweek / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['ds'].dt.dayofweek / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['ds'].dt.month / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['ds'].dt.month / 12)
    df['is_weekend'] = (df['ds'].dt.dayofweek >= 5).astype(float)
    df['is_night'] = ((df['ds'].dt.hour >= 0) & (df['ds'].dt.hour < 6)).astype(float)
    df['is_morning'] = ((df['ds'].dt.hour >= 6) & (df['ds'].dt.hour < 12)).astype(float)
    df['is_afternoon'] = ((df['ds'].dt.hour >= 12) & (df['ds'].dt.hour < 18)).astype(float)
    df['is_evening'] = ((df['ds'].dt.hour >= 18) & (df['ds'].dt.hour < 24)).astype(float)

    return df


# ============================================================================
# MODEL DEFINITIONS
# ============================================================================

def get_models():
    """
    Define los 3 modelos con configuracion conservadora para evitar overfit.
    - hidden_size bajo (64-128)
    - dropout activo
    - early stopping
    - MAE como loss (robusto a zeros)
    """
    common = dict(
        h=HORIZON,
        input_size=INPUT_SIZE,
        futr_exog_list=FUTR_FEATURES,
        hist_exog_list=HIST_FEATURES,
        max_steps=1000,
        val_check_steps=50,
        early_stop_patience_steps=5,
        learning_rate=1e-3,
        batch_size=32,
        loss=MAE(),
        valid_loss=MAE(),
        random_seed=42,
        scaler_type='standard',
        enable_progress_bar=True,
        enable_model_summary=False,
    )

    models = [
        NHITS(
            **common,
            n_pool_kernel_size=[8, 4, 1],         # Multi-rate: captura tendencias + detalle
            n_freq_downsample=[24, 4, 1],          # Downsample jerarquico
            stack_types=3 * ['identity'],
            n_blocks=3 * [1],
            mlp_units=3 * [[128, 128]],
            dropout_prob_theta=0.1,
        ),
        NBEATSx(
            **common,
            stack_types=['trend', 'seasonality', 'identity'],  # Interpretable + flexible
            n_blocks=3 * [1],
            mlp_units=3 * [[128, 128]],
            n_harmonics=3,                         # Estacionalidad
            n_polynomials=3,                       # Tendencia
            dropout_prob_theta=0.1,
        ),
        TiDE(
            **common,
            hidden_size=128,
            decoder_output_dim=16,
            num_encoder_layers=2,
            num_decoder_layers=2,
            temporal_decoder_dim=64,
            dropout=0.15,
            layernorm=True,
        ),
    ]

    return models


# ============================================================================
# BACKTESTING
# ============================================================================

def run_neural_backtesting(
    df_full: pd.DataFrame,
    series_full: pd.DataFrame,
    test_days: int = TEST_DAYS,
    step_hours: int = 24,
):
    """
    Backtesting rolling con NeuralForecast.

    Entrena UNA VEZ con datos de train, luego predice ventana por ventana
    en el periodo de test (igual que el benchmark de produccion).
    """
    # Split train/test
    test_start = df_full['ds'].max() - timedelta(days=test_days)
    train_df = df_full[df_full['ds'] <= test_start].copy()
    test_series = series_full[series_full.index > test_start]

    print(f"\nDatos de entrenamiento: {len(train_df)} horas")
    print(f"Periodo test: {test_start} -> {df_full['ds'].max()}")
    print(f"Horas test: {len(test_series)}")

    # Definir modelos
    models = get_models()
    model_names = ['NHITS', 'NBEATSx', 'TiDE']

    print(f"\nEntrenando {len(models)} modelos...")
    print("=" * 60)

    # Entrenar
    nf = NeuralForecast(models=models, freq='h')
    nf.fit(df=train_df, val_size=HORIZON * 7)  # 1 semana de validacion

    print("\nEntrenamiento completo. Iniciando backtesting...")
    print("=" * 60)

    # Backtesting: usar cross_validation de NeuralForecast
    # Esto hace rolling window automaticamente
    cv_results = nf.cross_validation(
        df=df_full,
        n_windows=test_days,      # 30 ventanas (1 por dia)
        step_size=step_hours,     # Avanzar 24h entre ventanas
        val_size=HORIZON,         # Cada ventana predice 24h
        refit=False,              # NO re-entrenar (usa modelo entrenado)
    )

    print(f"\nCross-validation completa: {len(cv_results)} predicciones")

    return cv_results, model_names


# ============================================================================
# METRICS
# ============================================================================

def compute_comparative_metrics(
    cv_results: pd.DataFrame,
    model_names: list,
    production_results_path: Path = None,
):
    """Calcula metricas por modelo, horizonte y hora. Compara con produccion."""

    # Cargar resultados de produccion
    prod_preds = None
    if production_results_path is None:
        production_results_path = RESULTS_DIR / "predictions_produccion_(lgb+xgb).csv"
    if production_results_path.exists():
        prod_preds = pd.read_csv(production_results_path)
        prod_preds['target_datetime'] = pd.to_datetime(prod_preds['target_datetime'])

    # Calcular horizonte para cada prediccion de NeuralForecast
    cv = cv_results.copy()
    cv = cv.sort_values('ds')

    # Identificar horizonte: para cada cutoff, las predicciones estan en orden
    cv['cutoff'] = cv.groupby('unique_id')['ds'].transform(
        lambda x: pd.factorize(x.dt.date)[0]
    )

    # Calcular horizonte basado en posicion dentro de cada ventana
    cv['horizon'] = cv.groupby('cutoff').cumcount() + 1
    cv['target_hour'] = cv['ds'].dt.hour

    all_metrics = {}

    for model_name in model_names:
        col = model_name
        if col not in cv.columns:
            print(f"  Warning: columna {col} no encontrada en resultados")
            continue

        model_cv = cv[['ds', 'y', col, 'horizon', 'target_hour', 'cutoff']].copy()
        model_cv = model_cv.rename(columns={col: 'predicted'})
        model_cv['predicted'] = model_cv['predicted'].clip(lower=0)  # CMG >= 0
        model_cv = model_cv.dropna(subset=['y', 'predicted'])

        model_cv['error'] = model_cv['y'] - model_cv['predicted']
        model_cv['abs_error'] = model_cv['error'].abs()

        # Metricas globales
        mae = model_cv['abs_error'].mean()
        rmse = np.sqrt((model_cv['error'] ** 2).mean())
        nonzero = model_cv['y'] != 0
        mape = (model_cv.loc[nonzero, 'abs_error'] / model_cv.loc[nonzero, 'y']).mean() * 100 if nonzero.sum() > 0 else np.nan

        # Por horizonte
        horizon_mae = model_cv.groupby('horizon')['abs_error'].mean().to_dict()

        # Por hora
        hourly_mae = model_cv.groupby('target_hour')['abs_error'].mean().to_dict()

        # Zero detection
        true_zero = model_cv['y'] == 0
        pred_zero = model_cv['predicted'] == 0
        tp = (true_zero & pred_zero).sum()
        fp = (~true_zero & pred_zero).sum()
        fn = (true_zero & ~pred_zero).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

        # Bloques de horizontes
        short_mae = model_cv[model_cv['horizon'] <= 6]['abs_error'].mean()
        mid_mae = model_cv[(model_cv['horizon'] > 6) & (model_cv['horizon'] <= 12)]['abs_error'].mean()
        long_mae = model_cv[model_cv['horizon'] > 12]['abs_error'].mean()

        all_metrics[model_name] = {
            'mae': mae,
            'rmse': rmse,
            'mape': mape,
            'zero_f1': f1,
            'n_predictions': len(model_cv),
            'n_windows': model_cv['cutoff'].nunique(),
            'horizon_mae': horizon_mae,
            'hourly_mae': hourly_mae,
            'short_mae': short_mae,
            'mid_mae': mid_mae,
            'long_mae': long_mae,
        }

    # Agregar produccion
    if prod_preds is not None:
        prod_metrics = _compute_prod_metrics(prod_preds)
        all_metrics['Produccion (LGB+XGB)'] = prod_metrics

    # Agregar persistencia 24h
    persist_mae = compute_persistence_on_cv(cv)
    if persist_mae:
        all_metrics['Persistencia 24h'] = persist_mae

    return all_metrics


def _compute_prod_metrics(prod_preds):
    """Extrae metricas del CSV de produccion."""
    df = prod_preds.copy()
    df['abs_error'] = df['actual'] - df['predicted']
    df['abs_error'] = df['abs_error'].abs()

    horizon_mae = df.groupby('horizon')['abs_error'].mean().to_dict()
    hourly_mae = df.groupby('target_hour')['abs_error'].mean().to_dict()

    short = df[df['horizon'] <= 6]['abs_error'].mean()
    mid = df[(df['horizon'] > 6) & (df['horizon'] <= 12)]['abs_error'].mean()
    long_ = df[df['horizon'] > 12]['abs_error'].mean()

    nonzero = df['actual'] != 0
    mape = (df.loc[nonzero, 'abs_error'] / df.loc[nonzero, 'actual']).mean() * 100 if nonzero.sum() > 0 else np.nan

    return {
        'mae': df['abs_error'].mean(),
        'rmse': np.sqrt(((df['actual'] - df['predicted']) ** 2).mean()),
        'mape': mape,
        'zero_f1': 0.0,
        'n_predictions': len(df),
        'n_windows': df['window'].nunique() if 'window' in df.columns else 0,
        'horizon_mae': {int(k): v for k, v in horizon_mae.items()},
        'hourly_mae': {int(k): v for k, v in hourly_mae.items()},
        'short_mae': short,
        'mid_mae': mid,
        'long_mae': long_,
    }


def compute_persistence_on_cv(cv):
    """Calcula baseline persistencia 24h sobre el mismo periodo del CV."""
    cv_copy = cv[['ds', 'y']].copy()
    cv_copy = cv_copy.drop_duplicates(subset='ds')
    cv_copy = cv_copy.set_index('ds').sort_index()
    cv_copy['persist_24h'] = cv_copy['y'].shift(24)
    cv_copy = cv_copy.dropna()

    if cv_copy.empty:
        return None

    errors = (cv_copy['y'] - cv_copy['persist_24h']).abs()
    nonzero = cv_copy['y'] != 0
    mape = (errors[nonzero] / cv_copy.loc[nonzero, 'y']).mean() * 100 if nonzero.sum() > 0 else np.nan

    return {
        'mae': errors.mean(),
        'rmse': np.sqrt(((cv_copy['y'] - cv_copy['persist_24h']) ** 2).mean()),
        'mape': mape,
        'zero_f1': 0.0,
        'n_predictions': len(cv_copy),
        'n_windows': 0,
        'horizon_mae': {},
        'hourly_mae': {},
        'short_mae': errors.mean(),
        'mid_mae': errors.mean(),
        'long_mae': errors.mean(),
    }


# ============================================================================
# REPORTING
# ============================================================================

def print_comparative_report(metrics: dict):
    """Imprime tabla comparativa completa."""

    print("\n" + "=" * 90)
    print("COMPARATIVA: MODELOS NEURALFORECAST vs PRODUCCION")
    print("=" * 90)

    # Tabla resumen
    print(f"\n{'Modelo':<25} {'MAE':>8} {'RMSE':>8} {'MAPE%':>8} {'Corto':>10} {'Medio':>10} {'Largo':>10}")
    print(f"{'':25} {'':>8} {'':>8} {'':>8} {'(t+1..6)':>10} {'(t+7..12)':>10} {'(t+13..24)':>10}")
    print("-" * 90)

    for name in sorted(metrics.keys(), key=lambda x: metrics[x]['mae']):
        m = metrics[name]
        short = m.get('short_mae', np.nan)
        mid = m.get('mid_mae', np.nan)
        long_ = m.get('long_mae', np.nan)
        print(
            f"{name:<25} "
            f"{m['mae']:>8.2f} "
            f"{m['rmse']:>8.2f} "
            f"{m['mape']:>8.1f} "
            f"${short:>9.2f} "
            f"${mid:>9.2f} "
            f"${long_:>9.2f}"
        )

    # MAE por horizonte (todos los modelos)
    models_with_horizons = {k: v for k, v in metrics.items() if v.get('horizon_mae')}
    if models_with_horizons:
        print(f"\n{'─' * 90}")
        print("MAE POR HORIZONTE")
        print(f"{'─' * 90}")

        names = list(models_with_horizons.keys())
        header = f"{'Horizonte':<12}" + "".join(f"{n:>18}" for n in names)
        print(header)
        print("-" * (12 + 18 * len(names)))

        for h in range(1, 25):
            row = f"  t+{h:<8}"
            for name in names:
                val = models_with_horizons[name]['horizon_mae'].get(h, np.nan)
                if np.isnan(val):
                    row += f"{'---':>18}"
                else:
                    row += f"${val:>16.2f}"
            print(row)

    # Foco: horizontes problematicos
    print(f"\n{'─' * 90}")
    print("FOCO: HORIZONTES PROBLEMATICOS (t+1 a t+12)")
    print(f"{'─' * 90}")

    best_short = min(metrics.items(), key=lambda x: x[1].get('short_mae', 999))
    best_mid = min(metrics.items(), key=lambda x: x[1].get('mid_mae', 999))

    prod = metrics.get('Produccion (LGB+XGB)', {})
    prod_short = prod.get('short_mae', 0)
    prod_mid = prod.get('mid_mae', 0)

    print(f"\n  Corto plazo (t+1..t+6):")
    print(f"    Produccion:  ${prod_short:.2f}")
    print(f"    Mejor nuevo: {best_short[0]} = ${best_short[1].get('short_mae', 0):.2f} "
          f"({(best_short[1].get('short_mae', 0) - prod_short) / prod_short * 100:+.1f}%)")

    print(f"\n  Medio plazo (t+7..t+12):")
    print(f"    Produccion:  ${prod_mid:.2f}")
    print(f"    Mejor nuevo: {best_mid[0]} = ${best_mid[1].get('mid_mae', 0):.2f} "
          f"({(best_mid[1].get('mid_mae', 0) - prod_mid) / prod_mid * 100:+.1f}%)")

    print("\n" + "=" * 90)


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 90)
    print("ENTRENAMIENTO NHITS + NBEATSx + TiDE - COMPARATIVA CON PRODUCCION")
    print("=" * 90)

    # 1. Cargar datos
    print("\n[1/4] CARGANDO Y PREPARANDO DATOS")
    print("-" * 40)

    loader = CMGDataLoader()
    df_raw = loader.load_cmg_online()
    series = loader.build_averaged_series(df_raw)

    # Preparar formato Nixtla
    df_nixtla = prepare_nixtla_data(series)
    print(f"\nDataset Nixtla: {len(df_nixtla)} filas")
    print(f"Features futuras: {FUTR_FEATURES}")
    print(f"Features historicas: {HIST_FEATURES}")

    # 2. Entrenar y hacer backtesting
    print("\n[2/4] ENTRENAMIENTO + BACKTESTING ROLLING")
    print("-" * 40)

    cv_results, model_names = run_neural_backtesting(
        df_full=df_nixtla,
        series_full=series,
        test_days=TEST_DAYS,
        step_hours=24,
    )

    # 3. Metricas comparativas
    print("\n[3/4] CALCULANDO METRICAS")
    print("-" * 40)

    metrics = compute_comparative_metrics(cv_results, model_names)

    # 4. Reporte
    print("\n[4/4] REPORTE")
    print_comparative_report(metrics)

    # Guardar resultados
    save_path = RESULTS_DIR / "neural_models_comparison.json"
    serializable = {}
    for name, m in metrics.items():
        serializable[name] = {
            k: (v if not isinstance(v, (np.floating, np.integer)) else float(v))
            for k, v in m.items()
            if k != 'horizon_mae' and k != 'hourly_mae'
        }
        serializable[name]['horizon_mae'] = {str(k): float(v) for k, v in m.get('horizon_mae', {}).items()}
        serializable[name]['hourly_mae'] = {str(k): float(v) for k, v in m.get('hourly_mae', {}).items()}

    with open(save_path, 'w') as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nResultados guardados en: {save_path}")

    # Guardar CV raw
    cv_path = RESULTS_DIR / "cv_neural_models.csv"
    cv_results.to_csv(cv_path, index=False)
    print(f"Predicciones CV guardadas en: {cv_path}")

    return metrics


if __name__ == '__main__':
    metrics = main()
