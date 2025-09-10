# 🔮 Pudidi CMG Prediction System

A production-ready system for predicting and analyzing Marginal Cost (CMG) values for Chilean electrical grid nodes, with focus on Chiloé region.

## 🌟 Features

- **Real-time CMG Predictions**: ML-based forecasting for next 48 hours
- **Performance Analysis**: Compare programmed vs actual CMG values
- **Hydro Optimization**: Linear programming optimization for hydroelectric dispatch
- **Automated Data Collection**: Hourly updates from Coordinador Eléctrico Nacional
- **Interactive Dashboard**: Web interface for visualization and analysis

## 🚀 Live Demo

- **Main Dashboard**: https://pudidicmgprediction.vercel.app
- **Performance Analysis**: https://pudidicmgprediction.vercel.app/rendimiento
- **Optimizer Tool**: https://pudidicmgprediction.vercel.app/optimizer

## 📁 Project Structure

```
pudidi_cmg_prediction/
├── api/                      # Vercel API endpoints
│   ├── index.py             # Main prediction endpoint
│   ├── performance.py       # Performance analysis API
│   ├── cache.py            # Cache management
│   ├── optimizer.py        # Optimization endpoint
│   ├── predictions_live.py # Live predictions
│   └── utils/              # API utilities
│       ├── cache_manager.py
│       ├── optimizer_lp.py
│       └── optimizer_simple.py
│
├── public/                  # Web interface
│   ├── index.html          # Main dashboard
│   ├── rendimiento.html    # Performance view
│   ├── optimizer.html      # Optimizer interface
│   ├── css/                # Stylesheets
│   └── js/                 # JavaScript files
│       ├── rendimiento.js
│       └── optimizer.js
│
├── scripts/                 # Automation scripts
│   ├── smart_cmg_online_update.py    # Fetch CMG Online data
│   ├── sync_from_partner_gist.py     # Sync CMG Programado
│   ├── cmg_online_pipeline.py        # CSV download pipeline
│   ├── store_historical.py           # Store historical data
│   ├── daily_performance_calculation.py
│   ├── trigger_optimization.py
│   ├── update_programmed_cache.py
│   └── [other utility scripts]
│
├── data/                    # Data storage
│   └── cache/              # Cached CMG data
│       ├── cmg_online_historical.json
│       ├── cmg_programmed_latest.json
│       └── hourly/         # Hourly snapshots
│
├── tests/                   # Test suite
│   ├── test_performance_fix.py
│   ├── test_multi_day.py
│   └── [other test files]
│
├── notebooks/               # Jupyter notebooks
│   ├── analysis/           # Data analysis notebooks
│   └── experiments/        # Experimental code
│
├── docs/                    # Documentation
│   ├── deployment/         # Deployment guides
│   ├── architecture/       # System architecture
│   └── guides/            # User guides
│
├── archive/                 # Legacy code (deprecated)
│
├── .github/                # GitHub configuration
│   └── workflows/          # CI/CD workflows
│       ├── unified_cmg_update.yml     # Main data update
│       ├── cmg_csv_pipeline.yml       # CSV download
│       ├── daily_performance.yml      # Daily calculations
│       └── [other workflows]
│
├── config files
├── vercel.json            # Vercel deployment config
├── .vercelignore         # Files to exclude from deployment
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- Node.js 14+ (for Vercel CLI)
- Playwright (for web scraping)

### Local Development

```bash
# Clone repository
git clone https://github.com/TM3-Corp/pudidi_cmg_prediction.git
cd pudidi_cmg_prediction

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Set environment variables
export GITHUB_TOKEN="your-github-token"
export GIST_ID="your-gist-id"

# Run locally
python -m http.server 8000
```

## 🔄 Data Pipeline

### Automated Updates (GitHub Actions)

1. **Hourly CMG Update** (`unified_cmg_update.yml`)
   - Runs every hour at :05
   - Fetches CMG Online and Programado data
   - Updates cache and GitHub Gists

2. **CSV Pipeline** (`cmg_csv_pipeline.yml`)
   - Downloads CSV from Coordinador website
   - Handles survey popups automatically
   - Processes and uploads to Gist

3. **Daily Performance** (`daily_performance.yml`)
   - Calculates performance metrics
   - Compares forecast vs actual values

## 📊 API Endpoints

### Main Prediction API
```
GET /api
Returns CMG predictions for next 48 hours
```

### Performance API
```
POST /api/performance
Body: {
  "start_date": "2025-09-04T00:00:00",
  "end_date": "2025-09-06T23:59:59",
  "node": "NVA_P.MONTT___220"
}
```

### Cache API
```
GET /api/cache
Returns cached CMG data
```

## 🔧 Configuration

### Environment Variables
- `GITHUB_TOKEN`: GitHub personal access token for Gist updates
- `GIST_ID`: Main data storage Gist ID
- `CMG_PROGRAMADO_GIST_ID`: CMG Programado data Gist
- `OPTIMIZATION_GIST_ID`: Optimization results Gist

### Node Configuration
Primary nodes monitored:
- `NVA_P.MONTT___220` (Puerto Montt)
- `PIDPID________110` (Pid Pid)
- `DALCAHUE______110` (Dalcahue)

## 📈 Performance Metrics

The system tracks:
- **Forecast Accuracy**: CMG Programado vs CMG Online
- **Optimization Efficiency**: Programmed dispatch vs perfect hindsight
- **Data Availability**: Hourly coverage statistics

## 🚢 Deployment

### Vercel Deployment

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy to production
vercel --prod
```

### GitHub Actions Setup

1. Add repository secrets:
   - `GITHUB_TOKEN`
   - `GIST_ID`
   - Other required tokens

2. Enable workflows in `.github/workflows/`

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📝 License

This project is proprietary software. All rights reserved.

## 👥 Team

- **Pudidi Energy** - System Development
- **TM3 Corp** - Infrastructure & Deployment

## 📞 Support

For issues or questions:
- GitHub Issues: https://github.com/TM3-Corp/pudidi_cmg_prediction/issues
- Email: support@pudidi.energy

---

**Last Updated**: September 2025
**Version**: 2.0.0
**Status**: Production ✅