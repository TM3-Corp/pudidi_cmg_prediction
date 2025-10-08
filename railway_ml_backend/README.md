# 🚂 Railway ML Backend

FastAPI backend for CMG ML predictions, deployed on Railway.

---

## 🎯 Architecture

```
User Browser
    ↓
Vercel (Dashboard + Proxy APIs)
    ↓
Railway (ML Backend + Models)
    ↓
Returns Predictions
```

**Why Split?**
- ✅ **Vercel**: Fast static hosting, great for dashboard
- ✅ **Railway**: No size limits, perfect for 103MB of ML models
- ✅ **Cost**: Both have generous free tiers

---

## 📦 What's Deployed

- **FastAPI Server**: Lightweight Python API
- **ML Models**: 103MB (144 models total)
- **Data**: Latest predictions JSON
- **Endpoints**:
  - `GET /` - API root & health
  - `GET /health` - Health check
  - `GET /api/ml_forecast` - 24-hour predictions
  - `GET /api/ml_thresholds` - Decision thresholds

---

## 🚀 Deployment Steps

### 1. Install Railway CLI

```bash
npm install -g @railway/cli
```

### 2. Login to Railway

```bash
railway login
```

### 3. Create New Project

```bash
# Navigate to project root
cd /home/paul/projects/Pudidi/pudidi_CMG_prediction_system/vercel_deploy

# Initialize Railway project
railway init

# Name it: "pudidi-ml-backend"
```

### 4. Deploy

```bash
# Deploy from current directory
railway up

# Or link to GitHub and auto-deploy
railway link
```

### 5. Get Your Railway URL

```bash
railway status
```

You'll get something like: `https://pudidi-ml-backend-production.up.railway.app`

### 6. Configure Vercel Environment Variable

In Vercel dashboard:
1. Go to your project → Settings → Environment Variables
2. Add new variable:
   - **Name**: `RAILWAY_ML_URL`
   - **Value**: `https://your-railway-url.up.railway.app`
   - **Scope**: Production, Preview, Development

### 7. Redeploy Vercel

```bash
git push origin main
```

Done! Your Vercel APIs will now proxy to Railway.

---

## 🧪 Testing Locally

### 1. Run Railway Backend Locally

```bash
cd railway_ml_backend
pip install -r requirements.txt
python main.py
```

Server runs on: `http://localhost:8000`

### 2. Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Predictions
curl http://localhost:8000/api/ml_forecast | jq

# Thresholds
curl http://localhost:8000/api/ml_thresholds | jq
```

---

## 📊 API Endpoints

### `GET /`
Root endpoint with API info

**Response**:
```json
{
  "service": "CMG ML Prediction API",
  "status": "running",
  "version": "1.0.0"
}
```

### `GET /health`
Health check

**Response**:
```json
{
  "status": "healthy",
  "predictions_available": true,
  "thresholds_available": true
}
```

### `GET /api/ml_forecast`
24-hour ML predictions

**Response**:
```json
{
  "success": true,
  "predictions_count": 24,
  "predictions": [
    {
      "datetime": "2025-09-06 02:00:00",
      "cmg_predicted": 0.0,
      "zero_probability": 0.4143,
      "confidence_lower": 32.67,
      "confidence_upper": 62.09
    }
  ]
}
```

### `GET /api/ml_thresholds`
Decision threshold configuration

**Response**:
```json
{
  "success": true,
  "thresholds": [
    {
      "horizon": 1,
      "optimal_threshold": 0.3382,
      "min_allowed": 0.2706,
      "max_allowed": 0.4058
    }
  ]
}
```

---

## 🔧 Configuration

### Environment Variables (Railway)

Set in Railway dashboard:

- `PORT` - Automatically set by Railway (default: 8000)
- `PYTHON_VERSION` - Set to `3.11` (optional)

### Dockerfile

The Dockerfile:
1. Uses Python 3.11 slim image
2. Copies entire project (models + data)
3. Installs minimal dependencies (FastAPI, uvicorn)
4. Runs on port 8000

---

## 💰 Cost Estimate

**Railway Free Tier**:
- $5 credit/month
- ~500 hours of uptime
- Plenty for this use case

**Expected Usage**:
- Always-on backend: ~$5/month
- API calls: Free (within limits)

**Total**: $0-5/month (covered by free tier)

---

## 🔄 Updating Models

When you retrain models:

1. **Update local predictions**:
   ```bash
   python scripts/ml_hourly_forecast.py
   ```

2. **Commit changes**:
   ```bash
   git add data/ml_predictions/ models_24h/
   git commit -m "Update ML models"
   git push
   ```

3. **Railway auto-deploys** (if linked to GitHub)

Or manually:
```bash
railway up
```

---

## 🐛 Troubleshooting

### Railway deployment fails

Check logs:
```bash
railway logs
```

### API returns 404

- Verify predictions file exists: `data/ml_predictions/latest.json`
- Check Railway logs for errors

### Vercel proxy fails

- Verify `RAILWAY_ML_URL` environment variable is set
- Check Railway service is running: `railway status`
- Test Railway endpoint directly

---

## 📝 Files

- `main.py` - FastAPI application
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration
- `railway.json` - Railway config
- `.dockerignore` - Exclude files from Docker build

---

## 🎉 Benefits

✅ **No size limits** (unlike Vercel's 250MB)
✅ **Better performance** (dedicated container)
✅ **Easy scaling** (upgrade plan if needed)
✅ **Clean separation** (ML logic separate from dashboard)
✅ **GitHub integration** (auto-deploy on push)

---

**Ready to deploy!** Follow the steps above and you'll have your ML backend running on Railway in minutes.
