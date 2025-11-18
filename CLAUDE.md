# CLAUDE.md - AI Assistant Context & Session Continuity

**Last Updated**: 2025-11-17
**Current Session**: Schema Migration & Data Pipeline Verification

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

## 🚨 CRITICAL CURRENT ISSUE: SCHEMA MISMATCH (Nov 17, 2025)

### The Problem

A **critical schema mismatch** was discovered between the documented schema and the actual Supabase database:

**Schema.sql (documented)**:
```sql
CREATE TABLE cmg_programado (
    forecast_datetime TIMESTAMPTZ,  -- When forecast was made
    target_datetime TIMESTAMPTZ,    -- What hour is being predicted
    cmg_usd DECIMAL(10, 2),
    ...
)
```

**Actual Supabase Database**:
```sql
-- Columns that actually exist:
datetime, fetched_at, cmg_programmed, date, hour, node
```

### Impact

1. ❌ All recent code changes (lib/utils/supabase_client.py, scripts/store_cmg_programado.py, api/historical_comparison.py) **fail with 400 errors**
2. ❌ CMG Programado data **cannot be queried** with new code
3. ✅ BUT: 696 existing records ARE in Supabase (just with old schema)
4. ✅ Gists contain 43,109 CMG Programado records (29 days) ready for backfill

### Migration Status

**Created** (Nov 17, 2025):
- ✅ `supabase/migrations/001_migrate_cmg_programado_schema.sql` - SQL migration script
- ✅ `scripts/migrate_cmg_programado_schema.py` - Python backfill script
- ✅ Committed and pushed to main branch

**Pending** (YOU MUST DO THIS):
1. ⏳ Run SQL migration in Supabase SQL Editor
2. ⏳ Run Python backfill script
3. ⏳ Verify data migration success
4. ⏳ Test all API endpoints
5. ⏳ Verify frontend displays data correctly

---

## 📊 CURRENT DATA STATUS (As of Nov 17, 2025)

Direct Supabase connection reveals:

| Table | Supabase Records | Gist Records | Status |
|-------|------------------|--------------|--------|
| **ml_predictions** | 1,000 (Nov 9-10, 17) | 2,208 (Nov 12-17) | ⚠️ Gist MORE complete |
| **cmg_programado** | 696 (wrong schema) | 43,109 (Oct 20 - Nov 17) | ❌ Schema mismatch, need migration |
| **cmg_online** | 1,000 (Nov 1-17) | 5,526 (Sep 2 - Nov 17) | ✅ Current, Gist has more history |

**Gist Coverage**:
- **ML Predictions**: Only 6 days (Nov 12-17) - 92 snapshots
- **CMG Programado**: 29 days (Oct 20 - Nov 17) - 603 snapshots ✅ EXCELLENT
- **CMG Online**: 77 days (Sep 2 - Nov 17) - 5,526 records ✅ EXCELLENT

**Key Finding**: Gists have significantly more historical data than Supabase! Migration will restore this data.

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

### Resolved (Nov 17, 2025)
- ✅ index.html "Conectando..." - Fixed by adding last_updated field
- ✅ forecast_comparison.html wrong structure - Fixed data transformation functions
- ✅ Identified schema mismatch in cmg_programado table

### Active (NEEDS MIGRATION)
- ❌ CMG Programado schema mismatch (migration scripts created, waiting to run)
- ❌ forecast_comparison.html shows no data (will fix after migration)
- ❌ API /historical_comparison returns 400 errors (will fix after migration)

### Future Improvements
- ⚠️ ML Predictions Gist only keeps 6 days (should keep all - Supabase has no storage limits)
- ⚠️ Backfill ML predictions from Nov 11-16 (gap in Supabase data)

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
