# Setting Up GitHub Repository for Collaboration

## Quick Setup (5 minutes)

### 1. Create GitHub Repository
Go to https://github.com/new and create a new repo:
- Name: `pudidi-cmg-prediction`
- Description: "CMG prediction system for Pudidi hydroelectric project - Chiloé 220kV"
- Set to **Private** (you can invite collaborators)
- Don't initialize with README (we have our own)

### 2. Initialize Git Locally
```bash
cd /home/paul/projects/Pudidi/pudidi_CMG_prediction_system/vercel_deploy

# Initialize git
git init

# Add all files
git add .

# Initial commit
git commit -m "Initial commit - Pudidi CMG Prediction System

- Web dashboard for CMG predictions
- ML model with weather integration  
- API with retry logic for unstable endpoints
- Testing notebooks and strategies
- Working on optimizing CMG Online fetch (no geographic filtering)"

# Add remote (replace with your repo URL)
git remote add origin https://github.com/YOUR_USERNAME/pudidi-cmg-prediction.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### 3. Invite Your Partner
In GitHub repository settings:
1. Go to Settings → Manage access
2. Click "Invite a collaborator"
3. Enter their GitHub username/email
4. They'll get an invitation email

## Repository Structure to Share

```
pudidi-cmg-prediction/
├── api/
│   ├── predictions.py           # Current production API
│   └── predictions_practical.py # Improved version
├── index.html                   # Web interface
├── test_cmg_online.ipynb       # API testing notebook
├── test_fetch_strategy.py      # Fetch optimization analysis
├── requirements.txt             # Dependencies
├── README_COLLABORATION.md     # Project documentation
├── .gitignore                   # Files to exclude
└── vercel.json                 # Deployment config
```

## What Your Partner Needs to Know

### Critical Code Sections

1. **Data Fetching Issue** (`api/predictions.py` lines 246-301)
```python
# PROBLEM: Must fetch ALL pages to get complete Chiloé data
# Currently limited to 10 pages (arbitrary)
# Should fetch until last page (100+ pages)
for page in range(1, max_pages + 1):  # <- This needs fixing
```

2. **The Core Challenge**
```python
# No geographic filtering available
# Must fetch ~100,000 records then filter for one node
# Each page takes 5-15 seconds
# Total: ~10-15 minutes for one complete day
```

3. **Current Workaround**
- Using PCP/PID endpoints (faster but less accurate)
- Only fetching 2 days of CMG Online (slow)
- Need 30 days ideally for good model training

## Collaboration Workflow

### For Your Partner:
```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/pudidi-cmg-prediction.git
cd pudidi-cmg-prediction

# 2. Create a branch for their work
git checkout -b optimize-fetch-logic

# 3. Make changes
# ... edit files ...

# 4. Commit and push
git add .
git commit -m "Optimize pagination to fetch all pages"
git push origin optimize-fetch-logic

# 5. Create Pull Request on GitHub
```

### For You:
- Review their pull requests
- Merge when ready
- Deploy to Vercel

## Key Areas for Collaboration

### Immediate Priorities:
1. **Fix Pagination** - Fetch ALL pages, not just 10
2. **Add Progress Tracking** - Show fetch progress
3. **Implement Caching** - Store fetched data

### Code Reviews Needed:
- `fetch_last_48h_cmg()` function
- `fetch_with_smart_retry()` retry logic
- ML model training with sparse data

### Performance Ideas:
- Parallel page fetching
- Background daily fetch at 3 AM
- Database storage for historical data

## Testing Together

### Share Test Results:
```bash
# Run fetch strategy test
python test_fetch_strategy.py > fetch_results.txt
git add fetch_results.txt
git commit -m "Test results: fetch strategy analysis"
git push
```

### Document Findings:
Create `docs/` folder for findings:
```
docs/
├── api_limitations.md      # What we've learned about the API
├── optimization_ideas.md   # Proposed solutions
└── test_results/           # Test outputs
```

## Communication

### In Code:
```python
# TODO: [Partner name] - Need to handle pagination better
# FIXME: This stops at 10 pages but should continue until end
# NOTE: Takes ~10 min for complete day fetch
```

### In Commits:
```bash
git commit -m "fix: Extend pagination to fetch all available pages

- Remove arbitrary 10-page limit
- Continue until last page detected
- Add progress logging

Addresses #1"
```

### Issues/Discussions:
Use GitHub Issues for:
- Bug reports
- Feature requests  
- Performance discussions
- API findings

## Security Notes

### Before Pushing:
1. API key is already public (test key)
2. No sensitive data in test files
3. `.gitignore` excludes temporary files

### For Production:
- Move API keys to environment variables
- Use GitHub Secrets for deployment
- Don't commit real CMG data if confidential

## Quick Share Option

If you just want to share files quickly without Git:

```bash
# Create archive
cd /home/paul/projects/Pudidi/pudidi_CMG_prediction_system
tar -czf pudidi_cmg_project.tar.gz vercel_deploy/

# Share via:
# - Email
# - Google Drive
# - Dropbox
# - WeTransfer
```

But GitHub is better for:
- Version control
- Collaboration
- Issue tracking
- Code review
- Deployment automation

---

Ready to share! Just follow steps 1-3 above to get your partner collaborating.