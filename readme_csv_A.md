README (Task A) — CSV 1 Revenue by Invoice and Category

What it does
- Exports a CSV that aggregates invoice line items by Category within each invoice.
- One invoice appears in multiple rows if multiple categories exist.
- Adds an invoice total row with Category=TotalInvoice.
- Output columns (strict):
  InvoiceNumber,Date,Customer,Category,AmountEUR

Data sources (Lexware Office / Lexoffice Public API)
- Invoice list: GET /v1/voucherlist (voucherType=invoice, voucherStatus=any, voucherDateFrom, voucherDateTo)
- Invoice details: GET /v1/invoices/{id}

Category mapping
- mapping.yaml defines categories and keyword rules.
- Each line item title/name is matched against keywords to produce a Category.
- Unmatched items go to default_category (default: Unmapped).
- Use --log-unmapped to log line items that did not match.

Required environment (.env)
- LEXOFFICE_TOKEN=...
- LEXOFFICE_BASE_URL=https://api.lexware.io   (optional, default used if missing)

Install
- pip install requests pyyaml python-dotenv

Run examples
1) Export single invoice
   python3 csv_a.py --invoice-id <invoice_id> --out csv_1.csv --delimiter ","

2) Export all invoices for a month (YYYY-MM)
   python3 csv_a.py --month 2026-01 --out csv_1_2026-01.csv --delimiter ","

3) Diagnose mapping gaps
   python3 csv_a.py --month 2026-01 --log-unmapped --log-level INFO

Logging and troubleshooting
- Logs go to console and to logs/csv_a_YYYYmmdd_HHMMSS.log by default.
- Each HTTP error includes E_HTTP and url/status/body snippet.
- Each runtime failure prints a ready-to-paste email block with an ErrorCode and logfile path.
- For month runs, use --continue-on-error to skip a broken invoice and finish the export.