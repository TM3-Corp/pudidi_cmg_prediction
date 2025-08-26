# Production Setup - Complete 24/7 Data System

## Architecture Overview

```
┌─────────────────────────────────────┐
│      Daily Fetch (3 AM)             │
│   fetch_complete_daily.py           │
│                                      │
│  • Fetches ALL pages (~440)         │
│  • Takes ~18 minutes per day        │
│  • Ensures 24/24 hour coverage      │
└──────────────┬──────────────────────┘
               │
               ▼ Stores
┌─────────────────────────────────────┐
│     SQLite Database                 │
│      cmg_data.db                    │
│                                      │
│  Tables:                            │
│  • cmg_data (historical)            │
│  • weather_data                     │
│  • fetch_log (monitoring)           │
└──────────────┬──────────────────────┘
               │
               ▼ Serves
┌─────────────────────────────────────┐
│        Fast API                     │
│   predictions_from_db.py            │
│                                      │
│  • Instant response (<100ms)        │
│  • No real-time API calls           │
│  • ML predictions from patterns     │
└─────────────────────────────────────┘
```

## Setup Instructions

### 1. Initial Setup

```bash
cd /home/paul/projects/Pudidi/pudidi_CMG_prediction_system/vercel_deploy

# Install dependencies
pip install requests sqlite3 numpy pytz

# Test the fetcher
python3 fetch_complete_daily.py
```

### 2. Setup Cron Job for Daily Fetch

```bash
# Edit crontab
crontab -e

# Add this line (runs at 3 AM Chile time daily)
0 3 * * * /usr/bin/python3 /home/paul/projects/Pudidi/pudidi_CMG_prediction_system/vercel_deploy/fetch_complete_daily.py >> /var/log/cmg_fetch.log 2>&1
```

### 3. Initial Data Population

For first time setup, fetch last 30 days:

```python
# In Python console
from fetch_complete_daily import CompleteDailyFetcher

fetcher = CompleteDailyFetcher()
fetcher.fetch_multiple_days(30)  # Will take ~9 hours total
```

Or fetch just recent days to start:

```python
fetcher.fetch_multiple_days(7)  # ~2 hours
```

### 4. Deploy API

#### Option A: Replace current Vercel API

```bash
# Backup current
cp api/predictions.py api/predictions_realtime_backup.py

# Use database version
cp api/predictions_from_db.py api/predictions.py

# Deploy
npx vercel --prod
```

#### Option B: Run local server with database

```python
# Create simple server
from http.server import HTTPServer
from api.predictions_from_db import handler

server = HTTPServer(('localhost', 8000), handler)
print("Server running on http://localhost:8000/api/predictions")
server.serve_forever()
```

### 5. Monitor Data Completeness

```python
import sqlite3
import pandas as pd

# Check fetch logs
conn = sqlite3.connect('cmg_data.db')
df = pd.read_sql_query('''
    SELECT date, source, hours_covered, fetch_time_seconds, created_at
    FROM fetch_log
    WHERE success = 1
    ORDER BY created_at DESC
    LIMIT 10
''', conn)

print(df)
conn.close()
```

## Database Schema

### cmg_data table
- `date`: Date of the data
- `hour`: Hour (0-23)
- `node`: Node name (e.g., CHILOE________220)
- `source`: Data source (real/pid/online)
- `cmg_value`: CMG value
- `created_at`: When record was stored

### weather_data table
- `date`: Date
- `hour`: Hour (0-23)
- `temperature`: Temperature in Celsius
- `wind_speed`: Wind speed in m/s
- `precipitation`: Precipitation in mm
- `cloud_cover`: Cloud cover percentage
- `created_at`: When stored

### fetch_log table
- `date`: Date fetched
- `source`: CMG source
- `pages_fetched`: Number of pages fetched
- `records_found`: Chiloé records found
- `hours_covered`: Hours covered (0-24)
- `fetch_time_seconds`: Time taken
- `success`: Whether fetch was successful
- `error_message`: Error if any
- `created_at`: When fetch occurred

## Production Monitoring

### Check Daily Fetch Success

```bash
# Check if today's fetch completed
sqlite3 cmg_data.db "SELECT * FROM fetch_log WHERE date = date('now', '-1 day')"
```

### Alert on Missing Data

```python
# monitoring.py
import sqlite3
from datetime import datetime, timedelta
import smtplib

def check_data_completeness():
    conn = sqlite3.connect('cmg_data.db')
    cursor = conn.cursor()
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    cursor.execute('''
        SELECT hours_covered 
        FROM fetch_log 
        WHERE date = ? AND source = 'real'
    ''', (yesterday,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[0] < 20:
        send_alert(f"Incomplete data for {yesterday}: {row[0] if row else 0}/24 hours")
        return False
    return True

def send_alert(message):
    # Configure your email settings
    print(f"ALERT: {message}")
    # Send email/SMS/Slack notification

if __name__ == "__main__":
    check_data_completeness()
```

## Backup Strategy

### Daily Database Backup

```bash
# backup.sh
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR="/backup/cmg_data"
mkdir -p $BACKUP_DIR

# Backup database
sqlite3 cmg_data.db ".backup $BACKUP_DIR/cmg_data_$DATE.db"

# Keep only last 30 days
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
```

### Add to crontab

```bash
# Run backup at 4 AM daily
0 4 * * * /home/user/backup.sh
```

## Performance Metrics

Based on test_data_integrity.ipynb results:

| Metric | Value |
|--------|-------|
| Fetch time per day | ~18 minutes |
| Pages per day | ~440 pages |
| Records per day | ~384 for Chiloé |
| Coverage | 24/24 hours ✅ |
| Storage per day | ~50 KB |
| API response time | <100ms |

## Troubleshooting

### Database locked error
```bash
# Check for stuck processes
ps aux | grep python
# Kill if necessary
kill -9 [PID]
```

### Missing hours
```python
# Check which hours are missing
conn = sqlite3.connect('cmg_data.db')
cursor = conn.cursor()
cursor.execute('''
    SELECT hour 
    FROM generate_series(0,23) h(hour)
    WHERE NOT EXISTS (
        SELECT 1 FROM cmg_data 
        WHERE date = ? AND hour = h.hour AND node = ?
    )
''', ('2025-08-25', 'CHILOE________220'))
missing = cursor.fetchall()
print(f"Missing hours: {missing}")
```

### Re-fetch specific day
```python
from fetch_complete_daily import CompleteDailyFetcher

fetcher = CompleteDailyFetcher()
fetcher.fetch_complete_day('2025-08-25')
```

## Cost Analysis

### Current (Real-time fetching)
- API calls: 1000+ per hour
- Response time: 10-30 seconds
- Reliability: Poor (timeouts, rate limits)
- Cost: High API load

### New (Database approach)
- API calls: ~440 per day (at 3 AM)
- Response time: <100ms
- Reliability: Excellent
- Cost: Minimal (one fetch per day)

## Next Steps

1. ✅ Run initial fetch for last 7-30 days
2. ✅ Setup daily cron job
3. ✅ Deploy database API
4. ⬜ Add monitoring/alerting
5. ⬜ Setup backup strategy
6. ⬜ Optimize ML model with more data
7. ⬜ Add admin dashboard for monitoring

## Conclusion

This production setup ensures:
- **Complete 24/24 hour data coverage**
- **Fast API responses** (<100ms)
- **Reliable predictions** from actual patterns
- **Low operational cost** (one fetch per day)
- **Scalable architecture** (can add more nodes easily)

The system is now production-ready and can handle real traffic!