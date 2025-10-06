# GitHub Actions Workflows - Updated Architecture
**Date:** October 5, 2025
**Status:** ✅ Separated and Simplified

## 🎯 New Workflow Structure

We now have **two independent, focused workflows**:

### 1. CMG Online Hourly Update
**File**: `.github/workflows/cmg_online_hourly.yml`
**Schedule**: Every hour at :05 (5, 6, 7, ...)
**Purpose**: Fetch and store CMG Online (actual) data
**Responsibilities**:
- ✅ Fetch CMG Online from SIP API
- ✅ Store to historical Gist
- ✅ Verify data integrity
- ✅ Commit and push

**Duration**: ~2-10 minutes (depending on API response)

### 2. CMG Programado Hourly Update
**File**: `.github/workflows/cmg_programado_hourly.yml`
**Schedule**: Every hour at :35 (35, 36, 37, ...)
**Purpose**: Download and process CMG Programado (forecast) data
**Responsibilities**:
- ✅ Download CSV from Coordinador portal
- ✅ Extract PMontt220 values
- ✅ Update both cache files
- ✅ Update Gist
- ✅ Commit and push

**Duration**: ~3-5 minutes

---

## 🔄 What Changed

### Before (Problematic)
- **`unified_cmg_update.yml`**: Mixed responsibilities
  - Fetched CMG Online ✅
  - ALSO synced CMG Programado ⚠️ (confusion!)
  - Unclear separation of concerns

- **`cmg_programado_hourly.yml`**: Good, but...
  - Independent, but conflicts with unified workflow
  - Timing overlap possible

### After (Clean)
- **`cmg_online_hourly.yml`**: ONE job, ONE purpose
  - ONLY handles CMG Online
  - Clear, focused, easy to debug

- **`cmg_programado_hourly.yml`**: Already good
  - No changes needed
  - Already independent and focused

---

## ⏰ Execution Schedule

```
:00  ─────────────────────────────────────
:05  ──[CMG Online Update]────────────────  ← Fetch from SIP API
:10  ─────────────────────────────────────
:15  ─────────────────────────────────────
:20  ─────────────────────────────────────
:25  ─────────────────────────────────────
:30  ─────────────────────────────────────
:35  ──[CMG Programado Update]────────────  ← Download CSV
:40  ─────────────────────────────────────
:45  ─────────────────────────────────────
:50  ─────────────────────────────────────
:55  ─────────────────────────────────────
:00  ───[Next Hour]───────────────────────
```

**30-minute separation** ensures no conflicts or race conditions.

---

## 📊 Workflow Details

### CMG Online Hourly (`cmg_online_hourly.yml`)

```yaml
Trigger:
  - schedule: '5 * * * *'  (hourly at :05)
  - workflow_dispatch        (manual trigger)
  - push to: cmg_online_hourly.yml, smart_cmg_online_update.py, store_historical.py

Concurrency:
  group: cmg-online-update
  cancel-in-progress: false  (waits for previous run)

Steps:
  1. Checkout code
  2. Setup Python 3.9
  3. Install: requests, pytz, numpy
  4. Fetch CMG Online (smart_cmg_online_update.py)
     - Fetches last 3 days
     - Smart caching (only missing hours)
     - Saves to: data/cache/cmg_historical_latest.json
  5. Store to Gist (store_historical.py)
     - Merges with existing Gist data
     - Updates: 8d7864eb26acf6e780d3c0f7fed69365
     - Saves: data/cache/cmg_online_historical.json
  6. Verify data integrity
     - Check record count
     - Verify last 3 days completeness
     - Show metadata
  7. Commit and push (if changes)
     - Retries up to 3 times
     - Handles merge conflicts
  8. Summary
     - Show cache metadata
     - Link to validation page

Secrets Required:
  - CMG_GIST_TOKEN (GitHub PAT with gist scope)
```

### CMG Programado Hourly (`cmg_programado_hourly.yml`)

```yaml
Trigger:
  - schedule: '35 * * * *'  (hourly at :35)
  - workflow_dispatch        (manual trigger)

Concurrency:
  (none - independent workflow)

Steps:
  1. Checkout code
  2. Setup Python 3.9
  3. Install: playwright, requests, pytz
  4. Install Chromium (for CSV download)
  5. Run CMG Programado Pipeline (cmg_programado_pipeline.py)
     a. Download CSV (download_cmg_programado_simple.py)
        - Uses Playwright headless
        - Saves to: downloads/cmg_programado_*.csv
     b. Process PMontt220 (process_pmontt_programado.py)
        - Extracts PMontt220 values
        - Saves to:
          * data/cache/pmontt_programado.json (reference)
          * data/cache/cmg_programmed_latest.json (API)
        - Updates Gist: d68bb21360b1ac549c32a80195f99b09
  6. Verify data
     - Check forecast hours
     - Show dates available
  7. Commit and push (if changes)
  8. Summary
     - Show cache status
     - Link to index page

Secrets Required:
  - CMG_GIST_TOKEN (GitHub PAT with gist scope)

Environment:
  - GITHUB_ACTIONS=true (for headless mode)
```

---

## 🔧 Concurrency Control

### CMG Online
- **Group**: `cmg-online-update`
- **Cancel**: `false` (waits for previous run)
- **Why**: Prevents data conflicts when merging with Gist

### CMG Programado
- **Group**: None (runs independently)
- **Why**: Each run is independent, no merging needed

---

## 🚨 Error Handling

Both workflows include:

1. **Timeout Protection**
   - CMG Online: 50 min for fetch, 5 min for store
   - CMG Programado: 10 min total

2. **Git Push Retry**
   - Up to 3 attempts
   - Handles merge conflicts automatically
   - Takes latest data on conflict

3. **Graceful Degradation**
   - If Gist update fails, data still saved locally
   - Workflow doesn't fail completely

4. **Status Reporting**
   - Always shows summary (even on failure)
   - Links to visualization pages

---

## 📁 Data Flow Summary

### CMG Online
```
SIP API
  ↓ (smart_cmg_online_update.py)
data/cache/cmg_historical_latest.json
  ↓ (store_historical.py)
├─→ Gist: 8d7864eb26acf6e780d3c0f7fed69365
└─→ data/cache/cmg_online_historical.json
  ↓ (cache_manager_readonly.py)
API: /api/cache
  ↓ (JavaScript fetch)
Frontend: validation.html
```

### CMG Programado
```
Coordinador Portal
  ↓ (download_cmg_programado_simple.py)
downloads/cmg_programado_*.csv
  ↓ (process_pmontt_programado.py)
├─→ data/cache/pmontt_programado.json (reference)
├─→ data/cache/cmg_programmed_latest.json (API)
└─→ Gist: d68bb21360b1ac549c32a80195f99b09
  ↓ (cache_manager_readonly.py)
API: /api/cache
  ↓ (JavaScript fetch)
Frontend: index.html
```

---

## ✅ Benefits of New Structure

1. **Single Responsibility**
   - Each workflow has ONE clear purpose
   - Easier to debug and maintain

2. **Independent Execution**
   - CMG Online failure doesn't affect CMG Programado
   - Can disable one without affecting the other

3. **Clear Separation of Concerns**
   - No confusion about which workflow does what
   - Code is easier to understand

4. **Better Monitoring**
   - Can monitor each workflow independently
   - Failures are easier to trace

5. **Simpler Debugging**
   - Less code per workflow
   - Fewer steps to check

---

## 🔄 Migration Steps

### What to Do

1. **Enable New Workflow**
   - ✅ Created: `cmg_online_hourly.yml`
   - ⏭️ Commit and push to main

2. **Disable Old Workflow**
   - ⏭️ Rename: `unified_cmg_update.yml` → `unified_cmg_update.yml.disabled`
   - OR delete it (keep in git history)

3. **Verify Operation**
   - ⏭️ Manually trigger `cmg_online_hourly.yml`
   - ⏭️ Check it completes successfully
   - ⏭️ Verify data updates

4. **Monitor for 24 Hours**
   - ⏭️ Watch both workflows run hourly
   - ⏭️ Confirm no conflicts
   - ⏭️ Verify data completeness

---

## 🎯 Next Actions

Based on the pipeline analysis:

### Immediate (Do Now)
1. ✅ Created separate CMG Online workflow
2. ⏭️ Commit and push the new workflow
3. ⏭️ Disable/rename old unified workflow
4. ⏭️ Manually trigger to test
5. ⏭️ Check GitHub Actions logs for Oct 3 failures

### Soon (Next 24 Hours)
6. ⏭️ Backfill missing Oct 3-5 data
   - Run `smart_cmg_online_update.py` locally
   - Or wait for workflows to catch up
7. ⏭️ Verify both workflows run successfully
8. ⏭️ Monitor data completeness

### Later (This Week)
9. ⏭️ Add workflow failure notifications
10. ⏭️ Implement data freshness monitoring
11. ⏭️ Set up 5PM forecast validation

---

## 📚 References

### Workflows
- **CMG Online**: `.github/workflows/cmg_online_hourly.yml` (NEW ✨)
- **CMG Programado**: `.github/workflows/cmg_programado_hourly.yml` (existing)
- **Old Unified**: `.github/workflows/unified_cmg_update.yml` (to be disabled)

### Scripts
- **CMG Online Fetch**: `scripts/smart_cmg_online_update.py`
- **CMG Online Store**: `scripts/store_historical.py`
- **CMG Programado Pipeline**: `scripts/cmg_programado_pipeline.py`
- **CMG Programado Download**: `scripts/download_cmg_programado_simple.py`
- **CMG Programado Process**: `scripts/process_pmontt_programado.py`

### Documentation
- **Full Analysis**: `CMG_PIPELINE_ANALYSIS.md`
- **This File**: `WORKFLOWS_UPDATED.md`
- **Data Flow**: `DATA_FLOW_VERIFIED.md`
- **Architecture**: `ARCHITECTURE_ANALYSIS.md`

---

## 🎉 Summary

**Before**: Confusing mixed workflows
**After**: Clean, independent, focused workflows

Each workflow now has ONE job:
- ✅ CMG Online = Fetch actual data from SIP API
- ✅ CMG Programado = Download forecast from portal

**Result**: Easier to maintain, debug, and monitor! 🚀
