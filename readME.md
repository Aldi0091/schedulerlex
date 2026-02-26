## Quick Setup — Run Monthly Reports (Windows Task Scheduler)

---

### Get started

1. Download and unpack `lexofficemonthlyreport.zip` file with scripts to any desired folder (Ensure that you captured **the absolute path** to working directory, as it will be needed for scheduler in below instructions)

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

### Setup Python


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

Once virtual python environment created & set up, we proceed next step.

---

### Configure a scheduled job in Windows Task Scheduler

Go to:

```
Win + R
```

and enter:

```
control schedtasks
```

Once Windows Task Scheduler is opened, follow:
1. Create a Task
2. Assign a name for a task, for example: `Lexoffice Monthly Report`
3. Go to `Trigger` and set your schedule, for example: `Monthly, 1st day, 08:00 AM`
4. Go to `Actions` and create a `Start a Program`

    a. Click `Browse` and paste *path* of our `venv` interpreter, e.g.:

        C:\<Absolute-Path>\lexofficemonthlyreport\venv\Scripts\python.exe

        
    a.1. or something like:

        C:\Users\Frank\Downloads\lexofficemonthlyreport\venv\Scripts\python.exe

    b. Then add an `argument` and paste `run_monthly.py` there

    c. **Critical**: paste to the `Start In` this (its required to pick `.env` credentials):

        C:\<Absolute-Path>\lexofficemonthlyreport
    
    c.1.: or its something like:

        C:\Users\Frank\Downloads\lexofficemonthlyreport

    d. Click OK.

Finished. Scheduler is configured.


