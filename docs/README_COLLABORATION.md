# Pudidi CMG Prediction System - Collaboration Guide

## Project Overview
Real-time CMG (Costo Marginal) prediction system for Chiloé 220kV node using machine learning.

## Current Status
- ✅ Web dashboard deployed on Vercel
- ⚠️ CMG Online API requires fetching ALL pages (no geographic filtering)
- ✅ ML model with safe lag features (24h, 48h) and weather integration
- 🔄 Working on optimizing data fetch performance

## Key Technical Challenges

### 1. CMG Online Data Fetching
The main bottleneck is the CMG Online API:
- **No geographic filtering** - must fetch ALL nodes then filter locally
- Returns 100,000+ records per day across all nodes
- Chiloé data scattered across multiple pages
- Need to fetch ALL pages to get complete 24-hour data
- Each page request takes 5-15 seconds

### 2. Current Data Flow
```
CMG Online API → Fetch all pages → Filter for CHILOE________220 → Train ML → Predict 48h
     ↓
  ~10 min for                ↓                              ↓
  one day                 3-5 records                   Every hour
                          per day found
```

## Repository Structure
```
vercel_deploy/
├── api/
│   ├── predictions.py          # Main API (current production)
│   ├── predictions_practical.py # Optimized version with retries
│   └── predictions_backup*.py   # Previous versions
├── index.html                  # Frontend dashboard
├── test_cmg_online.ipynb      # Testing notebook for API strategies
├── test_fetch_strategy.py     # Optimal fetching analysis
├── requirements.txt            # Python dependencies
└── README_COLLABORATION.md    # This file
```

## How to Collaborate

### 1. Clone and Setup
```bash
git clone [repository-url]
cd pudidi_CMG_prediction_system/vercel_deploy
pip install -r requirements.txt
```

### 2. Test Locally
```bash
# Test CMG fetching strategies
python test_fetch_strategy.py

# Run Jupyter notebook for interactive testing
jupyter notebook test_cmg_online.ipynb

# Test API locally
python -m http.server 8000
# Then visit http://localhost:8000
```

### 3. Key Files to Review

#### `api/predictions.py` (Line 190-340)
Current data fetching logic that needs optimization:
- `fetch_last_48h_cmg()` - Main data fetching function
- `fetch_with_smart_retry()` - Retry logic for 429/500 errors
- Pagination logic at line 246-301

#### `test_fetch_strategy.py`
Analysis of different fetching strategies:
- `test_one_day_complete_fetch()` - Shows how to get ALL Chiloé data
- Estimates ~10-15 minutes to fetch 30 days properly

## Proposed Solutions

### Solution 1: Background Daily Fetch (Recommended)
- Run a cron job at 3 AM daily
- Fetch complete month of data (takes ~15 min)
- Store in database/cache
- API uses cached data + real-time updates

### Solution 2: Distributed Fetching
- Split page fetching across multiple workers
- Parallel processing to reduce time
- Requires infrastructure changes

### Solution 3: Alternative Data Source
- Investigate if there's a bulk download option
- Check if historical data can be obtained differently
- Contact Coordinador Eléctrico for API improvements

## Current Issues to Fix

1. **Pagination Logic** (Line 254-295 in predictions.py)
   - Currently stops at page 10 (arbitrary limit)
   - Should fetch ALL pages until no more data
   - Need to handle 100+ pages per day

2. **Training Data Window**
   - Currently tries 48h-7 days
   - Should be 30 days for robust model
   - Limited by fetch time constraints

3. **Cache Strategy**
   - Currently 1-hour in-memory cache
   - Should persist to database
   - Need background refresh mechanism

## API Keys and Endpoints

```python
SIP_API_KEY = '1a81177c8ff4f69e7dd5bb8c61bc08b4'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
CHILOE_NODE = 'CHILOE________220'

# Weather API (no key needed)
CHILOE_LAT = -42.4472
CHILOE_LON = -73.6506
```

## Testing Credentials

The SIP API key is public for testing. For production:
1. Register at https://sipub.coordinador.cl/
2. Get your own API key
3. Update in environment variables

## How You Can Help

1. **Optimize Pagination Logic**
   - Make it fetch ALL pages efficiently
   - Add progress tracking
   - Handle failures gracefully

2. **Implement Caching Layer**
   - Design database schema
   - Background fetch scheduler
   - Cache invalidation strategy

3. **Improve ML Model**
   - Add more features
   - Test different algorithms
   - Validate predictions

4. **Performance Optimization**
   - Profile bottlenecks
   - Implement parallel fetching
   - Optimize data structures

## Communication

- Create issues for bugs/features
- Use pull requests for changes
- Comment code thoroughly
- Update this README with findings

## Deployment

Currently on Vercel (free tier):
```bash
npx vercel --prod
```

For production, consider:
- AWS Lambda for background jobs
- PostgreSQL for data storage
- Redis for caching
- GitHub Actions for CI/CD

## Questions/Discussion Points

1. Should we contact Coordinador for better API access?
2. Is 15-minute daily fetch acceptable for production?
3. Should we implement a paid solution for better performance?
4. Can we get historical bulk data to bootstrap the system?

---

**Last Updated**: August 25, 2025
**Primary Contact**: [Your contact info]
**Project Status**: Active Development