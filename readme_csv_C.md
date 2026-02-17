# CSV C Script Documentation --- Monthly Article Revenue Report


## Run

`python3 csv_c.py --month 2026-01`

------------------------------------------------------------------------

## Purpose

Exports all billed article items for a selected month from Lexoffice and
aggregates revenue per article.

------------------------------------------------------------------------

## What Script Produces

CSV file containing:

-   ArticleNumber
-   ArticleName
-   NetRevenueEUR

Optional audit CSV containing every invoice line item.

------------------------------------------------------------------------

## Requirements

-   Python 3.9+
-   Internet connection
-   Lexoffice API token

Check Python:

    python3 --version

------------------------------------------------------------------------

## Installation

Navigate to project folder:

    cd ~/lexoffice/scheduler

Install dependencies:

    pip install -r requirements.txt

------------------------------------------------------------------------

## Create Environment File

Create `.env` file:

    nano .env

Insert:

    LEXOFFICE_TOKEN=YOUR_TOKEN
    LEXOFFICE_BASE_URL=https://api.lexware.io

Save: CTRL+O → ENTER → CTRL+X

------------------------------------------------------------------------

## Basic Run

    python3 csv_c.py --month 2026-01

------------------------------------------------------------------------

## Run With Custom Output

    python3 csv_c.py --month 2026-01 --out reports/january.csv

------------------------------------------------------------------------

## Run With Audit File

    python3 csv_c.py --month 2026-01 --audit-out audit.csv

Audit file contains raw invoice line details for verification.

------------------------------------------------------------------------

## Optional Parameters

  Parameter     Description
  ------------- --------------------------
  --month       required month YYYY-MM
  --out         output CSV path
  --delimiter   CSV separator (, or ;)
  --throttle    delay between API calls
  --log-level   DEBUG INFO WARNING ERROR
  --audit-out   write detailed audit CSV

------------------------------------------------------------------------

## Output Files

After execution:

-   main CSV report
-   logs folder with execution log
-   optional audit CSV

------------------------------------------------------------------------

## Logs

View latest log:

    cat logs/csv_c_*.log

Logs show: - API retries - processed invoices - errors - summary

------------------------------------------------------------------------

## Automation (Optional Cron)

Run monthly:

    crontab -e

Add:

    0 3 1 * * python3 ~/lexoffice/scheduler/csv_c.py --month $(date +\%Y-\%m)

------------------------------------------------------------------------

## Troubleshooting

If script fails:

Check log file.

Common causes:

-   invalid token
-   network issue
-   wrong month format
-   API rate limit

------------------------------------------------------------------------

## Success Result

Script finishes with:

    csvC written path=...

Your CSV is ready for analysis.

------------------------------------------------------------------------

