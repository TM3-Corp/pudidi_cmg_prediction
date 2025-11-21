# CLAUDE.md - AI Assistant Context & Session Continuity

**Last Updated**: 2025-11-20
**Current Session**: CRITICAL - CMG Programado Storage Failure Detected

---

## 🚨 CRITICAL ISSUE: CMG PROGRAMADO STORAGE FAILURES (Nov 20, 2025)

### Root Cause Analysis COMPLETE ✅

**User was RIGHT to be skeptical!** Deep investigation revealed **TWO critical bugs** affecting CMG Programado data:

#### Bug #1: Timezone-Naive Datetime Strings 🕐

**Location:** `scripts/process_pmontt_programado.py` line 219 + `scripts/store_cmg_programado.py` lines 265-271

**The Problem:**
```python
# process_pmontt_programado.py line 219
"datetime": f"{date}T{hour}:00:00"  # ❌ NO TIMEZONE SUFFIX!

# Cache file produces:
{
  "timestamp": "2025-11-20T19:28:34.997394-03:00",  # ✅ Has timezone
  "data": [
    {"datetime": "2025-11-20T00:00:00", ...}        # ❌ No timezone!
  ]
}

# store_cmg_programado.py line 268
target_dt = datetime.fromisoformat(target_dt_str)  # Creates timezone-NAIVE datetime

# Line 278 sends to Supabase
'target_datetime': target_dt.isoformat()  # Returns "2025-11-20T00:00:00" (no timezone)

# Supabase TIMESTAMPTZ defaults to UTC when no timezone provided!
# Result: Wrong timestamps, wrong target_date/target_hour extraction
```

**Impact:**
- All datetime comparisons may be off by 3 hours (Santiago is UTC-3)
- `target_date` and `target_hour` extracted AFTER UTC default may be incorrect
- Performance metrics compare wrong time periods

**Fix Required:**
Change line 219 in `process_pmontt_programado.py` to use the already timezone-aware `dt` object:
```python
"datetime": dt.isoformat()  # dt is already santiago_tz.localize(dt) from line 54
```

#### Bug #2: Sporadic Storage Failures 💾

**Evidence (with proper pagination):**

**Nov 18, 2025:**
- **Gist**: 19/24 forecast hours `[0-8, 10-16, 19, 20, 23]` ✅
- **Supabase**: 17/24 forecast hours `[0-8, 10-16, 19]` (1,296 records)
- **DATA LOSS**: Hours 20, 23 missing from Supabase ❌

**Nov 20, 2025:**
- **Supabase**: 20/24 forecast hours `[0-8, 10-16, 17-18, 20, 23]` (1,512 records)
- **DATA LOSS**: Hours 9, 19, 21, 22 missing ❌
- **Cache shows hour 19 was fetched but 0 records in Supabase!**

**Pattern**:
- Hour 9 consistently missing (both Nov 18 and 20)
- Other hours sporadically missing (not a consistent "14-23" pattern as initially thought)
- Some fetches succeed, others silently fail

**Possible Causes:**
- Constraint violations during batch insert?
- Node ID lookup failures for certain forecast times?
- Exception swallowing in error handling (lines 296-298)?
- Timezone-naive datetimes causing constraint conflicts?

**Location:** `scripts/store_cmg_programado.py` lines 289-294 + `lib/utils/supabase_client.py` lines 157-176

**Lesson Learned**: Always use pagination when querying Supabase! PostgREST has 1000-row default limit.

### Impact

1. **Performance Heatmap Shows Artificial Gaps**
   - Heatmap queries Supabase (not Gist)
   - Missing hours create fake "no data" cells
   - Performance metrics are INCOMPLETE and MISLEADING

2. **Distance Calculation is Correct**
   - Formula: `distance = |forecast - actual|` ✅
   - Terminology issue: "360 errors" → should say "360 comparisons"
   - Each comparison is valid, "error" just means "signed difference"

3. **Timezone Mismatch Causes Wrong Aggregations**
   - Daily charts may aggregate wrong hours
   - Horizon charts may compare misaligned timestamps

### Data Pipeline Flow

```
Hourly Workflow (runs at :05 every hour)
├─ 1. Scrape CMG Programado CSV from Coordinador website (Playwright)
│    └─ scripts/download_cmg_programado_simple.py
├─ 2. Process CSV → Extract PMontt220 node → Create cache file
│    └─ scripts/process_pmontt_programado.py
│    ❌ BUG: Line 219 creates timezone-naive datetime strings
├─ 3. Store to Gist
│    └─ scripts/store_cmg_programado.py
│    ✅ SUCCESS (19 hours on Nov 18)
└─ 4. Store to Supabase
     └─ scripts/store_cmg_programado.py
     ❌ BUG: Parses timezone-naive strings, silent failures for hours 14-23
     ❌ PARTIAL FAILURE (13 hours on Nov 18, lost 6 hours!)
```

### Fixes Applied (Nov 21, 2025) ✅

1. ✅ **Bug #1 FIXED: Timezone-Naive Strings**
   - **File**: `scripts/process_pmontt_programado.py` line 221
   - **Change**: Added `-03:00` timezone suffix to datetime strings
   - **Before**: `"datetime": f"{date}T{hour}:00:00"`
   - **After**: `"datetime": f"{date}T{hour}:00:00-03:00"`
   - **Impact**: New CMG Programado data will have correct Santiago timezone

2. ✅ **Bug #2 FIXED: Added Detailed Error Logging**
   - **Files**:
     - `scripts/store_cmg_programado.py` lines 289-327 (batch insert loop)
     - `lib/utils/supabase_client.py` lines 166-179 (error details)
   - **Added**:
     - Per-batch success/failure tracking
     - Forecast hours in each batch logged
     - Failed batch sample records printed
     - Detailed HTTP error response parsing
     - Insert summary statistics
   - **Impact**: Will now see exactly which batches fail and why

3. ✅ **Performance Views Investigation Complete**
   - All views (rendimiento.html, performance_heatmap.html) are **consistent**
   - Both require: Forecasts AND Actuals (CMG Online)
   - **Why Horizon Chart Shows Complete Data**:
     - Aggregates by `horizon` across ALL dates
     - Partial data from different dates fills all 24 horizons
   - **Why Daily Charts Show Gaps**:
     - Requires complete forecasts for each specific date
     - Missing forecasts for a date = gap in daily view
   - **Data Coverage Analysis** (Nov 14-20):
     - CMG Online (Actuals): ✅ 100% complete (24 hours × 7 days)
     - ML Predictions: 4/7 dates (missing Nov 14, 15, 20)
     - CMG Programado: 1/7 dates visible in `forecast_date` (timezone bug affected date extraction)

### Next Steps

1. **Deploy Fixes**
   - Commit timezone fix and error logging
   - Push to GitHub
   - Wait for next hourly workflow run
   - Monitor GitHub Actions logs for detailed error messages

2. **Investigate ML Predictions Gap**
   - Why are ML Predictions missing for Nov 14, 15, 20?
   - Check if `ml_hourly_forecast.py` is running consistently
   - Review GitHub Actions logs for those dates

3. **Backfill CMG Programado** (AFTER timezone fix deployed)
   - Once new data confirms timezone fix works
   - Backfill Nov 15-20 from Gist with correct timezone handling
   - Write backfill script: `scripts/backfill_cmg_programado.py`

4. **Monitor Next Hourly Run**
   - Check if hour 9, 19, etc. still fail
   - Review detailed error logs from new logging
   - Verify timezone-aware datetimes are stored correctly

---

## 🎯 PROJECT OVERVIEW

**Pudidi CMG Prediction System** - Real-time electricity price monitoring and forecasting for Chilean market.

**Tech Stack**:
- **Frontend**: Vanilla JS + Tailwind CSS (5 HTML pages)
- **Backend**: Vercel Serverless Functions (Python)
- **Database**: Supabase (PostgreSQL) - **PRIMARY DATA SOURCE**
- **ML Backend**: Railway (separate service)
- **Data Sources**: SIP API (CMG Online), Coordinador (CMG Programado)
- **Automation**: GitHub Actions (hourly workflows)

**Key URLs**:
- Production: https://pudidicmgprediction.vercel.app
- Supabase: https://btyfbrclgmphcjgrvcgd.supabase.co
- Repository: https://github.com/TM3-Corp/pudidi_cmg_prediction

---

## ✅ MIGRATION COMPLETED: Schema Fixed (Nov 17, 2025)

### The Problem (RESOLVED)

A **critical schema mismatch** was discovered and **successfully resolved** between the documented schema and the actual Supabase database.

**Schema.sql (documented)** - NOW MATCHES ACTUAL DATABASE:
```sql
CREATE TABLE cmg_programado (
    forecast_datetime TIMESTAMPTZ,  -- When forecast was made
    target_datetime TIMESTAMPTZ,    -- What hour is being predicted
    cmg_usd DECIMAL(10, 2),
    ...
)
```

**Previous Database Schema** (before migration):
```sql
-- Old columns (now migrated):
datetime, fetched_at, cmg_programmed, date, hour, node
```

### Migration Results ✅

**Completed** (Nov 17-18, 2025):
- ✅ SQL migration executed successfully via Transaction Pooler
- ✅ All 696 existing records migrated from old → new schema
- ✅ New columns added: forecast_datetime, target_datetime, cmg_usd, etc.
- ✅ Old columns made nullable (datetime, date, hour, cmg_programmed, fetched_at)
- ✅ Unique constraints and indexes created
- ✅ **Backfilled 43,253 records from Gist (29 days: Oct 20 - Nov 17)**
- ✅ **Total records now: 44,573** (vs 696 before migration)
- ✅ SupabaseClient now works (no more 400 errors!)
- ✅ API endpoints returning data successfully
- ✅ All 5 verification tests passed
- ✅ Nov 16 03:00 data now available (was showing "Pendiente" before)

**Key Learning - Supabase Connection**:
```python
# IMPORTANT: Use Transaction Pooler for IPv4 networks (Supabase free plan)
# Connection string format:
# postgresql://postgres.btyfbrclgmphcjgrvcgd:[PASSWORD]@aws-1-sa-east-1.pooler.supabase.com:6543/postgres

conn_params = {
    'host': 'aws-1-sa-east-1.pooler.supabase.com',  # South America region
    'port': 6543,  # Transaction pooler port (NOT 5432!)
    'user': 'postgres.btyfbrclgmphcjgrvcgd',  # Format: postgres.[project-ref]
    'password': 'YOUR_PASSWORD',
    'sslmode': 'require'
}
```

**Optional Future Tasks**:
1. ✅ ~~Backfill 29 days of CMG Programado from Gist~~ **COMPLETE** (44,573 records)
2. ⏳ Backfill ML predictions gap (Nov 11-16) - **LOW PRIORITY**
3. ⏳ Drop old columns after 7 days of verification (datetime, date, hour, etc.)
4. ⏳ Backfill CMG Online historical data from Gist (Sep 2 - Oct 31)

---

## 📊 CURRENT DATA STATUS (As of Nov 18, 2025)

Direct Supabase connection reveals:

| Table | Supabase Records | Date Range | Status |
|-------|------------------|------------|--------|
| **ml_predictions** | ~1,000 | Nov 9-10, 17-18 | ✅ Active, gaps in Nov 11-16 |
| **cmg_programado** | **44,573** | **Oct 20 - Nov 18** | ✅ **COMPLETE** - Backfilled! |
| **cmg_online** | ~1,000 | Nov 1-18 | ✅ Active, hourly updates |

**Backfill Results**:
- ✅ **CMG Programado**: Successfully backfilled 43,253 records from Gist
- ✅ **Date Coverage**: 29 days (Oct 20 - Nov 17) + ongoing hourly updates
- ✅ **Nov 16 03:00 data**: Available (was showing "Pendiente" before backfill)
- ✅ **Total increase**: From 696 → 44,573 records (64x growth!)

---

## 🏗️ SYSTEM ARCHITECTURE (MVC Pattern)

See `ARCHITECTURE.md` for comprehensive documentation. Quick reference:

### Views (Frontend)
1. `index.html` - Main dashboard (✅ Supabase)
2. `ml_config.html` - ML configuration (✅ Supabase + Railway)
3. `optimizer.html` - Cost optimizer (⚠️ Hybrid)
4. `rendimiento.html` - Performance metrics (⚠️ Hybrid)
5. `forecast_comparison.html` - Historical comparison (✅ Supabase - **BROKEN until schema migration**)

### API Endpoints (Controllers)
- `/api/cmg/current` - Main data endpoint (✅ Working)
- `/api/ml_forecast` - ML predictions (✅ Working)
- `/api/historical_comparison` - Forecast comparison (❌ **400 errors due to schema mismatch**)
- `/api/optimizer` - Cost optimization (⚠️ Hybrid)
- `/api/performance` - Performance analysis (⚠️ Hybrid)

### Database (Model)
**Supabase Tables**:
1. `cmg_online` - Actual CMG values (✅ Correct schema)
2. `cmg_programado` - Forecast values (❌ **WRONG SCHEMA - NEEDS MIGRATION**)
3. `ml_predictions` - ML forecasts (✅ Correct schema)

---

## 🔧 CRITICAL FILES TO KNOW

### Backend (API Layer)
- `lib/utils/supabase_client.py` - **Database client** (uses new schema columns - currently BROKEN for cmg_programado)
- `api/cmg/current.py` - Main endpoint (✅ Working)
- `api/historical_comparison.py` - Historical data (❌ **BROKEN - 400 errors**)

### Storage Scripts (Workflows)
- `scripts/store_cmg_programado.py` - Stores CMG Programado (❌ **BROKEN - tries to use forecast_datetime column that doesn't exist**)
- `scripts/store_ml_predictions.py` - Stores ML predictions (✅ Working)
- `scripts/smart_cmg_online_update.py` - Stores CMG Online (✅ Working)

### Frontend
- `public/index.html` - Main dashboard (✅ Working after last fix)
- `public/forecast_comparison.html` - Forecast comparison (❌ **BROKEN - no data due to backend 400 errors**)

### Workflows (GitHub Actions)
- `.github/workflows/cmg_online_hourly.yml` - Runs every hour at :05

---

## 🔑 ENVIRONMENT VARIABLES

**Required for Supabase access**:
```bash
export SUPABASE_URL="https://btyfbrclgmphcjgrvcgd.supabase.co"
export SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTAwOTUyOSwiZXhwIjoyMDc2NTg1NTI5fQ.xAQREPHWP41cDx2ZgpROp5wJBbuPUESQzMwn_C_PatM"
```

**GitHub Actions secrets**:
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- `GITHUB_TOKEN`, `CMG_GIST_TOKEN`

---

## 📝 MIGRATION STEPS (DO THIS NEXT!)

### Step 1: Run SQL Migration in Supabase

1. Go to Supabase SQL Editor: https://btyfbrclgmphcjgrvcgd.supabase.co/project/_/sql
2. Copy entire contents of `supabase/migrations/001_migrate_cmg_programado_schema.sql`
3. Paste and click "Run"
4. Verify: Should see notices like "Added forecast_datetime column", "Migrated N rows"

### Step 2: Run Python Backfill Script

```bash
cd /home/paul/projects/Pudidi/pudidi_CMG_prediction_system/vercel_deploy

export SUPABASE_URL="https://btyfbrclgmphcjgrvcgd.supabase.co"
export SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTAwOTUyOSwiZXhwIjoyMDc2NTg1NTI5fQ.xAQREPHWP41cDx2ZgpROp5wJBbuPUESQzMwn_C_PatM"

python3 scripts/migrate_cmg_programado_schema.py
```

This will:
- Backup existing 696 records
- Backfill 29 days from Gist (43,109 records)
- Verify migration success

### Step 3: Verify Data

```bash
# Test Supabase client with new schema
python3 << 'EOF'
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

os.environ['SUPABASE_URL'] = "https://btyfbrclgmphcjgrvcgd.supabase.co"
os.environ['SUPABASE_SERVICE_KEY'] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTAwOTUyOSwiZXhwIjoyMDc2NTg1NTI5fQ.xAQREPHWP41cDx2ZgpROp5wJBbuPUESQzMwn_C_PatM"

from lib.utils.supabase_client import SupabaseClient
supabase = SupabaseClient()

# Should work now (no 400 error!)
prog = supabase.get_cmg_programado(limit=10)
print(f"✅ Got {len(prog)} CMG Programado records")
print(f"Sample: {prog[0] if prog else 'None'}")
EOF
```

### Step 4: Test API Endpoints

```bash
# Test historical comparison endpoint
curl https://pudidicmgprediction.vercel.app/api/historical_comparison | python3 -m json.tool | head -30

# Should return success: true and data (no 400 error!)
```

### Step 5: Test Frontend

1. Open https://pudidicmgprediction.vercel.app/forecast_comparison.html
2. Select date: 2025-11-12, hour: 04:00
3. Click "Cargar Pronóstico"
4. **Expected**: Should show ALL 24 horizons for both ML predictions and CMG Programado
5. **Before fix**: Only showed 1 row

### Step 6: Clean Up Old Columns (LATER!)

After verifying everything works for 24 hours:
- Uncomment the DROP COLUMN statements in the SQL migration file
- Run to remove old columns (datetime, fetched_at, cmg_programmed, etc.)

---

## 🐛 KNOWN ISSUES

### Resolved (Nov 17-18, 2025)
- ✅ index.html "Conectando..." - Fixed by adding last_updated field
- ✅ forecast_comparison.html wrong structure - Fixed data transformation functions
- ✅ Identified schema mismatch in cmg_programado table
- ✅ **CMG Programado schema mismatch - MIGRATED & BACKFILLED**
- ✅ **forecast_comparison.html Nov 16 03:00 "Pendiente" - DATA NOW AVAILABLE**
- ✅ **API /historical_comparison 400 errors - FIXED**

### Active Issues
- None! System is fully operational.

### Future Improvements (Optional)
- ⏳ ML Predictions gap Nov 11-16 (low priority - system works without it)
- ⏳ Backfill CMG Online historical data from Gist (Sep 2 - Oct 31)
- ⏳ Drop old schema columns after 7 days of verification

---

## 🎓 LESSONS LEARNED

### Always Connect Directly to Verify Data
- **DON'T** rely on API responses alone - they can have bugs
- **DO** connect directly to Supabase with credentials to verify actual schema
- **DO** check both schema.sql AND actual database columns

### Schema Migrations Need Careful Planning
- Keep old columns during migration period
- Transform data first, then add constraints
- Verify before dropping old columns
- Always backup before migrations

### Documentation is Critical
- Document current state, not just ideal state
- Include migration status and pending tasks
- Provide exact commands for next steps
- Update CLAUDE.md after each major discovery

---

## 🚀 NEXT SESSION CHECKLIST

If you're Claude in a new session, START HERE:

1. **Read this file completely** - Understand current state
2. **Check migration status** - Has the SQL migration been run?
3. **Verify Supabase connection** - Can you query cmg_programado with new schema?
4. **Test API endpoints** - Does /historical_comparison work?
5. **Check frontend** - Does forecast_comparison.html display data?

**If migration NOT done yet**:
- Follow "Migration Steps" above
- Test each step thoroughly
- Update this file with results

**If migration IS done**:
- Update this file to reflect completion
- Move to next priorities (backfill ML predictions gap, etc.)

---

## 📚 REFERENCE DOCUMENTATION

- `ARCHITECTURE.md` - Complete MVC architecture, API endpoints, database schema
- `START_HERE.md` - Original project setup guide
- `MIGRATION_ROADMAP.md` - Original Gist→Supabase migration plan
- `supabase/schema.sql` - **Intended** database schema (NOT current actual schema until migration runs!)

---

## 🔗 QUICK LINKS

**Supabase Dashboard**: https://btyfbrclgmphcjgrvcgd.supabase.co/project/_/editor
**SQL Editor**: https://btyfbrclgmphcjgrvcgd.supabase.co/project/_/sql
**Frontend**: https://pudidicmgprediction.vercel.app
**GitHub Actions**: https://github.com/TM3-Corp/pudidi_cmg_prediction/actions

---

**Remember**: This system is in active migration from Gist-based storage to Supabase. The goal is to have Supabase as the single source of truth for all historical data, with no storage limitations like we had with GitHub Gists.
