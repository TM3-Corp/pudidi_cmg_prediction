# CMG Data Pipeline - Complete Analysis
**Date:** October 5, 2025
**Analysis by:** Claude Code

## 🔍 Executive Summary

### Critical Issues Found
1. **🔴 GitHub Actions workflows STOPPED running** - Last update Oct 3 at ~12:00 PM
2. **🟡 Workflows are NOT independent** - Mixed responsibilities causing confusion
3. **🟠 Oct 3-5 data is INCOMPLETE** - Missing 36+ hours of CMG Online data
4. **🟢 Pipeline logic is CORRECT** - Previous session's fix to `store_historical.py` works

---

## 📊 Current Data Status

### CMG Online (Historical/Actual)
- **Source**: SIP API v4 (`/costo-marginal-online/v4/findByDate`)
- **Nodes**: NVA_P.MONTT___220, PIDPID________110, DALCAHUE______110
- **Cache File**: `data/cache/cmg_historical_latest.json`
- **Last Update**: 2025-10-03 12:22 PM ⚠️
- **Total Records**: 2,380 records (32 days)
- **Date Range**: Sept 2 - Oct 3

#### Data Completeness
| Date | Coverage | Status |
|------|----------|--------|
| Oct 1 | 24/24 hours ✅ | Complete |
| Oct 2 | 24/24 hours ✅ | Complete |
| Oct 3 | 12/24 hours ❌ | Incomplete (hours 0-11 only) |
| Oct 4 | 0/24 hours ❌ | Missing (workflow not running) |
| Oct 5 | 0/24 hours ❌ | Missing (workflow not running) |

**Missing**: Hours 12-23 for Oct 3, ALL hours for Oct 4-5

### CMG Programado (Forecast)
- **Source**: Downloaded CSV from Coordinador portal
- **Node**: PMontt220 (Puerto Montt)
- **Cache File**: `data/cache/cmg_programmed_latest.json` + `pmontt_programado.json`
- **Last Update**: 2025-10-03 11:47 AM ⚠️
- **Total Records**: 72 records (3 days)
- **Date Range**: Oct 3 - Oct 5

#### Data Completeness
| Date | Coverage | Status |
|------|----------|--------|
| Oct 3 | 24/24 hours ✅ | Complete |
| Oct 4 | 24/24 hours ✅ | Complete |
| Oct 5 | 24/24 hours ⚠️ | Complete but has 0.0 values for hours 9-18 |

---

## 🏗️ Pipeline Architecture

### CMG Online Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ 1. FETCH (smart_cmg_online_update.py)                       │
│    • Fetches from SIP API v4                                │
│    • Targets last 3 days                                    │
│    • Smart caching - only fetches missing hours             │
│    • Saves to: data/cache/cmg_historical_latest.json       │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. STORE HISTORICAL (store_historical.py)                   │
│    • Loads cmg_historical_latest.json                       │
│    • Fetches existing data from Gist                        │
│    • Merges (NEW data overwrites OLD - fixed!)             │
│    • Saves to Gist: 8d7864eb26acf6e780d3c0f7fed69365       │
│    • Also saves: data/cache/cmg_online_historical.json     │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. API SERVES DATA (cache_manager_readonly.py)             │
│    • Reads cmg_historical_latest.json                       │
│    • Filters last 24 hours                                  │
│    • Serves via /api/cache endpoint                         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. VISUALIZATION (index.html, validation.html)             │
│    • Fetches from /api/cache                                │
│    • Displays charts and tables                             │
└─────────────────────────────────────────────────────────────┘
```

**Workflow**: `unified_cmg_update.yml` - Runs hourly at :05

### CMG Programado Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ 1. DOWNLOAD (download_cmg_programado_simple.py)            │
│    • Uses Playwright to download CSV                        │
│    • Saves to: downloads/cmg_programado_YYYYMMDD_HHMM.csv │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. PROCESS (process_pmontt_programado.py)                  │
│    • Reads latest CSV                                       │
│    • Extracts PMontt220 values                             │
│    • Saves to TWO files:                                    │
│      - data/cache/pmontt_programado.json (reference)       │
│      - data/cache/cmg_programmed_latest.json (for API)     │
│    • Updates Gist: d68bb21360b1ac549c32a80195f99b09        │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. API SERVES DATA (cache_manager_readonly.py)             │
│    • Reads cmg_programmed_latest.json                       │
│    • Filters future hours only                              │
│    • Serves via /api/cache endpoint                         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. VISUALIZATION (index.html)                               │
│    • Fetches from /api/cache                                │
│    • Displays forecast data                                 │
└─────────────────────────────────────────────────────────────┘
```

**Workflow**: `cmg_programado_hourly.yml` - Runs hourly at :35

---

## ⚙️ Current GitHub Actions Workflows

### 1. `unified_cmg_update.yml` (Runs at :05 every hour)
**Purpose**: Update CMG Online data
**Steps**:
1. ✅ Fetch CMG Online (`smart_cmg_online_update.py`)
2. ⚠️ Sync CMG Programado historical (for reference only)
3. ✅ Store CMG Online to Gist (`store_historical.py`)
4. ✅ Verify data integrity
5. ✅ Commit and push

**Issues**:
- ❌ Stopped running after Oct 3 12:22 PM
- ⚠️ Step 2 syncs CMG Programado but notes say "Historical Only" - creates confusion
- ⚠️ Mixed responsibilities (handles both CMG Online AND CMG Programado sync)

### 2. `cmg_programado_hourly.yml` (Runs at :35 every hour)
**Purpose**: Update CMG Programado forecast
**Steps**:
1. ✅ Run CMG Programado Pipeline (`cmg_programado_pipeline.py`)
   - Downloads CSV
   - Processes PMontt220
   - Updates both cache files
   - Updates Gist
2. ✅ Verify data
3. ✅ Commit and push

**Issues**:
- ❌ Stopped running after Oct 3 11:47 AM
- ✅ This workflow is correctly isolated

### 3. Other workflows
- `cmg_csv_pipeline.yml` - Manual CSV processing (not active)
- `daily_optimization.yml` - Daily optimization (separate concern)
- `daily_performance.yml` - Daily performance (separate concern)
- `manual_update.yml` - Manual trigger (backup)
- `setup_gists.yml` - One-time setup
- `test_performance_system.yml` - Testing only

---

## 🐛 Issues Identified

### Issue #1: Workflows Not Running ⚠️ CRITICAL
**Symptom**: No data updates since Oct 3 ~12:00 PM
**Impact**: Missing 36+ hours of CMG Online data, potentially stale CMG Programado
**Root Cause**: Unknown - need to check GitHub Actions logs
**Possible Causes**:
- Workflow disabled
- Repository permissions changed
- Secrets expired/revoked (CMG_GIST_TOKEN)
- Git push conflicts causing workflow to fail
- Workflow concurrency lock

### Issue #2: Mixed Workflow Responsibilities
**Symptom**: `unified_cmg_update.yml` handles CMG Online BUT also syncs CMG Programado
**Impact**: Confusing architecture, harder to debug
**Root Cause**: Historical evolution - workflows were combined
**Solution**: Separate workflows completely

### Issue #3: store_historical.py Merging Bug (FIXED ✅)
**Symptom**: Previous session identified data corruption
**Impact**: Historical data was being overwritten with old Gist data
**Status**: FIXED in lines 143-145
**Verification**: Logic now correctly uses NEW data, preserves only programado from old

### Issue #4: Oct 5 CMG Programado has zeros
**Symptom**: Hours 9-18 on Oct 5 show 0.0 values
**Impact**: May cause incorrect forecasts
**Root Cause**: Could be real forecast data OR data quality issue from source CSV
**Action**: Monitor if this persists in next update

---

## ✅ What's Working Correctly

1. **Fetching Logic** ✅
   - `smart_cmg_online_update.py` correctly fetches from SIP API
   - Smart caching works - only fetches missing data
   - Proper error handling and retry logic

2. **Storage Logic** ✅
   - `store_historical.py` correctly merges data (after previous fix)
   - Rolling 30-day window works correctly
   - Gist updates work when workflow runs

3. **CMG Programado Download** ✅
   - Playwright automation works
   - CSV parsing extracts PMontt220 correctly
   - Dual cache files (reference + API) is good design

4. **API Layer** ✅
   - `cache_manager_readonly.py` correctly reads cache
   - Time filtering (last 24h historical, future only for programado) works
   - Vercel deployment serves data correctly

5. **Visualization** ✅
   - Frontend correctly displays data from API
   - Charts and tables work when data is available

---

## 🎯 Recommendations

### Immediate Actions (Priority 1)

1. **Check GitHub Actions Status**
   - Review workflow runs in GitHub
   - Check for errors in last runs (Oct 3)
   - Verify secrets are still valid (CMG_GIST_TOKEN)
   - Check repository permissions

2. **Manually Trigger Workflows**
   - Use workflow_dispatch to trigger both workflows
   - Verify they complete successfully
   - Check if data gets updated

3. **Backfill Missing Data**
   - Run `smart_cmg_online_update.py` locally for Oct 3-5
   - This will fetch missing hours 12-23 for Oct 3 and all of Oct 4-5
   - Push updated cache to repository

### Medium-term Improvements (Priority 2)

4. **Separate Workflows Completely**
   - Create `cmg_online_hourly.yml` (dedicated to CMG Online only)
   - Keep `cmg_programado_hourly.yml` as is
   - Remove CMG Programado sync from unified workflow
   - Archive/rename `unified_cmg_update.yml`

5. **Add Monitoring**
   - Add workflow failure notifications
   - Monitor data freshness in API
   - Alert if no updates in > 3 hours

6. **Improve Error Handling**
   - Add retry logic if git push fails
   - Better handling of API rate limits
   - Graceful degradation if Gist update fails

### Long-term Enhancements (Priority 3)

7. **Data Quality Checks**
   - Validate no duplicate records
   - Check for suspicious values (like Oct 5 zeros)
   - Verify hour completeness after each run

8. **5PM Forecast Validation** (from previous session)
   - Implement 5PM snapshot capture
   - Track forecast accuracy over time
   - Compare t+1, t+6, t+24 forecasts vs actuals

---

## 📁 Key Files Reference

### Scripts
- `scripts/smart_cmg_online_update.py` - CMG Online fetcher
- `scripts/store_historical.py` - Historical data storage to Gist
- `scripts/download_cmg_programado_simple.py` - CMG Programado downloader
- `scripts/process_pmontt_programado.py` - PMontt220 processor
- `scripts/cmg_programado_pipeline.py` - Programado orchestrator

### Data Files
- `data/cache/cmg_historical_latest.json` - CMG Online cache (2,380 records)
- `data/cache/cmg_online_historical.json` - Historical archive (Gist mirror)
- `data/cache/cmg_programmed_latest.json` - CMG Programado API cache (72 records)
- `data/cache/pmontt_programado.json` - CMG Programado reference (72 records)
- `data/cache/metadata.json` - Update metadata

### API
- `api/utils/cache_manager_readonly.py` - Cache reader for API
- `api/index.py` - Main API endpoint (uses Chiloé node for ML)
- `api/cache.py` - Dedicated cache endpoint

### Workflows
- `.github/workflows/unified_cmg_update.yml` - CMG Online (at :05)
- `.github/workflows/cmg_programado_hourly.yml` - CMG Programado (at :35)

### Gists
- CMG Online: `8d7864eb26acf6e780d3c0f7fed69365`
- CMG Programado: `d68bb21360b1ac549c32a80195f99b09`
- Partner's source: `a63a3a10479bafcc29e10aaca627bc73`

---

## 🔄 Next Steps for This Session

Based on your request to review and fix the pipeline:

1. ✅ **Review Complete** - Full pipeline analyzed
2. ⏭️ **Check GitHub Actions** - Investigate why workflows stopped
3. ⏭️ **Create Separate Workflows** - Split CMG Online and CMG Programado
4. ⏭️ **Test Data Flow** - Verify end-to-end after fixes
5. ⏭️ **Backfill Data** - Recover missing Oct 3-5 data

Ready to proceed? Let me know which action you'd like to tackle first!
