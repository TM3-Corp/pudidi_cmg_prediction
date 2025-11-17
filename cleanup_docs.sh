#!/bin/bash
# ============================================================
# Documentation Cleanup Script
# ============================================================
# Archives legacy AI-generated documentation to organize the
# project structure while preserving historical context.
#
# Usage: bash cleanup_docs.sh
# ============================================================

set -e  # Exit on error

echo "=================================================="
echo "📁 PROJECT DOCUMENTATION CLEANUP"
echo "=================================================="
echo ""

# Create archive directories
echo "📂 Creating archive directories..."
mkdir -p archive/docs
mkdir -p archive/audits
mkdir -p archive/migration

# Check if files exist before moving
echo ""
echo "📦 Archiving completed feature documentation..."

# Completed features → archive/docs/
for file in \
  ARCHITECTURE_ANALYSIS.md \
  CMG_PIPELINE_ANALYSIS.md \
  DEPLOYMENT_FIXES_SUMMARY.md \
  DEPLOYMENT_READY.md \
  DEPLOYMENT_SUCCESS.md \
  IMPLEMENTATION_COMPLETE.md \
  ML_DASHBOARD_COMPLETE.md \
  ML_DASHBOARD_INTEGRATION.md \
  ML_PREDICTIONS_FIX.md \
  PRODUCTION_VERIFICATION_REPORT.md \
  SNAPSHOT_SYSTEM_COMPLETE.md \
  WORKFLOWS_UPDATED.md \
  WORKFLOW_GUIDE.md \
  VALIDATION_VIEW_GUIDE.md
do
  if [ -f "$file" ]; then
    echo "  ✓ Archiving $file"
    mv "$file" archive/docs/
  else
    echo "  ⊘ Skipping $file (not found)"
  fi
done

echo ""
echo "📊 Archiving audit reports..."

# Audit reports → archive/audits/
for file in \
  EFFICIENCY_OVER_100_INVESTIGATION.md \
  OPTIMIZER_METRICS_AUDIT.md \
  WHY_EQUAL_STORAGE_CONSTRAINT_IS_NECESSARY.md
do
  if [ -f "$file" ]; then
    echo "  ✓ Archiving $file"
    mv "$file" archive/audits/
  else
    echo "  ⊘ Skipping $file (not found)"
  fi
done

echo ""
echo "🔄 Archiving migration documentation..."

# Migration docs → archive/migration/
for file in \
  GIST_TOKEN_SETUP.md \
  SUPABASE_MIGRATION.md \
  NEXT_STEPS.md
do
  if [ -f "$file" ]; then
    echo "  ✓ Archiving $file"
    mv "$file" archive/migration/
  else
    echo "  ⊘ Skipping $file (not found)"
  fi
done

echo ""
echo "📋 Optional: Railway deployment docs..."
echo "   (Keeping in root - move manually if not using Railway)"
echo "   - RAILWAY_DEPLOYMENT_GUIDE.md"
echo "   - RAILWAY_QUICK_START.md"

echo ""
echo "=================================================="
echo "✅ CLEANUP COMPLETE!"
echo "=================================================="
echo ""
echo "📊 Summary:"
echo "   - Created archive/ directory structure"
echo "   - Moved 14 completed feature docs"
echo "   - Moved 3 audit reports"
echo "   - Moved 3 migration guides"
echo ""
echo "📁 Files kept in root:"
ls -1 *.md 2>/dev/null | grep -v "^archive" | head -10 || echo "   (listing markdown files...)"

echo ""
echo "🔍 Review changes:"
echo "   git status"
echo ""
echo "💾 Commit changes:"
echo '   git add .'
echo '   git commit -m "docs: Archive legacy AI-generated documentation"'
echo ""
