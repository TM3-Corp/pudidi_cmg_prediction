#!/usr/bin/env python3
"""
Simple CMG Online Data Gap Analysis (no pandas required)
=========================================================
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Constants
DATA_DIR = Path(__file__).parent.parent / "data"
CMG_CACHE_FILE = DATA_DIR / "cache" / "cmg_historical_latest.json"


def parse_datetime(dt_str):
    """Parse datetime string"""
    # Try different formats
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except:
            continue
    raise ValueError(f"Could not parse datetime: {dt_str}")


def main():
    print("="*80)
    print("CMG ONLINE DATA GAP ANALYSIS")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load data
    print("Loading data...")
    with open(CMG_CACHE_FILE, 'r') as f:
        data = json.load(f)

    records = data.get('data', [])
    print(f"✓ Loaded {len(records)} records")
    print()

    # Group by node
    by_node = defaultdict(list)
    for record in records:
        node = record['node']
        dt = parse_datetime(record['datetime'])
        by_node[node].append({
            'datetime': dt,
            'cmg_usd': record['cmg_usd']
        })

    # Sort by datetime
    for node in by_node:
        by_node[node].sort(key=lambda x: x['datetime'])

    # Analyze each node
    print("="*80)
    print("GAP ANALYSIS BY NODE")
    print("="*80)

    all_gaps = []

    for node in sorted(by_node.keys()):
        records = by_node[node]
        print(f"\n{node}")
        print("-" * 60)

        min_dt = records[0]['datetime']
        max_dt = records[-1]['datetime']

        # Calculate expected hours
        total_hours = int((max_dt - min_dt).total_seconds() / 3600) + 1
        actual_hours = len(records)
        missing_hours = total_hours - actual_hours
        completeness = (actual_hours / total_hours * 100) if total_hours > 0 else 0

        print(f"  Date range: {min_dt.strftime('%Y-%m-%d %H:00')} to {max_dt.strftime('%Y-%m-%d %H:00')}")
        print(f"  Expected hours: {total_hours}")
        print(f"  Actual hours: {actual_hours}")
        print(f"  Missing hours: {missing_hours}")
        print(f"  Completeness: {completeness:.2f}%")

        # Find gaps
        if missing_hours > 0:
            gaps = []
            for i in range(len(records) - 1):
                current_dt = records[i]['datetime']
                next_dt = records[i + 1]['datetime']
                expected_next = current_dt + timedelta(hours=1)

                if next_dt != expected_next:
                    gap_hours = int((next_dt - expected_next).total_seconds() / 3600) + 1
                    gaps.append({
                        'start': expected_next,
                        'end': next_dt - timedelta(hours=1),
                        'hours': gap_hours
                    })

            print(f"\n  Found {len(gaps)} gap(s):")
            for gap in gaps:
                if gap['hours'] == 1:
                    print(f"    • {gap['start'].strftime('%Y-%m-%d %H:00')} (1 hour)")
                else:
                    print(f"    • {gap['start'].strftime('%Y-%m-%d %H:00')} to {gap['end'].strftime('%Y-%m-%d %H:00')} ({gap['hours']} hours)")

                all_gaps.append({
                    'node': node,
                    'start': gap['start'],
                    'end': gap['end'],
                    'hours': gap['hours']
                })
        else:
            print(f"\n  ✅ No gaps - complete time series!")

    # Recent data analysis
    print("\n" + "="*80)
    print("RECENT DATA ANALYSIS (Last 48 Hours)")
    print("="*80)

    now = datetime.now()
    cutoff_48h = now - timedelta(hours=48)
    cutoff_24h = now - timedelta(hours=24)

    for node in sorted(by_node.keys()):
        records = by_node[node]
        latest_dt = records[-1]['datetime']
        staleness_hours = (now - latest_dt).total_seconds() / 3600

        print(f"\n{node}:")
        print(f"  Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Latest data: {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Staleness: {staleness_hours:.1f} hours")

        if staleness_hours < 2:
            print("  ✅ Data is fresh (< 2 hours old)")
        elif staleness_hours < 6:
            print("  ⚠️  Data is slightly stale (2-6 hours old)")
        else:
            print("  ❌ Data is very stale (> 6 hours old)")

        # Count recent records
        recent_48h = [r for r in records if r['datetime'] >= cutoff_48h]
        recent_24h = [r for r in records if r['datetime'] >= cutoff_24h]

        print(f"  Last 48h: {len(recent_48h)}/48 hours ({len(recent_48h)/48*100:.1f}%)")
        print(f"  Last 24h: {len(recent_24h)}/24 hours ({len(recent_24h)/24*100:.1f}%)")

    # Daily completeness
    print("\n" + "="*80)
    print("DAILY COMPLETENESS (Last 14 Days)")
    print("="*80)

    for node in sorted(by_node.keys()):
        records = by_node[node]

        print(f"\n{node}:")
        print("-" * 60)

        # Group by date
        by_date = defaultdict(int)
        for record in records:
            date = record['datetime'].date()
            by_date[date] += 1

        # Get last 14 days
        latest_date = max(by_date.keys())
        last_14_days = [latest_date - timedelta(days=i) for i in range(14)]
        last_14_days.sort()

        incomplete_count = 0
        for date in last_14_days:
            count = by_date.get(date, 0)
            status = "✅" if count == 24 else "⚠️" if count > 0 else "❌"
            print(f"  {status} {date}: {count}/24 hours ({count/24*100:.0f}%)")
            if count < 24:
                incomplete_count += 1

        if incomplete_count == 0:
            print(f"\n  ✅ All 14 days complete!")
        else:
            print(f"\n  ⚠️  {incomplete_count} incomplete day(s)")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    if len(all_gaps) == 0:
        print("✅ NO GAPS FOUND - Data is complete!")
    else:
        total_gap_hours = sum(gap['hours'] for gap in all_gaps)
        print(f"⚠️  Found {len(all_gaps)} gap(s) totaling {total_gap_hours} hours")
        print(f"\nTop 10 largest gaps:")
        sorted_gaps = sorted(all_gaps, key=lambda x: x['hours'], reverse=True)[:10]
        for i, gap in enumerate(sorted_gaps, 1):
            print(f"  {i}. {gap['node']}: {gap['start'].strftime('%Y-%m-%d %H:00')} to {gap['end'].strftime('%Y-%m-%d %H:00')} ({gap['hours']} hours)")

    print()


if __name__ == '__main__':
    main()
