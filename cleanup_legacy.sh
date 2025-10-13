#!/bin/bash
# Safe cleanup script for legacy files
# This script moves unused files to archive/ and removes duplicate workflows

set -e  # Exit on error

echo "=========================================="
echo "PUDIDI CMG - LEGACY FILE CLEANUP"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -d ".github/workflows" ]; then
    echo "${RED}Error: Must run from project root (vercel_deploy/)${NC}"
    exit 1
fi

echo "${YELLOW}This script will:${NC}"
echo "  1. Create archive directories"
echo "  2. Move 11 legacy scripts to archive/scripts/"
echo "  3. Delete duplicate workflow: cmg_programado_hourly.yml"
echo "  4. Delete broken workflow: manual_update.yml"
echo ""
echo "${YELLOW}A git commit will be created at the end.${NC}"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "=========================================="
echo "STEP 1: Creating archive directories"
echo "=========================================="

mkdir -p archive/scripts
mkdir -p archive/workflows
echo "${GREEN}✅ Created archive directories${NC}"

echo ""
echo "=========================================="
echo "STEP 2: Moving legacy scripts"
echo "=========================================="

# Legacy scripts to move (not used in workflows)
LEGACY_SCRIPTS=(
    "store_forecast_matrices.py"
    "cmg_online_pipeline.py"
    "create_all_gists.py"
    "daily_performance_calculation.py"
    "download_force_click.py"
    "ml_feature_engineering.py"
    "sync_from_partner_gist.py"
    "update_cmg_programado_gist.py"
    "update_gist_ids.py"
    "update_programmed_cache.py"
)

for script in "${LEGACY_SCRIPTS[@]}"; do
    if [ -f "scripts/$script" ]; then
        git mv "scripts/$script" "archive/scripts/$script"
        echo "${GREEN}✅ Moved: scripts/$script${NC}"
    else
        echo "${YELLOW}⚠️  Not found: scripts/$script${NC}"
    fi
done

echo ""
echo "=========================================="
echo "STEP 3: Removing duplicate workflow"
echo "=========================================="

if [ -f ".github/workflows/cmg_programado_hourly.yml" ]; then
    git mv ".github/workflows/cmg_programado_hourly.yml" "archive/workflows/cmg_programado_hourly.yml"
    echo "${GREEN}✅ Moved duplicate workflow to archive${NC}"
    echo "   Reason: CMG Programado now handled by cmg_online_hourly.yml at :05"
else
    echo "${YELLOW}⚠️  Workflow already removed${NC}"
fi

echo ""
echo "=========================================="
echo "STEP 4: Removing broken workflow"
echo "=========================================="

if [ -f ".github/workflows/manual_update.yml" ]; then
    git mv ".github/workflows/manual_update.yml" "archive/workflows/manual_update.yml"
    echo "${GREEN}✅ Moved broken workflow to archive${NC}"
    echo "   Reason: References non-existent archive/simple_sequential_update_final.py"
else
    echo "${YELLOW}⚠️  Workflow already removed${NC}"
fi

echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo ""
echo "${GREEN}Cleanup complete!${NC}"
echo ""
echo "📁 Scripts moved to: archive/scripts/"
echo "📁 Workflows moved to: archive/workflows/"
echo ""
echo "Active workflows:"
git ls-files .github/workflows/*.yml | while read -r file; do
    echo "  ✅ $(basename "$file")"
done
echo ""
echo "Active scripts:"
git ls-files scripts/*.py | wc -l | xargs echo "  ✅ Total:"
echo ""

# Stage all changes
git add archive/

echo "=========================================="
echo "Ready to commit changes"
echo "=========================================="
echo ""

# Show what will be committed
git status --short

echo ""
read -p "Create git commit? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    git commit -m "Clean up legacy files and duplicate workflows

Moved to archive:
- 10 legacy scripts (unused in workflows)
- cmg_programado_hourly.yml (duplicate - runs at :35, superseded by cmg_online_hourly.yml at :05)
- manual_update.yml (broken - references non-existent file)

Kept in scripts/:
- 8 scripts used in active workflows
- 2 scripts used as dependencies (download_cmg_programado_simple.py, process_pmontt_programado.py)

Active workflows after cleanup:
- cmg_online_hourly.yml (main pipeline - runs every hour at :05)
- cmg_5pm_snapshot.yml (daily snapshot at 17:00)
- daily_optimization.yml (daily at 06:00)

Benefits:
- Reduced GitHub Actions usage (no duplicate CMG Programado scraping)
- Cleaner codebase
- Easier to maintain

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>"

    echo ""
    echo "${GREEN}✅ Commit created!${NC}"
    echo ""
    echo "To push changes:"
    echo "  git push origin main"
else
    echo "Commit skipped. You can commit manually with:"
    echo "  git commit"
fi

echo ""
echo "${GREEN}=========================================="
echo "CLEANUP COMPLETE"
echo "==========================================${NC}"
