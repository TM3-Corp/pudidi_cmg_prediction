#!/usr/bin/env python3
"""
Test script to verify prediction metadata calculation logic
"""

from datetime import datetime, timedelta
import json

def test_prediction_metadata():
    """Test the metadata calculation logic"""
    print("=" * 60)
    print("TESTING PREDICTION METADATA LOGIC")
    print("=" * 60)

    # Simulate scenario: current time is 16:00, base data is from 14:00
    now = datetime(2025, 11, 16, 16, 0, 0)
    base_datetime = datetime(2025, 11, 16, 14, 0, 0)

    # Calculate staleness
    data_staleness_hours = (now - base_datetime).total_seconds() / 3600

    print(f"\nScenario:")
    print(f"  Current time (now): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Base data time:     {base_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Data staleness:     {data_staleness_hours:.1f} hours")
    print()

    # Generate sample forecasts
    forecasts = []
    for h in range(1, 25):
        target_time = base_datetime + timedelta(hours=h)
        real_time_offset = (target_time - now).total_seconds() / 3600
        is_valid_forecast = (target_time > now)

        forecasts.append({
            'horizon': h,
            'target_datetime': target_time.strftime('%Y-%m-%d %H:00:00'),
            'real_time_offset': round(real_time_offset, 1),
            'is_valid_forecast': is_valid_forecast,
            'predicted_cmg': 50.0  # Mock value
        })

    # Display results
    print("Sample Forecasts:")
    print(f"{'Horizon':<10} {'Target DateTime':<20} {'Offset (h)':<12} {'Valid?':<8} {'Status'}")
    print("-" * 70)

    for f in forecasts[:5] + [forecasts[11]] + [forecasts[23]]:  # Show t+1 to t+5, t+12, t+24
        status = ""
        if f['real_time_offset'] < 0:
            status = "❌ PAST"
        elif f['real_time_offset'] == 0:
            status = "⚠️  NOW"
        else:
            status = "✅ FUTURE"

        print(f"t+{f['horizon']:<8} {f['target_datetime']:<20} {f['real_time_offset']:<12.1f} {str(f['is_valid_forecast']):<8} {status}")

    # Summary
    valid_count = sum(1 for f in forecasts if f['is_valid_forecast'])
    print()
    print("=" * 70)
    print(f"Summary:")
    print(f"  Total forecasts:      {len(forecasts)}")
    print(f"  Valid future forecasts: {valid_count}")
    print(f"  Past/current forecasts: {len(forecasts) - valid_count}")
    print()

    # Expected behavior
    print("Expected Behavior:")
    print(f"  ✅ t+1 (15:00) should be PAST (offset: -1.0h)")
    print(f"  ✅ t+2 (16:00) should be NOW (offset: 0.0h)")
    print(f"  ✅ t+3 (17:00) should be FUTURE (offset: 1.0h)")
    print(f"  ✅ When staleness = 2h, expect {24-2} = 22 valid forecasts")
    print()

    # Verify
    assert forecasts[0]['real_time_offset'] == -1.0, "t+1 offset should be -1.0h"
    assert forecasts[0]['is_valid_forecast'] == False, "t+1 should NOT be valid"

    assert forecasts[1]['real_time_offset'] == 0.0, "t+2 offset should be 0.0h"
    assert forecasts[1]['is_valid_forecast'] == False, "t+2 should NOT be valid"

    assert forecasts[2]['real_time_offset'] == 1.0, "t+3 offset should be 1.0h"
    assert forecasts[2]['is_valid_forecast'] == True, "t+3 should be valid"

    assert valid_count == 22, f"Should have 22 valid forecasts, got {valid_count}"

    print("✅ ALL TESTS PASSED!")
    print("=" * 70)

    # Generate sample JSON output
    output = {
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'base_datetime': base_datetime.strftime('%Y-%m-%d %H:00:00'),
        'data_staleness_hours': round(data_staleness_hours, 1),
        'forecasts': forecasts
    }

    print("\nSample JSON Output Structure:")
    print(json.dumps(output, indent=2)[:500] + "...")
    print()

    return True

if __name__ == "__main__":
    test_prediction_metadata()
