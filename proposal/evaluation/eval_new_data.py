#!/usr/bin/env python3
"""
Evaluacion Completa con Datos Nuevos (2 fases)
================================================

Fase 1: Entrena TiDE en datos locales, genera predicciones via CV
Fase 2: Corre produccion + zero detection + ensemble sobre datos nuevos

Separado en 2 fases para evitar OOM con torch + lightgbm simultaneo.

Uso:
    # Fase 1: Entrenar TiDE y generar CV
    python proposal/evaluation/eval_new_data.py --phase train

    # Fase 2: Produccion + ensemble + reporte
    python proposal/evaluation/eval_new_data.py --phase eval
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
NEW_DATA_FILE = RESULTS_DIR / "supabase_new_data.json"
CV_FILE = RESULTS_DIR / "cv_tide_new_data.csv"


def load_series():
    """Carga train (local) + test (supabase) y devuelve series."""
    from proposal.utils.data_loader import CMGDataLoader

    # Train
    loader = CMGDataLoader()
    df_local = loader.load_cmg_online()
    series_train = loader.build_averaged_series(df_local)

    # Test
    with open(NEW_DATA_FILE) as f:
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
    series_test = hourly.to_frame()

    n = len(series_test)
    n_miss = series_test['CMG [$/MWh]'].isna().sum()
    n_zero = (series_test['CMG [$/MWh]'] == 0).sum()
    print(f"Test: {n} horas | {series_test.index.min()} -> {series_test.index.max()}")
    print(f"  Faltantes: {n_miss} ({n_miss/n*100:.1f}%) | Zeros: {n_zero} ({n_zero/n*100:.1f}%)")
    print(f"  Media: ${series_test['CMG [$/MWh]'].mean():.2f}/MWh")

    # Full
    series_full = pd.concat([series_train, series_test])
    series_full = series_full[~series_full.index.duplicated(keep='last')].sort_index()

    return series_train, series_test, series_full


# ============================================================================
# PHASE 1: TRAIN TIDE + CV
# ============================================================================

def phase_train():
    """Entrena TiDE en datos locales y genera CV sobre datos nuevos."""
    import torch
    if torch.backends.mps.is_available():
        print("GPU MPS disponible - usando aceleracion Apple Silicon")
        accelerator = 'mps'
    else:
        torch.set_num_threads(4)
        accelerator = 'cpu'
    from neuralforecast import NeuralForecast
    from neuralforecast.models import TiDE
    from neuralforecast.losses.pytorch import MAE

    series_train, series_test, series_full = load_series()

    FUTR = ['hour_sin','hour_cos','dow_sin','dow_cos','month_sin','month_cos',
            'is_weekend','is_night','is_morning','is_afternoon','is_evening']
    HIST = ['cmg_mean_24h','cmg_std_24h','cmg_mean_168h','cmg_std_168h',
            'zeros_ratio_24h','zeros_ratio_168h','cmg_change_1h','cmg_change_24h']

    def prep(series):
        df = pd.DataFrame({'unique_id': 'CMG', 'ds': series.index, 'y': series['CMG [$/MWh]'].values})
        df['hour_sin'] = np.sin(2*np.pi*df['ds'].dt.hour/24)
        df['hour_cos'] = np.cos(2*np.pi*df['ds'].dt.hour/24)
        df['dow_sin'] = np.sin(2*np.pi*df['ds'].dt.dayofweek/7)
        df['dow_cos'] = np.cos(2*np.pi*df['ds'].dt.dayofweek/7)
        df['month_sin'] = np.sin(2*np.pi*df['ds'].dt.month/12)
        df['month_cos'] = np.cos(2*np.pi*df['ds'].dt.month/12)
        df['is_weekend'] = (df['ds'].dt.dayofweek>=5).astype(float)
        df['is_night'] = ((df['ds'].dt.hour>=0)&(df['ds'].dt.hour<6)).astype(float)
        df['is_morning'] = ((df['ds'].dt.hour>=6)&(df['ds'].dt.hour<12)).astype(float)
        df['is_afternoon'] = ((df['ds'].dt.hour>=12)&(df['ds'].dt.hour<18)).astype(float)
        df['is_evening'] = ((df['ds'].dt.hour>=18)&(df['ds'].dt.hour<24)).astype(float)
        s = df['y'].shift(1)
        df['cmg_mean_24h'] = s.rolling(24,min_periods=1).mean()
        df['cmg_std_24h'] = s.rolling(24,min_periods=1).std().fillna(0)
        df['cmg_mean_168h'] = s.rolling(168,min_periods=1).mean()
        df['cmg_std_168h'] = s.rolling(168,min_periods=1).std().fillna(0)
        iz = (s==0).astype(float)
        df['zeros_ratio_24h'] = iz.rolling(24,min_periods=1).mean()
        df['zeros_ratio_168h'] = iz.rolling(168,min_periods=1).mean()
        df['cmg_change_1h'] = s - s.shift(1)
        df['cmg_change_24h'] = s - s.shift(24)
        for c in HIST: df[c] = df[c].fillna(0)
        df['y'] = df['y'].ffill().fillna(0)
        return df

    df_train = prep(series_train)
    df_full = prep(series_full)

    print(f"\nEntrenando TiDE ({len(df_train)} horas train)...")
    model = TiDE(
        h=24, input_size=168,
        futr_exog_list=FUTR, hist_exog_list=HIST,
        max_steps=1000, val_check_steps=50, early_stop_patience_steps=5,
        learning_rate=1e-3, batch_size=32,
        loss=MAE(), valid_loss=MAE(),
        random_seed=42, scaler_type='standard',
        enable_progress_bar=True, enable_model_summary=False,
        accelerator=accelerator,
        hidden_size=128, decoder_output_dim=16,
        num_encoder_layers=2, num_decoder_layers=2,
        temporal_decoder_dim=64, dropout=0.15, layernorm=True,
    )

    nf = NeuralForecast(models=[model], freq='h')
    nf.fit(df=df_train, val_size=24*7)

    print("\nCross-validation sobre datos nuevos...")
    test_start = series_test.index.min()
    test_end = series_test.index.max()
    n_days = (test_end - test_start).days
    n_windows = min(n_days - 1, 45)

    cv = nf.cross_validation(df=df_full, n_windows=n_windows, step_size=24, val_size=24, refit=False)
    cv['ds'] = pd.to_datetime(cv['ds'])
    if cv['ds'].dt.tz is not None:
        cv['ds'] = cv['ds'].dt.tz_localize(None)

    cv.to_csv(CV_FILE, index=False)
    print(f"CV guardado: {CV_FILE} ({len(cv)} filas)")


# ============================================================================
# PHASE 2: PRODUCTION + ENSEMBLE + REPORT
# ============================================================================

def phase_eval():
    """Evalua produccion + ensemble + zero detection sobre datos nuevos."""
    from proposal.utils.benchmark import ProductionModelEvaluator
    from ml_feature_engineering import CleanCMGFeatureEngineering
    from proposal.evaluation.eval_zero_detection import ZeroDetector
    import lightgbm as lgb
    import xgboost as xgb

    series_train, series_test, series_full = load_series()

    # Cargar CV de TiDE
    cv = pd.read_csv(CV_FILE)
    cv['ds'] = pd.to_datetime(cv['ds'])
    cv = cv.sort_values(['cutoff', 'ds'])
    cv['horizon'] = cv.groupby('cutoff').cumcount() + 1

    neural_lookup = {}
    for _, row in cv.iterrows():
        neural_lookup[row['ds']] = {'TiDE': max(0, float(row.get('TiDE', 0))), 'horizon': int(row['horizon'])}

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

    cmg = series_full['CMG [$/MWh]'].dropna()
    test_start = series_test.index.min()
    test_end = series_test.index.max()

    window_starts = []
    current = test_start
    while current + timedelta(hours=24) <= test_end:
        if current - timedelta(hours=168) >= cmg.index.min():
            window_starts.append(current)
        current += timedelta(hours=24)

    print(f"\nBacktesting: {len(window_starts)} ventanas")

    all_preds = []
    for i, ws in enumerate(window_starts):
        he = ws
        hs = he - timedelta(hours=168)
        wd = series_full.loc[hs:he].copy()
        if len(wd) < 140:
            continue
        wd['CMG [$/MWh]'] = wd['CMG [$/MWh]'].ffill().fillna(0)

        try:
            df_feat = feature_engineer.create_features(wd)
            bc = [c for c in df_feat.columns if not c.startswith(('is_zero_t+','cmg_value_t+')) and c != 'CMG [$/MWh]']
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

            neural = neural_lookup.get(td)
            if neural is None:
                continue

            tide = neural['TiDE']
            w = max(0, 1 - (h-1)/24)
            weighted_raw = w * tide + (1-w) * p['predicted_cmg']
            val_weighted = w * tide + (1-w) * p['value_prediction']
            weighted_zd = 0.0 if iz else max(0, val_weighted)
            tide_zd = 0.0 if iz else tide

            all_preds.append({
                'window': i, 'target_datetime': td, 'horizon': h, 'target_hour': th,
                'actual': actual, 'actual_is_zero': actual == 0,
                'prod': p['predicted_cmg'], 'tide_raw': tide, 'tide_zd': tide_zd,
                'weighted_raw': weighted_raw, 'weighted_zd': weighted_zd,
                'zero_prob': zp, 'predicted_zero': iz,
            })

        if (i+1) % 10 == 0:
            print(f"  Ventana {i+1}/{len(window_starts)}")

    df = pd.DataFrame(all_preds)
    print(f"  Total: {len(df)} predicciones, {df['window'].nunique()} ventanas")

    # Persistencia 24h
    persist = cmg.shift(24)

    # Metricas
    models = {
        'Produccion (LGB+XGB)': df['prod'].values,
        'TiDE continuo': df['tide_raw'].values,
        'TiDE + Zero Detection': df['tide_zd'].values,
        'Weighted continuo': df['weighted_raw'].values,
        'Weighted + Zero Detection': df['weighted_zd'].values,
    }

    # Persistencia sobre mismos puntos
    persist_vals = []
    for _, row in df.iterrows():
        td = row['target_datetime']
        past = td - timedelta(hours=24)
        persist_vals.append(cmg.get(past, np.nan))
    df['persist_24h'] = persist_vals
    df_persist = df.dropna(subset=['persist_24h'])

    results = {}
    for name, preds in models.items():
        results[name] = _metrics(df['actual'].values, preds, df['horizon'].values, df['target_hour'].values)

    # Persistencia
    if len(df_persist) > 0:
        results['Persistencia 24h'] = _metrics(
            df_persist['actual'].values, df_persist['persist_24h'].values,
            df_persist['horizon'].values, df_persist['target_hour'].values
        )

    # Reporte
    _report(results, df)

    # Guardar
    df.to_csv(RESULTS_DIR / "new_data_predictions.csv", index=False)
    summary = {n: {k:v for k,v in m.items() if k not in ('h_mae','h_zero','hourly_mae')} for n, m in results.items()}
    with open(RESULTS_DIR / "new_data_comparison.json", 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nGuardado en {RESULTS_DIR}/")


def _metrics(y, p, horizons, hours):
    e = np.abs(y - p)
    sq = (y - p)**2
    nz = y != 0
    mape = np.mean(e[nz]/y[nz])*100 if nz.sum()>0 else np.nan
    h = horizons
    short = e[h<=6].mean(); mid = e[(h>6)&(h<=12)].mean(); long_ = e[h>12].mean()
    h_mae = {}
    for hi in range(1,25):
        m = h==hi
        if m.sum()>0: h_mae[hi] = float(e[m].mean())
    tz = y==0; pz = p==0
    tp=int((tz&pz).sum()); fp=int((~tz&pz).sum()); fn=int((tz&~pz).sum()); tn=int((~tz&~pz).sum())
    prec = tp/(tp+fp) if (tp+fp)>0 else 0
    rec = tp/(tp+fn) if (tp+fn)>0 else 0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0
    mz = e[tz].mean() if tz.sum()>0 else np.nan
    mnz = e[~tz].mean() if (~tz).sum()>0 else np.nan
    h_zero = {}
    for hi in range(1,25):
        m=h==hi
        if m.sum()==0: continue
        a,b=tz[m],pz[m]; t2=(a&b).sum(); f2=(~a&b).sum(); f3=(a&~b).sum()
        p2=t2/(t2+f2) if (t2+f2)>0 else 0; r2=t2/(t2+f3) if (t2+f3)>0 else 0
        h_zero[hi]=2*p2*r2/(p2+r2) if (p2+r2)>0 else 0
    return {'mae':float(e.mean()),'rmse':float(np.sqrt(sq.mean())),'mape':float(mape),
            'short':float(short),'mid':float(mid),'long':float(long_),
            'h_mae':h_mae,'h_zero':h_zero,
            'zero_f1':float(f1),'zero_precision':float(prec),'zero_recall':float(rec),
            'tp':tp,'fp':fp,'fn':fn,'tn':tn,
            'n_actual_zeros':int(tz.sum()),'n_pred_zeros':int(pz.sum()),
            'mae_when_zero':float(mz),'mae_when_nonzero':float(mnz),'n':len(y)}


def _report(results, df):
    nz = (df['actual']==0).sum(); n = len(df)
    print("\n"+"="*105)
    print("REPORTE: DATOS NUEVOS (Ene 28 - Abr 2, 2026) — NUNCA VISTOS POR NINGUN MODELO")
    print("="*105)
    print(f"Train: datos locales (Sep 2025 - Ene 27, 2026)")
    print(f"Test:  Supabase (Ene 28 - Abr 2, 2026)")
    print(f"Predicciones: {n} | Ventanas: {df['window'].nunique()} | Zeros: {nz} ({nz/n*100:.1f}%)")

    print(f"\n{'─'*105}")
    print("MAE")
    print(f"{'─'*105}")
    print(f"{'Modelo':<35} {'MAE':>7} {'RMSE':>7} {'Corto':>9} {'Medio':>9} {'Largo':>9} {'MAE(0)':>9} {'MAE(>0)':>9}")
    print(f"{'':35} {'':>7} {'':>7} {'(t+1..6)':>9} {'(t+7..12)':>9} {'(t+13..24)':>9} {'(real=0)':>9} {'(real>0)':>9}")
    print("-"*105)
    for name in sorted(results, key=lambda x: results[x]['mae']):
        m=results[name]
        print(f"{name:<35} {m['mae']:>7.2f} {m['rmse']:>7.2f} ${m['short']:>8.2f} ${m['mid']:>8.2f} ${m['long']:>8.2f} ${m['mae_when_zero']:>8.2f} ${m['mae_when_nonzero']:>8.2f}")

    print(f"\n{'─'*105}")
    print("DETECCION DE ZEROS")
    print(f"{'─'*105}")
    print(f"{'Modelo':<35} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Pred 0s':>10} {'Real 0s':>10}")
    print("-"*105)
    for name in sorted(results, key=lambda x: -results[x]['zero_f1']):
        m=results[name]
        print(f"{name:<35} {m['zero_precision']:>10.3f} {m['zero_recall']:>10.3f} {m['zero_f1']:>10.3f} {m['n_pred_zeros']:>10d} {m['n_actual_zeros']:>10d}")

    print(f"\n{'─'*105}")
    print("MATRICES DE CONFUSION")
    for name in ['Produccion (LGB+XGB)', 'Weighted + Zero Detection']:
        m=results[name]
        print(f"\n  {name}:")
        print(f"                    Pred=0    Pred>0")
        print(f"    Real=0    {m['tp']:>10d} {m['fn']:>10d}")
        print(f"    Real>0    {m['fp']:>10d} {m['tn']:>10d}")

    print(f"\n{'─'*105}")
    print("MAE POR HORIZONTE")
    print(f"{'─'*105}")
    km = ['Produccion (LGB+XGB)','Weighted continuo','Weighted + Zero Detection']
    print(f"{'h':<6}"+"".join(f"{n[:28]:>30}" for n in km))
    for hi in range(1,25):
        row=f"t+{hi:<4}"
        for n in km: row+=f"${results[n]['h_mae'].get(hi,np.nan):>28.2f}"
        print(row)

    prod=results['Produccion (LGB+XGB)']
    wzd=results['Weighted + Zero Detection']
    print(f"\n{'='*105}")
    print("RESUMEN FINAL")
    print(f"{'='*105}")
    print(f"\n  Weighted + Zero Detection vs Produccion:")
    print(f"    MAE:       ${wzd['mae']:.2f} vs ${prod['mae']:.2f} ({(wzd['mae']-prod['mae'])/prod['mae']*100:+.1f}%)")
    print(f"    Corto:     ${wzd['short']:.2f} vs ${prod['short']:.2f} ({(wzd['short']-prod['short'])/prod['short']*100:+.1f}%)")
    print(f"    Medio:     ${wzd['mid']:.2f} vs ${prod['mid']:.2f} ({(wzd['mid']-prod['mid'])/prod['mid']*100:+.1f}%)")
    print(f"    Largo:     ${wzd['long']:.2f} vs ${prod['long']:.2f} ({(wzd['long']-prod['long'])/prod['long']*100:+.1f}%)")
    print(f"    Zero F1:   {wzd['zero_f1']:.3f} vs {prod['zero_f1']:.3f}")
    print(f"    MAE(real=0): ${wzd['mae_when_zero']:.2f} vs ${prod['mae_when_zero']:.2f}")
    print(f"{'='*105}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['train', 'eval'], required=True)
    args = parser.parse_args()

    if args.phase == 'train':
        phase_train()
    else:
        phase_eval()
