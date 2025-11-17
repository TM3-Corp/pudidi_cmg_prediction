# Supabase Migration Roadmap
**Date:** 2025-11-10
**Branch:** `claude/migrate-to-supabase-011CUzraym9qhZV7Wnzjbn16`

---

## 🎯 Goals

1. **Migrate from GitHub Gist to Supabase** - Eliminate rate limiting issues
2. **Clean up project structure** - Remove legacy AI documentation
3. **Update ETL scripts** - Write to Supabase instead of Gist
4. **Zero downtime** - Maintain service during transition

---

## ✅ Current Status: READY TO EXECUTE

### What's Already Done (Previous Session)
- ✅ Analyzed all 3 Gist data structures
- ✅ Created complete Supabase schema (`supabase/schema.sql`)
- ✅ Created migration script (`scripts/migrate_to_supabase.py`)
- ✅ Documented data mappings (`supabase/GIST_DATA_STRUCTURES.md`)
- ✅ Set up Supabase client libraries

### What's Missing
- ❌ Supabase credentials (URL + Service Key)
- ❌ Schema deployed to Supabase
- ❌ Data migrated to Supabase
- ❌ ETL scripts updated to use Supabase
- ❌ Project cleanup

---

## 🗺️ Migration Plan

### Phase 1: Setup Supabase (15 minutes)

#### Step 1.1: Deploy Database Schema
1. Go to Supabase SQL Editor: https://supabase.com/dashboard/project/btyfbrclgmphcjgrvcgd/editor
2. Create new query
3. Copy entire contents of `supabase/schema.sql`
4. Run the query (Cmd/Ctrl + Enter)
5. Verify tables created: `cmg_online`, `cmg_programado`, `ml_predictions`

#### Step 1.2: Get API Credentials
1. Go to Project Settings → API
2. Copy these values:
   - **Project URL**: `https://btyfbrclgmphcjgrvcgd.supabase.co`
   - **anon key** (public, for reads)
   - **service_role key** (secret, for writes)

#### Step 1.3: Configure Environment Variables

**GitHub Actions (for ETL workflows):**
- Go to: https://github.com/TM3-Corp/pudidi_cmg_prediction/settings/secrets/actions
- Add secrets:
  - `SUPABASE_URL` = `https://btyfbrclgmphcjgrvcgd.supabase.co`
  - `SUPABASE_SERVICE_KEY` = (your service_role key)

**Local Testing (optional):**
```bash
cp .env.supabase.example .env
# Edit .env with your credentials
```

---

### Phase 2: Data Migration (10 minutes)

#### Step 2.1: Test Connection
```bash
python scripts/test_supabase_connection.py
```
Expected output: ✅ Successfully connected to all 3 tables

#### Step 2.2: Run Migration Script
```bash
python scripts/migrate_to_supabase.py
```

This will migrate:
- **CMG Online**: ~4,100 historical records (57 days)
- **CMG Programado**: ~720 historical records (30 days)
- **ML Predictions**: ~3,456 prediction records (6 days)

**Total estimated time**: 2-5 minutes

#### Step 2.3: Verify Data
Check Supabase Table Editor:
- CMG Online: https://supabase.com/dashboard/project/btyfbrclgmphcjgrvcgd/editor?table=cmg_online
- CMG Programado: https://supabase.com/dashboard/project/btyfbrclgmphcjgrvcgd/editor?table=cmg_programado
- ML Predictions: https://supabase.com/dashboard/project/btyfbrclgmphcjgrvcgd/editor?table=ml_predictions

---

### Phase 3: Update ETL Scripts (20 minutes)

#### Scripts to Modify:

**3.1. `scripts/smart_cmg_online_update.py`**
- Add Supabase write alongside Gist (dual-write)
- Keep cache file updates for backwards compatibility

**3.2. `scripts/store_cmg_programado.py`**
- Add Supabase write for historical data
- Keep Gist updates for forecast snapshots (if needed)

**3.3. `scripts/store_ml_predictions.py`**
- Add Supabase batch insert for predictions
- Implement rolling window (keep last 7 days)

**Strategy: Dual-Write Period**
- Week 1: Write to BOTH Gist and Supabase
- Week 2: Monitor Supabase performance
- Week 3: Switch to Supabase-only writes
- Keep Gist as read-only backup

---

### Phase 4: Project Cleanup (15 minutes)

#### Step 4.1: Archive Legacy Documentation
```bash
# Create archive structure
mkdir -p archive/docs archive/audits archive/migration

# Move completed feature docs (13 files)
mv ARCHITECTURE_ANALYSIS.md archive/docs/
mv CMG_PIPELINE_ANALYSIS.md archive/docs/
mv DEPLOYMENT_*.md archive/docs/
mv IMPLEMENTATION_COMPLETE.md archive/docs/
mv ML_DASHBOARD_*.md archive/docs/
mv ML_PREDICTIONS_FIX.md archive/docs/
mv PRODUCTION_VERIFICATION_REPORT.md archive/docs/
mv SNAPSHOT_SYSTEM_COMPLETE.md archive/docs/
mv WORKFLOWS_UPDATED.md archive/docs/
mv WORKFLOW_GUIDE.md archive/docs/

# Move audit reports (3 files)
mv EFFICIENCY_OVER_100_INVESTIGATION.md archive/audits/
mv OPTIMIZER_METRICS_AUDIT.md archive/audits/
mv WHY_EQUAL_STORAGE_CONSTRAINT_IS_NECESSARY.md archive/audits/

# Move migration docs (3 files - after Supabase migration complete)
mv GIST_TOKEN_SETUP.md archive/migration/
mv SUPABASE_MIGRATION.md archive/migration/
mv NEXT_STEPS.md archive/migration/
```

#### Step 4.2: Update .gitignore
Ensure `.env` is ignored (already done ✅)

#### Step 4.3: Commit Cleanup
```bash
git add .
git commit -m "docs: Archive legacy AI-generated documentation

- Move 13 completed feature docs to archive/docs/
- Move 3 audit reports to archive/audits/
- Move 3 migration guides to archive/migration/
- Keep only essential documentation in root

Improves project navigation while preserving history."
```

---

### Phase 5: Update Frontend (Optional - Future)

**Current State**: Frontend reads from Gist URLs → will continue working

**Future Enhancement**: Update frontend to use Supabase REST API
- `public/index.html` - Dashboard data fetching
- `public/forecast_comparison.html` - Comparison view
- `public/js/optimizer.js` - Optimizer data

**Benefit**: Faster loading, no rate limits, real-time updates

**Priority**: LOW (not blocking, Gist backup remains)

---

## 🚀 Quick Start (What to Do NOW)

### Option A: Full Migration (Recommended)
```bash
# 1. Set up credentials (see Phase 1)
# 2. Run migration
python scripts/migrate_to_supabase.py

# 3. Clean up docs
bash scripts/cleanup_legacy_docs.sh  # (I can create this)

# 4. Commit changes
git add .
git commit -m "feat: Migrate to Supabase and clean up documentation"
git push -u origin claude/migrate-to-supabase-011CUzraym9qhZV7Wnzjbn16
```

### Option B: Step-by-Step (Safer)
1. **Today**: Set up Supabase credentials + deploy schema
2. **Day 2**: Run data migration + verify
3. **Day 3**: Update ETL scripts (dual-write)
4. **Day 4**: Clean up documentation
5. **Week 2**: Monitor and switch to Supabase-only

---

## 📊 Before/After Comparison

| Aspect | Before (Gist) | After (Supabase) |
|--------|--------------|------------------|
| **Rate Limits** | 60 req/hour ❌ | 2GB/month ✅ |
| **Latency** | 500-1000ms | 50-100ms ⚡ |
| **Documentation** | 23 MD files 📚 | 3 essential docs 📄 |
| **Query Flexibility** | None | SQL queries ✅ |
| **Real-time** | No | Yes (optional) |
| **Maintenance** | Gist hacks | Proper database |

---

## 🔄 Rollback Plan

If anything goes wrong:

1. **ETL scripts still write to Gist** ✅
2. **Cache files still updated** ✅
3. **Frontend uses cache fallback** ✅
4. **Gist data unchanged** ✅

**Migration is reversible and safe!**

---

## 📝 Next Steps

**I can help you with:**

1. **Set up Supabase credentials** (guided walkthrough)
2. **Run the migration** (with real-time monitoring)
3. **Update ETL scripts** (with dual-write strategy)
4. **Clean up documentation** (automated archival)
5. **Test everything** (end-to-end verification)
6. **Create PR** (with comprehensive changelog)

**What would you like to do first?**

A) Set up Supabase and run migration NOW
B) Just clean up documentation first
C) Do both in phases (recommended)
D) Something else

Let me know and I'll guide you through it! 🚀
