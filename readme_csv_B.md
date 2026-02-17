

## Run Command

- python3 csv_b.py --month 2026-01


# CSV B Export Script --- Open Items (Receivables & Payables)

This guide explains how to install, configure, and run the CSV B script
that exports all open invoices from Lexoffice into a CSV file.

------------------------------------------------------------------------

## What This Script Does

-   connects to Lexoffice API
-   retrieves open invoices
-   retrieves overdue invoices
-   includes receivables + payables
-   merges results
-   creates CSV
-   logs actions
-   retries automatically if API fails

------------------------------------------------------------------------

## Output File Columns

PartnerNumber\
PartnerName\
InvoiceID\
CreationDate\
DueDate\
TotalNetAmountEUR

------------------------------------------------------------------------

## Requirements

-   Python 3.9+
-   Internet
-   Lexoffice API token

Check Python:

    python3 --version

------------------------------------------------------------------------

## Install Dependencies

    cd ~/lexoffice/scheduler
    pip install -r requirements.txt

------------------------------------------------------------------------

## Create .env File

    nano .env

Insert:

    LEXOFFICE_TOKEN=YOUR_TOKEN
    LEXOFFICE_BASE_URL=https://api.lexware.io

Save: CTRL+O → ENTER → CTRL+X

------------------------------------------------------------------------

## Run Script

    python3 csv_b.py

------------------------------------------------------------------------

## Run With Options

    python3 csv_b.py --out csv/open_items.csv --delimiter ";" --throttle 1.0

------------------------------------------------------------------------

## Output Files

After running: - CSV file - logs folder with log file

------------------------------------------------------------------------

## Logs

Example:

    processed=25/100 rows=25

Meaning script processed 25 invoices.

------------------------------------------------------------------------

## If Something Goes Wrong

Open log:

    cat logs/csv_b_*.log

Check last lines.

------------------------------------------------------------------------

## Automation (Optional)

    crontab -e

Add:

    0 2 * * * python3 ~/lexoffice/scheduler/csv_b.py

Runs daily at 02:00.

------------------------------------------------------------------------

## Quick Checklist

✔ Python installed\
✔ dependencies installed\
✔ .env created\
✔ token inserted\
✔ internet working

------------------------------------------------------------------------

## Result

You will receive a CSV file containing all open invoices.

------------------------------------------------------------------------

END