#!/bin/bash
# Academic Paper Pipeline — Weekly Automation
# Runs: discover → ingest → triage → digest → macOS notification

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="$SCRIPT_DIR/data/pipeline.log"
DATE=$(date '+%Y-%m-%d %H:%M')

echo "[$DATE] Pipeline starting..." >> "$LOG_FILE"

# Step 1: Discover new papers from OpenAlex (16 journals)
echo "[$DATE] Step 1: Discover" >> "$LOG_FILE"
python3 cli.py discover --days 7 >> "$LOG_FILE" 2>&1

# Step 2: Ingest papers from Google Sheet (Scholar/SSRN alerts)
echo "[$DATE] Step 2: Ingest" >> "$LOG_FILE"
python3 cli.py ingest >> "$LOG_FILE" 2>&1 || echo "[$DATE] Ingest skipped (GSHEET_CSV_URL not set?)" >> "$LOG_FILE"

# Step 3: Triage pending papers with Claude
echo "[$DATE] Step 3: Triage" >> "$LOG_FILE"
python3 cli.py triage --engine cli >> "$LOG_FILE" 2>&1

# Step 4: Generate digest
echo "[$DATE] Step 4: Digest" >> "$LOG_FILE"
python3 cli.py digest >> "$LOG_FILE" 2>&1

# Step 5: macOS notification
DIGEST_FILE="$SCRIPT_DIR/digests/digest_$(date '+%Y-%m-%d').md"
PENDING=$(python3 -c "import database; print(database.count_by_status('pending'))")
SCORED=$(python3 -c "import database; print(database.count_by_status('scored'))")

osascript -e "display notification \"$SCORED scored papers ready for review. Run: python cli.py promote\" with title \"📚 Paper Digest Ready\" subtitle \"$DIGEST_FILE\""

echo "[$DATE] Pipeline complete. $SCORED scored papers." >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
