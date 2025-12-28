#!/usr/bin/env python3
"""
Verify Rendimiento Logic - Exact Replication
=============================================

This script replicates EXACTLY the logic from api/performance_range.py
to verify that we understand the calculations correctly.

Key insight from user:
- Temporal Dimension (📅 Distancia por Día): Group by target_datetime
  "How did predictions FOR those days perform?"

- Structural Dimension (📈 Curva por Horizonte): Group by horizon
  "How did predictions at each horizon perform?"

Both dimensions use the SAME dataset, just grouped differently.
The API queries forecasts from (start_date - 1) to end_date to capture
t+24 predictions that target start_date.

Usage:
    export SUPABASE_URL="..." SUPABASE_SERVICE_KEY="..."
    python3 scripts/verify_rendimiento_logic.py --start 2025-12-21 --end 2025-12-27
"""

import os
import sys
import requests
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import pytz

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def main():
    parser = argparse.ArgumentParser(description='Verify Rendimiento logic')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    # Validate environment
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not supabase_url or not supabase_key:
        print(f"{Colors.RED}ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY{Colors.END}")
        sys.exit(1)

    base_url = f"{supabase_url}/rest/v1"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json"
    }

    santiago_tz = pytz.timezone('America/Santiago')

    start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    end_date = datetime.strptime(args.end, '%Y-%m-%d').date()
    num_days = (end_date - start_date).days + 1

    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}VERIFY RENDIMIENTO LOGIC - Exact API Replication{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"Date Range: {start_date} to {end_date} ({num_days} days)")

    # =========================================
    # STEP 1: Query forecasts (day by day to avoid 1000 limit)
    # =========================================
    # Key: Query from (start_date - 1) to capture t+24 predictions targeting start_date
    forecast_query_start = start_date - timedelta(days=1)

    print(f"\n{Colors.BOLD}Step 1: Loading ML Forecasts{Colors.END}")
    print(f"  Querying forecast_date from {forecast_query_start} to {end_date}")

    ml_forecasts = []
    current = forecast_query_start
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        params = [
            ("forecast_date", f"eq.{date_str}"),
            ("order", "forecast_hour.asc,horizon.asc"),
            ("limit", "1000")  # 576 max per day (24 hours × 24 horizons)
        ]
        resp = requests.get(f"{base_url}/ml_predictions_santiago", params=params, headers=headers)
        if resp.status_code == 200:
            day_data = resp.json()
            ml_forecasts.extend(day_data)
            print(f"    {date_str}: {len(day_data)} forecasts")
        current += timedelta(days=1)

    print(f"  Total ML forecasts: {len(ml_forecasts)}")

    print(f"\n{Colors.BOLD}Step 2: Loading CMG Programado{Colors.END}")
    prog_forecasts = []
    current = forecast_query_start
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        params = [
            ("forecast_date", f"eq.{date_str}"),
            ("order", "forecast_hour.asc,target_datetime.asc"),
            ("limit", "5000")  # 1,728 max per day
        ]
        resp = requests.get(f"{base_url}/cmg_programado_santiago", params=params, headers=headers)
        if resp.status_code == 200:
            day_data = resp.json()
            prog_forecasts.extend(day_data)
            print(f"    {date_str}: {len(day_data)} forecasts")
        current += timedelta(days=1)

    print(f"  Total CMG Programado forecasts (raw): {len(prog_forecasts)}")

    # Filter CMG Programado: only future forecasts and first 24 hours
    prog_filtered = []
    for p in prog_forecasts:
        forecast_dt = datetime.fromisoformat(p['forecast_datetime'].replace('Z', '+00:00'))
        target_dt = datetime.fromisoformat(p['target_datetime'].replace('Z', '+00:00'))

        if target_dt <= forecast_dt:  # Skip backwards
            continue

        horizon_hours = int((target_dt - forecast_dt).total_seconds() / 3600)
        if horizon_hours <= 24:  # Only first 24 hours
            p['horizon'] = horizon_hours
            p['target_date'] = target_dt.astimezone(santiago_tz).strftime('%Y-%m-%d')
            p['target_hour'] = target_dt.astimezone(santiago_tz).hour
            prog_filtered.append(p)

    print(f"  Filtered CMG Programado (t+1 to t+24): {len(prog_filtered)}")

    # Add target_date and target_hour to ML forecasts
    for ml in ml_forecasts:
        forecast_date = ml['forecast_date']
        forecast_hour = ml['forecast_hour']
        horizon = ml['horizon']

        forecast_dt = santiago_tz.localize(
            datetime.strptime(f"{forecast_date} {forecast_hour:02d}:00", "%Y-%m-%d %H:%M")
        )
        target_dt = forecast_dt + timedelta(hours=horizon)

        ml['target_date'] = target_dt.strftime('%Y-%m-%d')
        ml['target_hour'] = target_dt.hour

    # =========================================
    # STEP 3: Load CMG Online (actuals) - DAY BY DAY to avoid 1000-row limit
    # =========================================
    print(f"\n{Colors.BOLD}Step 3: Loading CMG Online (actuals){Colors.END}")
    print(f"  Querying date from {start_date} to {end_date} (day by day)")

    cmg_online = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        online_params = [
            ("date", f"eq.{date_str}"),
            ("order", "hour.asc"),
            ("limit", "1000")  # Max per day: 24 hours × 3 nodes = 72
        ]
        resp = requests.get(f"{base_url}/cmg_online_santiago", params=online_params, headers=headers)
        if resp.status_code == 200:
            day_data = resp.json()
            cmg_online.extend(day_data)
        current += timedelta(days=1)

    print(f"  Total CMG Online records: {len(cmg_online)}")

    # Build actuals lookup: (date, hour) → average CMG across nodes
    actuals_raw = defaultdict(list)
    for record in cmg_online:
        key = (record['date'], record['hour'])
        actuals_raw[key].append(record['cmg_usd'])

    actuals = {key: sum(values) / len(values) for key, values in actuals_raw.items()}
    print(f"  Unique (date, hour) combinations: {len(actuals)}")

    # Check actuals completeness per day
    actuals_per_day = defaultdict(set)
    for (d, h) in actuals.keys():
        actuals_per_day[d].add(h)

    print(f"\n  Actuals completeness per day:")
    for d in sorted(actuals_per_day.keys()):
        hours = actuals_per_day[d]
        if len(hours) == 24:
            status = f"{Colors.GREEN}✓{Colors.END}"
        else:
            status = f"{Colors.YELLOW}⚠ {len(hours)}/24{Colors.END}"
        print(f"    {d}: {status}")

    # =========================================
    # TEMPORAL DIMENSION: Metrics by Day
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}TEMPORAL DIMENSION: Average Error by Target Day{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")

    ml_daily_errors = defaultdict(list)
    prog_daily_errors = defaultdict(list)

    # ML predictions by day (using target_date)
    for forecast in ml_forecasts:
        target_date = forecast['target_date']
        target_hour = forecast['target_hour']
        predicted = forecast['cmg_predicted']

        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(predicted - actual)
            ml_daily_errors[target_date].append(error)

    # CMG Programado by day
    for forecast in prog_filtered:
        target_date = forecast['target_date']
        target_hour = forecast['target_hour']
        predicted = forecast['cmg_usd']

        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(predicted - actual)
            prog_daily_errors[target_date].append(error)

    # Calculate and display daily metrics (only for dates in range)
    print(f"\n{'Date':<12} {'ML Avg':<12} {'ML Count':<10} {'Prog Avg':<12} {'Prog Count':<10} {'Winner'}")
    print("-" * 70)

    metrics_by_day = []
    current = start_date
    ml_wins_days = 0
    prog_wins_days = 0

    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')

        ml_errors = ml_daily_errors.get(date_str, [])
        prog_errors = prog_daily_errors.get(date_str, [])

        ml_avg = sum(ml_errors) / len(ml_errors) if ml_errors else None
        prog_avg = sum(prog_errors) / len(prog_errors) if prog_errors else None

        if ml_avg is not None and prog_avg is not None:
            if ml_avg < prog_avg:
                winner = f"{Colors.GREEN}ML WINS{Colors.END}"
                ml_wins_days += 1
            else:
                winner = f"{Colors.BLUE}PROG WINS{Colors.END}"
                prog_wins_days += 1
        else:
            winner = "N/A"

        ml_str = f"${ml_avg:.2f}" if ml_avg else "N/A"
        prog_str = f"${prog_avg:.2f}" if prog_avg else "N/A"

        print(f"{date_str:<12} {ml_str:<12} {len(ml_errors):<10} {prog_str:<12} {len(prog_errors):<10} {winner}")

        metrics_by_day.append({
            'date': date_str,
            'ml_avg': ml_avg,
            'ml_count': len(ml_errors),
            'prog_avg': prog_avg,
            'prog_count': len(prog_errors)
        })

        current += timedelta(days=1)

    print("-" * 70)
    print(f"ML wins: {ml_wins_days} days, Prog wins: {prog_wins_days} days")

    # Calculate overall averages (average of daily averages)
    ml_days_with_data = [d for d in metrics_by_day if d['ml_avg'] is not None]
    prog_days_with_data = [d for d in metrics_by_day if d['prog_avg'] is not None]

    ml_overall_avg = sum(d['ml_avg'] for d in ml_days_with_data) / len(ml_days_with_data) if ml_days_with_data else None
    prog_overall_avg = sum(d['prog_avg'] for d in prog_days_with_data) / len(prog_days_with_data) if prog_days_with_data else None

    print(f"\n{Colors.BOLD}Temporal Summary:{Colors.END}")
    print(f"  ML Overall Average: ${ml_overall_avg:.2f}" if ml_overall_avg else "  ML Overall Average: N/A")
    print(f"  Prog Overall Average: ${prog_overall_avg:.2f}" if prog_overall_avg else "  Prog Overall Average: N/A")

    if ml_days_with_data:
        best_ml = min(ml_days_with_data, key=lambda x: x['ml_avg'])
        worst_ml = max(ml_days_with_data, key=lambda x: x['ml_avg'])
        print(f"  Best ML Day: {best_ml['date']}: ${best_ml['ml_avg']:.2f}")
        print(f"  Worst ML Day: {worst_ml['date']}: ${worst_ml['ml_avg']:.2f}")

    if prog_days_with_data:
        best_prog = min(prog_days_with_data, key=lambda x: x['prog_avg'])
        worst_prog = max(prog_days_with_data, key=lambda x: x['prog_avg'])
        print(f"  Best Prog Day: {best_prog['date']}: ${best_prog['prog_avg']:.2f}")
        print(f"  Worst Prog Day: {worst_prog['date']}: ${worst_prog['prog_avg']:.2f}")

    # =========================================
    # STRUCTURAL DIMENSION: Metrics by Horizon
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}STRUCTURAL DIMENSION: Average Error by Horizon{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")

    ml_horizon_errors = defaultdict(list)
    prog_horizon_errors = defaultdict(list)

    # ML predictions by horizon
    for forecast in ml_forecasts:
        horizon = forecast['horizon']
        target_date = forecast['target_date']
        target_hour = forecast['target_hour']
        predicted = forecast['cmg_predicted']

        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(predicted - actual)
            ml_horizon_errors[horizon].append(error)

    # CMG Programado by horizon
    for forecast in prog_filtered:
        horizon = forecast['horizon']
        target_date = forecast['target_date']
        target_hour = forecast['target_hour']
        predicted = forecast['cmg_usd']

        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(predicted - actual)
            prog_horizon_errors[horizon].append(error)

    print(f"\n{'Horizon':<10} {'ML Avg':<12} {'ML Count':<10} {'Prog Avg':<12} {'Prog Count':<10} {'Winner'}")
    print("-" * 70)

    ml_by_horizon = []
    prog_by_horizon = []
    ml_wins_horizon = 0
    prog_wins_horizon = 0

    for horizon in range(1, 25):
        ml_errors = ml_horizon_errors.get(horizon, [])
        prog_errors = prog_horizon_errors.get(horizon, [])

        ml_avg = sum(ml_errors) / len(ml_errors) if ml_errors else None
        prog_avg = sum(prog_errors) / len(prog_errors) if prog_errors else None

        if ml_avg is not None and prog_avg is not None:
            if ml_avg < prog_avg:
                winner = f"{Colors.GREEN}ML{Colors.END}"
                ml_wins_horizon += 1
            else:
                winner = f"{Colors.BLUE}PROG{Colors.END}"
                prog_wins_horizon += 1
        else:
            winner = "N/A"

        ml_str = f"${ml_avg:.2f}" if ml_avg else "N/A"
        prog_str = f"${prog_avg:.2f}" if prog_avg else "N/A"

        marker = " ← t+12" if horizon == 12 else ""
        print(f"t+{horizon:<8} {ml_str:<12} {len(ml_errors):<10} {prog_str:<12} {len(prog_errors):<10} {winner}{marker}")

        if ml_avg is not None:
            ml_by_horizon.append({'horizon': horizon, 'avg_distance': round(ml_avg, 2), 'count': len(ml_errors)})
        if prog_avg is not None:
            prog_by_horizon.append({'horizon': horizon, 'avg_distance': round(prog_avg, 2), 'count': len(prog_errors)})

    print("-" * 70)
    print(f"ML wins: {ml_wins_horizon} horizons, Prog wins: {prog_wins_horizon} horizons")

    # Degradation rates
    if len(ml_by_horizon) >= 2:
        ml_t1 = next((h['avg_distance'] for h in ml_by_horizon if h['horizon'] == 1), None)
        ml_t24 = next((h['avg_distance'] for h in ml_by_horizon if h['horizon'] == 24), None)
        if ml_t1 and ml_t24:
            ml_degradation = (ml_t24 - ml_t1) / 23
            print(f"\n{Colors.BOLD}Structural Summary:{Colors.END}")
            print(f"  ML t+1: ${ml_t1:.2f}")
            print(f"  ML t+24: ${ml_t24:.2f}")
            print(f"  ML Degradation Rate: ${ml_degradation:.2f}/hour")

    if len(prog_by_horizon) >= 2:
        prog_t1 = next((h['avg_distance'] for h in prog_by_horizon if h['horizon'] == 1), None)
        prog_t24 = next((h['avg_distance'] for h in prog_by_horizon if h['horizon'] == 24), None)
        if prog_t1 and prog_t24:
            prog_degradation = (prog_t24 - prog_t1) / 23
            print(f"  Prog t+1: ${prog_t1:.2f}")
            print(f"  Prog t+24: ${prog_t24:.2f}")
            print(f"  Prog Degradation Rate: ${prog_degradation:.2f}/hour")

    # =========================================
    # COMPARISON WITH RENDIMIENTO UI
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}EXPECTED VALUES (to compare with Rendimiento UI){Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"""
These values should match what you see at:
https://pudidicmgprediction.vercel.app/rendimiento.html

With date range: {start_date} to {end_date}

ML Predictions: ${ml_overall_avg:.2f}
CMG Programado: ${prog_overall_avg:.2f}
ML Degradation: ${ml_degradation:.2f}/h
Prog Degradation: ${prog_degradation:.2f}/h

ML: Horizon t+1: ${ml_t1:.2f}
ML: Horizon t+24: ${ml_t24:.2f}
Prog: Horizon t+1: ${prog_t1:.2f}
Prog: Horizon t+24: ${prog_t24:.2f}
""")

    print(f"\n{Colors.BOLD}Data Coverage:{Colors.END}")
    print(f"  ML forecasts loaded: {len(ml_forecasts)}")
    print(f"  Prog forecasts loaded (filtered): {len(prog_filtered)}")
    print(f"  Actuals hours: {len(actuals)}")

    print(f"\n{Colors.GREEN}Verification complete!{Colors.END}\n")


if __name__ == "__main__":
    main()
