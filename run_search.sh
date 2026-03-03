#!/bin/bash
# Job Search Campaign Manager - Daily Run Script
# Add to crontab for automated execution:
#   crontab -e
#   # Quick scan every 2 hours (6AM-10PM):
#   0 6,8,10,12,14,16,18,20,22 * * * /Users/devonfrancis/job_hunter/run_search.sh quick
#   # Full scan daily at 6AM:
#   0 6 * * * /Users/devonfrancis/job_hunter/run_search.sh full
#   # Daily digest at 7AM:
#   0 7 * * * /Users/devonfrancis/job_hunter/run_search.sh digest

cd /Users/devonfrancis/job_hunter

# Activate virtual environment
source venv/bin/activate

MODE=${1:-quick}

case $MODE in
    quick)
        echo "[$(date)] Running quick scan..."
        python main.py --quick >> logs/search.log 2>&1
        ;;
    full)
        echo "[$(date)] Running full pipeline..."
        python main.py >> logs/search.log 2>&1
        ;;
    digest)
        echo "[$(date)] Sending daily digest..."
        python main.py --digest >> logs/search.log 2>&1
        ;;
    report)
        echo "[$(date)] Generating report..."
        python main.py --report >> logs/search.log 2>&1
        ;;
    *)
        echo "Usage: $0 {quick|full|digest|report}"
        exit 1
        ;;
esac

echo "[$(date)] Done."
