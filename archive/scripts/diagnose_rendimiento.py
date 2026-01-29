"""
Diagnose Rendimiento Logic Issues
==================================
This script validates the logic of the performance_range API and identifies data issues.

Key questions to answer:
1. Is the TEMPORAL dimension (by day) filtering by target_datetime? (Expected: YES)
2. Is the STRUCTURAL dimension (by horizon) filtering by forecast_datetime? (Expected: YES per user)
3. Why does Dec 1-25 only show Dec 1-14 in plots?
4. Are there data gaps in CMG Online or predictions?
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import json

# Add lib path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from lib.utils.supabase_client import SupabaseClient
    import requests
    import pytz
    AVAILABLE = True
except Exception as e:
    print(f"Import error: {e}")
    AVAILABLE = False

def diagnose_data(start_date_str: str, end_date_str: str):
    """Run comprehensive diagnostics on the data for a date range."""

    if not AVAILABLE:
        print("ERROR: Required libraries not available")
        return

    santiago_tz = pytz.timezone('America/Santiago')
    supabase = SupabaseClient()

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    print("=" * 70)
    print(f"DIAGNOSING RENDIMIENTO DATA: {start_date_str} to {end_date_str}")
    print("=" * 70)

    # =========================================================================
    # 1. CHECK CMG ONLINE (ACTUALS) DATA
    # =========================================================================
    print("\n" + "=" * 70)
    print("1. CMG ONLINE (ACTUALS) DATA")
    print("=" * 70)

    online_url = f"{supabase.base_url}/cmg_online_santiago"
    cmg_online = []

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        params = [
            ("date", f"eq.{date_str}"),
            ("order", "hour.asc"),
            ("limit", "1000")
        ]
        response = requests.get(online_url, params=params, headers=supabase.headers)
        if response.status_code == 200:
            day_data = response.json()
            cmg_online.extend(day_data)
            hours_found = len(set(r['hour'] for r in day_data))
            missing_hours = set(range(24)) - set(r['hour'] for r in day_data)
            status = "COMPLETE" if hours_found == 24 else f"MISSING {24-hours_found} hours"
            if missing_hours:
                print(f"  {date_str}: {hours_found}/24 hours - {status} (missing: {sorted(missing_hours)[:5]}{'...' if len(missing_hours) > 5 else ''})")
            else:
                print(f"  {date_str}: {hours_found}/24 hours - {status}")
        else:
            print(f"  {date_str}: API ERROR {response.status_code}")
        current_date += timedelta(days=1)

    # Build actuals lookup
    actuals_raw = defaultdict(list)
    for record in cmg_online:
        key = (record['date'], record['hour'])
        actuals_raw[key].append(record['cmg_usd'])
    actuals = {k: sum(v)/len(v) for k, v in actuals_raw.items()}

    print(f"\n  Total CMG Online records: {len(cmg_online)}")
    print(f"  Unique (date, hour) pairs: {len(actuals)}")

    # =========================================================================
    # 2. CHECK ML PREDICTIONS DATA
    # =========================================================================
    print("\n" + "=" * 70)
    print("2. ML PREDICTIONS DATA")
    print("=" * 70)

    ml_url = f"{supabase.base_url}/ml_predictions_santiago"
    ml_forecasts = []

    # Query from start_date - 1 to end_date (to capture all predictions targeting the range)
    query_start = start_date - timedelta(days=1)
    current_date = query_start

    print(f"\n  Querying forecast_date from {query_start} to {end_date}")
    print(f"  (Including {query_start} because its t+24 predictions target {start_date})")

    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        params = [
            ("forecast_date", f"eq.{date_str}"),
            ("order", "forecast_hour.asc,horizon.asc"),
            ("limit", "1000")
        ]
        response = requests.get(ml_url, params=params, headers=supabase.headers)
        if response.status_code == 200:
            day_data = response.json()
            ml_forecasts.extend(day_data)
            print(f"  {date_str}: {len(day_data)} predictions")
        else:
            print(f"  {date_str}: API ERROR {response.status_code}")
        current_date += timedelta(days=1)

    # Add target_date and target_hour to ML forecasts
    for ml in ml_forecasts:
        forecast_date = ml['forecast_date']
        forecast_hour = ml['forecast_hour']
        horizon = ml['horizon']
        forecast_dt = santiago_tz.localize(datetime.strptime(f"{forecast_date} {forecast_hour:02d}:00", "%Y-%m-%d %H:%M"))
        target_dt = forecast_dt + timedelta(hours=horizon)
        ml['target_date'] = target_dt.strftime('%Y-%m-%d')
        ml['target_hour'] = target_dt.hour

    print(f"\n  Total ML predictions: {len(ml_forecasts)}")

    # =========================================================================
    # 3. CHECK CMG PROGRAMADO DATA
    # =========================================================================
    print("\n" + "=" * 70)
    print("3. CMG PROGRAMADO DATA")
    print("=" * 70)

    prog_url = f"{supabase.base_url}/cmg_programado_santiago"
    prog_forecasts = []

    current_date = query_start
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        params = [
            ("forecast_date", f"eq.{date_str}"),
            ("order", "forecast_hour.asc,target_datetime.asc"),
            ("limit", "5000")
        ]
        response = requests.get(prog_url, params=params, headers=supabase.headers)
        if response.status_code == 200:
            day_data = response.json()
            prog_forecasts.extend(day_data)
            print(f"  {date_str}: {len(day_data)} forecasts")
        else:
            print(f"  {date_str}: API ERROR {response.status_code}")
        current_date += timedelta(days=1)

    # Filter CMG Programado to future forecasts (t+1 to t+24)
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
            prog_filtered.append(p)

    print(f"\n  Total CMG Programado raw: {len(prog_forecasts)}")
    print(f"  After filtering (t+1 to t+24): {len(prog_filtered)}")

    # =========================================================================
    # 4. TEMPORAL DIMENSION: METRICS BY DAY (using target_datetime)
    # =========================================================================
    print("\n" + "=" * 70)
    print("4. TEMPORAL DIMENSION: METRICS BY DAY")
    print("    (Filtering by target_datetime - predictions FOR these days)")
    print("=" * 70)

    ml_daily_errors = defaultdict(list)
    prog_daily_errors = defaultdict(list)

    # Count predictions by target_date
    ml_by_target = defaultdict(list)
    prog_by_target = defaultdict(list)

    for ml in ml_forecasts:
        target_date = ml['target_date']
        ml_by_target[target_date].append(ml)

        if (ml['target_date'], ml['target_hour']) in actuals:
            actual = actuals[(ml['target_date'], ml['target_hour'])]
            error = abs(ml['cmg_predicted'] - actual)
            ml_daily_errors[target_date].append(error)

    for p in prog_filtered:
        target_date = p['target_date']
        prog_by_target[target_date].append(p)

        if (p['target_date'], p['target_hour']) in actuals:
            actual = actuals[(p['target_date'], p['target_hour'])]
            error = abs(p['cmg_usd'] - actual)
            prog_daily_errors[target_date].append(error)

    print(f"\n{'Date':<12} {'ML Pred':<10} {'ML Match':<10} {'ML Avg':<10} {'Prog Pred':<10} {'Prog Match':<10} {'Prog Avg':<10}")
    print("-" * 82)

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')

        ml_preds = len(ml_by_target.get(date_str, []))
        ml_matched = len(ml_daily_errors.get(date_str, []))
        ml_avg = sum(ml_daily_errors.get(date_str, [])) / ml_matched if ml_matched > 0 else None

        prog_preds = len(prog_by_target.get(date_str, []))
        prog_matched = len(prog_daily_errors.get(date_str, []))
        prog_avg = sum(prog_daily_errors.get(date_str, [])) / prog_matched if prog_matched > 0 else None

        ml_avg_str = f"${ml_avg:.2f}" if ml_avg else "N/A"
        prog_avg_str = f"${prog_avg:.2f}" if prog_avg else "N/A"

        print(f"{date_str:<12} {ml_preds:<10} {ml_matched:<10} {ml_avg_str:<10} {prog_preds:<10} {prog_matched:<10} {prog_avg_str:<10}")

        current_date += timedelta(days=1)

    # =========================================================================
    # 5. STRUCTURAL DIMENSION: METRICS BY HORIZON
    # =========================================================================
    print("\n" + "=" * 70)
    print("5. STRUCTURAL DIMENSION: METRICS BY HORIZON")
    print("=" * 70)

    # A) Current implementation (includes forecasts from start_date - 1)
    print("\n  A) CURRENT IMPLEMENTATION (forecast_date from start_date-1 to end_date):")
    ml_horizon_errors_current = defaultdict(list)
    prog_horizon_errors_current = defaultdict(list)

    for ml in ml_forecasts:
        if (ml['target_date'], ml['target_hour']) in actuals:
            actual = actuals[(ml['target_date'], ml['target_hour'])]
            error = abs(ml['cmg_predicted'] - actual)
            ml_horizon_errors_current[ml['horizon']].append(error)

    for p in prog_filtered:
        if (p['target_date'], p['target_hour']) in actuals:
            actual = actuals[(p['target_date'], p['target_hour'])]
            error = abs(p['cmg_usd'] - actual)
            prog_horizon_errors_current[p['horizon']].append(error)

    print(f"\n{'Horizon':<10} {'ML Count':<10} {'ML Avg':<10} {'Prog Count':<10} {'Prog Avg':<10}")
    print("-" * 50)
    for h in range(1, 25):
        ml_errs = ml_horizon_errors_current.get(h, [])
        prog_errs = prog_horizon_errors_current.get(h, [])
        ml_avg = sum(ml_errs) / len(ml_errs) if ml_errs else None
        prog_avg = sum(prog_errs) / len(prog_errs) if prog_errs else None
        ml_str = f"${ml_avg:.2f}" if ml_avg else "N/A"
        prog_str = f"${prog_avg:.2f}" if prog_avg else "N/A"
        print(f"t+{h:<8} {len(ml_errs):<10} {ml_str:<10} {len(prog_errs):<10} {prog_str:<10}")

    # B) User's expected implementation (only forecasts from start_date to end_date)
    print("\n  B) USER'S EXPECTED LOGIC (forecast_date from start_date to end_date):")
    print("     'How did predictions MADE during these days perform?'")

    ml_horizon_errors_expected = defaultdict(list)
    prog_horizon_errors_expected = defaultdict(list)

    for ml in ml_forecasts:
        # Only include if forecast_date is in the user's range
        forecast_date = datetime.strptime(ml['forecast_date'], '%Y-%m-%d').date()
        if forecast_date < start_date or forecast_date > end_date:
            continue

        if (ml['target_date'], ml['target_hour']) in actuals:
            actual = actuals[(ml['target_date'], ml['target_hour'])]
            error = abs(ml['cmg_predicted'] - actual)
            ml_horizon_errors_expected[ml['horizon']].append(error)

    for p in prog_filtered:
        forecast_dt = datetime.fromisoformat(p['forecast_datetime'].replace('Z', '+00:00'))
        forecast_date = forecast_dt.astimezone(santiago_tz).date()
        if forecast_date < start_date or forecast_date > end_date:
            continue

        if (p['target_date'], p['target_hour']) in actuals:
            actual = actuals[(p['target_date'], p['target_hour'])]
            error = abs(p['cmg_usd'] - actual)
            prog_horizon_errors_expected[p['horizon']].append(error)

    print(f"\n{'Horizon':<10} {'ML Count':<10} {'ML Avg':<10} {'Prog Count':<10} {'Prog Avg':<10}")
    print("-" * 50)
    for h in range(1, 25):
        ml_errs = ml_horizon_errors_expected.get(h, [])
        prog_errs = prog_horizon_errors_expected.get(h, [])
        ml_avg = sum(ml_errs) / len(ml_errs) if ml_errs else None
        prog_avg = sum(prog_errs) / len(prog_errs) if prog_errs else None
        ml_str = f"${ml_avg:.2f}" if ml_avg else "N/A"
        prog_str = f"${prog_avg:.2f}" if prog_avg else "N/A"
        print(f"t+{h:<8} {len(ml_errs):<10} {ml_str:<10} {len(prog_errs):<10} {prog_str:<10}")

    # =========================================================================
    # 6. IDENTIFY POTENTIAL ISSUES
    # =========================================================================
    print("\n" + "=" * 70)
    print("6. POTENTIAL ISSUES IDENTIFIED")
    print("=" * 70)

    issues = []

    # Check for missing actuals
    missing_actuals_dates = []
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        hours_with_actuals = sum(1 for h in range(24) if (date_str, h) in actuals)
        if hours_with_actuals < 24:
            missing_actuals_dates.append((date_str, hours_with_actuals))
        current_date += timedelta(days=1)

    if missing_actuals_dates:
        issues.append(f"CMG Online data incomplete for {len(missing_actuals_dates)} days:")
        for date_str, count in missing_actuals_dates[:5]:
            issues.append(f"  - {date_str}: {count}/24 hours")
        if len(missing_actuals_dates) > 5:
            issues.append(f"  - ... and {len(missing_actuals_dates) - 5} more")

    # Check horizon differences
    for h in range(1, 25):
        current_count = len(ml_horizon_errors_current.get(h, []))
        expected_count = len(ml_horizon_errors_expected.get(h, []))
        if current_count != expected_count:
            diff = current_count - expected_count
            issues.append(f"Horizon t+{h}: Current impl has {diff} extra samples from day before start_date")
            break  # Just show first one as example

    if issues:
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("  No issues found!")

    # =========================================================================
    # 7. SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("7. SUMMARY")
    print("=" * 70)

    # Calculate overall averages
    ml_all_errors = []
    prog_all_errors = []
    for errors in ml_daily_errors.values():
        ml_all_errors.extend(errors)
    for errors in prog_daily_errors.values():
        prog_all_errors.extend(errors)

    ml_overall = sum(ml_all_errors) / len(ml_all_errors) if ml_all_errors else None
    prog_overall = sum(prog_all_errors) / len(prog_all_errors) if prog_all_errors else None

    print(f"\n  ML Overall Avg Distance: ${ml_overall:.2f}" if ml_overall else "\n  ML Overall Avg Distance: N/A")
    print(f"  Prog Overall Avg Distance: ${prog_overall:.2f}" if prog_overall else "  Prog Overall Avg Distance: N/A")

    if ml_overall and prog_overall:
        winner = "ML" if ml_overall < prog_overall else "CMG Programado"
        diff = abs(ml_overall - prog_overall)
        print(f"\n  Winner: {winner} by ${diff:.2f}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Default: last 7 days
    if len(sys.argv) >= 3:
        start = sys.argv[1]
        end = sys.argv[2]
    else:
        # Default to Dec 21-27 as user mentioned
        start = "2025-12-21"
        end = "2025-12-27"

    diagnose_data(start, end)
