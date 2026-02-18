# lex_job.sh — Monthly Scheduler (Lexoffice CSV A/B/C + Email)

`lex_job.sh` is the wrapper script that:
1) prepares/activates the Python virtualenv  
2) installs dependencies (first run only, unless forced)  
3) runs CSV exports **A**, **B**, **C**  
4) sends email (`send_email.py`)  
5) purges old files (`purge.py`)

---

## What it runs

In order:
- `python csv_a.py` (CSV A: Revenue by Invoice & Category)
- `python csv_b.py` (CSV B: Open Items)
- `python csv_c.py` (CSV C: Article Revenue)
- `python send_email.py`
- `python purge.py`

It always runs from its own directory (so relative paths like `csv/`, `logs/`, `email/` work).

---

## Requirements

- `bash`
- `python3`
- `requirements.txt` present next to the script
- `.env` present next to the script

Make executable:
```bash
chmod +x lex_job.sh
```

---

## Configuration

### Required: `.env`
This script expects `.env` in the same folder.

Minimum:
```env
LEXOFFICE_TOKEN=your_lexoffice_public_api_token
```

Email sending (only if you run `send_email.py`):
```env
MAIL_ADDRESS=sender@example.com
MAIL_APP_PASSWORD=your_app_password_or_smtp_password
EMAIL_TO=receiver1@example.com,receiver2@example.com

# optional SMTP settings (if not Gmail defaults):
SMTP_HOST=smtp.example.com
SMTP_PORT=587
```

### Optional environment variables (override defaults)

You can override these when calling the script:

- `VENV_DIR` (default: `venv`)
- `PYTHON_BIN` (default: `python3`)
- `PIP_INSTALL_ALWAYS` (default: `0`)
  - `0` installs only once; `1` forces `pip install` every run
- `SEND_EMAIL_AFTER` (default: `1`)
  - `1` runs `send_email.py`, `0` skips it
- `PURGE_AFTER` (default: `1`)
  - `1` runs `purge.py`, `0` skips it

Example:
```bash
SEND_EMAIL_AFTER=0 PURGE_AFTER=0 ./lex_job.sh
```

---

## How to run manually

From the scheduler folder:
```bash
./lex_job.sh
```

Logs and outputs are written into:
- `csv/` (CSV files)
- `logs/` (per-script log files)
- `email/` (per-script report text files, used for notifications)

---

## Cron: run on the 1st day of every month

Goal: run on the **1st** and export the **previous month**.  
All CSV scripts already default to “previous month” when `--month` is not provided, so cron just runs `lex_job.sh`.

### 1) Add a crontab entry
Edit crontab:
```bash
crontab -e
```

Add this line (runs at **08:00** on day **1** of every month):
```cron
0 8 1 * * /bin/bash /ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR/lex_job.sh >> /ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR/cron.log 2>&1
```

Replace `/ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR` with your real path.

### 2) Verify cron environment
Cron runs with a minimal environment. The script:
- `cd`s into its own folder ✅
- activates the venv ✅
- reads `.env` from that folder ✅

So you normally do not need extra `cd` or exporting variables.

### 3) Test cron-like run (recommended)
Run the exact cron command in your shell:
```bash
/bin/bash /ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR/lex_job.sh >> /ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR/cron.log 2>&1
```

Then check:
```bash
tail -n 200 /ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR/cron.log
ls -la /ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR/csv
ls -la /ABSOLUTE/PATH/TO/YOUR-SCHEDULER-DIR/email
```

---

## Common issues

- **`.env not found`**
  - Ensure `.env` exists in the same folder as `lex_job.sh`.

- **Dependencies not installed**
  - First run installs dependencies automatically.
  - Force reinstall:
    ```bash
    PIP_INSTALL_ALWAYS=1 ./lex_job.sh
    ```

- **Email not sent**
  - Ensure `SEND_EMAIL_AFTER=1`
  - Ensure `.env` has `MAIL_ADDRESS`, `MAIL_APP_PASSWORD`, `EMAIL_TO`
