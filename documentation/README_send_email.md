# send_email.py — Send Monthly Reports (CSV + Logs)

`send_email.py` sends the monthly Lexoffice report email:
- **Email body** is built from `email/*.txt` reports (ordered **CSV A → CSV B → CSV C**)
- **Attachments** include:
  - CSV files from `csv/` (up to limits)
  - a **combined log** file generated from `logs/*.log`
  - any extra files passed via `--attach`

This script is typically executed by `lex_job.sh` after CSV generation.

---

## Requirements

- Python 3.10+ recommended
- Uses standard library `smtplib` + `python-dotenv`

Install dependencies (if not already):
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration (`.env`)

Create `.env` in the same folder as `send_email.py`:

### Required
```env
MAIL_ADDRESS=sender@example.com
MAIL_APP_PASSWORD=your_smtp_password_or_app_password
EMAIL_TO=receiver1@example.com,receiver2@example.com
```

### Optional (SMTP server)
Defaults are Gmail:
- `SMTP_HOST=smtp.gmail.com`
- `SMTP_PORT=587` (STARTTLS)

Override if needed:
```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
```

**Notes**
- `EMAIL_TO` can be separated by `,` or `;`
- duplicates are removed (case-insensitive)
- max recipients: 20

---

## What gets sent

### 1) Email body (from `email/*.txt`)
- Reads all `*.txt` in `email/`
- Groups by prefix:
  - `csv_A_...`
  - `csv_B_...`
  - `csv_C_...`
- Body sections are ordered:
  1) CSV A
  2) CSV B
  3) CSV C
  4) Other reports (if any)

Each report file may optionally start with:
```
Subject: <your subject here>
```
If present, this subject is used (first found, in priority A→B→C).  
If no subject is found, a default subject is used.

### 2) Attachments
- CSV files from `csv/` (default), filtered by `.csv`
- Combined log file created in `logs/` (new file named `logging_<timestamp>.log`)
- Any extra attachment paths provided via `--attach`

Attachment limits:
- max CSV files: 30 (default)
- max total CSV size: 20 MB (default)

---

## How to run

### A) Send email (normal)
```bash
python3 send_email.py
```

### B) Dry run (prints details, does not send)
```bash
python3 send_email.py --dry-run
```

---

## Useful options

### Custom directories
```bash
python3 send_email.py --csv-dir csv --logs-dir logs --email-dir email
```

### Limit attachments
```bash
python3 send_email.py --max-csv-files 10 --max-mb 15
```

### Attach oldest CSV first (default is newest first)
```bash
python3 send_email.py --oldest-first
```

### Attach extra file(s)
```bash
python3 send_email.py --attach /path/to/file1.pdf --attach /path/to/file2.txt
```

---

## Output / troubleshooting

If sending succeeds:
- prints recipients, subject, and list of attachments

Common failures:
- **Missing MAIL_ADDRESS or MAIL_APP_PASSWORD**
  - fix `.env`
- **Missing EMAIL_TO**
  - add recipients to `.env`
- **SMTP auth fails**
  - verify password/app-password, host/port, and whether STARTTLS is required
