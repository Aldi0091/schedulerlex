# Quick Setup — Run Monthly Reports Automatically (Cron)

This guide explains how to schedule automatic monthly execution of `lex_job.sh` so reports are generated and emailed.

---

## Step 1 — Verify script works manually

Run once to confirm everything is configured:

```bash
./lex_job.sh
```

If this works, cron will work.

---

## Step 2 — Get absolute path

Find full path of script directory:

```bash
pwd
```

Example result:
```
/home/user/lexoffice/scheduler
```

Script path will be:
```
/home/user/lexoffice/scheduler/lex_job.sh
```

---

## Step 3 — Make script executable

```bash
chmod +x lex_job.sh
```

---

## Step 4 — Open cron editor

```bash
crontab -e
```

---

## Step 5 — Add monthly job

Run on **1st day of every month at 08:00**:

```cron
0 8 1 * * /bin/bash /FULL/PATH/TO/lex_job.sh >> /FULL/PATH/TO/cron.log 2>&1
```

Replace `/FULL/PATH/TO/` with your actual path.

Example:
```cron
0 8 1 * * /bin/bash /home/user/lexoffice/scheduler/lex_job.sh >> /home/user/lexoffice/scheduler/cron.log 2>&1
```

---

## What happens automatically

On the 1st of each month:

1. Script runs
2. Previous month invoices are exported
3. CSV A / B / C are generated
4. Email is sent
5. Old files are cleaned (if enabled)

No manual action required.

---

## Check logs

If needed, check execution log:

```bash
tail -n 200 cron.log
```

---

## Common issues

**Nothing happens**
→ cron not running or wrong path

Check:
```bash
systemctl status cron
```

---

**Permission denied**
→ script not executable

Fix:
```bash
chmod +x lex_job.sh
```

---

**Email not sent**
→ verify `.env` credentials

---

## Done

Once cron entry is saved, reports run automatically every month.