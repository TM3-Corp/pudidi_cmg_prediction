# 🚀 Supabase Migration Guide

## ✅ Completed So Far

### 1. Schema Design ✓
- Created `supabase/schema.sql` with 3 tables:
  - `cmg_online`: Actual CMG values from SIP API
  - `cmg_programado`: Forecasts from Coordinador
  - `ml_predictions`: ML model predictions
- Added indexes for fast queries
- Added Row Level Security (RLS) for public read, service write
- Added helpful views for analytics

### 2. Python Client ✓
- Created `scripts/supabase_client.py`
- Handles environment variables
- Includes connection test function

### 3. First Dual-Write Script ✓
- Created `scripts/store_cmg_online_dual.py`
- Writes to BOTH Gist and Supabase
- Fails gracefully if Supabase unavailable

---

## 📋 Next Steps (Do This Now)

### Step 1: Run the Schema in Supabase

1. Go to https://btyfbrclgmphcjgrvcgd.supabase.co
2. Click **SQL Editor** in left sidebar
3. Click **New query**
4. Open `supabase/schema.sql` and copy ALL contents
5. Paste into SQL Editor
6. Click **Run** (or Cmd/Ctrl + Enter)
7. You should see: "Success. No rows returned"

**Verify:**
- Click **Table Editor**
- You should see 3 tables: `cmg_online`, `cmg_programado`, `ml_predictions`

### Step 2: Add Secrets to GitHub

1. Go to your GitHub repo: https://github.com/TM3-Corp/pudidi_cmg_prediction
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add these two secrets:

**Secret 1:**
- Name: `SUPABASE_URL`
- Value: `https://btyfbrclgmphcjgrvcgd.supabase.co`

**Secret 2:**
- Name: `SUPABASE_SERVICE_KEY`
- Value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTAwOTUyOSwiZXhwIjoyMDc2NTg1NTI5fQ.xAQREPHWP41cDx2ZgpROp5wJBbuPUESQzMwn_C_PatM`

### Step 3: Update GitHub Actions Workflow

I'll update the workflow to:
- Add `supabase` to pip install
- Add Supabase environment variables
- Use `store_cmg_online_dual.py` instead of `store_historical.py`

### Step 4: Test on Next Workflow Run

- Next run will write to BOTH Gist and Supabase
- Check Supabase Table Editor to see data appearing
- Gist will continue working as backup

---

## 🔜 What's Left to Build

1. **Dual-write for CMG Programado** (30 min)
   - Create `store_cmg_programado_dual.py`

2. **Dual-write for ML Predictions** (30 min)
   - Create `store_ml_predictions_dual.py`

3. **Historical Data Migration** (30 min)
   - Script to backfill existing Gist data to Supabase

4. **API Endpoints** (30 min)
   - Create Vercel API routes to query Supabase

5. **Frontend Testing** (30 min)
   - Test forecast_comparison.html with Supabase data

6. **Cutover** (5 min)
   - Switch frontend to Supabase endpoints

---

## 📊 Architecture Comparison

### Current (Gist-based):
```
GitHub Actions
  ↓ write
Gist (JSON blob)
  ↓ fetch
Frontend
```

### After Migration (Supabase):
```
GitHub Actions
  ↓ write (parallel)
  ├─→ Gist (backup, temporary)
  └─→ Supabase (primary)
       ↓ query via API
     Frontend
```

### Final State (Supabase-only):
```
GitHub Actions
  ↓ write
Supabase
  ↓ query via API
Frontend
```

---

## 🎯 Success Criteria

Before removing Gist writes:
- ✅ All 3 data types writing to Supabase
- ✅ Historical data migrated
- ✅ Frontend works with Supabase APIs
- ✅ Run in parallel for 48 hours with no issues
- ✅ Query performance is good

---

## 🚨 Rollback Plan

If something goes wrong:
1. Gist writes are still active (no data loss)
2. Frontend can switch back to Gist URLs
3. No permanent changes to existing system

---

## ⚡ Performance Benefits

**Gist:**
- 📥 Fetch entire 30MB JSON file
- ⚙️ Parse in browser
- 🐌 Slow for large datasets

**Supabase:**
- 📥 Query only needed rows
- ⚙️ Indexed database lookups
- 🚀 Fast, even with years of data

---

## 📖 Useful Supabase Queries

Once data is flowing, try these:

```sql
-- See latest CMG Online
SELECT * FROM cmg_online
ORDER BY datetime DESC
LIMIT 24;

-- Check data quality
SELECT date, COUNT(*) AS hours
FROM cmg_online
WHERE node = 'NVA_P.MONTT___220'
GROUP BY date
ORDER BY date DESC;

-- ML model accuracy over last week
SELECT
    AVG(absolute_error) AS mae,
    AVG(zero_classification_correct::int) * 100 AS accuracy_pct
FROM ml_forecast_accuracy
WHERE target_datetime > NOW() - INTERVAL '7 days';
```

---

## 🤝 Ready for Next Step?

Let me know when you've:
1. ✅ Run the schema SQL in Supabase
2. ✅ Added the secrets to GitHub

Then I'll:
1. Update the workflow to use dual-write
2. Create the other two dual-write scripts
3. We'll test on the next hourly run!
