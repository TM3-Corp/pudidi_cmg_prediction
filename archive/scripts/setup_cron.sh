#!/bin/bash
# Setup cron job for daily CMG data fetch

echo "Setting up daily CMG fetch cron job..."

# Get the current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create log directory if it doesn't exist
LOG_DIR="/var/log/cmg_fetch"
mkdir -p $LOG_DIR 2>/dev/null || {
    LOG_DIR="$HOME/logs/cmg_fetch"
    mkdir -p $LOG_DIR
    echo "Using user log directory: $LOG_DIR"
}

# Create the cron job entry
CRON_CMD="0 3 * * * /usr/bin/python3 $SCRIPT_DIR/fetch_complete_daily.py >> $LOG_DIR/fetch.log 2>&1"

# Check if cron job already exists
(crontab -l 2>/dev/null | grep -q "fetch_complete_daily.py") && {
    echo "Cron job already exists. Removing old entry..."
    (crontab -l 2>/dev/null | grep -v "fetch_complete_daily.py") | crontab -
}

# Add the cron job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "Cron job added successfully!"
echo "Job will run daily at 3:00 AM Santiago time"
echo "Logs will be written to: $LOG_DIR/fetch.log"

# Show current crontab
echo ""
echo "Current crontab:"
crontab -l | grep "fetch_complete_daily"

# Create a manual run script
cat > "$SCRIPT_DIR/run_fetch_manually.sh" << 'EOF'
#!/bin/bash
# Manual fetch script for testing

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Running manual CMG fetch..."
echo "Start time: $(date)"

python3 "$SCRIPT_DIR/fetch_complete_daily.py"

echo "End time: $(date)"
echo "Check cmg_data.db for results"
EOF

chmod +x "$SCRIPT_DIR/run_fetch_manually.sh"

echo ""
echo "Created manual run script: run_fetch_manually.sh"
echo "Use it to test the fetch process manually"