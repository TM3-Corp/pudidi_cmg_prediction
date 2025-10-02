# CMG Prediction System - Workflow Guide

**Clean Architecture - October 2, 2025**

---

## Quick Reference

### Active Workflows

| Workflow | Schedule | Purpose | Owner Of |
|----------|----------|---------|----------|
| **cmg_programado_hourly.yml** | `:35` every hour | CMG Programado forecast | `cmg_programmed_latest.json` |
| **unified_cmg_update.yml** | `:05` every hour | CMG Online historical | `cmg_historical_latest.json` |
| ~~cmg_csv_pipeline.yml~~ | ~~:15~~ | **DISABLED** | - |

---

## Data Ownership (Single Source of Truth)

### CMG Programado Forecast (72 hours)
**Owner:** `cmg_programado_hourly.yml`

```
Download → Process → Cache → Gist
```

**Files it owns:**
- ✅ `data/cache/cmg_programmed_latest.json` (API cache)
- ✅ `data/cache/pmontt_programado.json` (raw data)
- ✅ Gist: `d68bb21360b1ac549c32a80195f99b09`

**No other workflow modifies these files.**

---

### CMG Online Historical (Last 7 days)
**Owner:** `unified_cmg_update.yml`

```
Fetch API → Cache → Gist
```

**Files it owns:**
- ✅ `data/cache/cmg_historical_latest.json` (API cache)
- ✅ `data/cache/metadata.json`
- ✅ Gist: `8d7864eb26acf6e780d3c0f7fed69365`

**No other workflow modifies these files.**

---

## Workflow Details

### 1. CMG Programado Hourly (`:35`)

**What it does:**
1. Downloads CMG Programado CSV from Coordinador website (web scraping)
2. Extracts PMontt220 node forecast (72 hours)
3. Saves to local cache
4. Updates Gist with complete forecast
5. Commits to repo

**Scripts:**
- `scripts/cmg_programado_pipeline.py`
  - `scripts/download_cmg_programado_simple.py`
  - `scripts/process_pmontt_programado.py`

**Guaranteed output:** 72 hours of forecast data

---

### 2. Unified CMG Update (`:05`)

**What it does:**
1. Fetches CMG Online from SIP API
2. Updates CMG Online cache and Gist
3. Syncs CMG Programado from partner Gist (for historical comparison only)
4. Verifies data integrity
5. Commits to repo

**Scripts:**
- `scripts/smart_cmg_online_update.py`
- `scripts/sync_from_partner_gist.py`
- `scripts/store_historical.py`

**Important:** Does NOT modify CMG Programado API cache!

---

## Frontend Data Flow

### How the website gets data

```
User visits https://pudidicmgprediction.vercel.app/
  ↓
Frontend calls /api/cmg/current
  ↓
API reads:
  ├─ data/cache/cmg_historical_latest.json (CMG Online)
  └─ data/cache/cmg_programmed_latest.json (CMG Programado)
  ↓
Displays:
  ├─ 📊 CMG Online (last 24h coverage)
  └─ 🔮 CMG Programado (72h forecast)
```

---

## File Reference

### Cache Files (data/cache/)

| File | Purpose | Updated By | Used By |
|------|---------|------------|---------|
| `cmg_programmed_latest.json` | CMG Programado API cache (72h) | cmg_programado_hourly.yml | API |
| `pmontt_programado.json` | Raw CMG Programado data | cmg_programado_hourly.yml | Reference |
| `cmg_historical_latest.json` | CMG Online API cache | unified_cmg_update.yml | API |
| `metadata.json` | Cache metadata | unified_cmg_update.yml | API |

### Data Files (data/)

| File | Purpose | Updated By |
|------|---------|------------|
| `cmg_programado_history.json` | Historical CMG Programado archive | unified_cmg_update.yml (sync only) |

---

## Gists

| ID | Purpose | File | Updated By |
|----|---------|------|------------|
| `d68bb21360b1ac549c32a80195f99b09` | CMG Programado | cmg_programado_historical.json | cmg_programado_hourly.yml |
| `8d7864eb26acf6e780d3c0f7fed69365` | CMG Online | cmg_online_historical.json | unified_cmg_update.yml |
| `a63a3a10479bafcc29e10aaca627bc73` | Partner (reference) | - | READ ONLY |

---

## What Changed (October 2, 2025)

### Problems Fixed

1. **Data Overwriting** - CMG Programado was being reduced from 72h → 28h
2. **Duplicate Workflows** - Three workflows doing overlapping tasks
3. **Unclear Ownership** - Multiple workflows modifying the same files

### Solutions Implemented

1. **Disabled** `cmg_csv_pipeline.yml` (redundant)
2. **Removed** CMG Programado cache updates from `unified_cmg_update.yml`
3. **Established** clear data ownership:
   - CMG Programado → `cmg_programado_hourly.yml` ONLY
   - CMG Online → `unified_cmg_update.yml` ONLY

---

## How to Verify Everything is Working

### 1. Check Workflows Are Running

```bash
# View recent workflow runs
gh run list --limit 10
```

**Expected:**
- `cmg_programado_hourly.yml` runs at `:35` ✅
- `unified_cmg_update.yml` runs at `:05` ✅
- `cmg_csv_pipeline.yml` does NOT run ⛔

### 2. Check CMG Programado Data

```bash
cd /path/to/vercel_deploy

# Should show ~72 hours
cat data/cache/cmg_programmed_latest.json | jq '.data | length'

# Check timestamp
cat data/cache/cmg_programmed_latest.json | jq '.timestamp'
```

**Expected:** ~72 records, updated hourly at `:35`

### 3. Check CMG Online Data

```bash
# Should show several hundred records (7 days worth)
cat data/cache/cmg_historical_latest.json | jq '.data | length'

# Check timestamp
cat data/cache/metadata.json | jq '.last_update'
```

**Expected:** Multiple days of data, updated hourly at `:05`

### 4. Check Frontend

Visit: https://pudidicmgprediction.vercel.app/

**Expected:**
- 🔮 **CMG Programado:** Shows ~72 hours of forecast
- 📊 **CMG Online:** Shows last 24h coverage

---

## Troubleshooting

### CMG Programado shows less than 72 hours

**Diagnosis:**
```bash
# Check when file was last updated
ls -lh data/cache/cmg_programmed_latest.json

# Check file content
cat data/cache/cmg_programmed_latest.json | jq '.data | length'
```

**Fix:**
```bash
# Manually trigger the workflow
gh workflow run cmg_programado_hourly.yml

# Wait 5 minutes and check again
```

### Workflow Failed

**Check logs:**
```bash
# List recent runs
gh run list --workflow=cmg_programado_hourly.yml --limit 5

# View specific run
gh run view <run-id>
```

**Common issues:**
- Website changed structure (web scraping broke)
- API down (SIP API unavailable)
- Token expired (GitHub token needs refresh)

---

## Maintenance

### Weekly Checks

- [ ] Verify both workflows are running successfully
- [ ] Check data completeness on frontend
- [ ] Review GitHub Actions logs for warnings

### Monthly Tasks

- [ ] Review Gist sizes (cleanup if needed)
- [ ] Check for script updates/deprecations
- [ ] Verify data accuracy vs actual CMG values

---

## Need Help?

1. **Check documentation:** `ARCHITECTURE_ANALYSIS.md` (detailed technical analysis)
2. **Check logs:** GitHub Actions → Workflow runs
3. **Check files:** Review timestamps and contents of cache files
4. **Manual run:** Trigger workflows manually via `gh workflow run`

---

**Last Updated:** October 2, 2025
**Status:** Production - Clean Architecture ✅
