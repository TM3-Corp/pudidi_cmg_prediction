#!/usr/bin/env python3
"""
Horizon Performance Diagnostic Script
======================================

Investigates the t+12 performance issue in the CMG prediction system.

Runs diagnostic queries to verify:
1. Sample counts per horizon (data integrity)
2. Horizon calculation correctness
3. Performance by target hour
4. Head-to-head ML vs CMG Programado comparison

Usage:
    export SUPABASE_URL="https://your-project.supabase.co"
    export SUPABASE_SERVICE_KEY="your_service_key"

    python3 scripts/diagnose_horizon_performance.py
    python3 scripts/diagnose_horizon_performance.py --start 2025-12-01 --end 2025-12-25
"""

import os
import sys
import requests
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def get_supabase_config():
    """Get Supabase configuration from environment"""
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY')

    if not url or not key:
        print(f"{Colors.RED}ERROR:{Colors.END} Missing environment variables")
        print("  Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        sys.exit(1)

    return {
        'base_url': f"{url}/rest/v1",
        'headers': {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
    }


def query_supabase(config: dict, table: str, params: list) -> List[Dict]:
    """Execute query against Supabase REST API"""
    url = f"{config['base_url']}/{table}"
    response = requests.get(url, params=params, headers=config['headers'])

    if response.status_code == 200:
        return response.json()
    else:
        print(f"{Colors.RED}Query failed:{Colors.END} {response.status_code}")
        print(f"  {response.text[:200]}")
        return []


def check_sample_counts_per_horizon(config: dict, start_date: str, end_date: str):
    """
    Check 1: Sample count per horizon
    Expected: All horizons should have similar sample counts
    """
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}1. SAMPLE COUNT PER HORIZON{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print("Checking if all horizons have equal data representation...")

    # Query ML predictions grouped by horizon
    # Using PostgREST, we need to fetch all data and aggregate in Python
    params = [
        ("forecast_date", f"gte.{start_date}"),
        ("forecast_date", f"lte.{end_date}"),
        ("select", "horizon,cmg_predicted"),
        ("limit", "50000")
    ]

    data = query_supabase(config, "ml_predictions_santiago", params)

    if not data:
        print(f"{Colors.RED}No data found{Colors.END}")
        return {}

    # Aggregate by horizon
    horizon_counts = defaultdict(lambda: {'count': 0, 'sum': 0.0})
    for row in data:
        h = row['horizon']
        horizon_counts[h]['count'] += 1
        horizon_counts[h]['sum'] += row['cmg_predicted'] or 0

    # Display results
    print(f"\n{'Horizon':<10} {'Count':<10} {'Avg Prediction':<15} {'Status'}")
    print("-" * 50)

    # Calculate stats
    counts = [v['count'] for v in horizon_counts.values()]
    avg_count = sum(counts) / len(counts) if counts else 0
    min_count = min(counts) if counts else 0
    max_count = max(counts) if counts else 0

    results = {}
    for h in sorted(horizon_counts.keys()):
        count = horizon_counts[h]['count']
        avg_pred = horizon_counts[h]['sum'] / count if count > 0 else 0

        # Check if count deviates more than 10% from average
        deviation = abs(count - avg_count) / avg_count * 100 if avg_count > 0 else 0

        if deviation > 10:
            status = f"{Colors.RED}⚠ {deviation:.1f}% deviation{Colors.END}"
        else:
            status = f"{Colors.GREEN}✓{Colors.END}"

        print(f"t+{h:<8} {count:<10} ${avg_pred:<14.2f} {status}")
        results[h] = {'count': count, 'avg_prediction': avg_pred}

    print("-" * 50)
    print(f"Total records: {sum(counts)}")
    print(f"Average per horizon: {avg_count:.0f}")
    print(f"Min/Max: {min_count}/{max_count}")

    # Verdict
    if max_count - min_count > avg_count * 0.1:
        print(f"\n{Colors.YELLOW}⚠ POTENTIAL ISSUE:{Colors.END} Sample counts vary by more than 10%")
    else:
        print(f"\n{Colors.GREEN}✓ Sample counts are balanced across horizons{Colors.END}")

    return results


def verify_horizon_calculation(config: dict, start_date: str, end_date: str):
    """
    Check 2: Verify stored horizon matches calculated horizon
    """
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}2. HORIZON CALCULATION VERIFICATION{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print("Verifying stored horizon field matches datetime difference...")

    # Sample predictions to verify
    params = [
        ("forecast_date", f"gte.{start_date}"),
        ("forecast_date", f"lte.{end_date}"),
        ("select", "id,horizon,forecast_datetime,target_datetime"),
        ("limit", "1000"),
        ("order", "forecast_datetime.desc")
    ]

    data = query_supabase(config, "ml_predictions_santiago", params)

    if not data:
        print(f"{Colors.RED}No data found{Colors.END}")
        return

    mismatches = []
    for row in data:
        stored_horizon = row['horizon']

        # Parse datetimes
        forecast_dt = datetime.fromisoformat(row['forecast_datetime'].replace('Z', '+00:00'))
        target_dt = datetime.fromisoformat(row['target_datetime'].replace('Z', '+00:00'))

        # Calculate horizon
        calculated_horizon = int((target_dt - forecast_dt).total_seconds() / 3600)

        if stored_horizon != calculated_horizon:
            mismatches.append({
                'id': row['id'],
                'stored': stored_horizon,
                'calculated': calculated_horizon,
                'forecast': row['forecast_datetime'],
                'target': row['target_datetime']
            })

    if mismatches:
        print(f"\n{Colors.RED}❌ FOUND {len(mismatches)} MISMATCHES!{Colors.END}")
        print("\nSample mismatches:")
        for m in mismatches[:5]:
            print(f"  ID {m['id']}: stored={m['stored']}, calculated={m['calculated']}")
            print(f"    forecast: {m['forecast']}")
            print(f"    target:   {m['target']}")
    else:
        print(f"\n{Colors.GREEN}✓ All {len(data)} sampled records have correct horizon values{Colors.END}")


def check_cmg_online_completeness(config: dict, start_date: str, end_date: str):
    """
    Check 3: CMG Online (actuals) completeness
    """
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}3. CMG ONLINE (ACTUALS) COMPLETENESS{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print("Checking for missing actual values that could affect comparisons...")

    params = [
        ("date", f"gte.{start_date}"),
        ("date", f"lte.{end_date}"),
        ("select", "date,hour"),
        ("limit", "5000")
    ]

    data = query_supabase(config, "cmg_online_santiago", params)

    if not data:
        print(f"{Colors.RED}No data found{Colors.END}")
        return

    # Group by date
    by_date = defaultdict(set)
    for row in data:
        by_date[row['date']].add(row['hour'])

    # Check each date
    incomplete_dates = []
    for date in sorted(by_date.keys()):
        hours = by_date[date]
        if len(hours) < 24:
            missing = set(range(24)) - hours
            incomplete_dates.append({'date': date, 'available': len(hours), 'missing': sorted(missing)})

    if incomplete_dates:
        print(f"\n{Colors.YELLOW}⚠ Found {len(incomplete_dates)} days with incomplete data:{Colors.END}")
        for d in incomplete_dates[-10:]:  # Show last 10
            print(f"  {d['date']}: {d['available']}/24 hours (missing: {d['missing'][:5]}...)")
    else:
        print(f"\n{Colors.GREEN}✓ All {len(by_date)} days have complete 24-hour coverage{Colors.END}")


def analyze_performance_by_horizon(config: dict, start_date: str, end_date: str):
    """
    Check 4: Performance analysis by horizon
    Compare ML predictions vs CMG Programado for each horizon
    """
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}4. PERFORMANCE BY HORIZON (ML vs CMG Programado){Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print("Analyzing average error for each horizon...")

    # Get ML predictions with target info
    ml_params = [
        ("forecast_date", f"gte.{start_date}"),
        ("forecast_date", f"lte.{end_date}"),
        ("select", "horizon,target_datetime,cmg_predicted"),
        ("limit", "50000")
    ]
    ml_data = query_supabase(config, "ml_predictions_santiago", ml_params)

    # Get CMG Online (actuals)
    online_params = [
        ("date", f"gte.{start_date}"),
        ("date", f"lte.{end_date}"),
        ("select", "date,hour,cmg_usd"),
        ("limit", "5000")
    ]
    online_data = query_supabase(config, "cmg_online_santiago", online_params)

    if not ml_data or not online_data:
        print(f"{Colors.RED}Insufficient data for analysis{Colors.END}")
        return

    # Build actuals lookup: (date, hour) -> avg CMG
    actuals = defaultdict(list)
    for row in online_data:
        key = (row['date'], row['hour'])
        actuals[key].append(row['cmg_usd'])

    actuals_avg = {k: sum(v)/len(v) for k, v in actuals.items()}

    # Calculate errors by horizon
    import pytz
    santiago = pytz.timezone('America/Santiago')

    ml_errors = defaultdict(list)
    for row in ml_data:
        horizon = row['horizon']
        target_dt = datetime.fromisoformat(row['target_datetime'].replace('Z', '+00:00'))
        target_dt_stgo = target_dt.astimezone(santiago)

        target_date = target_dt_stgo.strftime('%Y-%m-%d')
        target_hour = target_dt_stgo.hour

        key = (target_date, target_hour)
        if key in actuals_avg:
            actual = actuals_avg[key]
            predicted = row['cmg_predicted']
            error = abs(predicted - actual)
            ml_errors[horizon].append(error)

    # Display results
    print(f"\n{'Horizon':<10} {'Avg Error':<12} {'Count':<10} {'Trend'}")
    print("-" * 45)

    prev_error = None
    for h in sorted(ml_errors.keys()):
        errors = ml_errors[h]
        avg_error = sum(errors) / len(errors)
        count = len(errors)

        if prev_error is not None:
            diff = avg_error - prev_error
            if diff > 1:
                trend = f"{Colors.RED}↑ +${diff:.2f}{Colors.END}"
            elif diff < -1:
                trend = f"{Colors.GREEN}↓ ${diff:.2f}{Colors.END}"
            else:
                trend = "→"
        else:
            trend = "-"

        # Highlight t+12
        if h == 12:
            print(f"{Colors.YELLOW}t+{h:<8} ${avg_error:<11.2f} {count:<10} {trend} ← INVESTIGATE{Colors.END}")
        else:
            print(f"t+{h:<8} ${avg_error:<11.2f} {count:<10} {trend}")

        prev_error = avg_error

    # Calculate degradation
    if 1 in ml_errors and 24 in ml_errors:
        t1_avg = sum(ml_errors[1]) / len(ml_errors[1])
        t24_avg = sum(ml_errors[24]) / len(ml_errors[24])
        degradation = (t24_avg - t1_avg) / 23
        print("-" * 45)
        print(f"Degradation rate: ${degradation:.2f}/hour")


def analyze_t12_by_target_hour(config: dict, start_date: str, end_date: str):
    """
    Check 5: Analyze t+12 performance by target hour
    To determine if specific hours (e.g., noon) are harder to predict
    """
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}5. t+12 PERFORMANCE BY TARGET HOUR{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print("Checking if certain target hours are harder to predict at t+12...")

    # Get t+12 predictions only
    ml_params = [
        ("forecast_date", f"gte.{start_date}"),
        ("forecast_date", f"lte.{end_date}"),
        ("horizon", "eq.12"),
        ("select", "target_datetime,cmg_predicted"),
        ("limit", "10000")
    ]
    ml_data = query_supabase(config, "ml_predictions_santiago", ml_params)

    # Get actuals
    online_params = [
        ("date", f"gte.{start_date}"),
        ("date", f"lte.{end_date}"),
        ("select", "date,hour,cmg_usd"),
        ("limit", "5000")
    ]
    online_data = query_supabase(config, "cmg_online_santiago", online_params)

    if not ml_data or not online_data:
        print(f"{Colors.RED}Insufficient data{Colors.END}")
        return

    # Build actuals lookup
    actuals = defaultdict(list)
    for row in online_data:
        key = (row['date'], row['hour'])
        actuals[key].append(row['cmg_usd'])
    actuals_avg = {k: sum(v)/len(v) for k, v in actuals.items()}

    # Analyze by target hour
    import pytz
    santiago = pytz.timezone('America/Santiago')

    errors_by_hour = defaultdict(list)
    for row in ml_data:
        target_dt = datetime.fromisoformat(row['target_datetime'].replace('Z', '+00:00'))
        target_dt_stgo = target_dt.astimezone(santiago)
        target_date = target_dt_stgo.strftime('%Y-%m-%d')
        target_hour = target_dt_stgo.hour

        key = (target_date, target_hour)
        if key in actuals_avg:
            actual = actuals_avg[key]
            predicted = row['cmg_predicted']
            error = abs(predicted - actual)
            errors_by_hour[target_hour].append(error)

    # Display
    print(f"\n{'Target Hour':<15} {'Avg Error':<12} {'Count':<10}")
    print("-" * 40)

    # Sort by average error to highlight problematic hours
    hour_stats = []
    for hour in sorted(errors_by_hour.keys()):
        errors = errors_by_hour[hour]
        avg = sum(errors) / len(errors)
        hour_stats.append((hour, avg, len(errors)))

    # Sort by error descending
    hour_stats_sorted = sorted(hour_stats, key=lambda x: -x[1])

    for hour, avg, count in hour_stats_sorted:
        if avg > sum(e[1] for e in hour_stats) / len(hour_stats) * 1.2:
            print(f"{Colors.RED}{hour:02d}:00{' '*9} ${avg:<11.2f} {count:<10} ← HIGH ERROR{Colors.END}")
        else:
            print(f"{hour:02d}:00{' '*9} ${avg:<11.2f} {count:<10}")


def main():
    parser = argparse.ArgumentParser(
        description='Diagnose horizon performance issues in CMG predictions'
    )
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)',
                        default=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
    parser.add_argument('--end', help='End date (YYYY-MM-DD)',
                        default=datetime.now().strftime('%Y-%m-%d'))

    args = parser.parse_args()

    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}CMG PREDICTION - HORIZON PERFORMANCE DIAGNOSTICS{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"Date Range: {args.start} to {args.end}")

    config = get_supabase_config()

    # Run all diagnostics
    check_sample_counts_per_horizon(config, args.start, args.end)
    verify_horizon_calculation(config, args.start, args.end)
    check_cmg_online_completeness(config, args.start, args.end)
    analyze_performance_by_horizon(config, args.start, args.end)
    analyze_t12_by_target_hour(config, args.start, args.end)

    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.GREEN}Diagnostics complete!{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")


if __name__ == "__main__":
    main()
