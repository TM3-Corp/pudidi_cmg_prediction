#!/usr/bin/env python3
"""Genera figuras para el documento LaTeX del storyline."""

import sys
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS = PROJECT_ROOT / "proposal" / "results"
FIGS = Path(__file__).parent / "figures"
FIGS.mkdir(exist_ok=True)

plt.rcParams.update({
    'figure.dpi': 150,
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 10,
    'legend.fontsize': 9,
    'figure.figsize': (7, 3.5),
    'axes.grid': True,
    'grid.alpha': 0.3,
})

COLORS = {
    'Produccion': '#d62728',
    'TiDE': '#2ca02c',
    'Weighted': '#1f77b4',
    'W+ZD': '#9467bd',
    'Persistencia': '#7f7f7f',
    'NHITS': '#ff7f0e',
    'NBEATSx': '#8c564b',
}


def fig1_serie_temporal():
    """Serie temporal CMG completa con zonas train/test."""
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "proposal"))
    from data_loader import CMGDataLoader

    loader = CMGDataLoader()
    df = loader.load_cmg_online()
    series = loader.build_averaged_series(df)

    # Supabase data
    new_file = RESULTS / "supabase_new_data.json"
    if new_file.exists():
        with open(new_file) as f:
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
        full = pd.concat([series, sn])
        full = full[~full.index.duplicated(keep='last')].sort_index()
    else:
        full = series

    fig, ax = plt.subplots(figsize=(7, 3))
    cmg = full['CMG [$/MWh]']

    ax.plot(cmg.index, cmg.values, linewidth=0.4, color='#333', alpha=0.8)

    # Shading
    cutoff_local = pd.Timestamp('2026-01-27')
    ax.axvspan(cmg.index.min(), cutoff_local, alpha=0.08, color='blue', label='Train (local)')
    ax.axvspan(cutoff_local, cmg.index.max(), alpha=0.08, color='red', label='Test (Supabase)')
    ax.axvline(cutoff_local, color='red', linestyle='--', linewidth=1, alpha=0.7)

    ax.set_ylabel('CMG [USD/MWh]')
    ax.set_xlabel('')
    ax.set_title('Serie Temporal CMG (promedio 3 nodos)')
    ax.legend(loc='upper left', framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate()
    plt.tight_layout()
    fig.savefig(FIGS / 'fig1_serie_temporal.pdf', bbox_inches='tight')
    plt.close()
    print("fig1 OK")


def fig2_mae_por_horizonte():
    """MAE por horizonte: produccion vs TiDE vs Weighted (backtesting 45d local)."""
    with open(RESULTS / "neural_models_comparison.json") as f:
        data = json.load(f)

    fig, ax = plt.subplots(figsize=(7, 3.5))

    for name, color, ls in [
        ('Produccion (LGB+XGB)', COLORS['Produccion'], '-'),
        ('TiDE', COLORS['TiDE'], '-'),
        ('Persistencia 24h', COLORS['Persistencia'], '--'),
    ]:
        if name not in data:
            continue
        hm = data[name].get('horizon_mae', {})
        if not hm:
            continue
        hs = sorted(int(k) for k in hm)
        vals = [hm[str(h)] for h in hs]
        ax.plot(hs, vals, marker='o', markersize=3, linewidth=1.5, color=color, linestyle=ls, label=name)

    ax.set_xlabel('Horizonte (horas)')
    ax.set_ylabel('MAE [USD/MWh]')
    ax.set_title('MAE por Horizonte (backtesting 45 dias)')
    ax.set_xticks(range(1, 25))
    ax.legend(loc='upper right', framealpha=0.9)
    plt.tight_layout()
    fig.savefig(FIGS / 'fig2_mae_horizonte.pdf', bbox_inches='tight')
    plt.close()
    print("fig2 OK")


def fig3_mae_por_horizonte_ensemble():
    """MAE por horizonte: Produccion vs Weighted vs W+ZD (con zero detection)."""
    zd_file = RESULTS / "ensemble_zero_detection_comparison.json"
    if not zd_file.exists():
        print("fig3 SKIP (no ensemble_zero_detection_comparison.json)")
        return

    # Use predictions CSV for more detail
    pred_file = RESULTS / "ensemble_zero_detection_predictions.csv"
    if not pred_file.exists():
        print("fig3 SKIP")
        return

    df = pd.read_csv(pred_file)

    fig, ax = plt.subplots(figsize=(7, 3.5))

    for col, name, color, ls in [
        ('prod', 'Produccion', COLORS['Produccion'], '-'),
        ('weighted_raw', 'Weighted continuo', COLORS['Weighted'], '-'),
        ('weighted_zd', 'Weighted + ZD', COLORS['W+ZD'], '--'),
    ]:
        mae_h = df.groupby('horizon').apply(lambda g: (g['actual'] - g[col]).abs().mean())
        ax.plot(mae_h.index, mae_h.values, marker='o', markersize=3, linewidth=1.5,
                color=color, linestyle=ls, label=name)

    ax.set_xlabel('Horizonte (horas)')
    ax.set_ylabel('MAE [USD/MWh]')
    ax.set_title('Efecto del Zero Detection en MAE por Horizonte')
    ax.set_xticks(range(1, 25))
    ax.legend(loc='upper right', framealpha=0.9)
    plt.tight_layout()
    fig.savefig(FIGS / 'fig3_mae_horizonte_zd.pdf', bbox_inches='tight')
    plt.close()
    print("fig3 OK")


def fig4_cv_folds():
    """MAE por fold del CV temporal."""
    summary_file = RESULTS / "timeseries_cv_summary.json"
    if not summary_file.exists():
        print("fig4 SKIP")
        return

    with open(summary_file) as f:
        summary = json.load(f)

    fig, ax = plt.subplots(figsize=(7, 3.5))

    models = ['Produccion (LGB+XGB)', 'TiDE continuo', 'Weighted continuo', 'Persistencia 24h']
    colors = [COLORS['Produccion'], COLORS['TiDE'], COLORS['Weighted'], COLORS['Persistencia']]

    x = np.arange(5)
    width = 0.18

    for i, (name, color) in enumerate(zip(models, colors)):
        if name not in summary:
            continue
        maes = summary[name]['fold_maes']
        ax.bar(x + i * width, maes, width, label=name, color=color, alpha=0.85)

    ax.set_xlabel('Fold')
    ax.set_ylabel('MAE [USD/MWh]')
    ax.set_title('MAE por Fold (CV Expanding Window, 5 folds)')
    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels(['Fold 0\n(Nov)', 'Fold 1\n(Dic)', 'Fold 2\n(Ene)', 'Fold 3\n(Feb)', 'Fold 4\n(Mar)'])
    ax.legend(loc='upper left', framealpha=0.9, fontsize=8)
    plt.tight_layout()
    fig.savefig(FIGS / 'fig4_cv_folds.pdf', bbox_inches='tight')
    plt.close()
    print("fig4 OK")


def fig5_new_data_comparison():
    """MAE out-of-sample (datos nuevos Supabase)."""
    pred_file = RESULTS / "new_data_predictions.csv"
    if not pred_file.exists():
        print("fig5 SKIP")
        return

    df = pd.read_csv(pred_file)

    fig, ax = plt.subplots(figsize=(7, 3.5))

    for col, name, color, ls in [
        ('prod', 'Produccion', COLORS['Produccion'], '-'),
        ('tide_raw', 'TiDE continuo', COLORS['TiDE'], '-'),
        ('weighted_raw', 'Weighted continuo', COLORS['Weighted'], '-'),
        ('weighted_zd', 'Weighted + ZD', COLORS['W+ZD'], '--'),
    ]:
        mae_h = df.groupby('horizon').apply(lambda g: (g['actual'] - g[col]).abs().mean())
        ax.plot(mae_h.index, mae_h.values, marker='o', markersize=3, linewidth=1.5,
                color=color, linestyle=ls, label=name)

    ax.set_xlabel('Horizonte (horas)')
    ax.set_ylabel('MAE [USD/MWh]')
    ax.set_title('MAE por Horizonte - Datos Nuevos (Ene-Abr 2026, out-of-sample)')
    ax.set_xticks(range(1, 25))
    ax.legend(loc='upper left', framealpha=0.9, fontsize=8)
    plt.tight_layout()
    fig.savefig(FIGS / 'fig5_new_data_horizonte.pdf', bbox_inches='tight')
    plt.close()
    print("fig5 OK")


def fig6_resumen_barras():
    """Barras comparativas de MAE global por evaluacion."""
    data = {
        'Backtesting\n45d local': {'Produccion': 50.76, 'TiDE': 48.82, 'Weighted': 47.00},
        'Out-of-sample\nSupabase': {'Produccion': 38.78, 'TiDE': 30.00, 'Weighted': 31.43},
        'CV 5 folds\n(media)': {'Produccion': 46.40, 'TiDE': 40.15, 'Weighted': 41.43},
    }

    fig, ax = plt.subplots(figsize=(7, 3.5))

    x = np.arange(len(data))
    width = 0.22

    for i, (model, color) in enumerate([
        ('Produccion', COLORS['Produccion']),
        ('TiDE', COLORS['TiDE']),
        ('Weighted', COLORS['Weighted']),
    ]):
        vals = [data[k][model] for k in data]
        bars = ax.bar(x + i * width, vals, width, label=model, color=color, alpha=0.85)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'${val:.0f}', ha='center', va='bottom', fontsize=8)

    ax.set_ylabel('MAE [USD/MWh]')
    ax.set_title('Comparativa MAE Global por Tipo de Evaluacion')
    ax.set_xticks(x + width)
    ax.set_xticklabels(data.keys())
    ax.legend(loc='upper right', framealpha=0.9)
    ax.set_ylim(0, 65)
    plt.tight_layout()
    fig.savefig(FIGS / 'fig6_resumen_barras.pdf', bbox_inches='tight')
    plt.close()
    print("fig6 OK")


if __name__ == '__main__':
    fig1_serie_temporal()
    fig2_mae_por_horizonte()
    fig3_mae_por_horizonte_ensemble()
    fig4_cv_folds()
    fig5_new_data_comparison()
    fig6_resumen_barras()
    print("\nTodas las figuras generadas en", FIGS)
