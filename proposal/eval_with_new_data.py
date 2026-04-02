#!/usr/bin/env python3
"""
Evaluacion con Datos Nuevos de Supabase
=========================================

Train: datos locales (Sep 2025 - Ene 27, 2026) — los que ya teniamos
Test:  datos nuevos de Supabase (Ene 28 - Abr 2, 2026) — nunca vistos

Evalua: Produccion, TiDE, Weighted, Weighted+ZD
Reporta: MAE global/por horizonte + Zero Detection

Uso:
    export $(grep -v '^#' .env | xargs) && python proposal/eval_with_new_data.py
"""

import sys
import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "proposal"))

MODELS_DIR = PROJECT_ROOT / "models_24h"
RESULTS_DIR = PROJECT_ROOT / "proposal" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

LOCAL_CUTOFF = '2026-01-27'  # Ultimo dia en cache local

import lightgbm as lgb
import xgboost as xgb
import torch
torch.set_num_threads(4)


# ============================================================================
# DATA LOADING
# ============================================================================

def load_all_data():
    """Carga datos locales (train) + Supabase (test)."""
    from data_loader import CMGDataLoader
    from lib.utils.supabase_client import SupabaseClient

    # Train: datos locales
    print("[1] Cargando datos locales (train)...")
    loader = CMGDataLoader()
    df_local = loader.load_cmg_online()
    series_train = loader.build_averaged_series(df_local)

    # Test: datos nuevos de Supabase
    print("\n[2] Cargando datos nuevos de Supabase (test)...")
    client = SupabaseClient()

    all_new = []
    page = 0
    page_size = 5000
    while True:
        records = client.get_cmg_online(
            start_date='2026-01-28',
            end_date='2026-04-03',
            limit=page_size,
        )
        if not records:
            break
        all_new.extend(records)
        if len(records) < page_size:
            break
        page += 1

    print(f"  Registros descargados: {len(all_new)}")

    df_new = pd.DataFrame(all_new)
    df_new['datetime'] = pd.to_datetime(df_new['datetime'], utc=True)
    df_new['cmg_usd'] = pd.to_numeric(df_new['cmg_usd'], errors='coerce')

    # Promediar nodos por hora
    df_new['hour_floor'] = df_new['datetime'].dt.floor('h')
    hourly_new = df_new.groupby('hour_floor')['cmg_usd'].mean()
    full_range = pd.date_range(
        start=hourly_new.index.min(),
        end=hourly_new.index.max(),
        freq='h',
    )
    hourly_new = hourly_new.reindex(full_range)
    hourly_new.index.name = 'datetime'
    hourly_new.name = 'CMG [$/MWh]'
    series_test = hourly_new.to_frame()

    # Hacer timezone-naive para compatibilidad
    if series_test.index.tz is not None:
        series_test.index = series_test.index.tz_localize(None)

    n_missing = series_test['CMG [$/MWh]'].isna().sum()
    n_zeros = (series_test['CMG [$/MWh]'] == 0).sum()
    n_total = len(series_test)

    print(f"  Serie test: {n_total} horas")
    print(f"  Rango: {series_test.index.min()} -> {series_test.index.max()}")
    print(f"  Faltantes: {n_missing} ({n_missing/n_total*100:.1f}%)")
    print(f"  Zeros: {n_zeros} ({n_zeros/n_total*100:.1f}%)")
    print(f"  Media: ${series_test['CMG [$/MWh]'].mean():.2f}/MWh")

    # Serie completa (train + test) para feature engineering
    series_full = pd.concat([series_train, series_test])
    series_full = series_full[~series_full.index.duplicated(keep='last')]
    series_full = series_full.sort_index()

    print(f"\n  Serie completa: {len(series_full)} horas")
    print(f"  Train: {len(series_train)} | Test: {len(series_test)}")

    return series_train, series_test, series_full


# ============================================================================
# NEURAL MODELS TRAINING
# ============================================================================

def train_neural_models(series_train: pd.DataFrame):
    """Entrena NHITS, NBEATSx, TiDE en datos locales (train)."""
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NHITS, NBEATSx, TiDE
    from neuralforecast.losses.pytorch import MAE

    HORIZON = 24
    INPUT_SIZE = 168

    FUTR_FEATURES = [
        'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos',
        'month_sin', 'month_cos', 'is_weekend',
        'is_night', 'is_morning', 'is_afternoon', 'is_evening',
    ]
    HIST_FEATURES = [
        'cmg_mean_24h', 'cmg_std_24h', 'cmg_mean_168h', 'cmg_std_168h',
        'zeros_ratio_24h', 'zeros_ratio_168h', 'cmg_change_1h', 'cmg_change_24h',
    ]

    # Preparar datos Nixtla
    df = _prepare_nixtla(series_train, FUTR_FEATURES, HIST_FEATURES)

    common = dict(
        h=HORIZON, input_size=INPUT_SIZE,
        futr_exog_list=FUTR_FEATURES, hist_exog_list=HIST_FEATURES,
        max_steps=1000, val_check_steps=50, early_stop_patience_steps=5,
        learning_rate=1e-3, batch_size=32,
        loss=MAE(), valid_loss=MAE(),
        random_seed=42, scaler_type='standard',
        enable_progress_bar=True, enable_model_summary=False,
    )

    models = [
        TiDE(**common,
             hidden_size=128, decoder_output_dim=16,
             num_encoder_layers=2, num_decoder_layers=2,
             temporal_decoder_dim=64, dropout=0.15, layernorm=True),
    ]

    nf = NeuralForecast(models=models, freq='h')
    nf.fit(df=df, val_size=HORIZON * 7)

    return nf, FUTR_FEATURES, HIST_FEATURES


def _prepare_nixtla(series, futr_features, hist_features):
    """Convierte serie a formato Nixtla con features."""
    df = pd.DataFrame({
        'unique_id': 'CMG',
        'ds': series.index,
        'y': series['CMG [$/MWh]'].values,
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

    for col in hist_features:
        df[col] = df[col].fillna(0)
    df['y'] = df['y'].ffill().fillna(0)

    return df


# ============================================================================
# BACKTESTING ON NEW DATA
# ============================================================================

def run_backtesting_new_data(
    series_full: pd.DataFrame,
    series_test: pd.DataFrame,
    nf_model,
    futr_features: list,
    hist_features: list,
):
    """
    Backtesting rolling diario sobre datos nuevos (Ene 28 - Abr 2).
    Train = datos locales. Los modelos NUNCA vieron estos datos.
    """
    from benchmark import ProductionModelEvaluator
    from ml_feature_engineering import CleanCMGFeatureEngineering
    from eval_ensemble_with_zero_detection import ZeroDetector

    print("\n[4] BACKTESTING SOBRE DATOS NUEVOS")
    print("=" * 60)

    # Cargar modelos de produccion
    prod_model = ProductionModelEvaluator()
    prod_model.load_models()

    zero_detector = ZeroDetector()
    zero_detector.load()

    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168],
    )

    # Preparar datos Nixtla para cross_validation
    df_nixtla_full = _prepare_nixtla(series_full, futr_features, hist_features)

    # Filtrar test period
    test_start = series_test.index.min()
    test_end = series_test.index.max()

    # NeuralForecast cross_validation sobre datos nuevos
    print("\nCross-validation modelos neurales...")
    n_test_days = (test_end - test_start).days
    n_windows = min(n_test_days - 1, 45)  # Maximo 45 ventanas

    cv_results = nf_model.cross_validation(
        df=df_nixtla_full,
        n_windows=n_windows,
        step_size=24,
        val_size=24,
        refit=False,
    )
    print(f"  CV neural: {len(cv_results)} predicciones, {n_windows} ventanas")

    # Crear lookup de predicciones neurales
    cv_results['ds'] = pd.to_datetime(cv_results['ds'])
    if cv_results['ds'].dt.tz is not None:
        cv_results['ds'] = cv_results['ds'].dt.tz_localize(None)

    neural_lookup = {}
    for _, row in cv_results.iterrows():
        neural_lookup[row['ds']] = {
            'TiDE': max(0, float(row.get('TiDE', 0))),
            'NHITS': max(0, float(row.get('NHITS', 0))),
            'NBEATSx': max(0, float(row.get('NBEATSx', 0))),
        }

    # Backtesting produccion (rolling diario)
    cmg = series_full['CMG [$/MWh]'].dropna()

    window_starts = []
    current = test_start
    while current + timedelta(hours=24) <= test_end:
        if current - timedelta(hours=168) >= cmg.index.min():
            window_starts.append(current)
        current += timedelta(hours=24)

    print(f"\nBacktesting produccion: {len(window_starts)} ventanas")

    all_preds = []

    for i, window_start in enumerate(window_starts):
        history_end = window_start
        history_start = history_end - timedelta(hours=168)
        window_data = series_full.loc[history_start:history_end].copy()

        if len(window_data) < 140:
            continue

        window_data['CMG [$/MWh]'] = window_data['CMG [$/MWh]'].ffill().fillna(0)

        try:
            df_feat = feature_engineer.create_features(window_data)
            base_cols = [c for c in df_feat.columns
                         if not c.startswith(('is_zero_t+', 'cmg_value_t+'))
                         and c != 'CMG [$/MWh]']
            latest_idx = df_feat.index[-1]
            X_base = df_feat.loc[[latest_idx], base_cols]
        except Exception:
            continue

        try:
            prod_preds = prod_model.predict_window(window_data)
        except Exception:
            continue

        for p in prod_preds:
            h = p['horizon']
            target_dt = p['target_datetime']
            target_hour = target_dt.hour

            if target_dt not in cmg.index:
                continue
            actual = cmg.loc[target_dt]
            if np.isnan(actual):
                continue

            # Zero detection
            zero_prob = zero_detector.predict_zero_prob(X_base, h)
            is_zero = zero_detector.should_be_zero(zero_prob, target_hour)

            prod_pred = p['predicted_cmg']

            # Predicciones neurales
            neural = neural_lookup.get(target_dt)
            tide_raw = neural['TiDE'] if neural else np.nan
            nhits_raw = neural['NHITS'] if neural else np.nan
            nbeatsx_raw = neural['NBEATSx'] if neural else np.nan

            if np.isnan(tide_raw):
                continue

            # Weighted ensemble
            w = max(0, 1 - (h - 1) / 24)
            weighted_raw = w * tide_raw + (1 - w) * prod_pred

            # Con zero detection
            value_for_weighted = w * tide_raw + (1 - w) * p['value_prediction']
            weighted_zd = 0.0 if is_zero else max(0, value_for_weighted)

            all_preds.append({
                'window': i,
                'target_datetime': target_dt,
                'horizon': h,
                'target_hour': target_hour,
                'actual': actual,
                'actual_is_zero': actual == 0,
                'prod': prod_pred,
                'tide_raw': tide_raw,
                'nhits_raw': nhits_raw,
                'weighted_raw': weighted_raw,
                'weighted_zd': weighted_zd,
                'zero_prob': zero_prob,
                'predicted_zero': is_zero,
            })

        if (i + 1) % 10 == 0:
            print(f"  Ventana {i+1}/{len(window_starts)}")

    df = pd.DataFrame(all_preds)
    print(f"\n  Total: {len(df)} predicciones, {df['window'].nunique()} ventanas")

    return df


# ============================================================================
# METRICS + REPORT
# ============================================================================

def compute_metrics(actual, predicted, horizons, target_hours):
    """Calcula todas las metricas."""
    y, p = actual, predicted
    errors = np.abs(y - p)
    sq = (y - p) ** 2
    nonzero = y != 0
    mape = np.mean(errors[nonzero] / y[nonzero]) * 100 if nonzero.sum() > 0 else np.nan

    h = horizons
    short = errors[h <= 6].mean()
    mid = errors[(h > 6) & (h <= 12)].mean()
    long_ = errors[h > 12].mean()

    h_mae = {}
    for hi in range(1, 25):
        mask = h == hi
        if mask.sum() > 0:
            h_mae[hi] = float(errors[mask].mean())

    true_zero = y == 0
    pred_zero = p == 0
    tp = int((true_zero & pred_zero).sum())
    fp = int((~true_zero & pred_zero).sum())
    fn = int((true_zero & ~pred_zero).sum())
    tn = int((~true_zero & ~pred_zero).sum())

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

    mae_zero = errors[true_zero].mean() if true_zero.sum() > 0 else np.nan
    mae_nonzero = errors[~true_zero].mean() if (~true_zero).sum() > 0 else np.nan

    # Zero F1 por horizonte
    h_zero = {}
    for hi in range(1, 25):
        mask = h == hi
        if mask.sum() == 0:
            continue
        tz, pz = true_zero[mask], pred_zero[mask]
        tp_h = (tz & pz).sum()
        fp_h = (~tz & pz).sum()
        fn_h = (tz & ~pz).sum()
        p_h = tp_h / (tp_h + fp_h) if (tp_h + fp_h) > 0 else 0
        r_h = tp_h / (tp_h + fn_h) if (tp_h + fn_h) > 0 else 0
        f1_h = 2 * p_h * r_h / (p_h + r_h) if (p_h + r_h) > 0 else 0
        h_zero[hi] = f1_h

    # MAE por hora
    hourly_mae = {}
    for hr in range(24):
        mask = target_hours == hr
        if mask.sum() > 0:
            hourly_mae[hr] = float(errors[mask].mean())

    return {
        'mae': float(errors.mean()), 'rmse': float(np.sqrt(sq.mean())), 'mape': float(mape),
        'short': float(short), 'mid': float(mid), 'long': float(long_),
        'h_mae': h_mae, 'h_zero': h_zero, 'hourly_mae': hourly_mae,
        'zero_f1': float(f1), 'zero_precision': float(prec), 'zero_recall': float(rec),
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'n_actual_zeros': int(true_zero.sum()), 'n_pred_zeros': int(pred_zero.sum()),
        'mae_when_zero': float(mae_zero), 'mae_when_nonzero': float(mae_nonzero),
        'n': len(y),
    }


def print_report(results, df):
    """Imprime reporte completo."""
    n_zeros = (df['actual'] == 0).sum()
    n_total = len(df)
    test_start = df['target_datetime'].min()
    test_end = df['target_datetime'].max()

    print("\n" + "=" * 105)
    print("REPORTE: EVALUACION CON DATOS NUEVOS DE SUPABASE")
    print("=" * 105)
    print(f"\nTrain: datos locales (Sep 2025 - Ene 27, 2026)")
    print(f"Test:  datos Supabase (Ene 28 - Abr 2, 2026) — NUNCA VISTOS")
    print(f"Predicciones: {n_total} | Ventanas: {df['window'].nunique()} | Zeros reales: {n_zeros} ({n_zeros/n_total*100:.1f}%)")

    # MAE
    print(f"\n{'─' * 105}")
    print("MAE")
    print(f"{'─' * 105}")
    print(f"{'Modelo':<35} {'MAE':>7} {'RMSE':>7} {'Corto':>9} {'Medio':>9} {'Largo':>9} {'MAE(0)':>9} {'MAE(>0)':>9}")
    print(f"{'':35} {'':>7} {'':>7} {'(t+1..6)':>9} {'(t+7..12)':>9} {'(t+13..24)':>9} {'(real=0)':>9} {'(real>0)':>9}")
    print("-" * 105)

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

    # Zero Detection
    print(f"\n{'─' * 105}")
    print("DETECCION DE ZEROS")
    print(f"{'─' * 105}")
    print(f"{'Modelo':<35} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Pred 0s':>10} {'Real 0s':>10}")
    print("-" * 105)

    for name in sorted(results, key=lambda x: -results[x]['zero_f1']):
        m = results[name]
        print(
            f"{name:<35} "
            f"{m['zero_precision']:>10.3f} "
            f"{m['zero_recall']:>10.3f} "
            f"{m['zero_f1']:>10.3f} "
            f"{m['n_pred_zeros']:>10d} "
            f"{m['n_actual_zeros']:>10d}"
        )

    # Confusion matrices
    print(f"\n{'─' * 105}")
    print("MATRICES DE CONFUSION")
    print(f"{'─' * 105}")
    for name in ['Produccion (LGB+XGB)', 'Weighted + Zero Detection']:
        m = results[name]
        print(f"\n  {name}:")
        print(f"                    Pred=0    Pred>0")
        print(f"    Real=0    {m['tp']:>10d} {m['fn']:>10d}")
        print(f"    Real>0    {m['fp']:>10d} {m['tn']:>10d}")

    # MAE por horizonte
    print(f"\n{'─' * 105}")
    print("MAE POR HORIZONTE")
    print(f"{'─' * 105}")
    key_models = ['Produccion (LGB+XGB)', 'Weighted continuo', 'Weighted + Zero Detection']
    header = f"{'h':<6}" + "".join(f"{n[:28]:>30}" for n in key_models)
    print(header)
    print("-" * (6 + 30 * len(key_models)))
    for h in range(1, 25):
        row = f"t+{h:<4}"
        for name in key_models:
            v = results[name]['h_mae'].get(h, np.nan)
            row += f"${v:>28.2f}"
        print(row)

    # Zero F1 por horizonte
    print(f"\n{'─' * 105}")
    print("ZERO F1 POR HORIZONTE")
    print(f"{'─' * 105}")
    zd_models = ['Produccion (LGB+XGB)', 'Weighted + Zero Detection']
    header = f"{'h':<6}" + "".join(f"{n[:28]:>30}" for n in zd_models)
    print(header)
    for h in range(1, 25):
        row = f"t+{h:<4}"
        for name in zd_models:
            v = results[name]['h_zero'].get(h, 0)
            row += f"{v:>30.3f}"
        print(row)

    # Resumen
    prod = results['Produccion (LGB+XGB)']
    wzd = results['Weighted + Zero Detection']

    print(f"\n{'=' * 105}")
    print("RESUMEN FINAL")
    print(f"{'=' * 105}")
    print(f"\n  Weighted + Zero Detection vs Produccion (datos NUEVOS):")
    print(f"    MAE:       ${wzd['mae']:.2f} vs ${prod['mae']:.2f} ({(wzd['mae']-prod['mae'])/prod['mae']*100:+.1f}%)")
    print(f"    Corto:     ${wzd['short']:.2f} vs ${prod['short']:.2f} ({(wzd['short']-prod['short'])/prod['short']*100:+.1f}%)")
    print(f"    Medio:     ${wzd['mid']:.2f} vs ${prod['mid']:.2f} ({(wzd['mid']-prod['mid'])/prod['mid']*100:+.1f}%)")
    print(f"    Largo:     ${wzd['long']:.2f} vs ${prod['long']:.2f} ({(wzd['long']-prod['long'])/prod['long']*100:+.1f}%)")
    print(f"    Zero F1:   {wzd['zero_f1']:.3f} vs {prod['zero_f1']:.3f}")
    print(f"    MAE(real=0): ${wzd['mae_when_zero']:.2f} vs ${prod['mae_when_zero']:.2f}")
    print(f"{'=' * 105}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 105)
    print("EVALUACION CON DATOS NUEVOS: TRAIN(LOCAL) + TEST(SUPABASE)")
    print("=" * 105)

    # 1-2. Cargar datos
    series_train, series_test, series_full = load_all_data()

    # 3. Entrenar modelos neurales en datos locales
    print("\n[3] ENTRENANDO MODELOS NEURALES (solo datos locales)...")
    print("=" * 60)
    nf_model, futr_features, hist_features = train_neural_models(series_train)

    # 4. Backtesting sobre datos nuevos
    df = run_backtesting_new_data(
        series_full, series_test, nf_model, futr_features, hist_features,
    )

    # 5. Metricas
    print("\n[5] CALCULANDO METRICAS")
    models = {
        'Produccion (LGB+XGB)': df['prod'].values,
        'TiDE continuo': df['tide_raw'].values,
        'Weighted continuo': df['weighted_raw'].values,
        'Weighted + Zero Detection': df['weighted_zd'].values,
    }

    results = {}
    for name, preds in models.items():
        results[name] = compute_metrics(
            df['actual'].values, preds,
            df['horizon'].values, df['target_hour'].values,
        )

    # 6. Reporte
    print_report(results, df)

    # Guardar
    df.to_csv(RESULTS_DIR / "new_data_predictions.csv", index=False)

    summary = {}
    for name, m in results.items():
        summary[name] = {k: v for k, v in m.items() if k not in ('h_mae', 'h_zero', 'hourly_mae')}
    with open(RESULTS_DIR / "new_data_comparison.json", 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nResultados guardados en {RESULTS_DIR}/")
    return results


if __name__ == '__main__':
    results = main()
