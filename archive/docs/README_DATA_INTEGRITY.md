# Data Integrity Checker - Quick Reference

## Ground Truth Values

| Data Source | Expected Per Hour | Expected Per Day | Notes |
|-------------|------------------|------------------|-------|
| **ML Predictions** | 24 predictions | 576 records | 24 forecast hours × 24 predictions |
| **CMG Programado** | ~72 predictions | Variable forecasts | Rolling 3-day forecast |
| **CMG Online** | 3 records (3 nodes) | 72 records | Historical data, 24 hours × 3 nodes |

## Quick Commands

```bash
# Setup (required once per session)
export SUPABASE_URL="https://btyfbrclgmphcjgrvcgd.supabase.co"
export SUPABASE_SERVICE_KEY="your_service_role_key"

# Check last 7 days (default)
python3 scripts/data_integrity_check.py

# Check yesterday and today
python3 scripts/data_integrity_check.py --days 2

# Check specific date range
python3 scripts/data_integrity_check.py --start 2025-11-14 --end 2025-11-21

# Save detailed report
python3 scripts/data_integrity_check.py --output report.md
```

## Interpreting Results

### Status Indicators
- ✅ **Green:** Data complete
- ⚠ **Yellow:** Partial (within acceptable range)
- ❌ **Red:** Missing data

### Expected Completeness Thresholds

**ML Predictions:**
- ✅ Complete: 576 records per day
- ⚠ Warning: 400-575 records
- ❌ Critical: < 400 records

**CMG Programado:**
- ✅ Complete: ≥22 forecast hours (allows for known hours 21-22 issue)
- ⚠ Warning: 18-21 hours
- ❌ Critical: < 18 hours

**CMG Online:**
- ✅ Complete: 72 records per day
- ⚠ Warning: 60-71 records
- ❌ Critical: < 60 records

## Known Issues

### Hours 21-22 Missing in CMG Programado
- **Pattern:** Consistently missing hours 21-22 (9-10 PM Santiago)
- **Cause:** GitHub Actions workflow issue at UTC 00:05 and 01:05
- **Severity:** ⚠ Warning (system still functional)
- **Fix:** Under investigation - see `data_audit.md`

### Current Day Showing Incomplete
- **Pattern:** Today's data shows missing hours
- **Cause:** Future hours haven't occurred yet
- **Severity:** ✅ Normal (expected behavior)
- **Fix:** Not an issue - wait for day to complete

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `SUPABASE_URL not set` | Environment variable missing | Run export commands above |
| `HTTP 401` | Invalid credentials | Use service_role key, not anon key |
| `All zeros` | Wrong date range | Check dates are not in future |
| `Very slow` | Checking many days | Normal - ~3 seconds per day |

## When to Run

- **Daily:** Check yesterday's data (`--days 2`)
- **Weekly:** Validate last week (`--days 7`)
- **Monthly:** Audit last 30 days (`--days 30 --output monthly_report.md`)
- **After deployment:** Verify data pipeline still working

## Full Documentation

See `docs/DATA_INTEGRITY_GUIDE.md` for:
- Detailed usage instructions
- Issue interpretation guide
- Automated reporting setup
- CI/CD integration examples
- System health monitoring tips

## Example Output

```
CMG Prediction System - Data Integrity Check
============================================================
Date Range: 2025-11-20 to 2025-11-22 (3 days)

Checking ML Predictions...
  2025-11-20: ✅  576/576 records
  2025-11-21: ❌  408/576 records
  2025-11-22: ✅  576/576 records

Checking CMG Programado...
  2025-11-20: ⚠  22/24 forecast hours
  2025-11-21: ⚠  22/24 forecast hours
  2025-11-22: ✅ Complete (24/24)

Checking CMG Online...
  2025-11-20: ✅ 72/72 records
  2025-11-21: ✅ 72/72 records
  2025-11-22: ⚠ 45/72 records (in progress)

✅ Data integrity check complete!
```

---

**Script Location:** `scripts/data_integrity_check.py`
**Documentation:** `docs/DATA_INTEGRITY_GUIDE.md`
**Version:** 1.0
**Last Updated:** 2025-11-22
