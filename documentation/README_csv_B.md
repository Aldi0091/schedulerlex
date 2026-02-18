# CSV B — Open Items (Receivables & Payables) (Lexoffice)

This script generates **CSV B (Open Items)** for a selected month (default: previous month).  
It collects **open receivables**, **open payables**, and **overdue** items via Lexoffice `voucherlist`, resolves net totals, and exports a single CSV.

---

## Output (CSV format)

**Header**
```
PartnerNumber,PartnerName,InvoiceID,CreationDate,DueDate,TotalNetAmountEUR
```

**Notes**
- Dates are formatted as **DD.MM.YYYY**
- `PartnerName` is sanitized to **letters + spaces**
- `PartnerNumber` is resolved via `/v1/contacts/<contactId>` (zero-padded to 5 digits).  
  If contact lookup fails, `00000` is used.
- The script filters voucherlist by:
  - `voucherType`: `invoice`, `purchaseinvoice`
  - `voucherStatus`: `open`, `sepadebit`, `overdue`
  - `voucherDateFrom` / `voucherDateTo` for the selected month

Default output path: `csv/csv_B_open_items_<YYYY-MM>.csv`

---

## Requirements

- Python 3.10+ recommended
- Packages:
  - `requests`, `python-dotenv`

Install:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the same folder as `csv_b.py`:

```env
LEXOFFICE_TOKEN=your_lexoffice_public_api_token
# optional:
LEXOFFICE_BASE_URL=https://api.lexware.io
```

---

## How to run

### A) Run for previous month (default)
```bash
python3 csv_b.py
```

### B) Run for a specific month
```bash
python3 csv_b.py --month 2026-01
```

---

## Useful options

### Choose output file
```bash
python3 csv_b.py --month 2026-01 --out csv/custom_open_items.csv
```

### Change CSV delimiter (comma or semicolon)
```bash
python3 csv_b.py --month 2026-01 --delimiter ";"
```

### Slow down requests (API rate-limit friendly)
```bash
python3 csv_b.py --month 2026-01 --throttle 1.0
```

### Log level and custom log file
```bash
python3 csv_b.py --month 2026-01 --log-level DEBUG --log-file logs/csv_b_debug.log
```

---

## Logs and troubleshooting

- Default log file: `logs/csv_b_<YYYYmmdd>_<HHMMSS>.log`
- Common error codes in logs:
  - `E_CONFIG` (missing env/config)
  - `E_HTTP` (API HTTP errors / retries)
  - `E_WRITE` (CSV write failures)
  - `E_RUNTIME` (unexpected runtime failures)

---

## Email report text file (for notifications)

The script always writes a text report you can attach to an email:
- Path: `email/csv_B_<YYYY-MM-DD>_<HHMMSS>.txt`
- Contains: status, period, summary, filter date range, and hints on failure.

(This script **does not send emails** by itself. Use your separate `send_email.py` to deliver CSV + report.)
