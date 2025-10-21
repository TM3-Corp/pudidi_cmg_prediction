# Supabase Database Setup

## 📋 Quick Start

### Step 1: Run the Schema

1. Go to your Supabase dashboard: https://btyfbrclgmphcjgrvcgd.supabase.co
2. Click **SQL Editor** in the left sidebar
3. Click **New query**
4. Copy the entire contents of `schema.sql` and paste it
5. Click **Run** (or press Cmd/Ctrl + Enter)

You should see: "Success. No rows returned"

### Step 2: Verify Tables

Click **Table Editor** in the left sidebar. You should see:
- ✅ `cmg_online` (0 rows)
- ✅ `cmg_programado` (0 rows)
- ✅ `ml_predictions` (0 rows)

### Step 3: Get Service Role Key

1. Go to **Settings → API**
2. Under **Project API keys**, find `service_role`
3. Click **Reveal** and copy the key
4. Save it - you'll need it for GitHub Secrets

## 🗃️ Database Schema

### Table 1: `cmg_online`
Stores actual CMG values from SIP API.

**Columns:**
- `datetime`: When the CMG value occurred (with timezone)
- `date`, `hour`: Extracted date and hour for easy filtering
- `node`: Electrical node (e.g., `NVA_P.MONTT___220`)
- `cmg_usd`: CMG value in USD/MWh
- `source`: Data source (default: `SIP_API_v4`)

**Example Query:**
```sql
-- Get last 24 hours of CMG Online for PMontt220
SELECT datetime, hour, cmg_usd
FROM cmg_online
WHERE node = 'NVA_P.MONTT___220'
  AND datetime > NOW() - INTERVAL '24 hours'
ORDER BY datetime DESC;
```

### Table 2: `cmg_programado`
Stores forecast values from Coordinador website.

**Columns:**
- `forecast_datetime`: When the forecast was made
- `target_datetime`: What hour is being forecasted
- `node`: Electrical node (e.g., `PMontt220`)
- `cmg_usd`: Forecasted CMG value in USD/MWh
- `source`: Data source (default: `Coordinador`)

**Example Query:**
```sql
-- Get all forecasts made today for tomorrow
SELECT forecast_hour, target_hour, node, cmg_usd
FROM cmg_programado
WHERE forecast_date = CURRENT_DATE
  AND target_date = CURRENT_DATE + 1
ORDER BY target_hour;
```

### Table 3: `ml_predictions`
Stores ML model predictions.

**Columns:**
- `forecast_datetime`: When the prediction was made
- `target_datetime`: What hour is being predicted
- `horizon`: Forecast horizon (t+1, t+2, ..., t+24)
- `cmg_predicted`: Final predicted CMG value
- `prob_zero`: Probability of CMG being zero (0.0-1.0)
- `threshold`: Decision threshold used
- `value_pred`: Regression value before thresholding
- `model_version`: ML model version

**Example Query:**
```sql
-- Get latest 24-hour forecast
SELECT horizon, target_datetime, cmg_predicted, prob_zero
FROM ml_predictions
WHERE forecast_datetime = (SELECT MAX(forecast_datetime) FROM ml_predictions)
ORDER BY horizon;
```

## 📊 Useful Views

The schema includes pre-built views for common queries:

### `latest_cmg_online`
Latest CMG value per node.
```sql
SELECT * FROM latest_cmg_online;
```

### `latest_ml_predictions`
Latest ML prediction per horizon.
```sql
SELECT * FROM latest_ml_predictions;
```

### `ml_forecast_accuracy`
Compare ML predictions vs actual values.
```sql
-- Get model performance over last 7 days
SELECT
    AVG(absolute_error) AS mae,
    AVG(zero_classification_correct::int) * 100 AS zero_accuracy_pct
FROM ml_forecast_accuracy
WHERE target_datetime > NOW() - INTERVAL '7 days';
```

## 🔒 Security

Row Level Security (RLS) is enabled:
- ✅ **Public read access**: Anyone can query data (needed for frontend)
- ✅ **Service role write access**: Only backend with service_role key can write
- ✅ **No public writes**: Prevents unauthorized data modification

## 🚀 Next Steps

After running the schema:
1. Get your service_role key from Settings → API
2. Add to GitHub Secrets:
   - `SUPABASE_URL`: `https://btyfbrclgmphcjgrvcgd.supabase.co`
   - `SUPABASE_SERVICE_KEY`: (your service_role key)
3. Run the dual-write scripts to start populating data
