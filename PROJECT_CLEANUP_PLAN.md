# Project Cleanup Plan
**Generated:** 2025-11-10
**Purpose:** Identify and remove legacy AI-generated documentation

---

## 📁 Files to KEEP (Core Documentation)

### Essential Documentation
- `README.md` - Project overview (KEEP)
- `supabase/GIST_DATA_STRUCTURES.md` - Migration reference (KEEP)
- `supabase/MIGRATION_GUIDE.md` - Supabase migration steps (KEEP)
- `supabase/README.md` - Supabase documentation (KEEP)

### Deployment Guides (Keep for reference)
- `RAILWAY_DEPLOYMENT_GUIDE.md` - If using Railway
- `RAILWAY_QUICK_START.md` - If using Railway

---

## 🗑️ Files to ARCHIVE (Legacy AI Documentation)

These are session artifacts from previous Claude Code sessions that are no longer needed:

### Phase 1: Completed Features (Move to `archive/docs/`)
- `ARCHITECTURE_ANALYSIS.md` - Old architecture analysis
- `CMG_PIPELINE_ANALYSIS.md` - Pipeline documentation (outdated)
- `DEPLOYMENT_FIXES_SUMMARY.md` - Old deployment issues
- `DEPLOYMENT_READY.md` - Deployment checklist (completed)
- `DEPLOYMENT_SUCCESS.md` - Deployment completion report
- `IMPLEMENTATION_COMPLETE.md` - Feature completion report
- `ML_DASHBOARD_COMPLETE.md` - Dashboard completion report
- `ML_DASHBOARD_INTEGRATION.md` - Integration docs (completed)
- `ML_PREDICTIONS_FIX.md` - Bug fix documentation (resolved)
- `PRODUCTION_VERIFICATION_REPORT.md` - Old verification report
- `SNAPSHOT_SYSTEM_COMPLETE.md` - Snapshot system docs
- `WORKFLOWS_UPDATED.md` - Workflow update notes
- `WORKFLOW_GUIDE.md` - Old workflow guide

### Phase 2: Investigation/Audit Reports (Move to `archive/audits/`)
- `EFFICIENCY_OVER_100_INVESTIGATION.md` - Investigation results
- `OPTIMIZER_METRICS_AUDIT.md` - Metrics audit report
- `WHY_EQUAL_STORAGE_CONSTRAINT_IS_NECESSARY.md` - Technical explanation

### Phase 3: Migration/Setup Guides (Keep until migration complete, then archive)
- `GIST_TOKEN_SETUP.md` - Gist setup (will be obsolete after Supabase)
- `SUPABASE_MIGRATION.md` - Can merge into supabase/MIGRATION_GUIDE.md
- `NEXT_STEPS.md` - Probably outdated

### Phase 4: User Guides (Keep if still relevant)
- `VALIDATION_VIEW_GUIDE.md` - Check if still used

---

## 📦 Recommended Directory Structure

```
pudidi_cmg_prediction/
├── README.md                    # Main project documentation
├── archive/                     # Historical documentation
│   ├── docs/                    # Completed feature docs
│   ├── audits/                  # Investigation reports
│   └── migration/               # Old migration guides
├── supabase/                    # Supabase-related docs
│   ├── GIST_DATA_STRUCTURES.md
│   ├── MIGRATION_GUIDE.md
│   ├── README.md
│   └── schema.sql
├── docs/                        # Current documentation
│   ├── architecture/
│   ├── guides/
│   └── deployment/
└── [rest of project]
```

---

## 🎯 Action Plan

### Step 1: Create Archive Structure
```bash
mkdir -p archive/docs
mkdir -p archive/audits
mkdir -p archive/migration
```

### Step 2: Move Completed Feature Docs
```bash
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
```

### Step 3: Move Audit Reports
```bash
mv EFFICIENCY_OVER_100_INVESTIGATION.md archive/audits/
mv OPTIMIZER_METRICS_AUDIT.md archive/audits/
mv WHY_EQUAL_STORAGE_CONSTRAINT_IS_NECESSARY.md archive/audits/
```

### Step 4: Move Migration Docs (after Supabase migration complete)
```bash
mv GIST_TOKEN_SETUP.md archive/migration/
mv SUPABASE_MIGRATION.md archive/migration/
mv NEXT_STEPS.md archive/migration/
```

### Step 5: Review and Clean User Guides
- Keep `VALIDATION_VIEW_GUIDE.md` if still used
- Keep Railway guides if deploying to Railway

---

## ✅ Benefits After Cleanup

1. **Cleaner root directory** (23 files → 2-3 essential docs)
2. **Easier navigation** for new contributors
3. **Historical context preserved** in archive/
4. **Clear separation** between active and legacy docs
5. **Better Git history** with single cleanup commit

---

## 📝 Commit Message Template

```
docs: Archive legacy AI-generated documentation

- Move 13 completed feature docs to archive/docs/
- Move 3 audit reports to archive/audits/
- Move 3 migration guides to archive/migration/
- Keep only essential documentation in root
- Preserve historical context for reference

This cleanup improves project navigation while maintaining
documentation history for future reference.
```
