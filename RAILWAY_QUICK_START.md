# 🚂 Railway Deployment - Quick Start

## ✅ What We Fixed

1. **Railway Configuration**: Added `railway.json` + `Procfile` in root
2. **Vercel Size Issue**: Updated `.vercelignore` to exclude 103MB of ML models
3. **Docker Configuration**: Fixed Dockerfile paths
4. **Tested Locally**: ✅ All endpoints working perfectly

---

## 🚀 Deploy to Railway (3 Steps)

### Option A: GitHub Integration (Recommended - Auto-Deploy)

1. **Go to Railway Dashboard**
   - Visit: https://railway.app/new
   - Click: "Deploy from GitHub repo"
   - Select: `TM3-Corp/pudidi_cmg_prediction`
   - Click: "Deploy Now"

2. **Configure Root Directory**
   - Railway will auto-detect the Dockerfile
   - If asked, set root directory: `/` (default)
   - Railway will use: `railway_ml_backend/Dockerfile`

3. **Get Your Railway URL**
   - After deployment completes (2-3 minutes)
   - Click "Settings" → "Domains"
   - Copy the URL: `https://your-app.up.railway.app`

### Option B: Railway CLI

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Navigate to project
cd /home/paul/projects/Pudidi/pudidi_CMG_prediction_system/vercel_deploy

# 4. Deploy
railway up

# 5. Get URL
railway status
```

---

## 🎯 Next: Configure Vercel

After Railway is deployed:

1. **Go to Vercel Dashboard**
   - Visit: https://vercel.com/tm3-corp/pudidicmgprediction/settings/environment-variables

2. **Add Environment Variable**
   - Name: `RAILWAY_ML_URL`
   - Value: `https://your-railway-url.up.railway.app`
   - Scope: ✅ Production ✅ Preview ✅ Development

3. **Redeploy Vercel**
   ```bash
   git push origin main
   ```

   Or in Vercel Dashboard → Deployments → Click "Redeploy"

---

## ✅ Testing

### Test Railway API Directly

```bash
# Health check
curl https://your-railway-url.up.railway.app/health

# ML Predictions
curl https://your-railway-url.up.railway.app/api/ml_forecast

# Thresholds
curl https://your-railway-url.up.railway.app/api/ml_thresholds
```

### Test Vercel Proxy

```bash
# After configuring RAILWAY_ML_URL in Vercel
curl https://pudidicmgprediction.vercel.app/api/ml_forecast

curl https://pudidicmgprediction.vercel.app/api/ml_thresholds
```

---

## 📊 Architecture

```
User Browser
    ↓
Vercel Dashboard (Lightweight - <10MB)
    ↓ (proxy via RAILWAY_ML_URL)
Railway ML Backend (Heavy - 103MB models)
    ↓
Returns ML Predictions
```

**Benefits:**
- ✅ Vercel: Under 250MB limit (models excluded)
- ✅ Railway: No size limits for ML models
- ✅ Both: Free tiers available
- ✅ Auto-deploy: Push to GitHub → Auto-deploy both

---

## 🐛 Troubleshooting

### Railway Error: "No start command found"

**Fixed!** ✅ We added:
- `railway.json` with Dockerfile config
- `Procfile` as fallback

### Vercel Error: "Function exceeds 250MB"

**Fixed!** ✅ We updated `.vercelignore` to exclude:
- `models_24h/` (103MB)
- `railway_ml_backend/`
- `data/ml_predictions/`

### Railway Logs Show Error

```bash
# Via Dashboard
Railway Dashboard → Your Service → Logs

# Via CLI
railway logs
```

### Vercel Can't Connect to Railway

1. Check Railway is running: `curl https://your-railway-url.up.railway.app/health`
2. Verify `RAILWAY_ML_URL` in Vercel: Settings → Environment Variables
3. Redeploy Vercel after setting env var

---

## 💰 Cost

- **Railway Free Tier**: $5 credit/month (enough for this!)
- **Vercel Free Tier**: Unlimited (hobby projects)
- **Total**: $0/month 🎉

---

## 📝 Files Changed

```
vercel_deploy/
├── railway.json          ← NEW (Railway config)
├── Procfile             ← NEW (Fallback start command)
├── .vercelignore        ← UPDATED (Exclude models)
└── railway_ml_backend/
    ├── Dockerfile       ← UPDATED (Fixed paths)
    ├── main.py          ← ✅ Working
    └── requirements.txt ← ✅ Minimal deps
```

---

**Ready to Deploy! 🚀**

Follow Option A above (GitHub Integration) for the easiest deployment experience.
