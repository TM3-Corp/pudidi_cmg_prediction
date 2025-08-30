#!/bin/bash

echo "🚀 Pushing workflow fixes and updating cache..."
echo ""

# Navigate to the vercel_deploy directory
cd "$(dirname "$0")"

# Try to push the workflow fixes
echo "📤 Pushing workflow fixes to GitHub..."
git push origin main 2>&1 || {
    echo "⚠️ Direct push failed. You may need to:"
    echo "   1. Set up GitHub credentials"
    echo "   2. Or manually push using: git push origin main"
    echo ""
    echo "After pushing, trigger a manual cache update from GitHub Actions:"
    echo "https://github.com/PVSH97/pudidi_cmg_prediction/actions/workflows/manual_update.yml"
    exit 1
}

echo "✅ Workflow fixes pushed successfully!"
echo ""
echo "Now you can:"
echo "1. Go to: https://github.com/PVSH97/pudidi_cmg_prediction/actions/workflows/manual_update.yml"
echo "2. Click 'Run workflow' to trigger a manual cache update"
echo "3. The updated workflow will handle any conflicts automatically"
echo ""
echo "Or wait for the next hourly update at :05 past the hour"