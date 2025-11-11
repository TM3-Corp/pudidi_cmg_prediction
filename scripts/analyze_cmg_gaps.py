#!/usr/bin/env python3
"""
CMG Online Data Gap Analysis
=============================

Analyzes CMG Online historical data for:
1. Missing hours (gaps) in the time series
2. Data completeness by day
3. Recent data staleness

Helps identify if the fetching strategy has successfully maintained complete historical data.
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Constants
DATA_DIR = Path(__file__).parent.parent / "data"
CMG_CACHE_FILE = DATA_DIR / "cache" / "cmg_historical_latest.json"


def load_cmg_data():
    """Load CMG Online data from cache"""
    print("Loading CMG Online data...")

    with open(CMG_CACHE_FILE, 'r') as f:
        data = json.load(f)

    records = []

    # Handle 'data' structure
    if 'data' in data and data['data']:
        for record in data['data']:
            records.append({
                'datetime': pd.to_datetime(record['datetime']),
                'cmg_usd': record['cmg_usd'],
                'node': record.get('node', 'unknown')
            })

    df = pd.DataFrame(records)

    if len(df) == 0:
        raise ValueError("No records found in cache file")

    print(f"✓ Loaded {len(df)} records")
    print(f"  Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    print(f"  Nodes: {df['node'].unique().tolist()}")
    print()

    return df


def analyze_gaps(df):
    """Analyze gaps in the time series"""
    print("="*80)
    print("GAP ANALYSIS")
    print("="*80)

    # Group by node
    nodes = df['node'].unique()

    all_gaps = []

    for node in nodes:
        node_df = df[df['node'] == node].copy()
        node_df = node_df.sort_values('datetime')

        print(f"\nNode: {node}")
        print("-" * 40)

        # Get min and max datetime
        min_dt = node_df['datetime'].min()
        max_dt = node_df['datetime'].max()

        # Create expected hourly range
        expected_hours = pd.date_range(start=min_dt, end=max_dt, freq='H')
        actual_hours = set(node_df['datetime'])

        # Find missing hours
        missing_hours = sorted([dt for dt in expected_hours if dt not in actual_hours])

        total_expected = len(expected_hours)
        total_actual = len(actual_hours)
        total_missing = len(missing_hours)
        completeness_pct = (total_actual / total_expected * 100) if total_expected > 0 else 0

        print(f"  Expected hours: {total_expected}")
        print(f"  Actual hours: {total_actual}")
        print(f"  Missing hours: {total_missing}")
        print(f"  Completeness: {completeness_pct:.2f}%")

        if missing_hours:
            # Group consecutive missing hours
            gaps = []
            gap_start = missing_hours[0]
            gap_end = missing_hours[0]

            for i in range(1, len(missing_hours)):
                if missing_hours[i] == gap_end + timedelta(hours=1):
                    gap_end = missing_hours[i]
                else:
                    gaps.append((gap_start, gap_end))
                    gap_start = missing_hours[i]
                    gap_end = missing_hours[i]

            gaps.append((gap_start, gap_end))

            print(f"\n  Found {len(gaps)} gap(s):")
            for gap_start, gap_end in gaps:
                gap_hours = int((gap_end - gap_start).total_seconds() / 3600) + 1
                all_gaps.append({
                    'node': node,
                    'start': gap_start,
                    'end': gap_end,
                    'hours': gap_hours
                })

                if gap_hours == 1:
                    print(f"    • {gap_start.strftime('%Y-%m-%d %H:00')} (1 hour)")
                else:
                    print(f"    • {gap_start.strftime('%Y-%m-%d %H:00')} to {gap_end.strftime('%Y-%m-%d %H:00')} ({gap_hours} hours)")
        else:
            print(f"\n  ✅ No gaps - complete time series!")

    return all_gaps


def analyze_recent_data(df):
    """Analyze recent data completeness"""
    print("\n" + "="*80)
    print("RECENT DATA ANALYSIS (Last 48 Hours)")
    print("="*80)

    now = datetime.now()
    cutoff_48h = now - timedelta(hours=48)
    cutoff_24h = now - timedelta(hours=24)

    # Get most recent timestamp in data
    latest_dt = df['datetime'].max()
    staleness_hours = (now - latest_dt).total_seconds() / 3600

    print(f"\nCurrent time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Latest data: {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Data staleness: {staleness_hours:.1f} hours")

    if staleness_hours < 2:
        print("  ✅ Data is fresh (< 2 hours old)")
    elif staleness_hours < 6:
        print("  ⚠️  Data is slightly stale (2-6 hours old)")
    else:
        print("  ❌ Data is very stale (> 6 hours old)")

    # Analyze last 48 hours by node
    for node in df['node'].unique():
        node_df = df[df['node'] == node].copy()

        recent_48h = node_df[node_df['datetime'] >= cutoff_48h]
        recent_24h = node_df[node_df['datetime'] >= cutoff_24h]

        print(f"\n{node}:")
        print(f"  Last 48h: {len(recent_48h)}/48 hours ({len(recent_48h)/48*100:.1f}%)")
        print(f"  Last 24h: {len(recent_24h)}/24 hours ({len(recent_24h)/24*100:.1f}%)")

        # Check for recent gaps
        if len(recent_24h) < 24:
            expected_recent = pd.date_range(start=cutoff_24h, end=now, freq='H')
            actual_recent = set(node_df['datetime'])
            missing_recent = sorted([dt for dt in expected_recent if dt not in actual_recent])

            if missing_recent:
                print(f"  ⚠️  Missing {len(missing_recent)} hour(s) in last 24h:")
                for missing_dt in missing_recent[-5:]:  # Show last 5
                    print(f"      - {missing_dt.strftime('%Y-%m-%d %H:00')}")
                if len(missing_recent) > 5:
                    print(f"      ... and {len(missing_recent) - 5} more")


def analyze_daily_completeness(df):
    """Analyze completeness by day"""
    print("\n" + "="*80)
    print("DAILY COMPLETENESS ANALYSIS")
    print("="*80)

    # Add date column
    df['date'] = df['datetime'].dt.date

    for node in df['node'].unique():
        node_df = df[df['node'] == node].copy()

        print(f"\n{node}:")
        print("-" * 40)

        # Count hours per day
        daily_counts = node_df.groupby('date').size()

        incomplete_days = daily_counts[daily_counts < 24]

        if len(incomplete_days) == 0:
            print("  ✅ All days complete (24/24 hours)")
        else:
            print(f"  Found {len(incomplete_days)} incomplete day(s):")
            for date, count in incomplete_days.items():
                print(f"    • {date}: {count}/24 hours ({count/24*100:.1f}%)")

        # Show last 7 days
        last_7_days = sorted(daily_counts.tail(7).items(), reverse=True)
        print(f"\n  Last 7 days:")
        for date, count in last_7_days:
            status = "✅" if count == 24 else "⚠️"
            print(f"    {status} {date}: {count}/24 hours")


def main():
    """Main analysis"""
    print("="*80)
    print("CMG ONLINE DATA GAP ANALYSIS")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        # Load data
        df = load_cmg_data()

        # Analyze gaps
        gaps = analyze_gaps(df)

        # Analyze recent data
        analyze_recent_data(df)

        # Analyze daily completeness
        analyze_daily_completeness(df)

        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)

        if len(gaps) == 0:
            print("✅ NO GAPS FOUND - Data is complete!")
        else:
            total_gap_hours = sum(gap['hours'] for gap in gaps)
            print(f"⚠️  Found {len(gaps)} gap(s) totaling {total_gap_hours} hours")
            print(f"\nLargest gaps:")
            sorted_gaps = sorted(gaps, key=lambda x: x['hours'], reverse=True)[:5]
            for gap in sorted_gaps:
                print(f"  • {gap['node']}: {gap['start'].strftime('%Y-%m-%d %H:00')} to {gap['end'].strftime('%Y-%m-%d %H:00')} ({gap['hours']} hours)")

        print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
