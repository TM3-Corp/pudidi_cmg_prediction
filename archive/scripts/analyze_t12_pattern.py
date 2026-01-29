#!/usr/bin/env python3
"""
Analyze t+12 Pattern - Deep Dive Investigation
================================================

Investigates why ML predictions at horizon t+12 perform worse than other horizons.

Hypotheses to test:
1. Target hour correlation: t+12 predictions might target volatile mid-day hours
2. Forecast hour correlation: Specific forecast hours might be problematic
3. Systematic bias: ML might be consistently over/under-predicting at t+12

Usage:
    SUPABASE_URL="..." SUPABASE_SERVICE_KEY="..." python3 analyze_t12_pattern.py --start 2025-12-21 --end 2025-12-27
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
    parser = argparse.ArgumentParser(description='Analyze t+12 pattern')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

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
    forecast_query_start = start_date - timedelta(days=1)

    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}T+12 PATTERN ANALYSIS{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"Date Range: {start_date} to {end_date}")

    # Load ML forecasts day by day
    print(f"\n{Colors.BOLD}Loading data...{Colors.END}")
    ml_forecasts = []
    current = forecast_query_start
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        params = [
            ("forecast_date", f"eq.{date_str}"),
            ("limit", "1000")
        ]
        resp = requests.get(f"{base_url}/ml_predictions_santiago", params=params, headers=headers)
        if resp.status_code == 200:
            ml_forecasts.extend(resp.json())
        current += timedelta(days=1)

    print(f"  ML forecasts loaded: {len(ml_forecasts)}")

    # Load CMG Programado day by day
    prog_forecasts = []
    current = forecast_query_start
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        params = [
            ("forecast_date", f"eq.{date_str}"),
            ("limit", "5000")
        ]
        resp = requests.get(f"{base_url}/cmg_programado_santiago", params=params, headers=headers)
        if resp.status_code == 200:
            prog_forecasts.extend(resp.json())
        current += timedelta(days=1)

    # Filter CMG Programado
    prog_filtered = []
    for p in prog_forecasts:
        forecast_dt = datetime.fromisoformat(p['forecast_datetime'].replace('Z', '+00:00'))
        target_dt = datetime.fromisoformat(p['target_datetime'].replace('Z', '+00:00'))
        if target_dt <= forecast_dt:
            continue
        horizon_hours = int((target_dt - forecast_dt).total_seconds() / 3600)
        if horizon_hours <= 24:
            p['horizon'] = horizon_hours
            p['target_date'] = target_dt.astimezone(santiago_tz).strftime('%Y-%m-%d')
            p['target_hour'] = target_dt.astimezone(santiago_tz).hour
            p['forecast_hour'] = forecast_dt.astimezone(santiago_tz).hour
            prog_filtered.append(p)

    print(f"  CMG Programado filtered: {len(prog_filtered)}")

    # Add target info to ML forecasts
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

    # Load actuals
    online_params = [
        ("date", f"gte.{start_date}"),
        ("date", f"lte.{end_date}"),
        ("limit", "5000")
    ]
    resp = requests.get(f"{base_url}/cmg_online_santiago", params=online_params, headers=headers)
    cmg_online = resp.json() if resp.status_code == 200 else []

    actuals_raw = defaultdict(list)
    for record in cmg_online:
        key = (record['date'], record['hour'])
        actuals_raw[key].append(record['cmg_usd'])
    actuals = {key: sum(values) / len(values) for key, values in actuals_raw.items()}

    print(f"  Actuals hours: {len(actuals)}")

    # =========================================
    # ANALYSIS 1: Error by Target Hour for t+12
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}ANALYSIS 1: ML t+12 Error by Target Hour{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print("(Which hours of the day are hardest to predict 12 hours ahead?)")

    t12_by_target_hour = defaultdict(list)
    for ml in ml_forecasts:
        if ml['horizon'] != 12:
            continue
        target_date = ml['target_date']
        target_hour = ml['target_hour']
        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(ml['cmg_predicted'] - actual)
            t12_by_target_hour[target_hour].append(error)

    print(f"\n{'Target Hour':<12} {'Avg Error':<12} {'Count':<8} {'Visual'}")
    print("-" * 60)
    for hour in range(24):
        errors = t12_by_target_hour.get(hour, [])
        if errors:
            avg = sum(errors) / len(errors)
            bar = "█" * int(avg / 5)
            color = Colors.RED if avg > 50 else Colors.YELLOW if avg > 30 else Colors.GREEN
            print(f"{hour:02d}:00        {color}${avg:>8.2f}{Colors.END}   {len(errors):<8} {bar}")
        else:
            print(f"{hour:02d}:00        N/A")

    # =========================================
    # ANALYSIS 2: Error by Forecast Hour for t+12
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}ANALYSIS 2: ML t+12 Error by Forecast Hour{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print("(Which hours of day produce worst t+12 predictions?)")

    t12_by_forecast_hour = defaultdict(list)
    for ml in ml_forecasts:
        if ml['horizon'] != 12:
            continue
        forecast_hour = ml['forecast_hour']
        target_date = ml['target_date']
        target_hour = ml['target_hour']
        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(ml['cmg_predicted'] - actual)
            t12_by_forecast_hour[forecast_hour].append(error)

    print(f"\n{'Forecast Hour':<14} {'Avg Error':<12} {'Count':<8} {'Targets'}")
    print("-" * 60)
    for hour in range(24):
        errors = t12_by_forecast_hour.get(hour, [])
        if errors:
            avg = sum(errors) / len(errors)
            target_h = (hour + 12) % 24
            color = Colors.RED if avg > 50 else Colors.YELLOW if avg > 30 else Colors.GREEN
            print(f"{hour:02d}:00          {color}${avg:>8.2f}{Colors.END}   {len(errors):<8} → {target_h:02d}:00")

    # =========================================
    # ANALYSIS 3: Bias Direction for t+12
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}ANALYSIS 3: ML t+12 Bias Direction{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print("(Is ML systematically over or under-predicting?)")

    t12_biases = []
    for ml in ml_forecasts:
        if ml['horizon'] != 12:
            continue
        target_date = ml['target_date']
        target_hour = ml['target_hour']
        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            bias = ml['cmg_predicted'] - actual  # Positive = over-predict
            t12_biases.append(bias)

    if t12_biases:
        over_predict = sum(1 for b in t12_biases if b > 0)
        under_predict = sum(1 for b in t12_biases if b < 0)
        avg_bias = sum(t12_biases) / len(t12_biases)

        print(f"\n  Total t+12 predictions: {len(t12_biases)}")
        print(f"  Over-predictions: {over_predict} ({over_predict/len(t12_biases)*100:.1f}%)")
        print(f"  Under-predictions: {under_predict} ({under_predict/len(t12_biases)*100:.1f}%)")
        print(f"  Average bias: ${avg_bias:.2f}")

        if avg_bias > 5:
            print(f"\n  {Colors.YELLOW}→ ML tends to OVER-PREDICT at t+12{Colors.END}")
        elif avg_bias < -5:
            print(f"\n  {Colors.YELLOW}→ ML tends to UNDER-PREDICT at t+12{Colors.END}")
        else:
            print(f"\n  {Colors.GREEN}→ ML has no significant bias at t+12{Colors.END}")

    # =========================================
    # ANALYSIS 4: Compare t+12 vs other horizons
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}ANALYSIS 4: ML Bias Direction by Horizon{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print("(Does bias pattern change across horizons?)")

    horizon_biases = defaultdict(list)
    for ml in ml_forecasts:
        target_date = ml['target_date']
        target_hour = ml['target_hour']
        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            bias = ml['cmg_predicted'] - actual
            horizon_biases[ml['horizon']].append(bias)

    print(f"\n{'Horizon':<10} {'Avg Bias':<12} {'Over%':<10} {'Under%':<10}")
    print("-" * 50)
    for h in range(1, 25):
        biases = horizon_biases.get(h, [])
        if biases:
            avg = sum(biases) / len(biases)
            over_pct = sum(1 for b in biases if b > 0) / len(biases) * 100
            under_pct = 100 - over_pct
            marker = " ← t+12" if h == 12 else ""
            color = Colors.RED if abs(avg) > 10 else Colors.YELLOW if abs(avg) > 5 else Colors.GREEN
            print(f"t+{h:<8} {color}${avg:>8.2f}{Colors.END}   {over_pct:>6.1f}%    {under_pct:>6.1f}%{marker}")

    # =========================================
    # ANALYSIS 5: CMG Programado vs ML at t+12
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}ANALYSIS 5: CMG Programado t+12 Performance{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")

    prog_t12 = [p for p in prog_filtered if p['horizon'] == 12]
    prog_t12_errors = []
    for p in prog_t12:
        target_date = p['target_date']
        target_hour = p['target_hour']
        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(p['cmg_usd'] - actual)
            prog_t12_errors.append(error)

    ml_t12 = [m for m in ml_forecasts if m['horizon'] == 12]
    ml_t12_errors = []
    for m in ml_t12:
        target_date = m['target_date']
        target_hour = m['target_hour']
        if (target_date, target_hour) in actuals:
            actual = actuals[(target_date, target_hour)]
            error = abs(m['cmg_predicted'] - actual)
            ml_t12_errors.append(error)

    print(f"\n  CMG Programado t+12 avg error: ${sum(prog_t12_errors)/len(prog_t12_errors):.2f}" if prog_t12_errors else "  No data")
    print(f"  ML t+12 avg error: ${sum(ml_t12_errors)/len(ml_t12_errors):.2f}" if ml_t12_errors else "  No data")

    if prog_t12_errors and ml_t12_errors:
        diff = sum(ml_t12_errors)/len(ml_t12_errors) - sum(prog_t12_errors)/len(prog_t12_errors)
        print(f"  Difference: ${diff:.2f} (ML is {'worse' if diff > 0 else 'better'})")

    # =========================================
    # ANALYSIS 6: Actual CMG Volatility by Hour
    # =========================================
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}ANALYSIS 6: Actual CMG Volatility by Hour{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print("(Which hours have the most variable actual CMG values?)")

    hour_values = defaultdict(list)
    for (date, hour), cmg in actuals.items():
        hour_values[hour].append(cmg)

    print(f"\n{'Hour':<8} {'Avg CMG':<12} {'Std Dev':<12} {'Min':<10} {'Max':<10}")
    print("-" * 60)
    for hour in range(24):
        values = hour_values.get(hour, [])
        if values:
            avg = sum(values) / len(values)
            variance = sum((x - avg) ** 2 for x in values) / len(values)
            std_dev = variance ** 0.5
            color = Colors.RED if std_dev > 30 else Colors.YELLOW if std_dev > 20 else Colors.GREEN
            print(f"{hour:02d}:00    ${avg:>8.2f}   {color}${std_dev:>8.2f}{Colors.END}   ${min(values):>7.2f}   ${max(values):>7.2f}")

    print(f"\n{Colors.GREEN}Analysis complete!{Colors.END}\n")


if __name__ == "__main__":
    main()
