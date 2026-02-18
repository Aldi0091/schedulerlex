# CSV C — Article Revenue (Lexoffice)

This script generates **CSV C (Article Revenue)** for a selected month (default: previous month).  
It fetches all invoices in the month, aggregates revenue by **ArticleNumber**, and exports a single CSV.

---

## Output (CSV format)

**Header**
```
ArticleNumber,ArticleName,NetRevenueEUR
```

**Notes**
- The script reads invoices via `voucherlist` (month-filtered) and then loads each invoice detail.
- It aggregates revenue per article using invoice line items:
  - `type=="text"` items are ignored
  - line items are mapped to an article via `lineItem.id` (UUID expected)
  - article metadata comes from `/v1/articles/<article_id>`
- Amount calculation:
  - If `lineItemAmount` exists: uses it directly
  - Otherwise: `quantity * unitPrice.netAmount`

Default output path: `csv/csv_C_<YYYY-MM>.csv`

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

Create a `.env` file in the same folder as `csv_c.py`:

```env
LEXOFFICE_TOKEN=your_lexoffice_public_api_token
# optional:
LEXOFFICE_BASE_URL=https://api.lexware.io
```

---

## How to run

### A) Run for previous month (default)
```bash
python3 csv_c.py
```

### B) Run for a specific month
```bash
python3 csv_c.py --month 2026-01
```

---

## Useful options

### Choose output file
```bash
python3 csv_c.py --month 2026-01 --out csv/custom_articles.csv
```

### Slow down requests (API rate-limit friendly)
```bash
python3 csv_c.py --month 2026-01 --throttle 1.0
```

---

## Logs and troubleshooting

- Log file is created automatically:
  - `logs/csv_c_<YYYYmmdd>_<HHMMSS>.log`
- Logs include counts (found invoices, progress, rows) and retry warnings for temporary API errors (429/5xx).

---

## Email report text file (for notifications)

The script writes a short status report you can attach to an email:
- Path: `email/csv_C_<YYYY-MM-DD>_<HHMMSS>.txt`
- Contains: status, month, row count, and output file path.

(This script **does not send emails** by itself. Use your separate `send_email.py` to deliver CSV + report.)
