# Manual Run — Monthly Reports (Windows)

This guide explains how to manually run `run_monthly.py` to ensure
everything works before creating a scheduled task.

------------------------------------------------------------------------

## 1. Requirements

-   Windows 10 / 11
-   Python 3.x installed

Check Python in PowerShell:

    python --version

------------------------------------------------------------------------

## 2. Configure .env

Open `.env` in the project root and set:

```
LEXOFFICE_TOKEN=your_lexoffice_public_api_token

MAIL_ADDRESS=sender@example.com
MAIL_APP_PASSWORD=your_smtp_password_or_app_password
EMAIL_TO=receiver@example.com

SMTP_HOST=smtp.example.com
SMTP_PORT=587
```

Save the file.

------------------------------------------------------------------------

## 3. Prepare Python Environment (one-time setup)

Open PowerShell inside the project folder and run:

    python -m venv venv
    .\venv\Scripts\python -m pip install --upgrade pip
    .\venv\Scripts\pip install -r requirements.txt

------------------------------------------------------------------------

## 4. Run Manually

From the project folder:

    .\venv\Scripts\python run_monthly.py

------------------------------------------------------------------------

## 5. Verify

After execution:

-   Email should be received by the address in `EMAIL_TO`


------------------------------------------------------------------------

If the script runs successfully and email is received, the system is
ready for scheduling.
