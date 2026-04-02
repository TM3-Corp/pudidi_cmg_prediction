#!/usr/bin/env python3
"""
Evaluacion de Ensembles Hibridos
=================================

Combina TiDE (mejor en corto plazo) con Produccion (mejor en largo plazo)
en distintas configuraciones y evalua cual es optima.

Uso:
    python proposal/eval_hybrid_ensemble.py
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def load_and_merge():
    """Carga predicciones de produccion y modelos neurales, las alinea por datetime."""
    prod = pd.read_csv(RESULTS_DIR / "predictions_produccion_(lgb+xgb).csv")
    cv = pd.read_csv(RESULTS_DIR / "cv_neural_models.csv")

    prod['target_datetime'] = pd.to_datetime(prod['target_datetime'])
    cv['ds'] = pd.to_datetime(cv['ds'])

    # Recalcular horizonte en CV
    cv = cv.sort_values(['cutoff', 'ds'])
    cv['horizon'] = cv.groupby('cutoff').cumcount() + 1

    # Merge por datetime
    merged = prod.merge(
        cv[['ds', 'NHITS', 'NBEATSx', 'TiDE']].rename(columns={'ds': 'target_datetime'}),
        on='target_datetime',
        how='inner',
    )

    # Clip neurales a >= 0
    for col in ['NHITS', 'NBEATSx', 'TiDE']:
        merged[col] = merged[col].clip(lower=0)

    merged['target_hour'] = pd.to_datetime(merged['target_datetime']).dt.hour

    print(f"Datos alineados: {len(merged)} predicciones, {merged['window'].nunique()} ventanas")
    return merged


def build_ensembles(df):
    """Construye todas las variantes de ensemble hibrido."""

    ensembles = {}

    # 1-5: TiDE + Produccion con distintos cutoffs
    for cutoff in [6, 9, 12, 15]:
        name = f"TiDE(1-{cutoff}) + Prod({cutoff+1}-24)"
        ensembles[name] = np.where(df['horizon'] <= cutoff, df['TiDE'], df['predicted'])

    # 6-7: NHITS + Produccion
    for cutoff in [9, 12]:
        name = f"NHITS(1-{cutoff}) + Prod({cutoff+1}-24)"
        ensembles[name] = np.where(df['horizon'] <= cutoff, df['NHITS'], df['predicted'])

    # 8: Promedio ponderado TiDE + Prod (peso TiDE decrece linealmente)
    w_tide = np.array([max(0, 1 - (h - 1) / 24) for h in df['horizon']])
    ensembles["Weighted: TiDE*w + Prod*(1-w)"] = w_tide * df['TiDE'] + (1 - w_tide) * df['predicted']

    # 9: Promedio simple TiDE + Prod (para corto) + Prod (para largo)
    ensembles["Avg(TiDE,Prod) h<=12 + Prod"] = np.where(
        df['horizon'] <= 12,
        (df['TiDE'] + df['predicted']) / 2,
        df['predicted'],
    )

    # 10: Oracle - mejor modelo por horizonte
    best_per_h = {}
    for h in range(1, 25):
        hm = df[df['horizon'] == h]
        if hm.empty:
            continue
        maes = {
            'predicted': (hm['actual'] - hm['predicted']).abs().mean(),
            'TiDE': (hm['actual'] - hm['TiDE']).abs().mean(),
            'NHITS': (hm['actual'] - hm['NHITS']).abs().mean(),
            'NBEATSx': (hm['actual'] - hm['NBEATSx']).abs().mean(),
        }
        best_per_h[h] = min(maes, key=maes.get)

    oracle = df['predicted'].copy()
    for h, model in best_per_h.items():
        mask = df['horizon'] == h
        oracle[mask] = df.loc[mask, model]
    ensembles["Oracle (mejor por h)"] = oracle

    return ensembles, best_per_h


def compute_metrics(y_true, y_pred, horizons):
    """Calcula metricas globales y por bloque de horizonte."""
    errors = np.abs(y_true - y_pred)
    sq = (y_true - y_pred) ** 2
    nonzero = y_true != 0

    mape = np.mean(errors[nonzero] / y_true[nonzero]) * 100 if nonzero.sum() > 0 else np.nan

    short = errors[horizons <= 6].mean()
    mid = errors[(horizons > 6) & (horizons <= 12)].mean()
    long_ = errors[horizons > 12].mean()

    h_mae = {}
    for h in range(1, 25):
        hm = errors[horizons == h]
        if len(hm) > 0:
            h_mae[h] = float(hm.mean())

    return {
        'mae': float(errors.mean()),
        'rmse': float(np.sqrt(sq.mean())),
        'mape': float(mape),
        'short': float(short),
        'mid': float(mid),
        'long': float(long_),
        'h_mae': h_mae,
    }


def main():
    # Cargar datos
    df = load_and_merge()
    horizons = df['horizon'].values

    # Modelos base
    base_models = {
        'Produccion (LGB+XGB)': df['predicted'].values,
        'TiDE': df['TiDE'].values,
        'NHITS': df['NHITS'].values,
        'NBEATSx': df['NBEATSx'].values,
    }

    # Ensembles
    ensembles, best_per_h = build_ensembles(df)

    # Calcular metricas para todo
    all_metrics = {}
    for name, preds in {**base_models, **ensembles}.items():
        all_metrics[name] = compute_metrics(df['actual'].values, np.array(preds), horizons)

    # ================================================================
    # REPORTE
    # ================================================================
    print("\n" + "=" * 100)
    print("EVALUACION ENSEMBLES HIBRIDOS")
    print("=" * 100)

    print(f"\n{'Modelo':<42} {'MAE':>7} {'RMSE':>7} {'MAPE%':>7} {'Corto':>9} {'Medio':>9} {'Largo':>9}")
    print(f"{'':42} {'':>7} {'':>7} {'':>7} {'(t+1..6)':>9} {'(t+7..12)':>9} {'(t+13..24)':>9}")
    print("-" * 100)

    for name in sorted(all_metrics, key=lambda x: all_metrics[x]['mae']):
        m = all_metrics[name]
        marker = " ***" if name == min(all_metrics, key=lambda x: all_metrics[x]['mae']) else ""
        print(
            f"{name:<42} "
            f"{m['mae']:>7.2f} "
            f"{m['rmse']:>7.2f} "
            f"{m['mape']:>7.1f} "
            f"${m['short']:>8.2f} "
            f"${m['mid']:>8.2f} "
            f"${m['long']:>8.2f}"
            f"{marker}"
        )

    # MAE por horizonte: top 4
    print(f"\n{'─' * 100}")
    print("MAE POR HORIZONTE")
    print(f"{'─' * 100}")

    top_names = [
        'Produccion (LGB+XGB)',
        'TiDE',
        min(ensembles, key=lambda x: all_metrics[x]['mae']),
        'Oracle (mejor por h)',
    ]
    # Deduplicate
    top_names = list(dict.fromkeys(top_names))

    header = f"{'h':<6}" + "".join(f"{n[:22]:>24}" for n in top_names)
    print(header)
    print("-" * (6 + 24 * len(top_names)))

    for h in range(1, 25):
        row = f"t+{h:<4}"
        for name in top_names:
            v = all_metrics[name]['h_mae'].get(h, np.nan)
            row += f"${v:>22.2f}"
        print(row)

    # Oracle selection
    print(f"\n{'─' * 100}")
    print("ORACLE: MODELO SELECCIONADO POR HORIZONTE")
    print(f"{'─' * 100}")

    for h in sorted(best_per_h):
        model = best_per_h[h]
        model_label = 'Produccion' if model == 'predicted' else model
        mae_val = all_metrics['Oracle (mejor por h)']['h_mae'].get(h, 0)
        print(f"  t+{h:>2}: {model_label:<12} (MAE=${mae_val:.2f})")

    # Resumen final
    best_ensemble_name = min(
        [n for n in ensembles if 'Oracle' not in n],
        key=lambda x: all_metrics[x]['mae'],
    )
    best = all_metrics[best_ensemble_name]
    prod = all_metrics['Produccion (LGB+XGB)']
    oracle = all_metrics['Oracle (mejor por h)']

    print(f"\n{'=' * 100}")
    print("RESUMEN")
    print(f"{'=' * 100}")
    print(f"\n  Mejor ensemble practico: {best_ensemble_name}")
    print(f"    MAE global: ${best['mae']:.2f} vs Produccion ${prod['mae']:.2f} ({(best['mae']-prod['mae'])/prod['mae']*100:+.1f}%)")
    print(f"    Corto:      ${best['short']:.2f} vs ${prod['short']:.2f} ({(best['short']-prod['short'])/prod['short']*100:+.1f}%)")
    print(f"    Medio:      ${best['mid']:.2f} vs ${prod['mid']:.2f} ({(best['mid']-prod['mid'])/prod['mid']*100:+.1f}%)")
    print(f"    Largo:      ${best['long']:.2f} vs ${prod['long']:.2f} ({(best['long']-prod['long'])/prod['long']*100:+.1f}%)")
    print(f"\n  Techo teorico (Oracle): ${oracle['mae']:.2f} ({(oracle['mae']-prod['mae'])/prod['mae']*100:+.1f}% vs Produccion)")
    print(f"{'=' * 100}")

    # Guardar
    df_out = df.copy()
    for name, preds in ensembles.items():
        safe_name = name.replace(' ', '_').replace('(', '').replace(')', '').replace('+', '_')
        df_out[safe_name] = preds
    df_out.to_csv(RESULTS_DIR / "hybrid_ensemble_predictions.csv", index=False)

    summary = {
        name: {k: v for k, v in m.items() if k != 'h_mae'}
        for name, m in all_metrics.items()
    }
    summary['oracle_selection'] = {str(h): m for h, m in best_per_h.items()}

    with open(RESULTS_DIR / "hybrid_ensemble_comparison.json", 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nResultados guardados en {RESULTS_DIR}/")


if __name__ == '__main__':
    main()
