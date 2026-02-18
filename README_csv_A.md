# CSV A — Revenue by Invoice and Category (Lexoffice)

This script fetches Lexoffice invoices for a given month (or a single invoice) and generates **CSV A**:
**Revenue by Invoice and Category**, including a **TotalInvoice** row per invoice.

---

## Output (CSV format)

**Header**
```
InvoiceNumber,Date,Customer,Category,AmountEUR
```

**Rules**
- `Date` is **DD.MM.YYYY**
- `Customer` is sanitized to **letters + spaces**
- One invoice can appear in multiple rows (one row per category)
- Each invoice always includes an extra row:
  - `Category=TotalInvoice`
  - `AmountEUR=<invoice net total>`

Default output path (month run): `csv/csv_A_<YYYY-MM>.csv`

---

## Requirements

- Python 3.10+ recommended
- Packages:
  - `requests`, `pyyaml`, `python-dotenv`

Install:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

### 1) `.env`
Create a `.env` file in the same folder as `csv_a.py`:

```env
LEXOFFICE_TOKEN=your_lexoffice_public_api_token
# optional:
LEXOFFICE_BASE_URL=https://api.lexware.io
```

### 2) `mapping.yaml`
This file defines revenue categories via keywords (substring or regex).

Example:
```yaml
default_category: Unmapped
categories:
  - name: Sales
    keywords: ["sale", "product", "artikel"]
  - name: Transport
    keywords: ["transport", "delivery", "/^ship(ping)?/"]
```

---

## How to run

### A) Run for previous month (default)
If you run without parameters, the script automatically exports the **previous full month**:
```bash
python3 csv_a.py
```

### B) Run for a specific month
```bash
python3 csv_a.py --month 2026-01
```

### C) Run for a single invoice (by invoice id)
```bash
python3 csv_a.py --invoice-id <INVOICE_ID>
```

---

## Useful options

### Choose output file
```bash
python3 csv_a.py --month 2026-01 --out csv/custom_name.csv
```

### Change CSV delimiter (comma or semicolon)
```bash
python3 csv_a.py --month 2026-01 --delimiter ";"
```

### Slow down requests (API rate-limit friendly)
```bash
python3 csv_a.py --month 2026-01 --throttle 1.0
```

### Log unmapped line items (helps tune mapping.yaml)
```bash
python3 csv_a.py --month 2026-01 --log-unmapped
```

### Continue month run even if some invoices fail
```bash
python3 csv_a.py --month 2026-01 --continue-on-error
```

### Log level and custom log file
```bash
python3 csv_a.py --month 2026-01 --log-level DEBUG --log-file logs/csv_a_debug.log
```

---

## Logs and troubleshooting

- Default log file: `logs/csv_a_<YYYYmmdd>_<HHMMSS>.log`
- The script prints structured errors with codes like:
  - `E_CONFIG` (missing env/config)
  - `E_HTTP` (API HTTP errors / retries)
  - `E_MAPPING` (mapping issues, unmapped items)
  - `E_WRITE` (CSV write failures)
  - `E_RUNTIME` (unexpected runtime failures)

---

## Email report text file (for notifications)

The script always writes a text report you can attach to an email:
- Path: `email/csv_A_<YYYY-MM-DD>_<HHMMSS>.txt`
- Contains: status, period/invoiceId, short summary, and hints on failure.

(This script **does not send emails** by itself. Use your separate `send_email.py` to deliver CSV + report.)
