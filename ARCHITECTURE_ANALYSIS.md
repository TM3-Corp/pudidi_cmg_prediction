# CMG Prediction System - Architecture Analysis & Fix Documentation

**Date:** October 2, 2025
**Status:** CRITICAL ISSUES IDENTIFIED - FIXES IMPLEMENTED

---

## Executive Summary

The CMG Programado data was being correctly downloaded (72 hours) but then **overwritten by competing workflows**, reducing it to only 28 future hours. This document details the complete analysis, root causes, and implemented fixes.

---

## System Architecture

### Purpose
Monitor and predict CMG (Costo Marginal) for Puerto Montt electricity market:
1. **CMG Online** - Historical real-time data from SIP API
2. **CMG Programado** - 72-hour forecast from Coordinador website

### Frontend
- URL: https://pudidicmgprediction.vercel.app/index.html
- Displays:
  - 📊 CMG Online historical data (last 24h coverage)
  - 🔮 CMG Programado forecast data (should be 72h)

---

## GitHub Actions Workflows

### Active Workflows (Before Fix)

| Workflow | Schedule | Function | Status |
|----------|----------|----------|--------|
| `cmg_programado_hourly.yml` | :35 every hour | Download CMG Programado via web scraping | ✅ Working correctly |
| `unified_cmg_update.yml` | :05 every hour | Fetch CMG Online + sync CMG Programado | ⚠️ Caused conflicts |
| `cmg_csv_pipeline.yml` | :15 every hour | Download CMG Online CSV + sync programado | ⚠️ LEGACY - Redundant |

### Workflow Details

#### 1. `cmg_programado_hourly.yml` (:35)
**Purpose:** Download and process CMG Programado forecast data

**Steps:**
1. Download CMG Programado CSV from Coordinador website (Playwright)
2. Extract PMontt220 node data (72 hours)
3. Save to local cache files
4. Update Gist with forecast data
5. Commit changes to repo

**Scripts Used:**
- `scripts/cmg_programado_pipeline.py` (orchestrator)
  - `scripts/download_cmg_programado_simple.py` (web scraper)
  - `scripts/process_pmontt_programado.py` (data processor)

**Data Files Created:**
- `data/cache/pmontt_programado.json` (72 hours) ✅
- `data/cache/cmg_programmed_latest.json` (72 hours) ✅
- Gist: `d68bb21360b1ac549c32a80195f99b09` ✅

---

#### 2. `unified_cmg_update.yml` (:05)
**Purpose:** Unified update for all CMG data

**Steps:**
1. Fetch CMG Online from SIP API → `smart_cmg_online_update.py`
2. Sync CMG Programado from partner Gist → `sync_from_partner_gist.py`
3. **❌ PROBLEM:** Update CMG Programado cache → `update_programmed_cache.py` (OVERWRITES!)
4. Update CMG Programado Gist → `update_cmg_programado_gist.py`
5. Store historical to Gist → `store_historical.py`
6. Commit changes

**Issue:** Step 3 filters out past hours, overwriting the 72-hour dataset with only ~28 future hours.

---

#### 3. `cmg_csv_pipeline.yml` (:15) - LEGACY
**Purpose:** Download CMG Online via CSV (old method)

**Steps:**
1. Download CMG Online CSV from Coordinador
2. Sync CMG Programado from partner Gist
3. **❌ PROBLEM:** Update CMG Programado cache (OVERWRITES AGAIN!)

**Issue:** Completely redundant with `unified_cmg_update.yml`. Does the same overwriting.

---

## Root Cause Analysis

### The Overwriting Timeline

```
Hour X:35 - cmg_programado_hourly.yml runs
├─ Downloads fresh CMG Programado (72 hours)
├─ Saves pmontt_programado.json ✅ (72 hours)
├─ Saves cmg_programmed_latest.json ✅ (72 hours)
└─ Updates Gist d68bb21360b1ac549c32a80195f99b09 ✅

Hour X+1:05 - unified_cmg_update.yml runs
├─ Fetches CMG Online ✅
├─ Syncs from partner Gist to cmg_programado_history.json
├─ ❌ Runs update_programmed_cache.py
│   └─ Reads cmg_programado_history.json
│   └─ FILTERS to only future hours (current_hour < hour)
│   └─ OVERWRITES cmg_programmed_latest.json (28 hours)
└─ Result: 72 hours → 28 hours ❌

Hour X+1:15 - cmg_csv_pipeline.yml runs
└─ ❌ Runs update_programmed_cache.py AGAIN (further damage)
```

### Evidence

**Before overwrite:**
```bash
pmontt_programado.json: 72 hours
  Dates: ['2025-09-20', '2025-09-21', '2025-09-22']

cmg_programmed_latest.json: 72 hours
  Timestamp: 2025-09-20T14:47:33.208312-03:00
```

**After overwrite:**
```bash
cmg_programmed_latest.json: 28 hours
  Timestamp: 2025-09-20T19:23:57.743435-03:00
  (Only future hours from current time)
```

### The Culprit Code

File: `scripts/update_programmed_cache.py:49`

```python
# Line 49 - Filters out all past hours
if date_str > current_date or (date_str == current_date and hour > current_hour):
    programmed_data.append({...})
```

This filter makes sense for a "future forecast only" view, but it **overwrites the complete dataset** that was just downloaded.

---

## Data Flow Diagrams

### CMG Online Flow (Working Correctly)

```
SIP API
  ↓
smart_cmg_online_update.py (API calls)
  ↓
data/cache/cmg_historical_latest.json
  ↓
store_historical.py
  ↓
Gist: 8d7864eb26acf6e780d3c0f7fed69365
  ↓
Frontend API: /api/cmg/current
  ↓
cache_manager_readonly.py reads cmg_historical_latest.json
  ↓
Display: "📊 Calidad de Datos Históricos"
```

### CMG Programado Flow (BROKEN → FIXED)

**Before Fix:**
```
Coordinador Website
  ↓
download_cmg_programado_simple.py (Playwright scraper)
  ↓
process_pmontt_programado.py
  ↓
├─ pmontt_programado.json (72h) ✅
├─ cmg_programmed_latest.json (72h) ✅
└─ Gist: d68bb21360b1ac549c32a80195f99b09 ✅
  ↓
[30 minutes later]
  ↓
update_programmed_cache.py ❌
  ↓
OVERWRITES cmg_programmed_latest.json (28h)
  ↓
Frontend shows incomplete data
```

**After Fix:**
```
Coordinador Website
  ↓
download_cmg_programado_simple.py (Playwright scraper)
  ↓
process_pmontt_programado.py
  ↓
├─ pmontt_programado.json (72h) ✅
├─ cmg_programmed_latest.json (72h) ✅
└─ Gist: d68bb21360b1ac549c32a80195f99b09 ✅
  ↓
[NO MORE OVERWRITING]
  ↓
Frontend API: /api/cmg/current
  ↓
cache_manager_readonly.py reads cmg_programmed_latest.json
  ↓
Display: "🔮 Datos Programados Disponibles" (FULL 72h)
```

---

## Gist Inventory

| Gist ID | Purpose | Owner | Updated By Script | Contains |
|---------|---------|-------|-------------------|----------|
| `d68bb21360b1ac549c32a80195f99b09` | CMG Programado Forecast | PVSH97 | process_pmontt_programado.py | cmg_programado_historical.json |
| `8d7864eb26acf6e780d3c0f7fed69365` | CMG Online Historical | PVSH97 | store_historical.py, cmg_online_pipeline.py | cmg_online_historical.json |
| `a63a3a10479bafcc29e10aaca627bc73` | Partner Gist (Reference) | Partner | READ ONLY | CMG data from partner |

---

## Cache Files Explained

### CMG Online Cache Files

| File | Purpose | Updated By | Used By |
|------|---------|------------|---------|
| `data/cache/cmg_historical_latest.json` | Latest CMG Online data from API | smart_cmg_online_update.py | API endpoint |
| `data/cache/cmg_online_historical.json` | CMG Online from CSV download | cmg_online_pipeline.py | Legacy (being phased out) |
| `data/cache/metadata.json` | Cache metadata | smart_cmg_online_update.py | API endpoint |

### CMG Programado Cache Files

| File | Purpose | Updated By | Used By |
|------|---------|------------|---------|
| `data/cache/pmontt_programado.json` | Raw forecast (72h) | process_pmontt_programado.py | Reference only |
| `data/cache/cmg_programmed_latest.json` | **API CACHE (72h)** | process_pmontt_programado.py | **API endpoint** |
| `data/cmg_programado_history.json` | Historical archive | sync_from_partner_gist.py | update_programmed_cache.py |

**KEY INSIGHT:** The API reads from `cmg_programmed_latest.json`, which was being overwritten!

---

## Solutions Implemented

### Fix #1: Disable `cmg_csv_pipeline.yml`
**Action:** Disable the entire workflow (it's redundant)

**Rationale:**
- 100% duplicate of `unified_cmg_update.yml` CMG Online functionality
- Also performs the problematic CMG Programado cache overwrite
- No unique value - can be safely removed

**Implementation:**
- Workflow disabled by adding condition that always evaluates to false
- Preserved for historical reference

---

### Fix #2: Remove CMG Programado Cache Update from `unified_cmg_update.yml`
**Action:** Remove Step 3 that runs `update_programmed_cache.py`

**Rationale:**
- `cmg_programado_hourly.yml` is the authoritative source for CMG Programado
- Syncing from partner Gist (`cmg_programado_history.json`) is fine for historical comparison
- But DON'T overwrite the fresh download cache (`cmg_programmed_latest.json`)

**Implementation:**
- Removed lines 77-85 (Update CMG Programado Cache step)
- Kept the sync from partner Gist (for historical analysis)
- Removed Step 4 (Update CMG Programado Gist) - now handled by cmg_programado_hourly.yml only

---

## New Clean Architecture

### Workflow Responsibilities (After Fix)

| Workflow | Schedule | Sole Responsibility | Status |
|----------|----------|---------------------|--------|
| `cmg_programado_hourly.yml` | :35 hourly | **CMG Programado ONLY** - Download, process, cache, Gist | ✅ Active |
| `unified_cmg_update.yml` | :05 hourly | **CMG Online ONLY** - Fetch API, cache, Gist + historical sync | ✅ Active (Fixed) |
| `cmg_csv_pipeline.yml` | :15 hourly | **DISABLED** - Legacy, redundant | ⛔ Disabled |

### Separation of Concerns

**CMG Programado Pipeline (cmg_programado_hourly.yml):**
- Downloads CMG Programado CSV from Coordinador
- Extracts PMontt220 forecast (72 hours)
- Updates `cmg_programmed_latest.json` (for API)
- Updates Gist `d68bb21360b1ac549c32a80195f99b09`
- **NO OTHER WORKFLOW TOUCHES THIS DATA**

**CMG Online Pipeline (unified_cmg_update.yml):**
- Fetches CMG Online from SIP API
- Updates `cmg_historical_latest.json` (for API)
- Updates Gist `8d7864eb26acf6e780d3c0f7fed69365`
- Syncs partner Gist for historical comparison only
- **DOES NOT MODIFY CMG PROGRAMADO CACHE**

---

## Key Scripts Reference

### CMG Programado Scripts

| Script | Purpose | Writes To |
|--------|---------|-----------|
| `cmg_programado_pipeline.py` | Orchestrator | - |
| `download_cmg_programado_simple.py` | Web scraper (Playwright) | downloads/cmg_programado_*.csv |
| `process_pmontt_programado.py` | Data processor | pmontt_programado.json, cmg_programmed_latest.json, Gist |

### CMG Online Scripts

| Script | Purpose | Writes To |
|--------|---------|-----------|
| `smart_cmg_online_update.py` | SIP API fetcher | cmg_historical_latest.json, metadata.json |
| `store_historical.py` | Gist updater | Gist 8d7864eb26acf6e780d3c0f7fed69365 |

### Sync & Helper Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `sync_from_partner_gist.py` | Sync from partner for historical comparison | ✅ Active (used by unified) |
| `update_programmed_cache.py` | Filter to future hours only | ⛔ REMOVED from workflows |
| `update_cmg_programado_gist.py` | Update programado Gist | ⛔ REMOVED (done by process_pmontt) |

---

## Testing & Verification

### How to Verify Fix is Working

1. **Check workflow runs:**
   ```bash
   # cmg_programado_hourly.yml should run at :35
   # unified_cmg_update.yml should run at :05
   # cmg_csv_pipeline.yml should NOT run (disabled)
   ```

2. **Check cache files after cmg_programado_hourly.yml runs:**
   ```bash
   cat data/cache/cmg_programmed_latest.json | jq '.data | length'
   # Should show ~72 hours (3 days * 24 hours)
   ```

3. **Check cache files after unified_cmg_update.yml runs:**
   ```bash
   cat data/cache/cmg_programmed_latest.json | jq '.data | length'
   # Should STILL show ~72 hours (NOT reduced to 28)
   ```

4. **Check frontend:**
   - Visit: https://pudidicmgprediction.vercel.app/index.html
   - Look for "🔮 Datos Programados Disponibles"
   - Should show ~72 hours of forecast data

---

## Future Improvements

### Recommended Enhancements

1. **Add data validation:**
   - Verify 72 hours downloaded before committing
   - Alert if data drops below expected threshold

2. **Consolidate Gists:**
   - Consider merging both Gists into a single unified Gist
   - Separate files: cmg_online.json, cmg_programado.json

3. **Add monitoring:**
   - Track workflow success/failure rates
   - Monitor data completeness over time
   - Alert on anomalies

4. **Optimize schedule:**
   - CMG Programado updates every 4-6 hours (hourly may be excessive)
   - CMG Online can stay hourly

5. **Clean up legacy code:**
   - Remove `cmg_csv_pipeline.yml` entirely (after verification period)
   - Archive unused scripts

---

## Troubleshooting Guide

### Issue: CMG Programado shows < 72 hours

**Check:**
1. Did `cmg_programado_hourly.yml` run successfully?
2. Is `update_programmed_cache.py` being called anywhere?
3. Check file timestamps to identify which workflow modified the cache last

**Fix:**
```bash
# Manually trigger cmg_programado_hourly.yml
gh workflow run cmg_programado_hourly.yml
```

### Issue: Workflow conflicts/race conditions

**Check:**
1. Are multiple workflows running at the same time?
2. Check concurrency settings in workflows

**Fix:**
- Stagger schedules (already done: :05, :15, :35)
- Add concurrency groups to prevent parallel runs

---

## Change Log

### 2025-10-02 - Critical Architecture Fix
- **Identified:** Data overwriting conflict between 3 workflows
- **Fixed:** Disabled `cmg_csv_pipeline.yml`
- **Fixed:** Removed CMG Programado cache update from `unified_cmg_update.yml`
- **Result:** CMG Programado data integrity restored (72 hours maintained)
- **Created:** This comprehensive documentation

---

## Contact & Maintenance

**System Owner:** PVSH97
**Documentation Maintained By:** Claude Code Analysis
**Last Updated:** October 2, 2025

**For Issues:**
- Check GitHub Actions logs
- Review this document for architecture understanding
- Verify cache file timestamps and contents

---

## Appendix: File Structure

```
pudidi_CMG_prediction_system/vercel_deploy/
├── .github/workflows/
│   ├── cmg_programado_hourly.yml          # ✅ CMG Programado pipeline
│   ├── unified_cmg_update.yml             # ✅ CMG Online pipeline (FIXED)
│   ├── cmg_csv_pipeline.yml               # ⛔ DISABLED
│   └── [other workflows...]
├── scripts/
│   ├── cmg_programado_pipeline.py         # CMG Programado orchestrator
│   ├── download_cmg_programado_simple.py  # Web scraper
│   ├── process_pmontt_programado.py       # Data processor
│   ├── smart_cmg_online_update.py         # CMG Online API fetcher
│   ├── sync_from_partner_gist.py          # Historical sync
│   ├── store_historical.py                # Gist updater (Online)
│   ├── update_programmed_cache.py         # ⚠️ Removed from workflows
│   └── [other scripts...]
├── data/
│   ├── cache/
│   │   ├── cmg_programmed_latest.json     # ⭐ API cache (72h)
│   │   ├── pmontt_programado.json         # Raw forecast
│   │   ├── cmg_historical_latest.json     # CMG Online cache
│   │   └── metadata.json
│   └── cmg_programado_history.json        # Historical archive
├── api/
│   ├── cmg/current.py                     # Main API endpoint
│   └── utils/cache_manager_readonly.py    # Cache reader
└── public/
    └── index.html                         # Frontend
```

---

**END OF DOCUMENT**
