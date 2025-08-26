# 🚀 DEPLOY TO VERCEL IN 3 MINUTES

## What You'll Get:
✅ **Live website** showing CMG predictions for Chiloé 220kV  
✅ **Auto-training ML model** using last 7 days of real CMG data  
✅ **48-hour predictions** updated every 5 minutes  
✅ **Beautiful dashboard** with interactive charts  
✅ **100% FREE hosting** on Vercel  

---

## Step 1: Prepare Files (30 seconds)

You have everything ready in the `vercel_deploy` folder:
```
vercel_deploy/
├── api/
│   └── predictions.py    # Backend that fetches & predicts
├── index.html            # Frontend dashboard
├── vercel.json          # Vercel configuration
├── requirements.txt     # Python dependencies
└── package.json         # Project info
```

---

## Step 2: Deploy with Vercel CLI (2 minutes)

### Option A: Using NPX (No installation needed)

1. Open terminal in the `vercel_deploy` folder:
```bash
cd vercel_deploy
```

2. Deploy with one command:
```bash
npx vercel
```

3. Follow the prompts:
   - **Set up and deploy?** → `Y`
   - **Which scope?** → Select your account
   - **Link to existing project?** → `N`
   - **Project name?** → `pudidi-cmg` (or press Enter for default)
   - **Directory?** → `./` (press Enter)
   - **Override settings?** → `N`

4. **That's it!** Your site is live at the URL shown (e.g., `https://pudidi-cmg-xxx.vercel.app`)

### Option B: Using Vercel CLI (If you have it installed)

```bash
cd vercel_deploy
vercel --prod
```

---

## Step 3: Visit Your Live Site! 🎉

After deployment, you'll get a URL like:
```
https://pudidi-cmg.vercel.app
```

Open it in your browser and you'll see:
- Real-time CMG data from the last 24 hours
- ML predictions for the next 48 hours
- Statistics and charts
- Auto-refresh every 5 minutes

---

## Alternative: Deploy via GitHub (5 minutes)

### 1. Push to GitHub:
```bash
cd vercel_deploy
git init
git add .
git commit -m "Pudidi CMG Prediction System"
git remote add origin https://github.com/YOUR_USERNAME/pudidi-cmg.git
git push -u origin main
```

### 2. Connect to Vercel:
1. Go to [vercel.com](https://vercel.com)
2. Click **"New Project"**
3. Import your GitHub repo
4. Click **"Deploy"**

---

## How It Works:

1. **Fetches Real Data**: Gets last 7 days of CMG from CHILOE_220 node
2. **Trains Model**: Quick RandomForest model with time features and lags
3. **Makes Predictions**: 48-hour forecast based on patterns
4. **Updates Live**: Auto-refreshes every 5 minutes

---

## Troubleshooting:

### "Module not found" error:
- Make sure `requirements.txt` is in the folder
- Vercel automatically installs Python packages

### No data showing:
- The SIP API might be down
- The app will show mock data as fallback

### Want to update the code?
```bash
# Make changes to files
vercel --prod  # Redeploy
```

---

## Monitor Your App:

### View logs:
```bash
vercel logs
```

### Check function status:
```bash
vercel inspect [deployment-url]
```

---

## Next Steps:

1. **Custom Domain**: Add your own domain in Vercel dashboard
2. **Improve Model**: Add weather data, more features
3. **Add Authentication**: Protect with password if needed
4. **Analytics**: Enable Vercel Analytics (free tier)

---

## 🎊 Congratulations! Your CMG prediction system is LIVE!

The system will:
- Fetch real CMG data every 5 minutes
- Train a new model with recent data
- Predict next 48 hours
- Display beautiful charts
- Run 100% free on Vercel

---

## Quick Test Your API:

Once deployed, test the API directly:
```bash
curl https://your-app.vercel.app/api/predictions
```

You should see JSON with predictions!

---

**Need help?** The deployment usually takes less than 3 minutes. If you see your URL in the terminal, it worked!