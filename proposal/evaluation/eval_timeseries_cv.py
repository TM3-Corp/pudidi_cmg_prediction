#!/usr/bin/env python3
"""
Time Series Cross-Validation (Expanding Window)
=================================================

Multiples folds temporales, cada uno con train creciente y test fijo de 30 dias.
Se re-entrena TiDE en cada fold. Sin data leakage.

Esquema (datos: Sep 2025 - Abr 2026, ~7 meses):

  Fold 1: |==TRAIN (Sep-Nov)==|--TEST 30d (Dic)--|
  Fold 2: |====TRAIN (Sep-Dic)====|--TEST 30d (Ene)--|
  Fold 3: |======TRAIN (Sep-Ene)======|--TEST 30d (Feb)--|
  Fold 4: |========TRAIN (Sep-Feb)========|--TEST 30d (Mar)--|

Cada fold:
  1. Entrena TiDE desde cero en datos de train
  2. Corre produccion (modelos pre-entrenados) en datos de test
  3. Genera predicciones rolling diario (24h) en test
  4. Calcula metricas por fold

Al final: media +/- std de MAE por modelo, horizonte y hora.

Ejecutar en 2 fases para evitar OOM (torch + lightgbm):
    python proposal/evaluation/eval_timeseries_cv.py --phase train
    python proposal/evaluation/eval_timeseries_cv.py --phase eval

Uso:
    export $(grep -v '^#' .env | xargs)
    python proposal/evaluation/eval_timeseries_cv.py --phase train
    python proposal/evaluation/eval_timeseries_cv.py --phase eval
"""

import sys
import os
import json
import pickle
import warnings
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

MODELS_DIR = PROJECT_ROOT / "models_24h"
RESULTS_DIR = PROJECT_ROOT / "proposal" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# CV config
TEST_DAYS = 30
MIN_TRAIN_DAYS = 60  # Minimo de train para el primer fold
HORIZON = 24
INPUT_SIZE = 168

FUTR = ['hour_sin', 'hour_cos', 'dow_sin', 'dow_cos', 'month_sin', 'month_cos',
        'is_weekend', 'is_night', 'is_morning', 'is_afternoon', 'is_evening']
HIST = ['cmg_mean_24h', 'cmg_std_24h', 'cmg_mean_168h', 'cmg_std_168h',
        'zeros_ratio_24h', 'zeros_ratio_168h', 'cmg_change_1h', 'cmg_change_24h']


# ============================================================================
# DATA
# ============================================================================

def load_full_series():
    """Carga serie completa (local + supabase)."""
    from proposal.utils.data_loader import CMGDataLoader

    loader = CMGDataLoader()
    df_local = loader.load_cmg_online()
    series_local = loader.build_averaged_series(df_local)

    # Supabase data
    new_data_file = RESULTS_DIR / "supabase_new_data.json"
    if new_data_file.exists():
        with open(new_data_file) as f:
            new_records = json.load(f)
        df_new = pd.DataFrame(new_records)
        df_new['datetime'] = pd.to_datetime(df_new['datetime'], utc=True).dt.tz_localize(None)
        df_new['cmg_usd'] = pd.to_numeric(df_new['cmg_usd'], errors='coerce')
        df_new['hour_floor'] = df_new['datetime'].dt.floor('h')
        hourly = df_new.groupby('hour_floor')['cmg_usd'].mean()
        full_range = pd.date_range(hourly.index.min(), hourly.index.max(), freq='h')
        hourly = hourly.reindex(full_range)
        hourly.index.name = 'datetime'
        hourly.name = 'CMG [$/MWh]'
        series_new = hourly.to_frame()

        series = pd.concat([series_local, series_new])
        series = series[~series.index.duplicated(keep='last')].sort_index()
        print(f"Serie completa (local + supabase): {len(series)} horas")
    else:
        series = series_local
        print(f"Serie (solo local): {len(series)} horas")

    print(f"  Rango: {series.index.min()} -> {series.index.max()}")
    n_zeros = (series['CMG [$/MWh]'] == 0).sum()
    n_miss = series['CMG [$/MWh]'].isna().sum()
    print(f"  Zeros: {n_zeros} ({n_zeros/len(series)*100:.1f}%) | Faltantes: {n_miss}")

    return series


def compute_folds(series: pd.DataFrame):
    """Calcula los folds de CV expanding window."""
    total_hours = len(series)
    total_days = total_hours // 24

    folds = []
    # Primer fold: MIN_TRAIN_DAYS de train + TEST_DAYS de test
    # Cada fold siguiente: train crece TEST_DAYS
    fold_start_offset = MIN_TRAIN_DAYS
    fold_idx = 0

    while fold_start_offset + TEST_DAYS <= total_days:
        train_end_idx = fold_start_offset * 24
        test_end_idx = min((fold_start_offset + TEST_DAYS) * 24, total_hours)

        train_end = series.index[train_end_idx - 1]
        test_start = series.index[train_end_idx]
        test_end = series.index[test_end_idx - 1]

        folds.append({
            'fold': fold_idx,
            'train_start': series.index[0],
            'train_end': train_end,
            'test_start': test_start,
            'test_end': test_end,
            'train_hours': train_end_idx,
            'test_hours': test_end_idx - train_end_idx,
        })

        fold_start_offset += TEST_DAYS
        fold_idx += 1

    return folds


def prepare_nixtla(series):
    """Convierte serie a formato Nixtla."""
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

    s = df['y'].shift(1)
    df['cmg_mean_24h'] = s.rolling(24, min_periods=1).mean()
    df['cmg_std_24h'] = s.rolling(24, min_periods=1).std().fillna(0)
    df['cmg_mean_168h'] = s.rolling(168, min_periods=1).mean()
    df['cmg_std_168h'] = s.rolling(168, min_periods=1).std().fillna(0)
    iz = (s == 0).astype(float)
    df['zeros_ratio_24h'] = iz.rolling(24, min_periods=1).mean()
    df['zeros_ratio_168h'] = iz.rolling(168, min_periods=1).mean()
    df['cmg_change_1h'] = s - s.shift(1)
    df['cmg_change_24h'] = s - s.shift(24)

    for c in HIST:
        df[c] = df[c].fillna(0)
    df['y'] = df['y'].ffill().fillna(0)
    return df


# ============================================================================
# PHASE 1: TRAIN TIDE PER FOLD
# ============================================================================

def phase_train():
    """Entrena TiDE en cada fold y genera predicciones CV."""
    import torch
    if torch.backends.mps.is_available():
        print("GPU MPS disponible")
        accelerator = 'mps'
    else:
        torch.set_num_threads(4)
        accelerator = 'cpu'

    from neuralforecast import NeuralForecast
    from neuralforecast.models import TiDE
    from neuralforecast.losses.pytorch import MAE

    series = load_full_series()
    folds = compute_folds(series)

    print(f"\n{len(folds)} folds de CV (expanding window, {TEST_DAYS}d test cada uno)")
    for f in folds:
        print(f"  Fold {f['fold']}: train {f['train_hours']}h ({f['train_start'].date()} -> {f['train_end'].date()}) | "
              f"test {f['test_hours']}h ({f['test_start'].date()} -> {f['test_end'].date()})")

    all_cv = []

    for fold in folds:
        print(f"\n{'='*60}")
        print(f"FOLD {fold['fold']}: train={fold['train_hours']}h, test={fold['test_hours']}h")
        print(f"{'='*60}")

        # Datos hasta fin de test (para cross_validation)
        series_fold = series.loc[:fold['test_end']].copy()
        df_fold = prepare_nixtla(series_fold)

        # Train subset
        df_train = df_fold[df_fold['ds'] <= fold['train_end']].copy()

        print(f"  Entrenando TiDE ({len(df_train)} horas)...")

        model = TiDE(
            h=HORIZON, input_size=INPUT_SIZE,
            futr_exog_list=FUTR, hist_exog_list=HIST,
            max_steps=1000, val_check_steps=50, early_stop_patience_steps=5,
            learning_rate=1e-3, batch_size=32,
            loss=MAE(), valid_loss=MAE(),
            random_seed=42, scaler_type='standard',
            enable_progress_bar=False, enable_model_summary=False,
            accelerator=accelerator,
            hidden_size=128, decoder_output_dim=16,
            num_encoder_layers=2, num_decoder_layers=2,
            temporal_decoder_dim=64, dropout=0.15, layernorm=True,
        )

        nf = NeuralForecast(models=[model], freq='h')
        nf.fit(df=df_train, val_size=HORIZON * 7)

        # CV sobre el test period
        n_windows = fold['test_hours'] // HORIZON - 1
        if n_windows < 1:
            n_windows = 1

        print(f"  Cross-validation ({n_windows} ventanas)...")
        cv = nf.cross_validation(
            df=df_fold, n_windows=n_windows, step_size=24,
            val_size=HORIZON, refit=False,
        )

        cv['ds'] = pd.to_datetime(cv['ds'])
        if cv['ds'].dt.tz is not None:
            cv['ds'] = cv['ds'].dt.tz_localize(None)
        cv['fold'] = fold['fold']

        # Solo mantener predicciones del periodo test
        cv = cv[cv['ds'] >= fold['test_start']]

        print(f"  Predicciones en test: {len(cv)}")
        all_cv.append(cv)

        # Liberar memoria
        del nf, model
        import gc
        gc.collect()

    df_cv = pd.concat(all_cv, ignore_index=True)
    cv_file = RESULTS_DIR / "cv_timeseries_cv_tide.csv"
    df_cv.to_csv(cv_file, index=False)
    print(f"\nCV completo guardado: {cv_file} ({len(df_cv)} filas, {df_cv['fold'].nunique()} folds)")

    # Guardar fold info
    fold_file = RESULTS_DIR / "cv_fold_info.json"
    fold_info = [{k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in f.items()} for f in folds]
    with open(fold_file, 'w') as f:
        json.dump(fold_info, f, indent=2)


# ============================================================================
# PHASE 2: PRODUCTION + ENSEMBLE + REPORT
# ============================================================================

def phase_eval():
    """Corre produccion en cada fold, ensambla, reporta."""
    from proposal.utils.benchmark import ProductionModelEvaluator
    from ml_feature_engineering import CleanCMGFeatureEngineering
    from proposal.evaluation.eval_zero_detection import ZeroDetector

    series = load_full_series()
    folds = compute_folds(series)

    # Cargar CV TiDE
    cv = pd.read_csv(RESULTS_DIR / "cv_timeseries_cv_tide.csv")
    cv['ds'] = pd.to_datetime(cv['ds'])
    cv = cv.sort_values(['fold', 'cutoff', 'ds'])
    cv['horizon'] = cv.groupby(['fold', 'cutoff']).cumcount() + 1

    neural_lookup = {}
    for _, row in cv.iterrows():
        neural_lookup[(int(row['fold']), row['ds'])] = {
            'TiDE': max(0, float(row.get('TiDE', 0))),
        }

    # Modelos
    prod_model = ProductionModelEvaluator()
    prod_model.load_models()

    zero_detector = ZeroDetector()
    zero_detector.load()

    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168],
    )

    cmg = series['CMG [$/MWh]'].dropna()

    all_preds = []

    for fold in folds:
        print(f"\nFold {fold['fold']}: backtesting produccion...")

        test_start = fold['test_start']
        test_end = fold['test_end']

        window_starts = []
        current = test_start
        while current + timedelta(hours=24) <= test_end:
            if current - timedelta(hours=168) >= cmg.index.min():
                window_starts.append(current)
            current += timedelta(hours=24)

        for i, ws in enumerate(window_starts):
            he = ws
            hs = he - timedelta(hours=168)
            wd = series.loc[hs:he].copy()
            if len(wd) < 140:
                continue
            wd['CMG [$/MWh]'] = wd['CMG [$/MWh]'].ffill().fillna(0)

            try:
                df_feat = feature_engineer.create_features(wd)
                bc = [c for c in df_feat.columns
                      if not c.startswith(('is_zero_t+', 'cmg_value_t+')) and c != 'CMG [$/MWh]']
                li = df_feat.index[-1]
                X_base = df_feat.loc[[li], bc]
            except Exception:
                continue

            try:
                pp = prod_model.predict_window(wd)
            except Exception:
                continue

            for p in pp:
                h = p['horizon']
                td = p['target_datetime']
                th = td.hour

                if td not in cmg.index:
                    continue
                actual = cmg.loc[td]
                if np.isnan(actual):
                    continue

                zp = zero_detector.predict_zero_prob(X_base, h)
                iz = zero_detector.should_be_zero(zp, th)

                neural = neural_lookup.get((fold['fold'], td))
                if neural is None:
                    continue

                tide = neural['TiDE']
                w = max(0, 1 - (h - 1) / 24)
                weighted_raw = w * tide + (1 - w) * p['predicted_cmg']
                val_weighted = w * tide + (1 - w) * p['value_prediction']
                weighted_zd = 0.0 if iz else max(0, val_weighted)

                # Persistencia
                past_24 = td - timedelta(hours=24)
                persist = cmg.get(past_24, np.nan)

                all_preds.append({
                    'fold': fold['fold'],
                    'window': i,
                    'target_datetime': td,
                    'horizon': h,
                    'target_hour': th,
                    'actual': actual,
                    'prod': p['predicted_cmg'],
                    'tide_raw': tide,
                    'weighted_raw': weighted_raw,
                    'weighted_zd': weighted_zd,
                    'persist_24h': persist,
                    'zero_prob': zp,
                    'predicted_zero': iz,
                })

        print(f"  {sum(1 for p in all_preds if p['fold'] == fold['fold'])} predicciones")

    df = pd.DataFrame(all_preds)
    print(f"\nTotal: {len(df)} predicciones, {df['fold'].nunique()} folds")

    # Metricas
    print_cv_report(df, folds)

    # Guardar
    df.to_csv(RESULTS_DIR / "timeseries_cv_predictions.csv", index=False)
    print(f"\nGuardado en {RESULTS_DIR}/")


# ============================================================================
# METRICS & REPORT
# ============================================================================

def _fold_metrics(y, p):
    """Metricas para un fold."""
    e = np.abs(y - p)
    sq = (y - p) ** 2
    nz = y != 0
    mape = np.mean(e[nz] / y[nz]) * 100 if nz.sum() > 0 else np.nan

    tz = y == 0
    pz = p == 0
    tp = (tz & pz).sum()
    fp = (~tz & pz).sum()
    fn = (tz & ~pz).sum()
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

    return {
        'mae': float(e.mean()),
        'rmse': float(np.sqrt(sq.mean())),
        'mape': float(mape),
        'zero_f1': float(f1),
        'zero_prec': float(prec),
        'zero_rec': float(rec),
        'n': len(y),
        'n_zeros': int(tz.sum()),
    }


def print_cv_report(df, folds):
    """Reporte completo de CV temporal."""
    models = {
        'Produccion (LGB+XGB)': 'prod',
        'TiDE continuo': 'tide_raw',
        'Weighted continuo': 'weighted_raw',
        'Weighted + Zero Detection': 'weighted_zd',
    }

    # Agregar persistencia si existe
    df_p = df.dropna(subset=['persist_24h'])
    if len(df_p) > 0:
        models['Persistencia 24h'] = 'persist_24h'

    n_folds = df['fold'].nunique()

    print("\n" + "=" * 110)
    print("TIME SERIES CROSS-VALIDATION (EXPANDING WINDOW)")
    print("=" * 110)
    print(f"\nFolds: {n_folds} | Test: {TEST_DAYS} dias cada uno | Train: expanding")
    print(f"Total predicciones: {len(df)}")

    for fold_info in folds:
        f = fold_info['fold']
        fd = df[df['fold'] == f]
        nz = (fd['actual'] == 0).sum()
        print(f"  Fold {f}: train {fold_info['train_hours']}h -> test {fold_info['test_hours']}h "
              f"| {len(fd)} preds | {nz} zeros ({nz/max(len(fd),1)*100:.0f}%)")

    # Metricas por fold por modelo
    fold_metrics = {name: [] for name in models}

    for f in sorted(df['fold'].unique()):
        fd = df[df['fold'] == f]
        for name, col in models.items():
            if col == 'persist_24h':
                fd_clean = fd.dropna(subset=[col])
                if len(fd_clean) == 0:
                    continue
                m = _fold_metrics(fd_clean['actual'].values, fd_clean[col].values)
            else:
                m = _fold_metrics(fd['actual'].values, fd[col].values)
            m['fold'] = f
            fold_metrics[name].append(m)

    # Tabla: MAE por fold
    print(f"\n{'─' * 110}")
    print("MAE POR FOLD")
    print(f"{'─' * 110}")

    header = f"{'Fold':<8}" + "".join(f"{n[:25]:>22}" for n in models)
    print(header)
    print("-" * (8 + 22 * len(models)))

    for f in sorted(df['fold'].unique()):
        row = f"  {f:<6}"
        for name in models:
            fm = [m for m in fold_metrics[name] if m['fold'] == f]
            if fm:
                row += f"${fm[0]['mae']:>20.2f}"
            else:
                row += f"{'---':>22}"
        print(row)

    # Media +/- std
    print("-" * (8 + 22 * len(models)))
    row_mean = f"{'Media':<8}"
    row_std = f"{'Std':<8}"
    for name in models:
        maes = [m['mae'] for m in fold_metrics[name]]
        row_mean += f"${np.mean(maes):>20.2f}"
        row_std += f"{'±':>3}${np.std(maes):>17.2f}"
    print(row_mean)
    print(row_std)

    # Tabla resumen global: media +/- std
    print(f"\n{'─' * 110}")
    print("RESUMEN GLOBAL (media +/- std sobre folds)")
    print(f"{'─' * 110}")
    print(f"{'Modelo':<35} {'MAE':>14} {'RMSE':>14} {'MAPE%':>14} {'Zero F1':>14}")
    print("-" * 95)

    summary = {}
    for name in sorted(models, key=lambda x: np.mean([m['mae'] for m in fold_metrics[x]])):
        maes = [m['mae'] for m in fold_metrics[name]]
        rmses = [m['rmse'] for m in fold_metrics[name]]
        mapes = [m['mape'] for m in fold_metrics[name] if not np.isnan(m['mape'])]
        f1s = [m['zero_f1'] for m in fold_metrics[name]]

        print(
            f"{name:<35} "
            f"${np.mean(maes):>6.2f} ± {np.std(maes):>5.2f} "
            f"${np.mean(rmses):>6.2f} ± {np.std(rmses):>5.2f} "
            f"{np.mean(mapes):>6.1f} ± {np.std(mapes):>5.1f} "
            f"{np.mean(f1s):>6.3f} ± {np.std(f1s):>5.3f}"
        )
        summary[name] = {
            'mae_mean': float(np.mean(maes)), 'mae_std': float(np.std(maes)),
            'rmse_mean': float(np.mean(rmses)), 'rmse_std': float(np.std(rmses)),
            'mape_mean': float(np.mean(mapes)), 'mape_std': float(np.std(mapes)),
            'zero_f1_mean': float(np.mean(f1s)), 'zero_f1_std': float(np.std(f1s)),
            'n_folds': len(maes),
            'fold_maes': maes,
        }

    # MAE por horizonte (media sobre folds)
    print(f"\n{'─' * 110}")
    print("MAE POR HORIZONTE (media sobre folds)")
    print(f"{'─' * 110}")

    key_models = ['Produccion (LGB+XGB)', 'TiDE continuo', 'Weighted continuo', 'Weighted + Zero Detection']
    key_models = [m for m in key_models if m in models]
    header = f"{'h':<6}" + "".join(f"{n[:25]:>28}" for n in key_models)
    print(header)
    print("-" * (6 + 28 * len(key_models)))

    for hi in range(1, 25):
        row = f"t+{hi:<4}"
        for name in key_models:
            col = models[name]
            h_errors = []
            for f in sorted(df['fold'].unique()):
                fd = df[(df['fold'] == f) & (df['horizon'] == hi)]
                if len(fd) > 0:
                    h_errors.append(np.abs(fd['actual'] - fd[col]).mean())
            if h_errors:
                row += f"${np.mean(h_errors):>20.2f} ±{np.std(h_errors):>4.1f}"
            else:
                row += f"{'---':>28}"
        print(row)

    # Bloques
    print(f"\n{'─' * 110}")
    print("MAE POR BLOQUE DE HORIZONTE (media ± std sobre folds)")
    print(f"{'─' * 110}")

    for name in key_models:
        col = models[name]
        shorts, mids, longs = [], [], []
        for f in sorted(df['fold'].unique()):
            fd = df[df['fold'] == f]
            shorts.append(np.abs(fd[fd['horizon'] <= 6]['actual'] - fd[fd['horizon'] <= 6][col]).mean())
            mids.append(np.abs(fd[(fd['horizon'] > 6) & (fd['horizon'] <= 12)]['actual'] -
                               fd[(fd['horizon'] > 6) & (fd['horizon'] <= 12)][col]).mean())
            longs.append(np.abs(fd[fd['horizon'] > 12]['actual'] - fd[fd['horizon'] > 12][col]).mean())

        print(f"  {name:<35}")
        print(f"    Corto  (t+1..6):   ${np.mean(shorts):>6.2f} ± {np.std(shorts):>5.2f}")
        print(f"    Medio  (t+7..12):  ${np.mean(mids):>6.2f} ± {np.std(mids):>5.2f}")
        print(f"    Largo  (t+13..24): ${np.mean(longs):>6.2f} ± {np.std(longs):>5.2f}")

    # Zero detection
    print(f"\n{'─' * 110}")
    print("DETECCION DE ZEROS (media ± std sobre folds)")
    print(f"{'─' * 110}")
    print(f"{'Modelo':<35} {'Precision':>14} {'Recall':>14} {'F1':>14}")
    print("-" * 80)

    for name in models:
        precs = [m['zero_prec'] for m in fold_metrics[name]]
        recs = [m['zero_rec'] for m in fold_metrics[name]]
        f1s = [m['zero_f1'] for m in fold_metrics[name]]
        print(
            f"{name:<35} "
            f"{np.mean(precs):>6.3f} ± {np.std(precs):>5.3f} "
            f"{np.mean(recs):>6.3f} ± {np.std(recs):>5.3f} "
            f"{np.mean(f1s):>6.3f} ± {np.std(f1s):>5.3f}"
        )

    # Resumen final
    best = min(summary, key=lambda x: summary[x]['mae_mean'])
    prod = summary.get('Produccion (LGB+XGB)', {})

    print(f"\n{'=' * 110}")
    print("CONCLUSION")
    print(f"{'=' * 110}")
    print(f"\n  Mejor modelo: {best}")
    print(f"    MAE: ${summary[best]['mae_mean']:.2f} ± {summary[best]['mae_std']:.2f}")
    if prod:
        diff = (summary[best]['mae_mean'] - prod['mae_mean']) / prod['mae_mean'] * 100
        print(f"    vs Produccion: ${prod['mae_mean']:.2f} ± {prod['mae_std']:.2f} ({diff:+.1f}%)")
    print(f"    Consistencia: std = ${summary[best]['mae_std']:.2f} sobre {summary[best]['n_folds']} folds")
    print(f"{'=' * 110}")

    # Guardar resumen
    with open(RESULTS_DIR / "timeseries_cv_summary.json", 'w') as f:
        json.dump(summary, f, indent=2, default=str)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['train', 'eval'], required=True)
    args = parser.parse_args()

    if args.phase == 'train':
        phase_train()
    else:
        phase_eval()
