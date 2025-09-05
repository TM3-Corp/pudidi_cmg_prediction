# CMG Data Architecture Setup

## Overview
We use a 3-Gist architecture for reliable CMG data storage:

1. **CMG Online Gist** (Existing)
   - ID: `8d7864eb26acf6e780d3c0f7fed69365`
   - Purpose: Stores historical actual CMG values
   - URL: https://gist.github.com/PVSH97/8d7864eb26acf6e780d3c0f7fed69365

2. **Partner's CMG Programado Gist** (External)
   - ID: `a63a3a10479bafcc29e10aaca627bc73`
   - Purpose: Source of fresh CMG Programado data
   - URL: https://gist.github.com/arbanados/a63a3a10479bafcc29e10aaca627bc73
   - Note: Overwrites data, creates gaps - use as source only

3. **Your CMG Programado Gist** (New - to be created)
   - Purpose: Reliable storage of CMG Programado with no gaps
   - Preserves all historical data
   - Updated daily by GitHub Actions

## Setup Instructions

### Step 1: Create GitHub Personal Access Token (PAT)

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Name it: `CMG Gist Updater`
4. Select scope: `gist` (create gists)
5. Generate and copy the token

### Step 2: Create Your CMG Programado Gist

```bash
# Set your token
export GITHUB_TOKEN='your_pat_token_here'

# Create the Gist
python scripts/create_cmg_programado_gist.py
```

This will:
- Create a new public Gist with your CMG Programado data
- Save the Gist ID to `cmg_programado_gist_config.json`
- Display the Gist URL

### Step 3: Add Token to GitHub Repository Secrets

1. Go to your repository on GitHub
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `CMG_GIST_TOKEN`
5. Value: Your PAT token from Step 1

### Step 4: Test the Complete Flow

1. **Locally test the sync:**
```bash
# Sync from partner's Gist
python scripts/sync_from_partner_gist.py

# Update your Gist
export GITHUB_TOKEN='your_pat_token'
python scripts/update_cmg_programado_gist.py
```

2. **Trigger GitHub Actions:**
- Go to Actions → "CMG Programado Update"
- Run workflow manually

## Data Flow

```
Partner's Gist (source) 
    ↓ [sync_from_partner_gist.py]
Local Storage (data/cmg_programado_history.json)
    ↓ [update_cmg_programado_gist.py]
Your CMG Programado Gist (reliable storage)
    ↓ [performance.py reads from]
Rendimiento View (performance analysis)
```

## Benefits

1. **No data loss**: Your Gist preserves all historical values
2. **No gaps**: Missing hours are never deleted
3. **Fresh data**: Daily sync from partner's Gist
4. **Reliable**: Even if partner's Gist has issues, your history is safe
5. **Public access**: Anyone can read your CMG Programado data

## Maintenance

- The workflow runs daily at 6 AM Santiago time
- Manual trigger available in GitHub Actions
- Check your Gist for data completeness
- Monitor for Sept 1-3 data when available

## Troubleshooting

**Gist update fails:**
- Check if `CMG_GIST_TOKEN` secret is set in repository
- Verify token has `gist` scope
- Check token hasn't expired

**Missing data:**
- Partner's Gist may not have certain dates
- Check partner's Gist directly for available dates
- Your Gist preserves whatever has been synced

**Workflow errors:**
- Check Actions logs for specific errors
- Ensure all Python dependencies are installed
- Verify file paths are correct