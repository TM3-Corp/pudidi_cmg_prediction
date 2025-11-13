# GitHub Secrets Setup for Supabase Integration

This guide explains how to add Supabase credentials to GitHub Actions secrets.

## Required Secrets

You need to add the following secrets to your GitHub repository:

### 1. SUPABASE_URL
- **Value**: `https://btyfbrclgmphcjgrvcgd.supabase.co`
- **Purpose**: Your Supabase project URL
- **Used by**: All ETL scripts (CMG Online, ML Predictions, CMG Programado)

### 2. SUPABASE_SERVICE_KEY
- **Value**: (provided by user - service_role key)
- **Purpose**: Service role key for write access to Supabase
- **Used by**: ETL scripts that write data to Supabase
- **⚠️ Security**: This is a SECRET key with full database access. Never commit it to git!

## How to Add Secrets to GitHub Actions

1. Go to your repository on GitHub:
   ```
   https://github.com/TM3-Corp/pudidi_cmg_prediction
   ```

2. Navigate to **Settings** → **Secrets and variables** → **Actions**:
   ```
   https://github.com/TM3-Corp/pudidi_cmg_prediction/settings/secrets/actions
   ```

3. Click **"New repository secret"**

4. Add each secret:

   **First Secret:**
   - Name: `SUPABASE_URL`
   - Value: `https://btyfbrclgmphcjgrvcgd.supabase.co`
   - Click **"Add secret"**

   **Second Secret:**
   - Name: `SUPABASE_SERVICE_KEY`
   - Value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTAwOTUyOSwiZXhwIjoyMDc2NTg1NTI5fQ.a1W8TfNbQ9dVQXmJtQmFBpWQXyZyJ8LgZJ5pLe7MZIi8`
   - Click **"Add secret"**

## Verification

After adding the secrets:

1. Go to **Actions** tab in your repository
2. Find the workflow `cmg_online_hourly.yml`
3. Click **"Run workflow"** → **"Run workflow"** to trigger it manually
4. Watch the logs to verify:
   - ETL scripts run successfully
   - Supabase writes complete without errors
   - Look for messages like:
     ```
     ☁️  Writing new records to Supabase...
     ✅ Wrote X records to Supabase
     ```

## Troubleshooting

### Secret not working
- Make sure secret names match exactly (case-sensitive)
- Check that the service_role key is correct (not anon key)
- Verify the Supabase URL is correct

### ETL still using Gist only
- Check GitHub Actions logs for errors
- Ensure secrets are added to the correct repository
- Verify the workflow has access to secrets

### API endpoints not using Supabase
- For Vercel deployment, you also need to add secrets there:
  1. Go to Vercel project settings
  2. Add Environment Variables:
     - `SUPABASE_URL`
     - `SUPABASE_SERVICE_KEY` (for ETL scripts)
     - `SUPABASE_ANON_KEY` (for API endpoints - read-only)

## Anon Key (for Frontend/API)

The anon key is already hard-coded in the frontend JavaScript files and API endpoints. It provides read-only access and is safe to expose publicly:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwMDk1MjksImV4cCI6MjA3NjU4NTUyOX0.WQK2xJMa6YWUABsXq2MQwJGpOQHt5GfZJ5pLe7MZIi8
```

This is already configured in:
- `public/js/supabase-client.js`
- `lib/utils/supabase_client.py` (fallback)

## Summary

✅ **What's Updated:**
- All 4 frontend pages now fetch from Supabase (via API endpoints)
- All 3 ETL scripts now write to Supabase (dual-write with Gist)
- API endpoints (`/api/cmg/current`, `/api/ml_forecast`, `/api/cache`) read from Supabase

✅ **Next Steps:**
1. Add the 2 GitHub secrets (SUPABASE_URL and SUPABASE_SERVICE_KEY)
2. Trigger a manual workflow run to test
3. Verify data appears correctly on https://pudidicmgprediction.vercel.app
4. Monitor Supabase dashboard for incoming data

---

**Date**: 2025-11-13
**Branch**: `claude/migrate-to-supabase-011CUzraym9qhZV7Wnzjbn16`
