import os
import csv
import time
import argparse
import re
import unicodedata
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, date, timedelta

import requests
import yaml
from dotenv import load_dotenv


DEFAULT_TIMEOUT = 30

# Error codes
E_CONFIG = "E_CONFIG"
E_HTTP = "E_HTTP"
E_SCHEMA = "E_SCHEMA"
E_MAPPING = "E_MAPPING"
E_WRITE = "E_WRITE"
E_RUNTIME = "E_RUNTIME"


def ensure_dir(path):
    if not path:
        return
    os.makedirs(path, exist_ok=True)

def write_text_file(path, text):
    if not path:
        return
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def setup_logger(log_file=None, level="INFO"):
    level = (level or "INFO").upper()
    level_value = getattr(logging, level, logging.INFO)

    logger = logging.getLogger("lex_csv_a")
    logger.setLevel(level_value)
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    ch = logging.StreamHandler()
    ch.setLevel(level_value)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_file:
        ensure_dir(os.path.dirname(log_file))
        fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        fh.setLevel(level_value)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def normalize_base(base_url):
    base_url = (base_url or "").strip()
    if not base_url:
        return "https://api.lexware.io"
    return base_url.rstrip("/")


def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    })
    return s


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def request_json(session, method, url, logger, params=None, throttle=0.6, max_retries=5):
    last = None
    for attempt in range(1, max_retries + 1):
        if throttle:
            time.sleep(throttle)

        try:
            if method == "GET":
                r = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            else:
                raise ValueError("Unsupported method: " + method)

            # temporary / rate limit
            if r.status_code in (429, 502, 503, 504):
                wait = min(10, attempt * 1.5)
                logger.warning("%s retry in %ss (attempt %s/%s) url=%s",
                               E_HTTP, wait, attempt, max_retries, r.url)
                time.sleep(wait)
                last = (r.status_code, r.text[:2000])
                continue

            out = {
                "ok": r.status_code < 400,
                "status": r.status_code,
                "url": r.url,
                "data": safe_json(r),
            }

            if r.status_code >= 400:
                text = r.text[:4000]
                out["text"] = text
                logger.error("%s http_error status=%s url=%s body=%s",
                             E_HTTP, r.status_code, r.url, text)

            return out

        except Exception as e:
            wait = min(10, attempt * 1.5)
            logger.warning("%s exception retry in %ss (attempt %s/%s) -> %s",
                           E_HTTP, wait, attempt, max_retries, e)
            time.sleep(wait)
            last = str(e)

    logger.error("%s request_failed_after_retries url=%s last=%s", E_HTTP, url, last)
    return {"ok": False, "status": None, "url": url, "error": last}


def parse_date_ddmmyyyy(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except Exception:
        try:
            d = date.fromisoformat(value[:10])
            return d.strftime("%d.%m.%Y")
        except Exception:
            return value


def month_range(yyyy_mm):
    y, m = yyyy_mm.split("-")
    y = int(y)
    m = int(m)
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)
    return start, end


def sanitize_customer_name(name):
    # letters only + spaces (unicode)
    if not name:
        return ""
    cleaned = []
    for ch in name:
        if ch.isspace():
            cleaned.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    s = "".join(cleaned)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_text(s):
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def compile_rule_keywords(keywords, logger):
    compiled = []
    for k in keywords or []:
        k = (k or "").strip()
        if not k:
            continue
        if len(k) >= 2 and k.startswith("/") and k.endswith("/"):
            pattern = k[1:-1]
            try:
                compiled.append({"type": "regex", "value": re.compile(pattern, flags=re.IGNORECASE), "raw": k})
            except Exception:
                logger.warning("%s bad_regex_keyword=%s fallback=substr", E_MAPPING, k)
                compiled.append({"type": "substr", "value": normalize_text(pattern), "raw": k})
        else:
            compiled.append({"type": "substr", "value": normalize_text(k), "raw": k})
    return compiled


def load_mapping(path, logger):
    logger.info("loading mapping: %s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    default_category = data.get("default_category") or "Unmapped"
    cats = data.get("categories") or []

    compiled = []
    for c in cats:
        name = (c or {}).get("name")
        keywords = (c or {}).get("keywords") or []
        if not name:
            continue
        compiled.append({
            "name": name,
            "keywords": compile_rule_keywords(keywords, logger),
        })

    logger.info("mapping loaded categories=%s default=%s", len(compiled), default_category)
    return {"default": default_category, "categories": compiled}


def categorize_line_item(text, mapping):
    t = normalize_text(text)
    for c in mapping["categories"]:
        for kw in c["keywords"]:
            if kw["type"] == "substr":
                if kw["value"] and kw["value"] in t:
                    return c["name"]
            else:
                if kw["value"].search(text or ""):
                    return c["name"]
    return mapping["default"]


def net_from_item(item):
    qty = float(item.get("quantity") or 0)
    unit_price = item.get("unitPrice") or {}

    net = unit_price.get("netAmount")
    if net is None:
        net = unit_price.get("netPrice") or unit_price.get("amount") or 0

    return qty * float(net)


def invoice_total_net(inv):
    total_price = inv.get("totalPrice") or {}
    for key in ("netTotal", "totalNetAmount", "netAmount"):
        if key in total_price and total_price[key] is not None:
            try:
                return float(total_price[key])
            except Exception:
                pass

    s = 0.0
    for it in (inv.get("lineItems") or []):
        s += net_from_item(it)
    return s


def extract_invoice_fields(inv):
    invoice_number = inv.get("voucherNumber") or inv.get("invoiceNumber") or ""
    if not invoice_number:
        raise ValueError("Missing invoice number (voucherNumber/invoiceNumber)")

    invoice_date = parse_date_ddmmyyyy(inv.get("voucherDate") or inv.get("createdDate") or "")

    customer_name = ""
    addr = inv.get("address") or {}
    if isinstance(addr, dict):
        customer_name = addr.get("name") or ""

    if not customer_name:
        customer_name = (inv.get("contact") or {}).get("name") or ""

    customer_name = sanitize_customer_name(customer_name)
    return invoice_number, invoice_date, customer_name


def format_amount(x):
    try:
        return f"{float(x):.2f}"
    except Exception:
        return "0.00"


def build_rows_for_invoice(inv, mapping, logger, log_unmapped=False):
    invoice_number, invoice_date, customer_name = extract_invoice_fields(inv)
    inv_id = inv.get("id") or ""

    grouped = {}
    unmapped_titles = []

    for it in (inv.get("lineItems") or []):
        name = it.get("name") or it.get("title") or ""
        cat = categorize_line_item(name, mapping)
        grouped[cat] = grouped.get(cat, 0.0) + net_from_item(it)

        if log_unmapped and cat == mapping["default"]:
            unmapped_titles.append(name)

    if log_unmapped and unmapped_titles:
        logger.warning("%s unmapped_lineitems invoiceNumber=%s invoiceId=%s titles=%s",
                       E_MAPPING, invoice_number, inv_id, unmapped_titles)

    rows = []
    for cat in sorted(grouped.keys()):
        rows.append([
            invoice_number,
            invoice_date,
            customer_name,
            cat,
            format_amount(grouped[cat]),
        ])

    total = invoice_total_net(inv)
    rows.append([
        invoice_number,
        invoice_date,
        customer_name,
        "TotalInvoice",
        format_amount(total),
    ])

    logger.info("invoice processed invoiceNumber=%s invoiceId=%s rows=%s", invoice_number, inv_id, len(rows))
    return rows


def fetch_invoice(session, base_url, invoice_id, throttle, logger):
    url = base_url + "/v1/invoices/" + invoice_id
    resp = request_json(session, "GET", url, logger, throttle=throttle)
    if not resp["ok"]:
        raise RuntimeError("%s fetch_invoice_failed invoiceId=%s status=%s url=%s" %
                           (E_HTTP, invoice_id, resp.get("status"), resp.get("url")))
    return resp["data"]


def fetch_invoice_ids_for_month(session, base_url, yyyy_mm, throttle, logger):
    start, end = month_range(yyyy_mm)
    url = base_url + "/v1/voucherlist"

    params = {
        "voucherType": "invoice",
        "voucherStatus": "any",
        "voucherDateFrom": start.isoformat(),
        "voucherDateTo": end.isoformat(),
        "size": 250,
        "page": 0,
    }

    ids = []
    while True:
        resp = request_json(session, "GET", url, logger, params=params, throttle=throttle)
        if not resp["ok"]:
            raise RuntimeError("%s voucherlist_failed month=%s status=%s url=%s" %
                               (E_HTTP, yyyy_mm, resp.get("status"), resp.get("url")))

        data = resp["data"] or {}
        content = data.get("content") or []
        logger.info("voucherlist page=%s got=%s", params["page"], len(content))

        for row in content:
            if "id" in row:
                ids.append(row["id"])

        if len(content) < int(params["size"]):
            break

        params["page"] += 1

    logger.info("voucherlist done month=%s invoiceIds=%s", yyyy_mm, len(ids))
    return ids


def write_csv(path, rows, delimiter=",", logger=None):
    # Task A header
    header = ["InvoiceNumber", "Date", "Customer", "Category", "AmountEUR"]
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=delimiter)
            w.writerow(header)
            w.writerows(rows)
        if logger:
            logger.info("csv written path=%s rows=%s", path, len(rows))
    except Exception as e:
        if logger:
            logger.error("%s csv_write_failed path=%s err=%s", E_WRITE, path, e)
        raise


def build_failure_email_block(error_code, log_file, exc_text, hint_items):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("Subject: [Lexoffice CSV A] FAILED (%s) %s" % (error_code, ts))
    lines.append("")
    lines.append("Execution status: FAILED")
    lines.append("ErrorCode: %s" % error_code)
    lines.append("Time: %s" % ts)
    if log_file:
        lines.append("LogFile: %s" % log_file)
    lines.append("")
    lines.append("Error summary:")
    lines.append(exc_text.strip()[:1200])
    if hint_items:
        lines.append("")
        lines.append("Hints:")
        for h in hint_items[:8]:
            lines.append("- " + h)
    return "\n".join(lines)


def _human_reason_from_exception(exc_text):
    t = (exc_text or "").lower()
    if "name resolution" in t or "failed to resolve" in t:
        return "Network/DNS issue: host api.lexware.io could not be resolved"
    if "timed out" in t or "timeout" in t:
        return "Network timeout while calling Lexoffice API"
    if "401" in t or "unauthorized" in t:
        return "Authorization failed (token invalid/expired)"
    if "403" in t or "forbidden" in t:
        return "Access forbidden (token permissions/scopes)"
    return "Unexpected error during execution"


def build_email_report(status, error_code, log_file, args, summary_lines, hint_items=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    subj_status = "SUCCESS" if status == "SUCCESS" else "FAILED"
    subject = "[Lexoffice CSV A] %s (%s) %s" % (subj_status, error_code, ts)

    lines = []
    lines.append("Subject: %s" % subject)
    lines.append("")
    lines.append("Execution status: %s" % subj_status)
    lines.append("Time: %s" % ts)
    if log_file:
        lines.append("LogFile: %s" % log_file)

    # Context (helps client understand what was attempted)
    if args:
        lines.append("Job: CSV A (Revenue by Invoice and Category)")
        if getattr(args, "month", None):
            lines.append("Period: %s" % args.month)
        if getattr(args, "invoice_id", None):
            lines.append("InvoiceId: %s" % args.invoice_id)
        if getattr(args, "out", None):
            lines.append("Output: %s" % args.out)
        if getattr(args, "mapping", None):
            lines.append("Mapping: %s" % args.mapping)

    lines.append("")
    lines.append("Summary:")
    for s in (summary_lines or []):
        lines.append("- " + s)

    if hint_items:
        lines.append("")
        lines.append("Hints:")
        for h in hint_items[:10]:
            lines.append("- " + h)

    return "\n".join(lines)


def main():
    load_dotenv()

    p = argparse.ArgumentParser(description="CSV A: Revenue by Invoice and Category (Task A)")
    p.add_argument("--mapping", default="mapping.yaml", help="path to mapping.yaml")
    p.add_argument("--invoice-id", default=None, help="single invoice id")
    p.add_argument("--month", default=None, help="YYYY-MM to export all invoices in that month")
    p.add_argument("--out", default="csv_1_revenue_by_invoice_and_category.csv")
    p.add_argument("--delimiter", default=",", help="CSV delimiter (default , ; also possible)")
    p.add_argument("--throttle", type=float, default=0.6, help="sleep seconds before each request")
    p.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    p.add_argument("--log-file", default=None, help="path to log file; default logs/csv_a_YYYYmmdd_HHMMSS.log")
    p.add_argument("--log-unmapped", action="store_true", help="log line items that did not match any category rule")
    p.add_argument("--continue-on-error", action="store_true", help="skip failed invoices and continue month run")

    args = p.parse_args()

    if not args.invoice_id and not args.month:
        raise SystemExit("Provide --invoice-id or --month YYYY-MM")

    token = os.getenv("LEXOFFICE_TOKEN")
    if not token:
        raise SystemExit("%s LEXOFFICE_TOKEN missing in .env" % E_CONFIG)

    base_url = normalize_base(os.getenv("LEXOFFICE_BASE_URL"))

    if not args.log_file:
        ensure_dir("logs")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.log_file = os.path.join("logs", "csv_a_%s.log" % ts)

    ensure_dir("email")
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    email_report_file = os.path.join("email", f"csv_A_{ts}.txt")

    logger = setup_logger(args.log_file, level=args.log_level)
    logger.info("start csv_a invoice_id=%s month=%s out=%s mapping=%s", args.invoice_id, args.month, args.out, args.mapping)

    session = build_session(token)
    mapping = load_mapping(args.mapping, logger)

    all_rows = []
    failures = []

    try:
        if args.invoice_id:
            logger.info("fetching single invoice id=%s", args.invoice_id)
            inv = fetch_invoice(session, base_url, args.invoice_id, args.throttle, logger)
            all_rows.extend(build_rows_for_invoice(inv, mapping, logger, log_unmapped=args.log_unmapped))

        if args.month:
            logger.info("fetching invoices for month=%s", args.month)
            ids = fetch_invoice_ids_for_month(session, base_url, args.month, args.throttle, logger)
            logger.info("found invoices: %s", len(ids))

            for i, invoice_id in enumerate(ids, 1):
                logger.info("fetch invoice %s/%s id=%s", i, len(ids), invoice_id)
                try:
                    inv = fetch_invoice(session, base_url, invoice_id, args.throttle, logger)
                    all_rows.extend(build_rows_for_invoice(inv, mapping, logger, log_unmapped=args.log_unmapped))
                except Exception as e:
                    msg = "%s invoice_failed id=%s err=%s" % (E_RUNTIME, invoice_id, e)
                    logger.error(msg)
                    failures.append({"invoice_id": invoice_id, "error": str(e)})
                    if not args.continue_on_error:
                        raise
        
        write_csv(args.out, all_rows, delimiter=args.delimiter, logger=logger)

        if failures:
            logger.warning("completed_with_failures count=%s sample=%s", len(failures), failures[:3])

        email_report = build_email_report(
            status="SUCCESS",
            error_code="OK",
            log_file=args.log_file,
            args=args,
            summary_lines=[
                "CSV generated successfully",
                "Rows exported: %s" % len(all_rows),
            ],
            hint_items=None
        )

        write_text_file(email_report_file, email_report)
        logger.info("email report written: %s", email_report_file)

        print("\n" + "=" * 60 + "\n" + email_report + "\n" + "=" * 60 + "\n")
        logger.info("done ok out=%s rows=%s log=%s", args.out, len(all_rows), args.log_file)

    except Exception as e:
        logger.error("%s failure: %s", E_RUNTIME, e)

        human_reason = _human_reason_from_exception(str(e))
        hints = [
            "If this is DNS/network: check server internet, DNS resolver, proxy/VPN rules",
            "Try again in 1-2 minutes (temporary network failures happen)",
            "Check LEXOFFICE_TOKEN and LEXOFFICE_BASE_URL in .env",
            "If rate limit: increase --throttle (e.g. 1.0) and retry",
        ]

        email_report = build_email_report(
            status="FAILED",
            error_code=E_RUNTIME,
            log_file=args.log_file,
            args=args,
            summary_lines=[
                human_reason,
                "Technical: %s" % str(e),
            ],
            hint_items=hints
        )

        write_text_file(email_report_file, email_report)
        logger.info("email report written: %s", email_report_file)

        print("\n" + "=" * 60 + "\n" + email_report + "\n" + "=" * 60 + "\n")
        raise SystemExit(2)



if __name__ == "__main__":
    main()

