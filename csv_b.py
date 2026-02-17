import os
import csv
import json
import time
import argparse
import re
import unicodedata
import logging
from datetime import datetime

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


def setup_logger(name, log_dir="logs", level=logging.INFO):
    ensure_dir(log_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{name}_{ts}.log")

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers = []
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(level)
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
                logger.warning("HTTP %s retry in %.1fs attempt=%s/%s url=%s", r.status_code, wait, attempt, max_retries, r.url)
                time.sleep(wait)
                last = (r.status_code, r.text[:2000])
                continue

            if r.status_code >= 400:
                logger.error("HTTP %s error url=%s body=%s", r.status_code, r.url, (r.text or "")[:2000])

            out = {
                "ok": r.status_code < 400,
                "status": r.status_code,
                "url": r.url,
                "data": safe_json(r),
                "text": (r.text or "")[:4000],
            }
            return out

        except Exception as e:
            wait = min(10, attempt * 1.5)
            logger.warning("exception retry in %.1fs attempt=%s/%s url=%s err=%s", wait, attempt, max_retries, url, e)
            time.sleep(wait)
            last = str(e)

    return {"ok": False, "status": None, "url": url, "error": last, "data": None, "text": ""}


def parse_date_ddmmyyyy(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except Exception:
        try:
            d = datetime.fromisoformat(value[:19])
            return d.strftime("%d.%m.%Y")
        except Exception:
            return value


def sanitize_partner_name(name):
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


def format_amount(x):
    try:
        return f"{float(x):.2f}"
    except Exception:
        return "0.00"


def pad5(n):
    try:
        return str(int(n)).zfill(5)
    except Exception:
        return "00000"


def fetch_voucherlist(session, base_url, logger, voucher_types, voucher_statuses, throttle, size=250):
    url = base_url + "/v1/voucherlist"
    params = {
        "voucherType": ",".join(voucher_types),
        "voucherStatus": ",".join(voucher_statuses),
        "size": int(size),
        "page": 0,
    }

    all_rows = []
    while True:
        resp = request_json(session, "GET", url, logger, params=params, throttle=throttle)
        if not resp["ok"]:
            raise SystemExit(json.dumps(resp, ensure_ascii=False, indent=2))

        data = resp["data"] or {}
        content = data.get("content") or []
        all_rows.extend(content)

        logger.info("voucherlist page=%s got=%s total_so_far=%s types=%s status=%s",
                    params["page"], len(content), len(all_rows), params["voucherType"], params["voucherStatus"])

        if len(content) < int(params["size"]):
            break
        params["page"] += 1

    return all_rows


def fetch_invoice_detail_net(session, base_url, logger, invoice_id, throttle):
    url = base_url + "/v1/invoices/" + invoice_id
    resp = request_json(session, "GET", url, logger, throttle=throttle)
    if not resp["ok"]:
        return None

    inv = resp["data"] or {}
    tp = inv.get("totalPrice") or {}
    if "totalNetAmount" in tp and tp["totalNetAmount"] is not None:
        try:
            return float(tp["totalNetAmount"])
        except Exception:
            return None
    return None


def fetch_voucher_detail_net(session, base_url, logger, voucher_id, throttle):
    url = base_url + "/v1/vouchers/" + voucher_id
    resp = request_json(session, "GET", url, logger, throttle=throttle)
    if not resp["ok"]:
        return None

    v = resp["data"] or {}

    if "totalNetAmount" in v and v["totalNetAmount"] is not None:
        try:
            return float(v["totalNetAmount"])
        except Exception:
            pass

    gross = v.get("totalGrossAmount")
    tax = v.get("totalTaxAmount")
    try:
        if gross is not None and tax is not None:
            return float(gross) - float(tax)
    except Exception:
        return None

    return None


def fetch_contact_number(session, base_url, logger, contact_id, kind, cache, throttle):
    if not contact_id:
        return "00000"
    if contact_id in cache:
        return cache[contact_id]

    url = base_url + "/v1/contacts/" + contact_id
    resp = request_json(session, "GET", url, logger, throttle=throttle)
    if not resp["ok"]:
        cache[contact_id] = "00000"
        return cache[contact_id]

    c = resp["data"] or {}
    roles = c.get("roles") or {}
    num = None

    if kind == "receivable":
        num = ((roles.get("customer") or {}).get("number")) or ((roles.get("vendor") or {}).get("number"))
    else:
        num = ((roles.get("vendor") or {}).get("number")) or ((roles.get("customer") or {}).get("number"))

    cache[contact_id] = pad5(num)
    return cache[contact_id]


def classify_kind(voucher_type):
    vt = (voucher_type or "").strip().lower()
    if vt in ("purchaseinvoice", "purchasecreditnote"):
        return "payable"
    return "receivable"


def resolve_total_net(session, base_url, logger, voucher_meta, throttle):
    voucher_type = (voucher_meta.get("voucherType") or "").lower()
    vid = voucher_meta.get("id")

    if not vid:
        return None

    if voucher_type == "invoice":
        return fetch_invoice_detail_net(session, base_url, logger, vid, throttle)

    if voucher_type == "purchaseinvoice":
        return fetch_voucher_detail_net(session, base_url, logger, vid, throttle)

    # если внезапно прилетели salesinvoice и т.п. (тоже через /v1/vouchers)
    return fetch_voucher_detail_net(session, base_url, logger, vid, throttle)


def build_csv_rows(session, base_url, logger, vouchers, throttle):
    contact_cache = {}
    rows = []

    for i, v in enumerate(vouchers, 1):
        voucher_type = v.get("voucherType") or ""
        kind = classify_kind(voucher_type)

        # фильтруем только нужные типы, чтобы не тащить всё подряд
        if (voucher_type or "").lower() not in ("invoice", "purchaseinvoice"):
            continue

        partner_name = sanitize_partner_name(v.get("contactName") or "")
        invoice_id = v.get("voucherNumber") or v.get("id") or ""

        creation_date = parse_date_ddmmyyyy(v.get("createdDate") or "")
        due_date = parse_date_ddmmyyyy(v.get("dueDate") or "")

        contact_id = v.get("contactId")
        partner_number = fetch_contact_number(session, base_url, logger, contact_id, kind, contact_cache, throttle)

        total_net = resolve_total_net(session, base_url, logger, v, throttle)
        if total_net is None:
            # запасной вариант: если net не нашли, логируем и ставим 0.00,
            # чтобы CSV всё равно собрался (и ты увидел проблемные места).
            logger.warning("cannot resolve net amount voucherType=%s id=%s voucherNumber=%s", voucher_type, v.get("id"), v.get("voucherNumber"))
            total_net = 0.0

        rows.append([
            partner_number,
            partner_name,
            invoice_id,
            creation_date,
            due_date,
            format_amount(total_net),
        ])

        if i % 25 == 0:
            logger.info("processed=%s/%s rows=%s", i, len(vouchers), len(rows))

    return rows


def write_csv(path, rows, delimiter=","):
    header = [
        "PartnerNumber",
        "PartnerName",
        "InvoiceID",
        "CreationDate",
        "DueDate",
        "TotalNetAmountEUR",
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

    p = argparse.ArgumentParser(description="CSV B: Open Items (Receivables & Payables) via voucherlist")
    p.add_argument("--out", default=None, help="output CSV path")
    p.add_argument("--delimiter", default=",", help="CSV delimiter (, or ;)")
    p.add_argument("--throttle", type=float, default=0.6, help="sleep seconds before each request")
    p.add_argument("--log-dir", default="logs", help="directory for log files")
    args = p.parse_args()

    logger, log_path = setup_logger("csv_b", log_dir=args.log_dir, level=logging.INFO)

    out = args.out
    if not out:
        out = "csv_b_open_items.csv"

    logger.info("start csv_b out=%s base_url=%s", out, base_url)

    session = build_session(token)

    # 1) open + sepadebit вместе (разрешено списком через запятую)
    open_statuses = ["open", "sepadebit"]
    voucher_types = ["invoice", "purchaseinvoice"]
    v_open = fetch_voucherlist(session, base_url, logger, voucher_types, open_statuses, throttle=args.throttle)

    # 2) overdue отдельно (в доке указано, что overdue нельзя миксовать с другими статусами)
    v_overdue = fetch_voucherlist(session, base_url, logger, voucher_types, ["overdue"], throttle=args.throttle)

    combined = v_open + v_overdue
    logger.info("voucherlist combined total=%s (open=%s overdue=%s)", len(combined), len(v_open), len(v_overdue))

    rows = build_csv_rows(session, base_url, logger, combined, throttle=args.throttle)
    write_csv(out, rows, delimiter=args.delimiter)

    logger.info("csv written path=%s rows=%s", out, len(rows))
    logger.info("done ok rows=%s log=%s", len(rows), log_path)


if __name__ == "__main__":
    """
    Пример:
      python3 csv_b.py --out csvB_open_items.csv --delimiter "," --throttle 0.6

    Требует .env:
      LEXOFFICE_TOKEN=...
      LEXOFFICE_BASE_URL=https://api.lexware.io   (можно не задавать, по умолчанию так)
    """
    main()
