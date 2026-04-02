#!/usr/bin/env python3
"""
Optuna HPO para TiDE — Sin Data Leakage
=========================================

Optimiza hiperparametros de TiDE usando SOLO Fold 0 del CV temporal
(ventana de entrenamiento mas chica: 60 dias train, 30 dias test Nov 2025).

Luego valida la mejor configuracion en los 5 folds expanding window.
Los Folds 1-4 nunca fueron vistos por Optuna → cero leakage.

Ejecutar en 2 fases:
    # Fase 1: Busqueda Optuna (solo Fold 0)
    python proposal/training/optuna_tide.py --phase search --n-trials 30

    # Fase 2: Validacion del mejor config en 5 folds
    python proposal/training/optuna_tide.py --phase validate

    # (Opcional) Fase 3: Evaluar con zero detection
    python proposal/training/optuna_tide.py --phase validate-zd
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
os.environ['PYTHONWARNINGS'] = 'ignore'

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

MODELS_DIR = PROJECT_ROOT / "models_24h"
RESULTS_DIR = PROJECT_ROOT / "proposal" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OPTUNA_DIR = RESULTS_DIR / "optuna"
OPTUNA_DIR.mkdir(parents=True, exist_ok=True)

HORIZON = 24
MIN_TRAIN_DAYS = 60
TEST_DAYS = 30

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

    new_data_file = RESULTS_DIR / "supabase_new_data.json"
    if new_data_file.exists():
        with open(new_data_file) as f:
            recs = json.load(f)
        dfn = pd.DataFrame(recs)
        dfn['datetime'] = pd.to_datetime(dfn['datetime'], utc=True).dt.tz_localize(None)
        dfn['cmg_usd'] = pd.to_numeric(dfn['cmg_usd'], errors='coerce')
        dfn['hf'] = dfn['datetime'].dt.floor('h')
        hn = dfn.groupby('hf')['cmg_usd'].mean()
        fr = pd.date_range(hn.index.min(), hn.index.max(), freq='h')
        hn = hn.reindex(fr)
        hn.index.name = 'datetime'
        hn.name = 'CMG [$/MWh]'
        sn = hn.to_frame()
        series = pd.concat([series_local, sn])
        series = series[~series.index.duplicated(keep='last')].sort_index()
    else:
        series = series_local

    return series


def compute_folds(series):
    """Calcula los 5 folds de CV expanding window."""
    total_hours = len(series)
    total_days = total_hours // 24
    folds = []
    offset = MIN_TRAIN_DAYS
    idx = 0
    while offset + TEST_DAYS <= total_days:
        train_end_idx = offset * 24
        test_end_idx = min((offset + TEST_DAYS) * 24, total_hours)
        folds.append({
            'fold': idx,
            'train_start': series.index[0],
            'train_end': series.index[train_end_idx - 1],
            'test_start': series.index[train_end_idx],
            'test_end': series.index[test_end_idx - 1],
            'train_hours': train_end_idx,
            'test_hours': test_end_idx - train_end_idx,
        })
        offset += TEST_DAYS
        idx += 1
    return folds


def prepare_nixtla(series):
    """Convierte serie a formato Nixtla."""
    df = pd.DataFrame({
        'unique_id': 'CMG', 'ds': series.index,
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
# TRAIN + EVAL SINGLE FOLD
# ============================================================================

def train_and_eval_fold(params, series, fold, accelerator='cpu'):
    """Entrena TiDE con params dados, evalua en un fold. Retorna MAE."""
    from neuralforecast import NeuralForecast
    from neuralforecast.models import TiDE
    from neuralforecast.losses.pytorch import MAE

    series_fold = series.loc[:fold['test_end']].copy()
    df_fold = prepare_nixtla(series_fold)
    df_train = df_fold[df_fold['ds'] <= fold['train_end']].copy()

    model = TiDE(
        h=HORIZON,
        input_size=params['input_size'],
        futr_exog_list=FUTR,
        hist_exog_list=HIST,
        max_steps=params['max_steps'],
        val_check_steps=50,
        early_stop_patience_steps=params['early_stop_patience'],
        learning_rate=params['learning_rate'],
        batch_size=params['batch_size'],
        loss=MAE(),
        valid_loss=MAE(),
        random_seed=42,
        scaler_type=params['scaler_type'],
        enable_progress_bar=False,
        enable_model_summary=False,
        accelerator=accelerator,
        hidden_size=params['hidden_size'],
        decoder_output_dim=params['decoder_output_dim'],
        num_encoder_layers=params['num_encoder_layers'],
        num_decoder_layers=params['num_decoder_layers'],
        temporal_decoder_dim=params['temporal_decoder_dim'],
        dropout=params['dropout'],
        layernorm=params['layernorm'],
    )

    nf = NeuralForecast(models=[model], freq='h')
    nf.fit(df=df_train, val_size=HORIZON * 7)

    n_windows = fold['test_hours'] // HORIZON - 1
    if n_windows < 1:
        n_windows = 1

    cv = nf.cross_validation(
        df=df_fold, n_windows=n_windows, step_size=24,
        val_size=HORIZON, refit=False,
    )

    cv['ds'] = pd.to_datetime(cv['ds'])
    if cv['ds'].dt.tz is not None:
        cv['ds'] = cv['ds'].dt.tz_localize(None)

    # Filtrar solo test period
    cv = cv[cv['ds'] >= fold['test_start']]

    if len(cv) == 0:
        return float('inf'), cv

    cv['TiDE'] = cv['TiDE'].clip(lower=0)
    mae = (cv['y'] - cv['TiDE']).abs().mean()

    # Cleanup
    del nf, model
    import gc
    gc.collect()

    return float(mae), cv


# ============================================================================
# PHASE 1: OPTUNA SEARCH (SOLO FOLD 0)
# ============================================================================

def phase_search(n_trials=30):
    """Busqueda Optuna sobre Fold 0 unicamente."""
    import optuna
    import torch

    if torch.backends.mps.is_available():
        accelerator = 'mps'
        print("GPU MPS disponible")
    else:
        torch.set_num_threads(4)
        accelerator = 'cpu'

    series = load_full_series()
    folds = compute_folds(series)
    fold0 = folds[0]

    print(f"\nOPTUNA HPO — SOLO FOLD 0")
    print(f"  Train: {fold0['train_hours']}h ({fold0['train_start'].date()} -> {fold0['train_end'].date()})")
    print(f"  Test:  {fold0['test_hours']}h ({fold0['test_start'].date()} -> {fold0['test_end'].date()})")
    print(f"  Trials: {n_trials}")
    print()

    def objective(trial):
        params = {
            'input_size': trial.suggest_categorical('input_size', [72, 120, 168, 336]),
            'hidden_size': trial.suggest_categorical('hidden_size', [32, 64, 128, 256]),
            'num_encoder_layers': trial.suggest_int('num_encoder_layers', 1, 4),
            'num_decoder_layers': trial.suggest_int('num_decoder_layers', 1, 4),
            'decoder_output_dim': trial.suggest_categorical('decoder_output_dim', [8, 16, 32]),
            'temporal_decoder_dim': trial.suggest_categorical('temporal_decoder_dim', [16, 32, 64, 128]),
            'dropout': trial.suggest_float('dropout', 0.0, 0.4, step=0.05),
            'layernorm': trial.suggest_categorical('layernorm', [True, False]),
            'learning_rate': trial.suggest_float('learning_rate', 1e-4, 1e-2, log=True),
            'batch_size': trial.suggest_categorical('batch_size', [16, 32, 64]),
            'max_steps': trial.suggest_categorical('max_steps', [500, 1000, 1500]),
            'early_stop_patience': trial.suggest_int('early_stop_patience', 3, 10),
            'scaler_type': trial.suggest_categorical('scaler_type', ['standard', 'robust', 'minmax']),
        }

        try:
            mae, _ = train_and_eval_fold(params, series, fold0, accelerator)
            print(f"  Trial {trial.number}: MAE = ${mae:.2f} | "
                  f"hidden={params['hidden_size']}, enc={params['num_encoder_layers']}, "
                  f"drop={params['dropout']:.2f}, lr={params['learning_rate']:.4f}")
            return mae
        except Exception as e:
            print(f"  Trial {trial.number}: FAILED ({e})")
            return float('inf')

    # Optuna study
    study = optuna.create_study(
        direction='minimize',
        study_name='tide_hpo_fold0',
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.NopPruner(),
    )

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    # Resultados
    print(f"\n{'='*70}")
    print(f"OPTUNA COMPLETADO — {n_trials} trials")
    print(f"{'='*70}")
    print(f"  Mejor MAE (Fold 0): ${study.best_value:.2f}")
    print(f"  Mejores params:")
    for k, v in study.best_params.items():
        print(f"    {k}: {v}")

    # Guardar
    best_config = {
        'best_mae_fold0': study.best_value,
        'best_params': study.best_params,
        'n_trials': n_trials,
        'fold0_train': str(fold0['train_end'].date()),
        'fold0_test': str(fold0['test_end'].date()),
        'all_trials': [
            {'number': t.number, 'value': t.value, 'params': t.params}
            for t in study.trials if t.value != float('inf')
        ],
    }

    with open(OPTUNA_DIR / "best_config.json", 'w') as f:
        json.dump(best_config, f, indent=2, default=str)

    print(f"\nGuardado en {OPTUNA_DIR / 'best_config.json'}")

    # Top 5
    print(f"\nTop 5 trials:")
    sorted_trials = sorted(
        [t for t in study.trials if t.value != float('inf')],
        key=lambda t: t.value
    )
    for t in sorted_trials[:5]:
        print(f"  #{t.number}: MAE=${t.value:.2f} | hidden={t.params.get('hidden_size')}, "
              f"lr={t.params.get('learning_rate', 0):.4f}, drop={t.params.get('dropout', 0):.2f}")

    return study


# ============================================================================
# PHASE 2: VALIDATE BEST CONFIG ON ALL 5 FOLDS
# ============================================================================

def phase_validate():
    """Valida la mejor configuracion de Optuna en los 5 folds completos."""
    import torch

    if torch.backends.mps.is_available():
        accelerator = 'mps'
    else:
        torch.set_num_threads(4)
        accelerator = 'cpu'

    # Cargar mejor config
    config_file = OPTUNA_DIR / "best_config.json"
    if not config_file.exists():
        print("ERROR: Primero ejecutar --phase search")
        return

    with open(config_file) as f:
        config = json.load(f)

    params = config['best_params']
    # Completar params que objective() genera pero no guarda directamente
    full_params = {
        'input_size': params['input_size'],
        'hidden_size': params['hidden_size'],
        'num_encoder_layers': params['num_encoder_layers'],
        'num_decoder_layers': params['num_decoder_layers'],
        'decoder_output_dim': params['decoder_output_dim'],
        'temporal_decoder_dim': params['temporal_decoder_dim'],
        'dropout': params['dropout'],
        'layernorm': params['layernorm'],
        'learning_rate': params['learning_rate'],
        'batch_size': params['batch_size'],
        'max_steps': params['max_steps'],
        'early_stop_patience': params['early_stop_patience'],
        'scaler_type': params['scaler_type'],
    }

    # Config por defecto (la que usamos antes)
    default_params = {
        'input_size': 168,
        'hidden_size': 128,
        'num_encoder_layers': 2,
        'num_decoder_layers': 2,
        'decoder_output_dim': 16,
        'temporal_decoder_dim': 64,
        'dropout': 0.15,
        'layernorm': True,
        'learning_rate': 1e-3,
        'batch_size': 32,
        'max_steps': 1000,
        'early_stop_patience': 5,
        'scaler_type': 'standard',
    }

    print(f"VALIDACION: MEJOR CONFIG OPTUNA vs DEFAULT EN 5 FOLDS")
    print(f"{'='*70}")
    print(f"Optuna MAE en Fold 0: ${config['best_mae_fold0']:.2f}")
    print(f"\nParams optimizados:")
    for k in sorted(full_params):
        opt_v = full_params[k]
        def_v = default_params[k]
        changed = " <<<" if opt_v != def_v else ""
        print(f"  {k:<25} optuna={opt_v:<12} default={def_v}{changed}")

    series = load_full_series()
    folds = compute_folds(series)

    print(f"\nEvaluando en {len(folds)} folds...")

    results = {'optuna': [], 'default': []}

    for fold in folds:
        print(f"\n  Fold {fold['fold']} (train={fold['train_hours']}h):")

        # Optuna config
        mae_opt, cv_opt = train_and_eval_fold(full_params, series, fold, accelerator)
        results['optuna'].append({'fold': fold['fold'], 'mae': mae_opt, 'n': len(cv_opt)})
        print(f"    Optuna:  MAE = ${mae_opt:.2f}")

        # Default config
        mae_def, cv_def = train_and_eval_fold(default_params, series, fold, accelerator)
        results['default'].append({'fold': fold['fold'], 'mae': mae_def, 'n': len(cv_def)})
        print(f"    Default: MAE = ${mae_def:.2f}")

    # Reporte
    print(f"\n{'='*70}")
    print("RESULTADOS: OPTUNA vs DEFAULT")
    print(f"{'='*70}")

    opt_maes = [r['mae'] for r in results['optuna']]
    def_maes = [r['mae'] for r in results['default']]

    print(f"\n{'Fold':<8} {'Optuna':>12} {'Default':>12} {'Diferencia':>12} {'Nota':>20}")
    print("-" * 68)
    for i in range(len(folds)):
        diff = opt_maes[i] - def_maes[i]
        nota = "<- Optuna optimizo aqui" if i == 0 else ""
        print(f"  {i:<6} ${opt_maes[i]:>10.2f} ${def_maes[i]:>10.2f} {diff:>+10.2f}   {nota}")

    # METRICA PRINCIPAL: solo Folds 1-4 (no vistos por Optuna)
    opt_unseen = opt_maes[1:]
    def_unseen = def_maes[1:]
    opt_mean_u, opt_std_u = np.mean(opt_unseen), np.std(opt_unseen)
    def_mean_u, def_std_u = np.mean(def_unseen), np.std(def_unseen)
    pct_unseen = (opt_mean_u - def_mean_u) / def_mean_u * 100

    print(f"\n{'='*70}")
    print("METRICA PRINCIPAL: Folds 1-4 (NUNCA vistos por Optuna)")
    print(f"{'='*70}")
    print(f"  Optuna:  ${opt_mean_u:.2f} ± {opt_std_u:.2f}")
    print(f"  Default: ${def_mean_u:.2f} ± {def_std_u:.2f}")
    print(f"  Mejora:  {pct_unseen:+.1f}%")
    print(f"  Optuna gana en {sum(1 for o, d in zip(opt_unseen, def_unseen) if o < d)}/4 folds no vistos")

    # Referencia: todos los folds (incluye Fold 0 sesgado)
    opt_mean_all, opt_std_all = np.mean(opt_maes), np.std(opt_maes)
    def_mean_all, def_std_all = np.mean(def_maes), np.std(def_maes)
    pct_all = (opt_mean_all - def_mean_all) / def_mean_all * 100

    print(f"\n  (Referencia, 5 folds incluyendo Fold 0 sesgado: {pct_all:+.1f}%)")
    print(f"\n{'='*70}")

    pct = pct_unseen  # Para guardar

    # Guardar
    validation_results = {
        'optuna_params': full_params,
        'default_params': default_params,
        'optuna_fold_maes': opt_maes,
        'default_fold_maes': def_maes,
        'optuna_mean': opt_mean,
        'optuna_std': opt_std,
        'default_mean': def_mean,
        'default_std': def_std,
        'improvement_pct': pct,
        'optuna_wins': sum(1 for o, d in zip(opt_maes, def_maes) if o < d),
        'unseen_folds_improvement_pct': pct_unseen if len(folds) > 1 else None,
    }

    with open(OPTUNA_DIR / "validation_results.json", 'w') as f:
        json.dump(validation_results, f, indent=2, default=str)
    print(f"Guardado en {OPTUNA_DIR}/")


# ============================================================================
# PHASE 3: VALIDATE WITH ZERO DETECTION
# ============================================================================

def phase_validate_zd():
    """Valida el mejor TiDE + Zero Detection con threshold optimizado."""
    import torch
    import optuna

    if torch.backends.mps.is_available():
        accelerator = 'mps'
    else:
        torch.set_num_threads(4)
        accelerator = 'cpu'

    config_file = OPTUNA_DIR / "best_config.json"
    if not config_file.exists():
        print("ERROR: Primero ejecutar --phase search")
        return

    with open(config_file) as f:
        config = json.load(f)
    params = config['best_params']

    full_params = {k: params[k] for k in [
        'input_size', 'hidden_size', 'num_encoder_layers', 'num_decoder_layers',
        'decoder_output_dim', 'temporal_decoder_dim', 'dropout', 'layernorm',
        'learning_rate', 'batch_size', 'max_steps', 'early_stop_patience', 'scaler_type',
    ]}

    series = load_full_series()
    folds = compute_folds(series)
    fold0 = folds[0]

    # Entrenar TiDE optimizado en Fold 0 y obtener predicciones
    print("Entrenando TiDE optimizado en Fold 0 para calibrar ZD threshold...")
    mae_opt, cv_opt = train_and_eval_fold(full_params, series, fold0, accelerator)

    # Cargar zero detector
    from proposal.evaluation.eval_zero_detection import ZeroDetector
    from ml_feature_engineering import CleanCMGFeatureEngineering

    zero_detector = ZeroDetector()
    zero_detector.load()

    # Buscar threshold optimo en Fold 0
    # Probar escalas sobre los thresholds existentes
    print(f"\nOptimizando threshold scale en Fold 0 (MAE base TiDE: ${mae_opt:.2f})...")

    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168],
    )

    cmg = series['CMG [$/MWh]'].dropna()

    # Generar zero probs para Fold 0 test
    zd_data = _generate_zero_probs(
        series, fold0, cmg, zero_detector, feature_engineer, cv_opt
    )

    if not zd_data:
        print("No se pudieron generar zero probs")
        return

    df_zd = pd.DataFrame(zd_data)

    # Buscar mejor threshold scale
    best_scale = 1.0
    best_mae = float('inf')

    for scale in np.arange(0.5, 2.5, 0.05):
        scaled_thresh = {h: min(t * scale, 0.99) for h, t in zero_detector.thresholds.items()}
        preds = []
        for _, row in df_zd.iterrows():
            th = scaled_thresh.get(row['target_hour'], 0.5)
            pred = 0.0 if row['zero_prob'] > th else row['tide_pred']
            preds.append(pred)
        mae = np.mean(np.abs(df_zd['actual'].values - np.array(preds)))
        if mae < best_mae:
            best_mae = mae
            best_scale = scale

    print(f"  Mejor threshold scale: {best_scale:.2f} (MAE: ${best_mae:.2f} vs continuo ${mae_opt:.2f})")

    # Validar en 5 folds con el threshold optimizado
    print(f"\nValidando TiDE+ZD (scale={best_scale:.2f}) en 5 folds...")

    results_cont = []
    results_zd = []

    for fold in folds:
        print(f"  Fold {fold['fold']}:")

        mae_cont, cv_fold = train_and_eval_fold(full_params, series, fold, accelerator)

        zd_fold = _generate_zero_probs(
            series, fold, cmg, zero_detector, feature_engineer, cv_fold
        )

        if not zd_fold:
            continue

        df_fold = pd.DataFrame(zd_fold)

        # Apply ZD with optimized scale
        scaled_thresh = {h: min(t * best_scale, 0.99) for h, t in zero_detector.thresholds.items()}
        preds_zd = []
        for _, row in df_fold.iterrows():
            th = scaled_thresh.get(row['target_hour'], 0.5)
            pred = 0.0 if row['zero_prob'] > th else row['tide_pred']
            preds_zd.append(pred)

        mae_zd = np.mean(np.abs(df_fold['actual'].values - np.array(preds_zd)))

        # Zero metrics
        y = df_fold['actual'].values
        p_zd = np.array(preds_zd)
        tz = y == 0
        pz = p_zd == 0
        tp = (tz & pz).sum()
        fp = (~tz & pz).sum()
        fn = (tz & ~pz).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

        results_cont.append(mae_cont)
        results_zd.append({'mae': mae_zd, 'f1': f1})

        print(f"    Continuo: ${mae_cont:.2f} | ZD: ${mae_zd:.2f} (F1={f1:.3f})")

    # Reporte
    cont_mean = np.mean(results_cont)
    zd_maes = [r['mae'] for r in results_zd]
    zd_f1s = [r['f1'] for r in results_zd]

    print(f"\n{'='*70}")
    print("TiDE OPTUNA + ZERO DETECTION (5 folds)")
    print(f"{'='*70}")
    print(f"  Threshold scale: {best_scale:.2f} (optimizado en Fold 0)")
    print(f"  TiDE continuo:   ${np.mean(results_cont):.2f} ± {np.std(results_cont):.2f}")
    print(f"  TiDE + ZD:       ${np.mean(zd_maes):.2f} ± {np.std(zd_maes):.2f} (F1={np.mean(zd_f1s):.3f})")
    pct = (np.mean(zd_maes) - cont_mean) / cont_mean * 100
    print(f"  Efecto ZD:       {pct:+.1f}% MAE")
    print(f"{'='*70}")

    # Guardar
    zd_results = {
        'best_threshold_scale': best_scale,
        'optuna_params': full_params,
        'continuo_maes': results_cont,
        'zd_maes': zd_maes,
        'zd_f1s': zd_f1s,
    }
    with open(OPTUNA_DIR / "zd_validation_results.json", 'w') as f:
        json.dump(zd_results, f, indent=2, default=str)


def _generate_zero_probs(series, fold, cmg, zero_detector, feature_engineer, cv_results):
    """Genera zero probabilities para las predicciones de un fold."""
    import xgboost as xgb

    cv_results['ds'] = pd.to_datetime(cv_results['ds'])
    if cv_results['ds'].dt.tz is not None:
        cv_results['ds'] = cv_results['ds'].dt.tz_localize(None)

    cv_lookup = {}
    cv_sorted = cv_results.sort_values(['cutoff', 'ds'])
    cv_sorted['horizon'] = cv_sorted.groupby('cutoff').cumcount() + 1
    for _, row in cv_sorted.iterrows():
        cv_lookup[row['ds']] = {
            'tide': max(0, float(row.get('TiDE', 0))),
            'horizon': int(row['horizon']),
        }

    test_start = fold['test_start']
    test_end = fold['test_end']

    window_starts = []
    current = test_start
    while current + timedelta(hours=24) <= test_end:
        if current - timedelta(hours=168) >= cmg.index.min():
            window_starts.append(current)
        current += timedelta(hours=24)

    all_data = []
    for ws in window_starts:
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

        base_time = li
        for h in range(1, 25):
            td = base_time + timedelta(hours=h)
            if td not in cmg.index:
                continue
            actual = cmg.loc[td]
            if np.isnan(actual):
                continue

            neural = cv_lookup.get(td)
            if neural is None:
                continue

            zp = zero_detector.predict_zero_prob(X_base, h)
            all_data.append({
                'target_datetime': td,
                'horizon': h,
                'target_hour': td.hour,
                'actual': actual,
                'tide_pred': neural['tide'],
                'zero_prob': zp,
            })

    return all_data


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['search', 'validate', 'validate-zd'], required=True)
    parser.add_argument('--n-trials', type=int, default=30)
    args = parser.parse_args()

    if args.phase == 'search':
        phase_search(n_trials=args.n_trials)
    elif args.phase == 'validate':
        phase_validate()
    elif args.phase == 'validate-zd':
        phase_validate_zd()
