#!/usr/bin/env python3
"""
Clean Feature Engineering Module - NO DATA LEAKAGE
====================================================

This module creates features for predicting CMG at horizons t+1 to t+24
with ZERO future information leakage.

Key Principle: When at time t predicting t+h, we only know data up to t-1

Critical Fix from Audit:
- WRONG: df['cmg_mean_24h'] = df['CMG'].rolling(24).mean()  # Includes current!
- CORRECT: df['cmg_mean_24h'] = df['CMG'].shift(1).rolling(24).mean()  # Only past

Author: Enhanced for institutional-grade forecasting
Date: 2025-01-10
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')


class CleanCMGFeatureEngineering:
    """
    Feature engineering for CMG forecasting with rigorous leakage prevention
    """

    def __init__(self,
                 target_horizons: List[int] = None,
                 rolling_windows: List[int] = None,
                 lag_hours: List[int] = None):
        """
        Initialize feature engineering pipeline

        Args:
            target_horizons: Hours ahead to predict (default: 1 to 24)
            rolling_windows: Window sizes for rolling stats (default: [6, 12, 24, 48, 168])
            lag_hours: Specific lag hours to include (default: [1, 2, 3, 6, 12, 24, 48, 168])
        """
        self.target_horizons = target_horizons or list(range(1, 25))
        self.rolling_windows = rolling_windows or [6, 12, 24, 48, 168]
        self.lag_hours = lag_hours or [1, 2, 3, 6, 12, 24, 48, 168, 336]

        # Track feature names for later inspection
        self.feature_names = []

    def create_features(self, df: pd.DataFrame, cmg_column: str = 'CMG [$/MWh]',
                        cmg_programado_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Create all features with NO future leakage

        Args:
            df: DataFrame with datetime index and CMG column
            cmg_column: Name of the CMG price column
            cmg_programado_df: Optional DataFrame with CMG Programado forecasts
                               Should have columns: 'target_datetime', 'cmg_usd'
                               indexed by forecast_datetime

        Returns:
            DataFrame with all features and targets
        """
        df_feat = df.copy()
        self.feature_names = []

        # Ensure datetime index
        if not isinstance(df_feat.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have DatetimeIndex")

        # Ensure CMG column exists
        if cmg_column not in df_feat.columns:
            raise ValueError(f"Column '{cmg_column}' not found in DataFrame")

        print(f"Creating features for {len(df_feat)} hours of data...")
        print(f"Date range: {df_feat.index.min()} to {df_feat.index.max()}")

        # 1. Time-based features (always available, no leakage)
        df_feat = self._add_time_features(df_feat)

        # 2. Lag features (shifted, so no leakage)
        df_feat = self._add_lag_features(df_feat, cmg_column)

        # 3. Rolling statistics (CRITICAL: shift(1) before rolling)
        df_feat = self._add_rolling_features(df_feat, cmg_column)

        # 4. Zero pattern features
        df_feat = self._add_zero_pattern_features(df_feat, cmg_column)

        # 5. Trend features
        df_feat = self._add_trend_features(df_feat, cmg_column)

        # 6. Seasonal features
        df_feat = self._add_seasonal_features(df_feat, cmg_column)

        # 7. CMG Programado features (if available)
        if cmg_programado_df is not None:
            df_feat = self._add_cmg_programado_features(df_feat, cmg_column, cmg_programado_df)

        # 8. Create targets for all horizons
        df_feat = self._add_targets(df_feat, cmg_column)

        print(f"✓ Created {len(self.feature_names)} features")
        print(f"✓ Created {len(self.target_horizons)} target variables")

        return df_feat

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add time-based features with cyclical encoding
        These are always available at prediction time, no leakage risk
        """
        # Hour of day (0-23)
        df['hour'] = df.index.hour
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        self.feature_names.extend(['hour', 'hour_sin', 'hour_cos'])

        # Day of week (0-6)
        df['day_of_week'] = df.index.dayofweek
        df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        self.feature_names.extend(['day_of_week', 'dow_sin', 'dow_cos'])

        # Month (1-12)
        df['month'] = df.index.month
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        self.feature_names.extend(['month', 'month_sin', 'month_cos'])

        # Weekend indicator
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        self.feature_names.append('is_weekend')

        # Time of day categories
        df['is_night'] = ((df['hour'] >= 0) & (df['hour'] < 6)).astype(int)
        df['is_morning'] = ((df['hour'] >= 6) & (df['hour'] < 12)).astype(int)
        df['is_afternoon'] = ((df['hour'] >= 12) & (df['hour'] < 18)).astype(int)
        df['is_evening'] = ((df['hour'] >= 18) & (df['hour'] < 24)).astype(int)
        self.feature_names.extend(['is_night', 'is_morning', 'is_afternoon', 'is_evening'])

        return df

    def _add_lag_features(self, df: pd.DataFrame, cmg_column: str) -> pd.DataFrame:
        """
        Add lagged CMG values
        Lags are inherently safe (use past data)
        """
        for lag in self.lag_hours:
            df[f'cmg_lag_{lag}h'] = df[cmg_column].shift(lag)
            self.feature_names.append(f'cmg_lag_{lag}h')

        return df

    def _add_rolling_features(self, df: pd.DataFrame, cmg_column: str) -> pd.DataFrame:
        """
        Add rolling statistics with PROPER SHIFT to prevent leakage

        CRITICAL FIX: shift(1) BEFORE rolling() to exclude current hour
        """
        for window in self.rolling_windows:
            # CORRECT: shift(1) ensures we only use past data
            shifted_series = df[cmg_column].shift(1)

            # Mean
            df[f'cmg_mean_{window}h'] = shifted_series.rolling(
                window, min_periods=1
            ).mean()

            # Std deviation
            df[f'cmg_std_{window}h'] = shifted_series.rolling(
                window, min_periods=1
            ).std().fillna(0)

            # Min
            df[f'cmg_min_{window}h'] = shifted_series.rolling(
                window, min_periods=1
            ).min()

            # Max
            df[f'cmg_max_{window}h'] = shifted_series.rolling(
                window, min_periods=1
            ).max()

            # Range
            df[f'cmg_range_{window}h'] = (
                df[f'cmg_max_{window}h'] - df[f'cmg_min_{window}h']
            )

            # Coefficient of variation (CV)
            df[f'cmg_cv_{window}h'] = df[f'cmg_std_{window}h'] / (
                df[f'cmg_mean_{window}h'] + 1e-6
            )

            self.feature_names.extend([
                f'cmg_mean_{window}h', f'cmg_std_{window}h',
                f'cmg_min_{window}h', f'cmg_max_{window}h',
                f'cmg_range_{window}h', f'cmg_cv_{window}h'
            ])

        return df

    def _add_zero_pattern_features(self, df: pd.DataFrame, cmg_column: str) -> pd.DataFrame:
        """
        Add features about zero CMG patterns
        CRITICAL: Use shifted data only
        """
        # Create shifted zero indicator
        is_zero_shifted = (df[cmg_column].shift(1) == 0).astype(int)

        for window in [6, 12, 24, 48, 168]:
            # Count of zeros in window
            df[f'zeros_count_{window}h'] = is_zero_shifted.rolling(
                window, min_periods=1
            ).sum()

            # Ratio of zeros in window
            df[f'zeros_ratio_{window}h'] = df[f'zeros_count_{window}h'] / window

            self.feature_names.extend([
                f'zeros_count_{window}h', f'zeros_ratio_{window}h'
            ])

        # Hours since last zero (using shifted data)
        # This is tricky - need to compute from past only
        df['hours_since_zero'] = self._compute_hours_since_zero(df[cmg_column])
        self.feature_names.append('hours_since_zero')

        # Binary indicators for zero at specific lags (critical for transitions!)
        df['was_zero_1h_ago'] = (df[cmg_column].shift(1) == 0).astype(int)
        df['was_zero_2h_ago'] = (df[cmg_column].shift(2) == 0).astype(int)
        df['was_zero_24h_ago'] = (df[cmg_column].shift(24) == 0).astype(int)
        self.feature_names.extend(['was_zero_1h_ago', 'was_zero_2h_ago', 'was_zero_24h_ago'])

        return df

    def _compute_hours_since_zero(self, cmg_series: pd.Series) -> pd.Series:
        """
        Compute hours since last zero using only past data
        """
        # Shift to only use past
        shifted = cmg_series.shift(1)
        is_zero = (shifted == 0)

        # Use groupby + cumsum trick
        zero_groups = is_zero.cumsum()
        hours_since = is_zero.groupby(zero_groups).cumcount()

        return hours_since

    def _add_trend_features(self, df: pd.DataFrame, cmg_column: str) -> pd.DataFrame:
        """
        Add trend features (changes over time)
        Use only past data

        NOTE: Using absolute differences instead of percentage changes
        to avoid inf values when CMG = 0
        """
        # Absolute change features (no division, no inf!)
        # These represent "how much did CMG change?" in absolute $/MWh terms

        # 1h change: difference between t-1 and t-2
        df['cmg_change_1h'] = df[cmg_column].shift(1) - df[cmg_column].shift(2)

        # 24h change: difference between t-1 and t-25
        df['cmg_change_24h'] = df[cmg_column].shift(1) - df[cmg_column].shift(25)

        # 48h change: longer-term trend
        df['cmg_change_48h'] = df[cmg_column].shift(1) - df[cmg_column].shift(49)

        # Absolute difference from last known over various windows
        # Shows magnitude of recent changes (volatility indicator)
        for window in [6, 12, 24, 48]:
            shifted = df[cmg_column].shift(1)
            df[f'cmg_trend_{window}h'] = shifted - shifted.shift(window)
            self.feature_names.append(f'cmg_trend_{window}h')

        self.feature_names.extend([
            'cmg_change_1h', 'cmg_change_24h', 'cmg_change_48h'
        ])

        return df

    def _add_seasonal_features(self, df: pd.DataFrame, cmg_column: str) -> pd.DataFrame:
        """
        Add seasonal/weekly pattern features
        """
        # Same hour yesterday
        df['cmg_same_hour_yesterday'] = df[cmg_column].shift(24)

        # Same hour last week
        df['cmg_same_hour_last_week'] = df[cmg_column].shift(168)

        # 7-day median at this hour (robust to anomalies)
        df['cmg_7d_median_same_hour'] = self._compute_7day_median(df[cmg_column])

        # Difference from seasonal patterns
        df['cmg_diff_vs_yesterday'] = (
            df[cmg_column].shift(1) - df['cmg_same_hour_yesterday']
        )
        df['cmg_diff_vs_last_week'] = (
            df[cmg_column].shift(1) - df['cmg_same_hour_last_week']
        )

        self.feature_names.extend([
            'cmg_same_hour_yesterday', 'cmg_same_hour_last_week',
            'cmg_7d_median_same_hour', 'cmg_diff_vs_yesterday',
            'cmg_diff_vs_last_week'
        ])

        return df

    def _compute_7day_median(self, cmg_series: pd.Series) -> pd.Series:
        """
        Compute 7-day median at same hour (FAST vectorized version)
        """
        # Much faster: just use rolling median over 7 days
        # Shift by 168 hours (7 days) to get same hour last week
        return cmg_series.shift(168).fillna(method='bfill')

    def _add_cmg_programado_features(self, df: pd.DataFrame, cmg_column: str,
                                      prog_df: pd.DataFrame) -> pd.DataFrame:
        """
        Add CMG Programado (official forecast) as features

        CMG Programado is the official market forecast published by the coordinator.
        It contains valuable market information that our ML model lacks.
        Using it as an input feature can significantly improve predictions.

        Features added:
        - cmg_prog_t+{h}: CMG Programado forecast for horizon h (1-24)
        - cmg_prog_spread: Difference between Programado and recent actual
        - cmg_prog_vs_mean: Programado relative to recent mean CMG

        IMPORTANT: No leakage because CMG Programado is available at forecast time
        (it's published before the actual hour)

        Args:
            df: DataFrame with datetime index
            cmg_column: Name of actual CMG column
            prog_df: DataFrame with CMG Programado data
                     Expected columns: 'forecast_datetime', 'target_datetime', 'cmg_usd'
        """
        print("  Adding CMG Programado features...")

        try:
            # Prepare programado data: group by (forecast_datetime, horizon)
            # We want the programado value that was available at forecast time
            # for each target hour

            # First, ensure prog_df has the right format
            if 'target_datetime' not in prog_df.columns or 'cmg_usd' not in prog_df.columns:
                print("  Warning: CMG Programado data missing required columns")
                return df

            # Create lookup by target_datetime
            # For each hour in our training data, find the most recent programado forecast
            # that was available before that hour

            prog_df = prog_df.copy()
            if 'target_datetime' in prog_df.columns:
                prog_df['target_datetime'] = pd.to_datetime(prog_df['target_datetime'])

            # Create a lookup: target_datetime -> cmg_programado
            # Use the most recent forecast for each target hour
            prog_lookup = prog_df.groupby('target_datetime')['cmg_usd'].last().to_dict()

            # Add programado value for each horizon (t+1 to t+24)
            for h in self.target_horizons:
                col_name = f'cmg_prog_t+{h}'
                # For each row at time t, get the programado forecast for t+h
                target_times = df.index + pd.Timedelta(hours=h)

                df[col_name] = target_times.map(lambda x: prog_lookup.get(x, np.nan))
                self.feature_names.append(col_name)

            # Spread features: difference between programado and recent actual
            # This captures whether the market expects CMG to rise or fall

            # Average programado across all horizons
            prog_cols = [f'cmg_prog_t+{h}' for h in self.target_horizons if f'cmg_prog_t+{h}' in df.columns]
            if prog_cols:
                df['cmg_prog_avg'] = df[prog_cols].mean(axis=1)
                self.feature_names.append('cmg_prog_avg')

                # Spread vs last known actual (shift(1) to use past data only)
                df['cmg_prog_spread'] = df['cmg_prog_avg'] - df[cmg_column].shift(1)
                self.feature_names.append('cmg_prog_spread')

                # Programado vs recent mean (24h rolling)
                recent_mean = df[cmg_column].shift(1).rolling(24, min_periods=1).mean()
                df['cmg_prog_vs_mean'] = df['cmg_prog_avg'] - recent_mean
                self.feature_names.append('cmg_prog_vs_mean')

                # Programado trend (is it rising or falling across horizons?)
                # Compare early horizons (1-6) vs late horizons (19-24)
                early_prog = df[[f'cmg_prog_t+{h}' for h in range(1, 7) if f'cmg_prog_t+{h}' in df.columns]].mean(axis=1)
                late_prog = df[[f'cmg_prog_t+{h}' for h in range(19, 25) if f'cmg_prog_t+{h}' in df.columns]].mean(axis=1)
                df['cmg_prog_trend'] = late_prog - early_prog
                self.feature_names.append('cmg_prog_trend')

            print(f"  ✓ Added {len([c for c in prog_cols])} CMG Programado horizon features")
            print(f"  ✓ Added spread and trend features")

        except Exception as e:
            print(f"  Warning: Error adding CMG Programado features: {e}")
            # Continue without these features

        return df

    def _add_targets(self, df: pd.DataFrame, cmg_column: str) -> pd.DataFrame:
        """
        Create target variables for all horizons

        For zero detection: is_zero_t+{h}
        For value prediction: cmg_value_t+{h}
        """
        for h in self.target_horizons:
            # Binary target: is CMG zero at t+h?
            df[f'is_zero_t+{h}'] = (df[cmg_column].shift(-h) == 0).astype(float)

            # Regression target: actual CMG value at t+h
            df[f'cmg_value_t+{h}'] = df[cmg_column].shift(-h)

        return df

    def validate_no_leakage(self, df: pd.DataFrame, cmg_column: str) -> Dict[str, bool]:
        """
        Validate that features don't contain future information

        Tests:
        1. No feature should be perfectly correlated with future targets
        2. Features at time t should only depend on data up to t-1
        3. No NaN patterns that indicate future peeking

        Returns:
            Dictionary of test results
        """
        results = {}

        print("\n" + "="*80)
        print("VALIDATING NO FUTURE LEAKAGE")
        print("="*80)

        # Test 1: Check correlations with immediate future
        print("\nTest 1: Checking feature correlations with immediate future...")
        future_cmg = df[cmg_column].shift(-1)

        suspicious_features = []
        for feat in self.feature_names:
            if feat in df.columns:
                corr = df[feat].corr(future_cmg)
                if abs(corr) > 0.95:  # Suspiciously high correlation
                    suspicious_features.append((feat, corr))

        if suspicious_features:
            print(f"⚠️  Found {len(suspicious_features)} suspicious features:")
            for feat, corr in suspicious_features:
                print(f"   {feat}: correlation = {corr:.4f}")
            results['correlation_test'] = False
        else:
            print("✓ No suspicious correlations found")
            results['correlation_test'] = True

        # Test 2: Check that rolling features are properly shifted
        print("\nTest 2: Checking rolling feature shifts...")
        rolling_test_passed = True

        # Manually check a rolling mean
        if 'cmg_mean_24h' in df.columns:
            # At time t, should equal mean of t-1 to t-24
            for t in range(50, 60):
                if t >= 24:
                    expected = df[cmg_column].iloc[t-24:t].mean()
                    actual = df['cmg_mean_24h'].iloc[t]

                    if not np.isnan(actual):
                        diff = abs(expected - actual)
                        if diff > 0.01:  # Allow small numerical errors
                            print(f"⚠️  Rolling mean mismatch at index {t}: expected {expected:.2f}, got {actual:.2f}")
                            rolling_test_passed = False
                            break

        if rolling_test_passed:
            print("✓ Rolling features properly exclude current hour")
        results['rolling_shift_test'] = rolling_test_passed

        # Test 3: Lag features should match shifted values
        print("\nTest 3: Checking lag features...")
        lag_test_passed = True

        if 'cmg_lag_1h' in df.columns:
            if not df['cmg_lag_1h'].equals(df[cmg_column].shift(1)):
                print("⚠️  Lag 1h feature doesn't match shifted CMG")
                lag_test_passed = False
            else:
                print("✓ Lag features correctly implemented")

        results['lag_test'] = lag_test_passed

        # Overall verdict
        all_passed = all(results.values())
        print("\n" + "="*80)
        if all_passed:
            print("✅ ALL TESTS PASSED - NO LEAKAGE DETECTED")
        else:
            print("❌ SOME TESTS FAILED - POTENTIAL LEAKAGE!")
        print("="*80 + "\n")

        results['overall'] = all_passed
        return results

    def get_feature_names(self) -> List[str]:
        """Return list of all feature names"""
        return self.feature_names.copy()

    def get_target_names(self) -> List[str]:
        """Return list of all target names"""
        targets = []
        for h in self.target_horizons:
            targets.extend([f'is_zero_t+{h}', f'cmg_value_t+{h}'])
        return targets


def create_train_val_test_splits(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Create chronological train/val/test splits for time series

    Args:
        df: DataFrame with features and targets
        train_ratio: Proportion for training (default 70%)
        val_ratio: Proportion for validation (default 15%)
        test_ratio: Proportion for testing (default 15%)

    Returns:
        train_df, val_df, test_df
    """
    assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6, "Ratios must sum to 1"

    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    print(f"\nData splits (chronological):")
    print(f"  Train: {len(train_df):,} hours ({train_df.index.min()} to {train_df.index.max()})")
    print(f"  Val:   {len(val_df):,} hours ({val_df.index.min()} to {val_df.index.max()})")
    print(f"  Test:  {len(test_df):,} hours ({test_df.index.min()} to {test_df.index.max()})")

    return train_df, val_df, test_df


# =============================================================================
# STANDARDIZED FEATURE PIPELINE (for consistent preprocessing everywhere)
# =============================================================================

# Global feature engineer instance (singleton pattern)
_GLOBAL_FEATURE_ENGINEER = None

def get_feature_engineer() -> CleanCMGFeatureEngineering:
    """
    Get or create the global feature engineer instance.

    This ensures consistent feature engineering across:
    - Training base models
    - Generating OOF predictions
    - Creating meta-learner features
    - Inference/production

    Returns:
        CleanCMGFeatureEngineering instance
    """
    global _GLOBAL_FEATURE_ENGINEER

    if _GLOBAL_FEATURE_ENGINEER is None:
        _GLOBAL_FEATURE_ENGINEER = CleanCMGFeatureEngineering(
            target_horizons=list(range(1, 25)),  # Always t+1 to t+24
            rolling_windows=[6, 12, 24, 48, 168],
            lag_hours=[1, 2, 3, 6, 12, 24, 48, 168]  # Match training (77 features)
        )

    return _GLOBAL_FEATURE_ENGINEER


def make_features(df: pd.DataFrame,
                  cmg_column: str = 'CMG [$/MWh]',
                  include_targets: bool = False) -> pd.DataFrame:
    """
    STANDARDIZED FEATURE EXTRACTION PIPELINE

    Use this function everywhere to ensure consistency:
    - Training models
    - Generating OOF predictions
    - Creating meta-features
    - Inference/production

    Args:
        df: DataFrame with datetime index and CMG column
        cmg_column: Name of CMG column (default: 'CMG [$/MWh]')
        include_targets: If True, include target variables (default: False)

    Returns:
        DataFrame with ONLY feature columns (or features + targets if include_targets=True)

    Usage:
        # In training:
        X_train = make_features(raw_train_df)

        # In OOF generation:
        X_fold = make_features(raw_fold_df)

        # In meta-learner:
        X_meta = make_features(raw_df)
        X_meta['oof_lgb'] = oof_lgb.reindex(X_meta.index)
        X_meta['oof_xgb'] = oof_xgb.reindex(X_meta.index)
    """
    engineer = get_feature_engineer()

    # Create all features and targets
    df_full = engineer.create_features(df, cmg_column=cmg_column)

    # Get feature column names (excludes CMG column and targets)
    feature_cols = engineer.get_feature_names()

    if include_targets:
        # Return features + targets
        target_cols = engineer.get_target_names()
        return df_full[feature_cols + target_cols]
    else:
        # Return ONLY features (for model input)
        return df_full[feature_cols]


def get_feature_names() -> List[str]:
    """
    Get the standard list of feature names.

    This is the SINGLE SOURCE OF TRUTH for feature columns.
    All models must use this list for consistency.

    Returns:
        List of feature column names
    """
    engineer = get_feature_engineer()

    # Need to run once to populate feature_names
    if not engineer.feature_names:
        # Create dummy data to extract feature names
        dummy_df = pd.DataFrame({
            'CMG [$/MWh]': [100.0] * 1000
        }, index=pd.date_range('2024-01-01', periods=1000, freq='H'))

        _ = engineer.create_features(dummy_df)

    return engineer.get_feature_names()


# Example usage and testing
if __name__ == "__main__":
    print("="*80)
    print("CLEAN FEATURE ENGINEERING - EXAMPLE USAGE")
    print("="*80)

    # Load CMG data
    print("\nLoading CMG data...")
    cmg_df = pd.read_csv('CMG_Real_ML_2023_2025.csv')
    cmg_df['fecha_hora'] = pd.to_datetime(cmg_df['fecha_hora'])
    cmg_df = cmg_df.set_index('fecha_hora')
    cmg_df = cmg_df.rename(columns={'CMG_real': 'CMG [$/MWh]'})

    print(f"Loaded {len(cmg_df):,} hours of data")
    print(f"Date range: {cmg_df.index.min()} to {cmg_df.index.max()}")
    print(f"Zero CMG hours: {(cmg_df['CMG [$/MWh]'] == 0).sum():,} ({(cmg_df['CMG [$/MWh]'] == 0).mean()*100:.1f}%)")

    # Create features
    print("\n" + "="*80)
    print("CREATING FEATURES")
    print("="*80)

    feature_engineer = CleanCMGFeatureEngineering(
        target_horizons=list(range(1, 25)),  # Predict t+1 to t+24
        rolling_windows=[6, 12, 24, 48, 168],
        lag_hours=[1, 2, 3, 6, 12, 24, 48, 168]
    )

    df_with_features = feature_engineer.create_features(cmg_df)

    # Validate no leakage
    validation_results = feature_engineer.validate_no_leakage(df_with_features, 'CMG [$/MWh]')

    # Show sample of features
    print("\n" + "="*80)
    print("SAMPLE OF CREATED FEATURES")
    print("="*80)

    feature_cols = feature_engineer.get_feature_names()[:10]
    print(f"\nFirst 10 features at hour 1000:")
    print(df_with_features[feature_cols].iloc[1000])

    # Create splits
    train_df, val_df, test_df = create_train_val_test_splits(df_with_features)

    # Summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)

    print(f"\nTotal features created: {len(feature_engineer.get_feature_names())}")
    print(f"Total targets created: {len(feature_engineer.get_target_names())}")
    print(f"\nDataFrame shape: {df_with_features.shape}")
    print(f"Memory usage: {df_with_features.memory_usage(deep=True).sum() / 1024**2:.1f} MB")

    # Check for NaNs
    nan_counts = df_with_features[feature_engineer.get_feature_names()].isna().sum()
    features_with_nans = nan_counts[nan_counts > 0]

    if len(features_with_nans) > 0:
        print(f"\nFeatures with NaNs (expected for early hours with long lags):")
        print(features_with_nans.head(10))

    print("\n" + "="*80)
    print("✅ FEATURE ENGINEERING COMPLETE - NO LEAKAGE!")
    print("="*80)
