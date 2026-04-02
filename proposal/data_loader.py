"""
Data Loader para Experimentacion ML - CMG Prediction
=====================================================

Carga datos desde cache local (data/cache/) y los prepara en formato
listo para entrenar/evaluar modelos de prediccion de CMG.

No requiere conexion a Supabase. Usa los JSON cacheados localmente.

Uso:
    from proposal.data_loader import CMGDataLoader

    loader = CMGDataLoader()
    df = loader.load_cmg_online()
    series = loader.build_hourly_series(df, node='NVA_P.MONTT___220')
    train, test = loader.train_test_split(series, test_days=30)
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import timedelta
from typing import Tuple, Optional
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Paths
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CMG_HISTORICAL_FILE = CACHE_DIR / "cmg_historical_latest.json"

# Nodes used in production
ACTIVE_NODES = ['NVA_P.MONTT___220', 'DALCAHUE______110', 'PIDPID________110']


class CMGDataLoader:
    """Carga y prepara datos CMG desde cache local para experimentacion ML."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or CACHE_DIR

    def load_cmg_online(
        self,
        node: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Carga datos historicos de CMG Online desde cache local.

        Args:
            node: Nodo especifico o None para todos
            start_date: Filtrar desde YYYY-MM-DD
            end_date: Filtrar hasta YYYY-MM-DD

        Returns:
            DataFrame con columnas: datetime, date, hour, node, cmg_usd
        """
        cache_file = self.cache_dir / "cmg_historical_latest.json"
        if not cache_file.exists():
            raise FileNotFoundError(f"Cache no encontrado: {cache_file}")

        with open(cache_file, 'r') as f:
            raw = json.load(f)

        records = raw.get('data', [])
        if not records:
            print("Sin datos en cache")
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df['datetime'] = pd.to_datetime(df['datetime'], format='mixed')
        df['cmg_usd'] = pd.to_numeric(df['cmg_usd'], errors='coerce')

        # Filtros opcionales
        if node:
            df = df[df['node'] == node]
        if start_date:
            df = df[df['date'] >= start_date]
        if end_date:
            df = df[df['date'] <= end_date]

        df = df.sort_values('datetime').reset_index(drop=True)

        metadata = raw.get('metadata', {})
        print(f"CMG Online cargado: {len(df)} registros")
        print(f"  Rango: {metadata.get('oldest_date', '?')} -> {metadata.get('newest_date', '?')}")
        print(f"  Nodos: {df['node'].unique().tolist()}")

        return df

    def build_hourly_series(
        self,
        df_online: pd.DataFrame,
        node: str = 'NVA_P.MONTT___220',
        fill_method: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Construye serie temporal horaria continua para un nodo.

        Args:
            df_online: DataFrame de load_cmg_online()
            node: Nodo a filtrar
            fill_method: 'ffill', 'zero', o None (dejar NaN)

        Returns:
            DataFrame con DatetimeIndex y columna 'CMG [$/MWh]'
        """
        df = df_online[df_online['node'] == node].copy()
        df['hour_floor'] = pd.to_datetime(df['datetime']).dt.floor('h')

        # Promediar si hay duplicados por hora
        hourly = df.groupby('hour_floor')['cmg_usd'].mean()

        # Crear rango continuo
        full_range = pd.date_range(
            start=hourly.index.min(),
            end=hourly.index.max(),
            freq='h',
        )
        hourly = hourly.reindex(full_range)
        hourly.index.name = 'datetime'
        hourly.name = 'CMG [$/MWh]'

        n_total = len(hourly)
        n_missing = hourly.isna().sum()
        n_zeros = (hourly == 0).sum()

        if fill_method == 'ffill':
            hourly = hourly.ffill()
        elif fill_method == 'zero':
            hourly = hourly.fillna(0)

        series = hourly.to_frame()

        print(f"Serie horaria [{node}]: {n_total} horas")
        print(f"  Rango: {series.index.min()} -> {series.index.max()}")
        print(f"  Faltantes: {n_missing} ({n_missing/n_total*100:.1f}%)")
        print(f"  Zeros (CMG=0): {n_zeros} ({n_zeros/n_total*100:.1f}%)")
        print(f"  Media: ${hourly.mean():.2f}/MWh | Std: ${hourly.std():.2f}")

        return series

    def build_averaged_series(
        self,
        df_online: pd.DataFrame,
        nodes: Optional[list] = None,
    ) -> pd.DataFrame:
        """
        Construye serie promediando multiples nodos (como hace produccion).

        Args:
            df_online: DataFrame de load_cmg_online()
            nodes: Lista de nodos a promediar (default: todos)

        Returns:
            DataFrame con DatetimeIndex y columna 'CMG [$/MWh]'
        """
        if nodes:
            df = df_online[df_online['node'].isin(nodes)].copy()
        else:
            df = df_online.copy()

        df['hour_floor'] = pd.to_datetime(df['datetime']).dt.floor('h')

        # Promediar todos los nodos por hora (como hace ml_hourly_forecast.py)
        hourly = df.groupby('hour_floor')['cmg_usd'].mean()

        full_range = pd.date_range(
            start=hourly.index.min(),
            end=hourly.index.max(),
            freq='h',
        )
        hourly = hourly.reindex(full_range)
        hourly.index.name = 'datetime'
        hourly.name = 'CMG [$/MWh]'

        series = hourly.to_frame()

        n_total = len(series)
        n_missing = series['CMG [$/MWh]'].isna().sum()
        n_zeros = (series['CMG [$/MWh]'] == 0).sum()

        print(f"Serie promediada ({len(df['node'].unique())} nodos): {n_total} horas")
        print(f"  Rango: {series.index.min()} -> {series.index.max()}")
        print(f"  Faltantes: {n_missing} ({n_missing/n_total*100:.1f}%)")
        print(f"  Zeros: {n_zeros} ({n_zeros/n_total*100:.1f}%)")
        print(f"  Media: ${series['CMG [$/MWh]'].mean():.2f}/MWh")

        return series

    def train_test_split(
        self,
        series: pd.DataFrame,
        test_days: int = 30,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split cronologico para series temporales.

        Args:
            series: DataFrame con DatetimeIndex
            test_days: Dias para test (los mas recientes)

        Returns:
            (train_df, test_df)
        """
        cutoff = series.index.max() - timedelta(days=test_days)
        train = series[series.index <= cutoff].copy()
        test = series[series.index > cutoff].copy()

        print(f"Split cronologico:")
        print(f"  Train: {len(train)} horas ({train.index.min()} -> {train.index.max()})")
        print(f"  Test:  {len(test)} horas ({test.index.min()} -> {test.index.max()})")

        return train, test


if __name__ == '__main__':
    loader = CMGDataLoader()

    print("=" * 60)
    print("TEST: Carga local de datos CMG")
    print("=" * 60)
    df = loader.load_cmg_online()

    print("\n" + "=" * 60)
    print("TEST: Serie horaria Puerto Montt")
    print("=" * 60)
    series = loader.build_hourly_series(df, node='NVA_P.MONTT___220')
    print(series.head())

    print("\n" + "=" * 60)
    print("TEST: Serie promediada (como produccion)")
    print("=" * 60)
    avg_series = loader.build_averaged_series(df)
    print(avg_series.head())

    print("\n" + "=" * 60)
    print("TEST: Train/Test split (30 dias test)")
    print("=" * 60)
    train, test = loader.train_test_split(avg_series, test_days=30)
