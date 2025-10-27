# SUPABASE MIGRATION GUIDE
## Replacing GitHub Gist with Production Database

---

## 🎯 WHY WE'RE MIGRATING

**Current Problem**: GitHub Gist returns `429 Too Many Requests` errors because:
- Gist has strict rate limits (60 requests/hour for unauthenticated)
- Your dashboard makes multiple requests (3 Gists × multiple users)
- Gist was never designed for production applications

**Supabase Solution**:
- ✅ Real PostgreSQL database (not a hack)
- ✅ Auto-generated RESTful API  
- ✅ Generous free tier (500MB storage, 2GB bandwidth/month)
- ✅ No rate limiting issues
- ✅ Real-time capabilities (optional future feature)
- ✅ Row Level Security for data protection

---

## 📋 MIGRATION CHECKLIST

### STEP 1: Run Database Schema (5 minutes)

1. Go to your Supabase project SQL Editor:  
   **https://supabase.com/dashboard/project/btyfbrclgmphcjgrvcgd/editor**

2. Click **"New Query"**

3. Copy the entire contents of `supabase/schema.sql`

4. Paste into the SQL editor

5. Click **"Run"** (or press Cmd/Ctrl + Enter)

6. Verify success - you should see:
   ```
   ✅ Created tables: cmg_online, cmg_programado, ml_predictions, system_metadata
   ✅ Created indexes
   ✅ Enabled Row Level Security
   ✅ Created helper functions and views
   ```

---

### STEP 2: Get API Credentials (2 minutes)

1. Go to **Project Settings → API**:  
   **https://supabase.com/dashboard/project/btyfbrclgmphcjgrvcgd/settings/api**

2. Copy these values:

   **Project URL**:
   ```
   https://btyfbrclgmphcjgrvcgd.supabase.co
   ```

   **Project API keys**:
   - `anon` key (public) - for frontend reads
   - `service_role` key (secret) - for backend writes

3. **Store these securely** - you'll need to add them as environment variables

---

### STEP 3: Add Environment Variables

#### A) GitHub Actions (for ETL scripts)

1. Go to your GitHub repository settings:  
   **https://github.com/TM3-Corp/pudidi_cmg_prediction/settings/secrets/actions**

2. Click **"New repository secret"** and add:

   | Name | Value |
   |------|-------|
   | `SUPABASE_URL` | `https://btyfbrclgmphcjgrvcgd.supabase.co` |
   | `SUPABASE_SERVICE_KEY` | (paste your service_role key) |

#### B) Vercel (for API endpoints)

1. Go to Vercel project settings:  
   **https://vercel.com/pauls-projects-4b2f38b6/pudidi_cmg_prediction/settings/environment-variables**

2. Add the same environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`

3. **IMPORTANT**: For Railway ML Backend, also add:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY` (use anon key for reads)

#### C) Local Development (optional)

Create a `.env` file in the project root:

```bash
SUPABASE_URL=https://btyfbrclgmphcjgrvcgd.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_key_here
```

**⚠️ NEVER commit `.env` to git!** (Already in `.gitignore`)

---

### STEP 4: Run Initial Data Migration (one-time)

Once you provide the API keys, I'll create a migration script that will:

1. Fetch all existing data from GitHub Gists
2. Transform and insert into Supabase tables
3. Verify data integrity
4. Generate migration report

This script will:
- Migrate CMG Online historical data (last 30 days)
- Migrate CMG Programado forecasts
- Migrate latest ML predictions

**Estimated migration time**: 2-5 minutes depending on data volume

---

### STEP 5: Update ETL Scripts

I will update these 3 scripts to write to Supabase instead of Gist:

1. **`scripts/store_historical.py`** → CMG Online
2. **`scripts/store_cmg_programado.py`** → CMG Programado  
3. **`scripts/store_ml_predictions.py`** → ML Predictions

Changes will be:
- Replace `requests.post` to Gist with `supabase_client.insert_*_batch()`
- Keep existing cache files (for backwards compatibility during transition)
- Add error handling and retry logic

---

### STEP 6: Update Frontend

I will update these files to read from Supabase API:

1. **`public/index.html`** - Main dashboard
2. **`public/forecast_comparison.html`** - Comparison view
3. **`public/js/optimizer.js`** - Optimizer data fetching

Changes will be:
- Replace Gist URLs with Supabase REST API endpoints
- Use anon key for public read access
- Add caching headers for better performance
- Keep fallback to local cache if API fails

**Example API endpoints**:
```javascript
// OLD (Gist - rate limited ❌)
https://gist.githubusercontent.com/PVSH97/8d7864eb26acf6e780d3c0f7fed69365/raw/cmg_online_historical.json

// NEW (Supabase - no limits ✅)
https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1/cmg_online?order=datetime.desc&limit=100
```

---

## 📊 BEFORE VS AFTER COMPARISON

| Aspect | GitHub Gist (Current) | Supabase (New) |
|--------|----------------------|-----------------|
| Rate Limits | 60 req/hour (❌) | 2GB bandwidth/month (✅) |
| Latency | ~500-1000ms | ~50-100ms |
| Query Flexibility | None (full file only) | SQL queries, filters, pagination |
| Data Structure | JSON files | PostgreSQL tables |
| API | Raw file URLs | RESTful API |
| Real-time | No | Yes (optional) |
| Security | Public only | Row Level Security |
| Cost | Free (but unusable) | Free tier sufficient |

---

## 🔧 ROLLBACK PLAN (IF NEEDED)

If anything goes wrong during migration, we can instantly rollback:

1. **ETL scripts** still write to local cache files
2. **Frontend** can use cache files as fallback
3. **Gist data** remains unchanged during testing

**Migration is SAFE and REVERSIBLE!**

---

## 🚀 NEXT STEPS

**Right now, please:**

1. ✅ Run `supabase/schema.sql` in Supabase SQL Editor
2. ✅ Get your API credentials (URL + service_role key + anon key)
3. ✅ Add environment variables to GitHub Actions and Vercel
4. ✅ Reply with "Schema created and keys added" when ready

**Then I will:**

1. Create migration script to import existing Gist data
2. Update all 3 ETL scripts to write to Supabase
3. Update frontend to read from Supabase
4. Test end-to-end
5. Deploy to production

---

## 📚 SUPABASE API REFERENCE

Once migration is complete, you can query your data directly:

### Get latest ML predictions:
```bash
curl "https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1/rpc/get_latest_ml_predictions" \
  -H "apikey: YOUR_ANON_KEY"
```

### Get CMG Online for specific date:
```bash
curl "https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1/cmg_online?date=eq.2025-10-22" \
  -H "apikey: YOUR_ANON_KEY"
```

### Get upcoming CMG Programado:
```bash
curl "https://btyfbrclgmphcjgrvcgd.supabase.co/rest/v1/cmg_programado?date=gte.2025-10-22&order=datetime.asc" \
  -H "apikey: YOUR_ANON_KEY"
```

---

## 💡 TIPS FOR SUCCESS

1. **Test in staging first** - Use a separate Supabase project for testing if desired
2. **Monitor usage** - Check Supabase dashboard for API usage and performance
3. **Set up alerts** - Configure email alerts for error rates or usage limits
4. **Backup data** - Supabase has automatic backups, but keep local copies too

---

## 🆘 TROUBLESHOOTING

**"Schema creation failed"**
- Check for syntax errors in SQL
- Ensure you're using the correct project
- Try running tables one at a time

**"Can't connect to Supabase"**
- Verify URL is correct
- Check API key is service_role (not anon) for writes
- Ensure environment variables are set correctly

**"Rate limit still occurring"**
- Check if frontend is using old Gist URLs
- Verify Supabase API endpoints are configured
- Clear browser cache

---

## ✅ READY TO PROCEED?

Once you've completed Steps 1-3 above, let me know and I'll:
- Create the migration script
- Update all ETL scripts
- Update the frontend
- Test everything end-to-end
- Deploy to production

**Expected total migration time**: 30-45 minutes  
**Expected downtime**: Zero (gradual cutover)

Let me know when you're ready to continue!
