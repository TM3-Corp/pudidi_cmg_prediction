# Data Integrity Check - Usage Guide

This guide explains how to use the data integrity checker to validate completeness of your CMG prediction system data.

## 🎯 Ground Truth Expectations

The data integrity checker validates against these **ground truth** values:

### 1. ML Predictions
- **Per Forecast:** 24 predictions (one for each target hour, t+1 to t+24)
- **Per Day:** 24 forecast hours × 24 predictions = **576 records**
- **Structure:** Each forecast made at hour X predicts all 24 hours of the next day

### 2. CMG Programado
- **Per Forecast:** Typically 72 predictions (rolling 3-day forecast)
- **Per Day:** Variable number of forecasts (ideally 24, one per hour)
- **Known Issue:** Hours 21-22 (9-10 PM Santiago) are consistently missing
- **Acceptable Threshold:** ≥22 forecast hours per day

### 3. CMG Online (Historical)
- **Per Hour:** 3 records (one per monitored node)
- **Per Day:** 24 hours × 3 nodes = **72 records**
- **Nodes Tracked:**
  - `NVA_P.MONTT___220` (Nueva Puerto Montt)
  - `DALCAHUE______110` (Dalcahue)
  - `PIDPID________110` (PIDPID)

---

## 📋 Quick Start

### Setup Environment

```bash
# Set Supabase credentials
export SUPABASE_URL="https://btyfbrclgmphcjgrvcgd.supabase.co"
export SUPABASE_SERVICE_KEY="your_service_role_key"

# Navigate to project directory
cd /path/to/pudidi_CMG_prediction_system/vercel_deploy
```

### Basic Usage

```bash
# Check last 7 days (default)
python3 scripts/data_integrity_check.py

# Check specific date range
python3 scripts/data_integrity_check.py --start 2025-11-14 --end 2025-11-21

# Check last 30 days
python3 scripts/data_integrity_check.py --days 30

# Save report to file
python3 scripts/data_integrity_check.py --output integrity_report.md
```

---

## 🔍 Understanding the Output

### Terminal Output

The script provides color-coded terminal output:

```
CMG Prediction System - Data Integrity Check
============================================================
Date Range: 2025-11-20 to 2025-11-22 (3 days)
============================================================

Checking ML Predictions...
  2025-11-20: ✅  576/576 records
  2025-11-21: ❌  408/576 records
  2025-11-22: ✅  576/576 records

Checking CMG Programado...
  2025-11-20: ⚠  22/24 forecast hours
  2025-11-21: ✅ Complete (24/24)
  2025-11-22: ❌ 15/24 forecast hours

Checking CMG Online...
  2025-11-20: ✅ 72/72 records
  2025-11-21: ✅ 72/72 records
  2025-11-22: ❌ 39/72 records
```

**Status Indicators:**
- ✅ **Green checkmark:** Data is complete
- ⚠ **Yellow warning:** Partial data (within acceptable threshold)
- ❌ **Red X:** Missing data beyond threshold

### Markdown Report

When using `--output`, a detailed markdown report is generated with:

1. **Daily Summary Tables:** Overall completeness by date
2. **Missing Hours:** Specific hours with zero data
3. **Incomplete Forecasts:** Forecasts with fewer predictions than expected
4. **Summary Statistics:** Overall data quality metrics

---

## 🚨 Common Issues and Interpretations

### Issue 1: Hours 21-22 Missing in CMG Programado

```
CMG Programado:
  2025-11-21: ⚠ 22/24 forecast hours

Missing Forecast Hours:
  2025-11-21: Hours 21, 22
```

**What it means:**
- This is a **known issue** with the workflow
- Hours 21-22 Santiago (9-10 PM) correspond to UTC 00:00-01:00
- The GitHub Actions cron job may be failing at these UTC hours

**Is it critical?**
- ⚠ **Warning level** - System still functional
- Most hours are covered (22/24)
- Consider acceptable if consistent

**How to fix:**
- Check GitHub Actions logs for UTC 00:05 and 01:05
- Add retry logic to the scraper workflow
- See `data_audit.md` for detailed analysis

### Issue 2: ML Predictions Missing Entire Hours

```
ML Predictions:
  2025-11-22: ❌ 288/576 records

Missing Forecast Hours:
  2025-11-22: Hours 14, 15, 16, 17, 18, 19, 20, 21, 22, 23
```

**What it means:**
- ML prediction workflow stopped running after hour 13
- Could indicate workflow crash, timeout, or resource limit

**Is it critical?**
- ❌ **Critical** - Half the daily forecasts missing
- Affects visualization and comparison features

**How to fix:**
- Check Railway ML backend logs for errors
- Verify ML model is running and accessible
- Check GitHub Actions workflow for ML predictions

### Issue 3: CMG Online Incomplete Hours (< 3 nodes)

```
CMG Online:
  2025-11-22 Hour 11: 2/3 nodes (NVA_P.MONTT___220, DALCAHUE______110)
```

**What it means:**
- One node's data is missing for that specific hour
- Missing node: `PIDPID________110` (in this example)

**Is it critical?**
- ⚠ **Warning level** - Partial historical data
- Other nodes still provide coverage

**How to fix:**
- Check scraper logs for that specific hour
- Verify all nodes are being queried
- May indicate temporary API unavailability

### Issue 4: Current Day Showing Incomplete

```
CMG Online:
  2025-11-22: ❌ 39/72 records

Missing Hours:
  2025-11-22: Hours 14, 15, 16, 17, 18, 19, 20, 21, 22, 23
```

**What it means:**
- It's currently 14:00 (2 PM) on Nov 22
- Hours 14-23 haven't happened yet

**Is it critical?**
- ✅ **Normal** - This is expected behavior
- Historical data is collected as the day progresses

**How to fix:**
- Not an issue - wait for the day to complete
- Re-run the check the next day to validate completeness

---

## 📊 Interpreting the Summary Section

The report ends with a summary:

```
Summary:
- ML Predictions: 2/3 days complete
- CMG Programado: 3/3 days complete (≥22 forecast hours)
- CMG Online: 2/3 days complete
```

### What "Complete" Means

**ML Predictions:**
- Complete = Exactly 576 records (24 hours × 24 predictions)

**CMG Programado:**
- Complete = ≥22 forecast hours (allows for known hours 21-22 issue)
- Strict complete = All 24 hours present

**CMG Online:**
- Complete = Exactly 72 records (24 hours × 3 nodes)

### Target Thresholds

For **healthy system operation**, aim for:

- **ML Predictions:** ≥95% days complete (27/30 days in a month)
- **CMG Programado:** ≥90% days complete with ≥22 hours (27/30 days)
- **CMG Online:** ≥98% days complete (29/30 days)

---

## 🔧 Troubleshooting

### Error: SUPABASE_URL environment variable not set

**Fix:**
```bash
export SUPABASE_URL="https://btyfbrclgmphcjgrvcgd.supabase.co"
export SUPABASE_SERVICE_KEY="your_service_role_key"
```

### Error: HTTP 401 (Unauthorized)

**Cause:** Invalid or missing service key

**Fix:**
- Verify `SUPABASE_SERVICE_KEY` is the **service_role** key (not anon key)
- Check Supabase dashboard > Settings > API for the correct key

### Script Runs Very Slowly

**Cause:** Checking many days with hourly granularity requires many API calls

**Expected Performance:**
- ~3 seconds per day (72 queries per day × 3 data sources)
- 7 days ≈ 21 seconds
- 30 days ≈ 90 seconds

**Tips:**
- Use `--days 7` for routine checks (faster)
- Use `--days 30` for monthly audits (slower but comprehensive)

### Report Shows All Zeros

**Cause:** Likely querying future dates or incorrect date format

**Fix:**
- Verify dates are in `YYYY-MM-DD` format
- Don't query dates in the future
- Use `--end $(date +%Y-%m-%d)` to ensure current date

---

## 🗓 Recommended Schedule

### Daily Quick Check
Run every morning to verify previous day's data:

```bash
# Check yesterday and today
python3 scripts/data_integrity_check.py --days 2
```

**Takes:** ~6 seconds
**Purpose:** Catch issues quickly

### Weekly Deep Check
Run every Monday to validate last 7 days:

```bash
# Generate weekly report
python3 scripts/data_integrity_check.py --days 7 \
  --output "reports/integrity_$(date +%Y%m%d).md"
```

**Takes:** ~21 seconds
**Purpose:** Comprehensive validation, track trends

### Monthly Audit
Run first day of month to validate previous month:

```bash
# Check last 30 days and save report
python3 scripts/data_integrity_check.py --days 30 \
  --output "reports/monthly_audit_$(date +%Y%m).md"
```

**Takes:** ~90 seconds
**Purpose:** Monthly reporting, identify systemic issues

---

## 📈 Using Results for System Health Monitoring

### Creating a Data Quality Dashboard

Track these metrics over time:

1. **ML Completeness Rate:** (Complete days / Total days) × 100
2. **Average Missing Hours per Day:** Total missing hours / Total days
3. **CMG Programado Forecast Coverage:** (Days with ≥22 hours / Total days) × 100
4. **CMG Online Uptime:** (Complete hours / Expected hours) × 100

### Setting Up Alerts

Create alerts when:

- ML Predictions < 400 records in a day (should be 576)
- CMG Programado < 20 forecast hours in a day (should be ≥22)
- CMG Online < 60 records in a day (should be 72)
- Any data source shows zero records for current day past 12:00 PM

### Identifying Workflow Issues

**Consistent missing hours = Workflow problem**

Example patterns:
- Hours 21-22 always missing → UTC midnight cron job issue
- Hours 14-23 missing → Afternoon workflow failures
- Random hours missing → Intermittent API failures

**Action:** Review GitHub Actions logs for those specific UTC hours

---

## 🛠 Advanced Usage

### Custom Date Ranges

```bash
# Check specific week
python3 scripts/data_integrity_check.py \
  --start 2025-11-01 \
  --end 2025-11-07

# Check specific month
python3 scripts/data_integrity_check.py \
  --start 2025-11-01 \
  --end 2025-11-30
```

### Automated Reporting

Add to crontab for daily reports:

```bash
# Run at 6 AM every day
0 6 * * * cd /path/to/vercel_deploy && \
  export SUPABASE_URL="..." && \
  export SUPABASE_SERVICE_KEY="..." && \
  python3 scripts/data_integrity_check.py --days 1 \
  --output "reports/daily_$(date +\%Y\%m\%d).md"
```

### Integration with CI/CD

Add to GitHub Actions workflow:

```yaml
- name: Data Integrity Check
  env:
    SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
    SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
  run: |
    python3 scripts/data_integrity_check.py --days 1
```

---

## 📞 Support

### When to Use This Tool

✅ **Good use cases:**
- Daily data validation
- Debugging visualization issues
- Verifying workflow deployments
- Monthly reporting
- Troubleshooting missing data

❌ **Not designed for:**
- Real-time monitoring (use alerting instead)
- Data content validation (checks quantity, not quality)
- Performance benchmarking

### Related Documentation

- `data_audit.md` - Deep dive into timezone handling and hour 21-22 issue
- `TIMEZONE_ANALYSIS_REPORT.md` - Comprehensive timezone analysis
- GitHub Actions workflows - Check `.github/workflows/` for automation

### Getting Help

If data integrity checks consistently fail:

1. **Review workflow logs:** Check GitHub Actions for errors
2. **Check API status:** Verify Supabase and Railway are operational
3. **Examine recent changes:** Review recent code deployments
4. **Run deep analysis:** Use `data_audit.md` methodology for investigation

---

**Last Updated:** 2025-11-22
**Script Version:** 1.0
**Author:** Claude AI Assistant
