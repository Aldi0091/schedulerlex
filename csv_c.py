import os
import csv
import json
import time
import argparse
import re
import logging
from datetime import datetime, date, timedelta

import requests
from dotenv import load_dotenv

DEFAULT_TIMEOUT = 30


def normalize_base(base_url):
    base_url = (base_url or "").strip()
    if not base_url:
        return "https://api.lexware.io"
    return base_url.rstrip("/")


def ensure_dir(path):
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def setup_logger(name, log_dir="logs", level="INFO"):
    ensure_dir(log_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{name}_{ts}.log")

    lvl = getattr(logging, (level or "INFO").upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(lvl)
    logger.handlers = []
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(lvl)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(lvl)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("logger initialized path=%s", log_path)
    return logger, log_path


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

            if r.status_code in (429, 502, 503, 504):
                wait = min(10, attempt * 1.5)
                logger.warning("HTTP %s retry in %.1fs url=%s", r.status_code, wait, r.url)
                time.sleep(wait)
                last = (r.status_code, r.text[:2000])
                continue

            if r.status_code >= 400:
                logger.error("HTTP %s error url=%s body=%s", r.status_code, r.url, (r.text or "")[:2000])

            return {
                "ok": r.status_code < 400,
                "status": r.status_code,
                "url": r.url,
                "data": safe_json(r),
                "text": (r.text or "")[:4000],
                "error": last,
            }

        except Exception as e:
            wait = min(10, attempt * 1.5)
            logger.warning("exception retry in %.1fs url=%s err=%s", wait, url, e)
            time.sleep(wait)
            last = str(e)

    return {"ok": False, "status": None, "url": url, "data": None, "text": "", "error": last}


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


def looks_like_uuid(s):
    if not s:
        return False
    return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", str(s)))


def net_from_line_item(it):
    # предпочтение: lineItemAmount (обычно уже нетто по позиции)
    if "lineItemAmount" in it and it["lineItemAmount"] is not None:
        try:
            return float(it["lineItemAmount"])
        except Exception:
            pass

    qty = it.get("quantity") or 0
    up = it.get("unitPrice") or {}
    net_amount = up.get("netAmount")
    if net_amount is None:
        net_amount = up.get("netPrice") or up.get("amount")

    try:
        return float(qty) * float(net_amount or 0)
    except Exception:
        return 0.0


def fetch_invoice_ids_for_month(session, base_url, yyyy_mm, voucher_status, logger, throttle):
    start, end = month_range(yyyy_mm)
    url = base_url + "/v1/voucherlist"

    params = {
        "voucherType": "invoice",
        "voucherStatus": voucher_status,
        "voucherDateFrom": start.isoformat(),
        "voucherDateTo": end.isoformat(),
        "size": 250,
        "page": 0,
    }

    ids = []
    while True:
        resp = request_json(session, "GET", url, logger, params=params, throttle=throttle)
        if not resp["ok"]:
            raise SystemExit(json.dumps(resp, ensure_ascii=False, indent=2))

        data = resp["data"] or {}
        content = data.get("content") or []
        for row in content:
            if "id" in row:
                ids.append(row["id"])

        logger.info("voucherlist page=%s got=%s total=%s", params["page"], len(content), len(ids))

        if len(content) < int(params["size"]):
            break
        params["page"] += 1

    return ids


def fetch_invoice(session, base_url, invoice_id, logger, throttle):
    url = base_url + "/v1/invoices/" + invoice_id
    resp = request_json(session, "GET", url, logger, throttle=throttle)
    if not resp["ok"]:
        raise SystemExit(json.dumps(resp, ensure_ascii=False, indent=2))
    return resp["data"] or {}


def fetch_article(session, base_url, article_id, logger, throttle):
    url = base_url + "/v1/articles/" + article_id
    resp = request_json(session, "GET", url, logger, throttle=throttle)
    if not resp["ok"]:
        return None
    return resp["data"] or {}


def write_csv_c(path, rows, delimiter=","):
    header = ["ArticleNumber", "ArticleName", "NetRevenueEUR"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)


def write_audit_lines(path, rows, delimiter=","):
    header = [
        "InvoiceNumber",
        "InvoiceDate",
        "CustomerName",
        "CustomerId",
        "LineType",
        "LineName",
        "Quantity",
        "NetRevenueEUR",
        "TaxRate",
        "ArticleId",
        "ArticleNumber",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)


def main():
    load_dotenv()

    token = os.getenv("LEXOFFICE_TOKEN")
    if not token:
        raise SystemExit("LEXOFFICE_TOKEN missing in .env")

    base_url = normalize_base(os.getenv("LEXOFFICE_BASE_URL"))

    p = argparse.ArgumentParser(description="CSV C: Monthly Article Revenue Report")
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--voucher-status", default="any", help="any|accepted|open|overdue|paid|paidoff|sepadebit ...")
    p.add_argument("--out", default=None, help="output csv path")
    p.add_argument("--delimiter", default=",")
    p.add_argument("--throttle", type=float, default=0.6)
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--audit-out", default=None, help="optional: dump all invoice line items into a detailed CSV")
    args = p.parse_args()

    logger, log_path = setup_logger("csv_c", level=args.log_level)

    out = args.out or f"csvC_article_revenue_{args.month}.csv"

    logger.info("start csv_c month=%s out=%s base_url=%s status=%s", args.month, out, base_url, args.voucher_status)

    session = build_session(token)

    invoice_ids = fetch_invoice_ids_for_month(session, base_url, args.month, args.voucher_status, logger, args.throttle)
    logger.info("found invoices=%s", len(invoice_ids))

    # article cache: article_id -> (articleNumber, title)
    article_cache = {}

    # aggregation: (articleNumber, articleName) -> net_sum
    agg = {}

    audit_rows = []

    for idx, invoice_id in enumerate(invoice_ids, 1):
        inv = fetch_invoice(session, base_url, invoice_id, logger, args.throttle)

        inv_number = inv.get("voucherNumber") or inv.get("invoiceNumber") or ""
        inv_date = parse_date_ddmmyyyy(inv.get("voucherDate") or inv.get("createdDate") or "")
        addr = inv.get("address") or {}
        cust_name = (addr.get("name") if isinstance(addr, dict) else "") or ""
        cust_id = (addr.get("contactId") if isinstance(addr, dict) else "") or ""

        line_items = inv.get("lineItems") or []
        for it in line_items:
            it_type = (it.get("type") or "").lower()
            if it_type == "text":
                continue

            line_name = it.get("name") or ""
            qty = it.get("quantity") or ""
            tax_rate = ""
            up = it.get("unitPrice") or {}
            if "taxRatePercentage" in up and up["taxRatePercentage"] is not None:
                tax_rate = up["taxRatePercentage"]

            net_val = net_from_line_item(it)

            # В Lexware docs у material/service id обязателен (скорее всего это и есть articleId) :contentReference[oaicite:3]{index=3}
            article_id = it.get("id")
            article_number = ""
            article_title = ""

            if looks_like_uuid(article_id):
                if article_id in article_cache:
                    article_number, article_title = article_cache[article_id]
                else:
                    art = fetch_article(session, base_url, article_id, logger, args.throttle)
                    if art:
                        article_number = art.get("articleNumber") or ""
                        article_title = art.get("title") or ""
                    article_cache[article_id] = (article_number, article_title)

            # CSV C требует только позиции, где реально есть articleNumber
            if article_number:
                key = (article_number, article_title or line_name or article_number)
                agg[key] = agg.get(key, 0.0) + float(net_val)

            # audit dump (если нужен)
            if args.audit_out:
                audit_rows.append([
                    inv_number,
                    inv_date,
                    cust_name,
                    cust_id,
                    it_type,
                    line_name,
                    qty,
                    f"{float(net_val):.2f}",
                    tax_rate,
                    article_id or "",
                    article_number or "",
                ])

        if idx % 10 == 0 or idx == len(invoice_ids):
            logger.info("processed invoices %s/%s cache_articles=%s", idx, len(invoice_ids), len(article_cache))

    # build output rows
    out_rows = []
    for (anum, aname), total in sorted(agg.items(), key=lambda x: (x[0][0], x[0][1])):
        out_rows.append([anum, aname, f"{float(total):.2f}"])

    write_csv_c(out, out_rows, delimiter=args.delimiter)
    logger.info("csvC written path=%s rows=%s log=%s", out, len(out_rows), log_path)

    if args.audit_out:
        write_audit_lines(args.audit_out, audit_rows, delimiter=args.delimiter)
        logger.info("audit written path=%s rows=%s", args.audit_out, len(audit_rows))


if __name__ == "__main__":
    """
    Пример:
      python3 csv_c.py --month 2026-01 --voucher-status any --out csvC_2026-01.csv
      python3 csv_c.py --month 2026-01 --audit-out audit_lines_2026-01.csv

      Только CSV C:

python3 csv_c.py --month 2026-01 --out csvC_2026-01.csv


CSV C + подробный “audit” по всем строкам инвойсов (это покрывает второе требование “Data to Extract from Lexoffice”):

python3 csv_c.py --month 2026-01 --audit-out audit_lines_2026-01.csv
    """
    main()
