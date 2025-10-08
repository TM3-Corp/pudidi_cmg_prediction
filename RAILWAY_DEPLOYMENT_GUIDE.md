# 🚂 Railway Deployment - Quick Start Guide

## 📋 What You'll Deploy

- **Railway**: ML backend with 103MB of models (FastAPI)
- **Vercel**: Dashboard with lightweight proxy APIs

---

## 🚀 Step-by-Step Deployment

### Step 1: Create Railway Account

1. Go to: https://railway.app/
2. Sign up with GitHub (free)
3. You get **$5 credit/month** (plenty for this!)

---

### Step 2: Deploy to Railway

**Option A: Via Railway Dashboard (Recommended)**

1. Go to: https://railway.app/new
2. Click **"Deploy from GitHub repo"**
3. Select: `TM3-Corp/pudidi_cmg_prediction`
4. Railway will auto-detect the Dockerfile
5. Click **"Deploy Now"**

**Option B: Via CLI**

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Navigate to your project
cd /home/paul/projects/Pudidi/pudidi_CMG_prediction_system/vercel_deploy

# Link to Railway
railway link

# Deploy
railway up
```

---

### Step 3: Get Railway URL

After deployment completes:

**Via Dashboard**:
1. Go to your Railway project
2. Click on the service
3. Go to **Settings** → **Domains**
4. Click **"Generate Domain"**
5. Copy the URL (e.g., `https://pudidi-ml-backend-production.up.railway.app`)

**Via CLI**:
```bash
railway status
```

---

### Step 4: Configure Vercel

1. Go to: https://vercel.com/tm3-corp/pudidicmgprediction
2. Click **Settings** → **Environment Variables**
3. Add new variable:
   - **Name**: `RAILWAY_ML_URL`
   - **Value**: `https://your-railway-url.up.railway.app` (from Step 3)
   - **Environment**: Production ✅ Preview ✅ Development ✅
4. Click **Save**

---

### Step 5: Redeploy Vercel

Trigger a new Vercel deployment:

```bash
# Already done - Vercel auto-deploys on git push
# Or manually trigger from Vercel dashboard
```

---

## ✅ Testing

### Test Railway Backend Directly

```bash
# Replace with your Railway URL
RAILWAY_URL="https://your-railway-url.up.railway.app"

# Health check
curl $RAILWAY_URL/health

# ML Predictions
curl $RAILWAY_URL/api/ml_forecast | jq '.predictions[0]'

# Thresholds
curl $RAILWAY_URL/api/ml_thresholds | jq '.thresholds[0]'
```

### Test Via Vercel Proxy

```bash
# ML Predictions (proxied through Vercel)
curl https://pudidicmgprediction.vercel.app/api/ml_forecast | jq '.predictions[0]'

# Thresholds (proxied through Vercel)
curl https://pudidicmgprediction.vercel.app/api/ml_thresholds | jq '.thresholds[0]'
```

---

## 🎯 Expected Results

**Railway Health Check**:
```json
{
  "status": "healthy",
  "predictions_available": true,
  "thresholds_available": true
}
```

**ML Predictions**:
```json
{
  "success": true,
  "predictions_count": 24,
  "predictions": [
    {
      "datetime": "2025-09-06 02:00:00",
      "cmg_predicted": 0.0,
      "zero_probability": 0.4143,
      "decision_threshold": 0.3382
    }
  ]
}
```

---

## 💰 Cost

**Railway Free Tier**:
- $5 credit/month
- ~500 execution hours
- Sufficient for this backend

**Usage Estimate**:
- Always-on FastAPI backend: ~$5/month
- **Covered by free tier!** 🎉

---

## 🔄 Auto-Deployment

Railway auto-deploys when you push to GitHub:

1. **Update models locally**:
   ```bash
   python scripts/ml_hourly_forecast.py
   ```

2. **Commit and push**:
   ```bash
   git add data/ml_predictions/
   git commit -m "Update ML predictions"
   git push origin main
   ```

3. **Railway auto-deploys** ✨

---

## 🐛 Troubleshooting

### "Failed to connect to ML prediction service"

**Check**:
1. Railway service is running: https://railway.app/dashboard
2. `RAILWAY_ML_URL` is set in Vercel
3. Railway URL is correct (no trailing slash)

**Fix**:
```bash
# Check Railway logs
railway logs

# Restart Railway service
railway restart
```

### Railway deployment fails

**Check Logs**:
```bash
railway logs
```

**Common Issues**:
- Dockerfile path: Should be `railway_ml_backend/Dockerfile`
- Missing files: Ensure models and data are committed to Git

---

## 📊 Architecture Diagram

```
┌─────────────────┐
│   User Browser  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  Vercel (Dashboard)         │
│  - Next.js/React UI         │
│  - Lightweight proxy APIs   │
└────────┬────────────────────┘
         │ RAILWAY_ML_URL
         ▼
┌─────────────────────────────┐
│  Railway (ML Backend)       │
│  - FastAPI server           │
│  - 103MB ML models          │
│  - 144 trained models       │
│  - Predictions JSON         │
└─────────────────────────────┘
```

---

## 🎉 Success!

Once deployed, your architecture:

✅ **Vercel**: Fast dashboard (stays under 250MB)
✅ **Railway**: ML backend (no size limits)
✅ **Free**: Both covered by free tiers
✅ **Auto-deploy**: Push to GitHub → Railway updates
✅ **Scalable**: Upgrade Railway plan if needed

Your ML predictions are now live! 🚀

---

## 📚 Next Steps

1. ✅ Deploy Railway backend
2. ✅ Set `RAILWAY_ML_URL` in Vercel
3. ✅ Test endpoints
4. 📊 Integrate into dashboard (see `ML_DASHBOARD_INTEGRATION.md`)
5. ⏰ Set up GitHub Actions for hourly predictions (optional)

**Questions?** Check Railway docs: https://docs.railway.app/
