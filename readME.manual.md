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

## 2. Download & Configure Credentials

1. Download and unpack `lexofficemonthlyreport.zip`

2. Once you unpack, then open `.env` file apply/override your working credentials for **LexOffice API & SMTP Email** configurations

```
LEXOFFICE_TOKEN=your_lexoffice_public_api_token
```

```
MAIL_ADDRESS=sender@example.com
MAIL_APP_PASSWORD=your_smtp_password_or_app_password
EMAIL_TO=receiver1@example.com,receiver2@example.com

SMTP_HOST=smtp.example.com
SMTP_PORT=587
```

---

## 3. Setup Python Requirements


1. Right click our unpacked folder `lexofficemonthlyreport` and click `Open in Terminal`

2. There in Terminal need to create virtual environment for python

```
python -m venv venv
```

Run this:

```
.\venv\Scripts\python -m pip install --upgrade pip

```
and then:
```
.\venv\Scripts\pip install -r requirements.txt
```


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
