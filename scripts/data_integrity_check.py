#!/usr/bin/env python3
"""
Comprehensive Data Integrity Checker for CMG Prediction System

This script validates data completeness across all three data sources:
1. ML Predictions - Expected: 24 predictions per forecast hour
2. CMG Programado - Expected: 72 predictions per forecast hour (typical)
3. CMG Online - Expected: 3 records per hour (one per node)

Usage:
    export SUPABASE_URL="https://btyfbrclgmphcjgrvcgd.supabase.co"
    export SUPABASE_SERVICE_KEY="your_service_key"

    # Check last 7 days (uses fast RPC method)
    python3 scripts/data_integrity_check.py

    # Check specific date range
    python3 scripts/data_integrity_check.py --start 2025-11-14 --end 2025-11-21

    # Save detailed report
    python3 scripts/data_integrity_check.py --output report.md

    # Force legacy mode (504 API calls instead of 1)
    python3 scripts/data_integrity_check.py --legacy

Ground Truth Expectations:
- ML Predictions: 24 forecast hours/day × 24 predictions = 576 per day
- CMG Programado: Variable forecasts per day, but each should have ~72 predictions
- CMG Online: 24 hours × 3 nodes = 72 records per day

Performance:
- RPC Mode (default): 1 API call, <1 second
- Legacy Mode: 504 API calls, ~46 seconds
"""

import os
import sys
import requests
import argparse
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def get_date_range(start_date: str = None, end_date: str = None, days: int = 7) -> List[str]:
    """Generate list of dates to check"""
    if end_date is None:
        end = datetime.now().date()
    else:
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

    if start_date is None:
        start = end - timedelta(days=days - 1)
    else:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    return dates


# ============================================================
# RPC-BASED INTEGRITY CHECK (FAST - 1 API CALL)
# ============================================================

def check_integrity_via_rpc(headers: dict, dates: List[str]) -> Optional[Tuple[Dict, Dict, Dict]]:
    """
    Call the RPC function to get all integrity data in a single API call.
    Returns (ml_results, prog_results, online_results) or None if RPC fails.
    """
    base_url = os.environ['SUPABASE_URL']
    url = f"{base_url}/rest/v1/rpc/check_data_integrity"

    # Prepare request
    rpc_headers = headers.copy()
    rpc_headers["Content-Type"] = "application/json"

    payload = {
        "p_start_date": dates[0],
        "p_end_date": dates[-1]
    }

    print(f"\n{Colors.BOLD}Using RPC function (1 API call)...{Colors.END}")

    try:
        response = requests.post(url, json=payload, headers=rpc_headers, timeout=30)

        if response.status_code == 200:
            rpc_data = response.json()
            return convert_rpc_to_results(rpc_data, dates)
        elif response.status_code == 404:
            print(f"  {Colors.YELLOW}RPC function not found. Falling back to legacy mode.{Colors.END}")
            print(f"  {Colors.YELLOW}Run migration 005 to enable RPC: supabase/migrations/005_add_integrity_check_function.sql{Colors.END}")
            return None
        else:
            print(f"  {Colors.RED}RPC call failed: {response.status_code}{Colors.END}")
            print(f"  {Colors.YELLOW}Falling back to legacy mode...{Colors.END}")
            return None

    except requests.exceptions.Timeout:
        print(f"  {Colors.RED}RPC call timed out{Colors.END}")
        print(f"  {Colors.YELLOW}Falling back to legacy mode...{Colors.END}")
        return None
    except Exception as e:
        print(f"  {Colors.RED}RPC error: {e}{Colors.END}")
        print(f"  {Colors.YELLOW}Falling back to legacy mode...{Colors.END}")
        return None


def convert_rpc_to_results(rpc_data: List[Dict], dates: List[str]) -> Tuple[Dict, Dict, Dict]:
    """
    Convert RPC response to the same format as legacy functions.
    This ensures the report generation works identically.
    """
    # Initialize result structures (matching legacy format)
    ml_results = {
        'daily_totals': {},
        'hourly_counts': defaultdict(lambda: defaultdict(int)),
        'incomplete_forecasts': [],
        'missing_hours': defaultdict(list)
    }

    prog_results = {
        'daily_forecast_counts': {},
        'forecast_lengths': defaultdict(lambda: defaultdict(int)),
        'short_forecasts': [],
        'missing_hours': defaultdict(list)
    }

    online_results = {
        'daily_totals': {},
        'hourly_nodes': defaultdict(lambda: defaultdict(set)),
        'missing_hours': defaultdict(list),
        'incomplete_hours': []
    }

    print(f"\n{Colors.BOLD}Checking ML Predictions...{Colors.END}")

    for row in rpc_data:
        date = row['check_date']

        # ============================================================
        # ML Predictions
        # ============================================================
        ml_total = row['ml_total']
        ml_expected = row['ml_expected']
        ml_missing = row['ml_missing_hours'] or []
        ml_incomplete = row['ml_incomplete_hours'] or []

        ml_results['daily_totals'][date] = ml_total
        ml_results['missing_hours'][date] = ml_missing

        # Process incomplete hours
        for item in ml_incomplete:
            ml_results['incomplete_forecasts'].append({
                'date': date,
                'hour': item['hour'],
                'count': item['count'],
                'expected': 24
            })
            ml_results['hourly_counts'][date][item['hour']] = item['count']

        # Mark complete hours (24 predictions each)
        for hour in range(24):
            if hour not in ml_missing and not any(i['hour'] == hour for i in ml_incomplete):
                ml_results['hourly_counts'][date][hour] = 24

        # Print status
        status = Colors.GREEN + "✅" + Colors.END if ml_total == ml_expected else Colors.RED + "❌" + Colors.END
        print(f"  {date}: {status} {ml_total:4d}/{ml_expected} records")

    print(f"\n{Colors.BOLD}Checking CMG Programado...{Colors.END}")

    for row in rpc_data:
        date = row['check_date']

        # ============================================================
        # CMG Programado
        # ============================================================
        prog_hours = row['prog_forecast_hours']
        prog_expected = row['prog_expected']
        prog_missing = row['prog_missing_hours'] or []

        prog_results['daily_forecast_counts'][date] = prog_hours
        prog_results['missing_hours'][date] = prog_missing

        # Print status
        if prog_hours >= 24:
            status = Colors.GREEN + "✅" + Colors.END
        elif prog_hours >= 22:
            status = Colors.YELLOW + "⚠" + Colors.END
        else:
            status = Colors.RED + "❌" + Colors.END

        print(f"  {date}: {status} {prog_hours:2d}/24 forecast hours")

    print(f"\n{Colors.BOLD}Checking CMG Online...{Colors.END}")

    for row in rpc_data:
        date = row['check_date']

        # ============================================================
        # CMG Online
        # ============================================================
        online_total = row['online_total']
        online_expected = row['online_expected']
        online_missing = row['online_missing_hours'] or []
        online_incomplete = row['online_incomplete_hours'] or []

        online_results['daily_totals'][date] = online_total
        online_results['missing_hours'][date] = online_missing

        # Process incomplete hours
        for item in online_incomplete:
            online_results['incomplete_hours'].append({
                'date': date,
                'hour': item['hour'],
                'count': item['count'],
                'nodes': item.get('nodes', []),
                'expected': 3
            })

        # Print status
        status = Colors.GREEN + "✅" + Colors.END if online_total == online_expected else Colors.RED + "❌" + Colors.END
        print(f"  {date}: {status} {online_total:2d}/{online_expected} records")

    return ml_results, prog_results, online_results

def check_ml_predictions(headers: dict, dates: List[str]) -> Dict:
    """
    Check ML Predictions completeness
    Expected: 24 predictions per forecast hour
    """
    base_url = os.environ['SUPABASE_URL']
    results = {
        'daily_totals': {},
        'hourly_counts': defaultdict(lambda: defaultdict(int)),
        'incomplete_forecasts': [],
        'missing_hours': defaultdict(list)
    }

    print(f"\n{Colors.BOLD}Checking ML Predictions...{Colors.END}")

    for date in dates:
        daily_total = 0

        for hour in range(24):
            url = f"{base_url}/rest/v1/ml_predictions_santiago"
            params = [
                ("forecast_date", f"eq.{date}"),
                ("forecast_hour", f"eq.{hour}"),
                ("select", "id"),
                ("limit", "100")
            ]

            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                count = len(response.json())
                results['hourly_counts'][date][hour] = count
                daily_total += count

                # Check if forecast is complete (should be 24 predictions)
                if count > 0 and count < 24:
                    results['incomplete_forecasts'].append({
                        'date': date,
                        'hour': hour,
                        'count': count,
                        'expected': 24
                    })
                elif count == 0:
                    results['missing_hours'][date].append(hour)
            else:
                print(f"  {Colors.RED}ERROR{Colors.END} querying {date} hour {hour}: {response.status_code}")

        results['daily_totals'][date] = daily_total

        # Expected: 24 hours × 24 predictions = 576
        expected = 576
        status = Colors.GREEN + "✅" + Colors.END if daily_total == expected else Colors.RED + "❌" + Colors.END
        print(f"  {date}: {status} {daily_total:4d}/{expected} records")

    return results

def check_cmg_programado(headers: dict, dates: List[str]) -> Dict:
    """
    Check CMG Programado completeness
    Expected: ~72 predictions per forecast (can vary)
    """
    base_url = os.environ['SUPABASE_URL']
    results = {
        'daily_forecast_counts': {},
        'forecast_lengths': defaultdict(lambda: defaultdict(int)),
        'short_forecasts': [],
        'missing_hours': defaultdict(list)
    }

    print(f"\n{Colors.BOLD}Checking CMG Programado...{Colors.END}")

    for date in dates:
        forecast_count = 0

        for hour in range(24):
            url = f"{base_url}/rest/v1/cmg_programado_santiago"
            params = [
                ("forecast_date", f"eq.{date}"),
                ("forecast_hour", f"eq.{hour}"),
                ("select", "id"),
                ("limit", "100")
            ]

            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                count = len(response.json())
                results['forecast_lengths'][date][hour] = count

                if count > 0:
                    forecast_count += 1

                    # Flag forecasts shorter than typical (72)
                    if count < 64:
                        results['short_forecasts'].append({
                            'date': date,
                            'hour': hour,
                            'count': count,
                            'expected': 72
                        })
                elif count == 0:
                    results['missing_hours'][date].append(hour)
            else:
                print(f"  {Colors.RED}ERROR{Colors.END} querying {date} hour {hour}: {response.status_code}")

        results['daily_forecast_counts'][date] = forecast_count

        # Expected: at least 22 forecasts per day (allowing for hours 21-22 issue)
        expected_min = 22
        if forecast_count >= 24:
            status = Colors.GREEN + "✅" + Colors.END
        elif forecast_count >= expected_min:
            status = Colors.YELLOW + "⚠" + Colors.END
        else:
            status = Colors.RED + "❌" + Colors.END

        print(f"  {date}: {status} {forecast_count:2d}/24 forecast hours")

    return results

def check_cmg_online(headers: dict, dates: List[str]) -> Dict:
    """
    Check CMG Online completeness
    Expected: 3 nodes per hour = 72 records per day
    """
    base_url = os.environ['SUPABASE_URL']
    results = {
        'daily_totals': {},
        'hourly_nodes': defaultdict(lambda: defaultdict(set)),
        'missing_hours': defaultdict(list),
        'incomplete_hours': []
    }

    print(f"\n{Colors.BOLD}Checking CMG Online...{Colors.END}")

    for date in dates:
        daily_total = 0

        for hour in range(24):
            url = f"{base_url}/rest/v1/cmg_online_santiago"
            params = [
                ("date", f"eq.{date}"),
                ("hour", f"eq.{hour}"),
                ("select", "node"),
                ("limit", "10")
            ]

            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                count = len(data)
                daily_total += count

                # Track which nodes we have for this hour
                nodes = set(r['node'] for r in data)
                results['hourly_nodes'][date][hour] = nodes

                # Expected: 3 nodes
                if count == 0:
                    results['missing_hours'][date].append(hour)
                elif count < 3:
                    results['incomplete_hours'].append({
                        'date': date,
                        'hour': hour,
                        'count': count,
                        'nodes': list(nodes),
                        'expected': 3
                    })
            else:
                print(f"  {Colors.RED}ERROR{Colors.END} querying {date} hour {hour}: {response.status_code}")

        results['daily_totals'][date] = daily_total

        # Expected: 24 hours × 3 nodes = 72
        expected = 72
        status = Colors.GREEN + "✅" + Colors.END if daily_total == expected else Colors.RED + "❌" + Colors.END
        print(f"  {date}: {status} {daily_total:2d}/{expected} records")

    return results

def generate_report(ml_results: Dict, prog_results: Dict, online_results: Dict,
                   dates: List[str]) -> str:
    """Generate comprehensive markdown report"""
    report = []
    report.append("# Data Integrity Check Report")
    report.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**Date Range:** {dates[0]} to {dates[-1]} ({len(dates)} days)")
    report.append("\n---\n")

    # ML Predictions Section
    report.append("## 1. ML Predictions")
    report.append("\n**Expected:** 24 predictions per forecast hour (576 per day)")
    report.append("\n### Daily Summary")
    report.append("\n| Date | Total | Expected | Status |")
    report.append("|------|-------|----------|--------|")

    for date in dates:
        total = ml_results['daily_totals'].get(date, 0)
        expected = 576
        status = "✅ Complete" if total == expected else f"❌ Missing {expected - total}"
        report.append(f"| {date} | {total} | {expected} | {status} |")

    # Missing hours
    if any(ml_results['missing_hours'].values()):
        report.append("\n### ❌ Missing Forecast Hours")
        for date in dates:
            missing = ml_results['missing_hours'].get(date, [])
            if missing:
                report.append(f"\n**{date}:** Hours {', '.join(map(str, sorted(missing)))}")

    # Incomplete forecasts
    if ml_results['incomplete_forecasts']:
        report.append("\n### ⚠ Incomplete Forecasts (< 24 predictions)")
        for item in ml_results['incomplete_forecasts']:
            report.append(f"- {item['date']} Hour {item['hour']:02d}: {item['count']}/24 predictions")

    # CMG Programado Section
    report.append("\n---\n")
    report.append("## 2. CMG Programado")
    report.append("\n**Expected:** ~72 predictions per forecast (can vary)")
    report.append("\n### Daily Summary")
    report.append("\n| Date | Forecast Hours | Status |")
    report.append("|------|----------------|--------|")

    for date in dates:
        count = prog_results['daily_forecast_counts'].get(date, 0)
        if count >= 24:
            status = "✅ Complete (24/24)"
        elif count >= 22:
            status = f"⚠ Partial ({count}/24) - Known hours 21-22 issue"
        else:
            status = f"❌ Incomplete ({count}/24)"
        report.append(f"| {date} | {count} | {status} |")

    # Missing hours
    if any(prog_results['missing_hours'].values()):
        report.append("\n### ❌ Missing Forecast Hours")
        for date in dates:
            missing = prog_results['missing_hours'].get(date, [])
            if missing:
                report.append(f"\n**{date}:** Hours {', '.join(map(str, sorted(missing)))}")

    # Short forecasts
    if prog_results['short_forecasts']:
        report.append("\n### ⚠ Short Forecasts (< 64 predictions)")
        for item in prog_results['short_forecasts']:
            report.append(f"- {item['date']} Hour {item['hour']:02d}: {item['count']} predictions (expected ~72)")

    # CMG Online Section
    report.append("\n---\n")
    report.append("## 3. CMG Online (Historical)")
    report.append("\n**Expected:** 3 nodes per hour (72 per day)")
    report.append("\n**Nodes:** NVA_P.MONTT___220, DALCAHUE______110, PIDPID________110")
    report.append("\n### Daily Summary")
    report.append("\n| Date | Total | Expected | Status |")
    report.append("|------|-------|----------|--------|")

    for date in dates:
        total = online_results['daily_totals'].get(date, 0)
        expected = 72
        status = "✅ Complete" if total == expected else f"❌ Missing {expected - total}"
        report.append(f"| {date} | {total} | {expected} | {status} |")

    # Missing hours
    if any(online_results['missing_hours'].values()):
        report.append("\n### ❌ Missing Hours")
        for date in dates:
            missing = online_results['missing_hours'].get(date, [])
            if missing:
                report.append(f"\n**{date}:** Hours {', '.join(map(str, sorted(missing)))}")

    # Incomplete hours
    if online_results['incomplete_hours']:
        report.append("\n### ⚠ Incomplete Hours (< 3 nodes)")
        for item in online_results['incomplete_hours']:
            nodes_str = ', '.join(item['nodes'])
            report.append(f"- {item['date']} Hour {item['hour']:02d}: {item['count']}/3 nodes ({nodes_str})")

    # Summary
    report.append("\n---\n")
    report.append("## Summary")

    ml_complete = sum(1 for d in dates if ml_results['daily_totals'].get(d, 0) == 576)
    prog_complete = sum(1 for d in dates if prog_results['daily_forecast_counts'].get(d, 0) >= 22)
    online_complete = sum(1 for d in dates if online_results['daily_totals'].get(d, 0) == 72)

    report.append(f"\n- **ML Predictions:** {ml_complete}/{len(dates)} days complete")
    report.append(f"- **CMG Programado:** {prog_complete}/{len(dates)} days complete (≥22 forecast hours)")
    report.append(f"- **CMG Online:** {online_complete}/{len(dates)} days complete")

    return '\n'.join(report)

def main():
    parser = argparse.ArgumentParser(
        description='Check data integrity for CMG Prediction System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=7, help='Number of days to check (default: 7)')
    parser.add_argument('--output', help='Save report to file (markdown format)')
    parser.add_argument('--legacy', action='store_true',
                        help='Use legacy mode (504 API calls instead of RPC)')

    args = parser.parse_args()

    # Check environment variables
    if 'SUPABASE_URL' not in os.environ:
        print(f"{Colors.RED}ERROR:{Colors.END} SUPABASE_URL environment variable not set")
        sys.exit(1)

    if 'SUPABASE_SERVICE_KEY' not in os.environ:
        print(f"{Colors.RED}ERROR:{Colors.END} SUPABASE_SERVICE_KEY environment variable not set")
        sys.exit(1)

    # Setup headers
    headers = {
        "apikey": os.environ['SUPABASE_SERVICE_KEY'],
        "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_KEY']}"
    }

    # Get date range
    dates = get_date_range(args.start, args.end, args.days)

    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}CMG Prediction System - Data Integrity Check{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"Date Range: {dates[0]} to {dates[-1]} ({len(dates)} days)")
    print(f"{'='*60}")

    # Run checks - try RPC first (fast), fall back to legacy (slow) if needed
    import time
    start_time = time.time()

    if args.legacy:
        print(f"\n{Colors.YELLOW}Using legacy mode (504 API calls)...{Colors.END}")
        ml_results = check_ml_predictions(headers, dates)
        prog_results = check_cmg_programado(headers, dates)
        online_results = check_cmg_online(headers, dates)
    else:
        # Try RPC first
        rpc_result = check_integrity_via_rpc(headers, dates)

        if rpc_result is not None:
            ml_results, prog_results, online_results = rpc_result
        else:
            # Fallback to legacy mode
            print(f"\n{Colors.YELLOW}Using legacy mode (504 API calls)...{Colors.END}")
            ml_results = check_ml_predictions(headers, dates)
            prog_results = check_cmg_programado(headers, dates)
            online_results = check_cmg_online(headers, dates)

    elapsed_time = time.time() - start_time
    print(f"\n{Colors.BLUE}Query time: {elapsed_time:.2f} seconds{Colors.END}")

    # Generate report
    report = generate_report(ml_results, prog_results, online_results, dates)

    # Save or display
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"\n{Colors.GREEN}✅ Report saved to: {args.output}{Colors.END}")
    else:
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(report)

    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.GREEN}✅ Data integrity check complete!{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")

if __name__ == "__main__":
    main()
