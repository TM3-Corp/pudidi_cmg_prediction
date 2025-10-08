# Gist Token Setup - Fix 403 Error

**Problem:** The 5PM snapshot workflow fails with:
```
❌ Failed to create Gist: 403
Response: {"message":"Resource not accessible by integration"...}
```

**Cause:** The default `GITHUB_TOKEN` doesn't have permission to create Gists.

**Solution:** Create a Personal Access Token (PAT) with Gist permissions.

---

## 📝 Step-by-Step Fix

### Step 1: Create Personal Access Token

1. **Go to GitHub Token Settings:**
   - Visit: https://github.com/settings/tokens
   - Or: Click your profile → Settings → Developer settings → Personal access tokens → Tokens (classic)

2. **Generate New Token:**
   - Click **"Generate new token"** → **"Generate new token (classic)"**

3. **Configure Token:**
   - **Note:** `CMG Snapshot Gist Token`
   - **Expiration:** No expiration (or 1 year if you prefer)
   - **Select scopes:**
     - ✅ **`gist`** ← ONLY check this box
     - ❌ Don't check anything else (for security)

4. **Generate and Copy:**
   - Click **"Generate token"** at the bottom
   - **Copy the token** immediately (you won't see it again!)
   - Example: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Step 2: Add Token to Repository Secrets

1. **Go to Repository Settings:**
   - Visit: https://github.com/TM3-Corp/pudidi_cmg_prediction/settings/secrets/actions
   - Or: Repository → Settings → Secrets and variables → Actions

2. **Create New Secret:**
   - Click **"New repository secret"**

3. **Configure Secret:**
   - **Name:** `CMG_GIST_TOKEN` (exactly this name!)
   - **Value:** Paste the token you copied (starts with `ghp_`)
   - Click **"Add secret"**

### Step 3: Verify Workflow is Updated

The workflow has been updated to use `CMG_GIST_TOKEN` instead of `GITHUB_TOKEN`.

**File:** `.github/workflows/cmg_5pm_snapshot.yml`
```yaml
- name: Capture 5PM CMG Programado Snapshot
  env:
    GITHUB_TOKEN: ${{ secrets.CMG_GIST_TOKEN }}  # ✅ Now uses PAT
    CMG_SNAPSHOT_GIST_ID: ${{ secrets.CMG_SNAPSHOT_GIST_ID }}
```

### Step 4: Test the Fix

**Option A: Wait for Next 5PM Run**
- The workflow runs automatically at 5PM Chilean time
- Check tomorrow at 5PM to see if it works

**Option B: Manual Test (Recommended)**
1. Go to: https://github.com/TM3-Corp/pudidi_cmg_prediction/actions/workflows/cmg_5pm_snapshot.yml
2. Click **"Run workflow"** → **"Run workflow"** (green button)
3. Wait ~30 seconds
4. Click on the running workflow to see logs
5. Look for:
   ```
   ✅ Created new snapshot Gist: [gist-id]
   URL: https://gist.github.com/[gist-id]
   ```

---

## ✅ Success Indicators

**After token is added, you should see:**

```
============================================================
CMG PROGRAMADO 5PM SNAPSHOT CAPTURE
============================================================
Time: 2025-10-07 17:10:44 -03

📊 Loading current CMG Programado forecast...
   Found forecast: 72 hours
   Dates: ['2025-10-07', '2025-10-08', '2025-10-09']

📸 Creating snapshot...
   Snapshot captured: 2025-10-07 17:10 -03
   Forecast hours: 72

📥 Fetching existing snapshots...
   Found 0 existing snapshots

📤 Uploading to Gist...
✅ Created new snapshot Gist: abc123def456  ← SUCCESS!
   URL: https://gist.github.com/abc123def456
   ⚠️  Save this Gist ID as CMG_SNAPSHOT_GIST_ID secret!

============================================================
✅ SNAPSHOT CAPTURED SUCCESSFULLY
============================================================
```

---

## 🔐 Security Notes

**Why create a separate token?**
- The default `GITHUB_TOKEN` has minimal permissions (intentionally)
- Creating Gists requires additional `gist` scope
- Using a PAT with only `gist` scope is secure and minimal

**Token Safety:**
- ✅ Only grant `gist` scope (nothing else)
- ✅ Store in repository secrets (encrypted, not visible in logs)
- ✅ Use "No expiration" or set reminder to renew annually
- ❌ Never commit the token to code
- ❌ Never share the token

**What can this token do?**
- Create/update/delete Gists on your account
- Nothing else (no repo access, no admin, no packages)

---

## 📊 After First Successful Run

Once the workflow runs successfully for the first time, it will:

1. **Create a new Gist** with your snapshot data
2. **Print the Gist ID** in the logs
3. **Save the Gist ID** to `.cmg_snapshot_gist_id` file

**You need to add the Gist ID as a secret:**

1. Copy the Gist ID from the workflow logs (e.g., `abc123def456`)
2. Go to: https://github.com/TM3-Corp/pudidi_cmg_prediction/settings/secrets/actions
3. Click **"New repository secret"**
4. Name: `CMG_SNAPSHOT_GIST_ID`
5. Value: The Gist ID you copied
6. Click **"Add secret"**

**Why?** This tells future runs to UPDATE the existing Gist instead of creating a new one each time.

---

## 🐛 Troubleshooting

### Still getting 403 after adding token?

**Check:**
1. Token has `gist` scope ✅
2. Secret name is exactly `CMG_GIST_TOKEN` (case-sensitive)
3. Workflow has been updated (should already be done)
4. Token hasn't expired

### Getting 404 instead of 403?

**This means:**
- Token is working
- But CMG_SNAPSHOT_GIST_ID secret is set to a Gist that doesn't exist

**Fix:**
- Delete the `CMG_SNAPSHOT_GIST_ID` secret (or leave it empty)
- Run workflow again - it will create a new Gist
- Then add the new Gist ID as secret

### Workflow not running at 5PM?

**Check:**
- Repository is active (GitHub disables workflows after 60 days of inactivity)
- Workflow file is in `main` branch
- Cron schedule: `0 20 * * *` (20:00 UTC = 17:00 Chilean time in winter)

---

## 📝 Summary Checklist

- [ ] Create Personal Access Token with `gist` scope
- [ ] Add token as `CMG_GIST_TOKEN` secret in repository
- [ ] Workflow updated to use `CMG_GIST_TOKEN` (already done ✅)
- [ ] Test with manual workflow run
- [ ] After first success, add `CMG_SNAPSHOT_GIST_ID` secret
- [ ] Verify daily 5PM runs work

---

**Once complete, your 5PM snapshots will automatically upload to Gist every day!** 🎉
