import os
import csv
import time
import argparse
import re
import logging
from datetime import datetime, date, timedelta

import requests
from dotenv import load_dotenv

DEFAULT_TIMEOUT = 30


# =========================
# helpers
# =========================

def ensure_dir(path):
    if path:
        os.makedirs(path, exist_ok=True)


def write_text_file(path, text):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def normalize_base(base_url):
    return (base_url or "https://api.lexware.io").rstrip("/")


def setup_logger(name, level="INFO"):
    ensure_dir("logs")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"logs/{name}_{ts}.log"

    lvl = getattr(logging, level.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(lvl)
    logger.handlers = []
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    logger.info("logger initialized path=%s", log_path)
    return logger, log_path


def build_session(token):
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + token, "Accept": "application/json"})
    return s


def request_json(session, url, logger, params=None, throttle=0.6, retries=5):
    last = None
    for i in range(1, retries + 1):
        time.sleep(throttle)
        try:
            r = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            if r.status_code in (429, 502, 503, 504):
                wait = min(10, i * 1.5)
                logger.warning("retry %s wait %.1fs", i, wait)
                time.sleep(wait)
                continue

            return {
                "ok": r.status_code < 400,
                "status": r.status_code,
                "data": r.json() if r.text else {},
                "text": r.text[:2000],
            }
        except Exception as e:
            last = str(e)
            logger.warning("retry %s error=%s", i, e)
    return {"ok": False, "error": last}


def month_range(yyyy_mm):
    y, m = map(int, yyyy_mm.split("-"))
    start = date(y, m, 1)
    end = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    return start, end


def prev_month_yyyy_mm(today=None):
    today = today or date.today()
    first = date(today.year, today.month, 1)
    prev_last = first - timedelta(days=1)
    return "%04d-%02d" % (prev_last.year, prev_last.month)


def looks_like_uuid(s):
    return bool(re.match(r"^[0-9a-fA-F-]{36}$", str(s)))


def net_from_item(it):
    if it.get("lineItemAmount"):
        return float(it["lineItemAmount"])
    qty = it.get("quantity") or 0
    price = (it.get("unitPrice") or {}).get("netAmount") or 0
    return float(qty) * float(price)


def main():
    load_dotenv()

    p = argparse.ArgumentParser()
    p.add_argument("--month", default=None, help="YYYY-MM (default: previous month)")
    p.add_argument("--out", default=None, help="output CSV path (default: csv/csv_C_YYYY-MM.csv)")
    p.add_argument("--throttle", type=float, default=0.6)
    args = p.parse_args()

    if not args.month:
        args.month = prev_month_yyyy_mm()

    token = os.getenv("LEXOFFICE_TOKEN")
    if not token:
        raise SystemExit("LEXOFFICE_TOKEN missing")

    base = normalize_base(os.getenv("LEXOFFICE_BASE_URL"))
    logger, log_path = setup_logger("csv_c")

    ensure_dir("csv")
    out = args.out or os.path.join("csv", "csv_C_%s.csv" % args.month)

    ensure_dir("email")

    session = build_session(token)

    logger.info("start month=%s out=%s", args.month, out)

    start, end = month_range(args.month)

    ids = []
    page = 0

    while True:
        resp = request_json(
            session,
            base + "/v1/voucherlist",
            logger,
            params={
                "voucherType": "invoice",
                "voucherStatus": "any",
                "voucherDateFrom": start.isoformat(),
                "voucherDateTo": end.isoformat(),
                "size": 250,
                "page": page,
            },
        )
        if not resp["ok"]:
            raise SystemExit(resp)

        data = resp["data"].get("content") or []
        for r in data:
            ids.append(r["id"])

        if len(data) < 250:
            break
        page += 1

    logger.info("found invoices=%s", len(ids))

    article_cache = {}
    agg = {}

    for idx, inv_id in enumerate(ids, 1):
        inv = request_json(session, f"{base}/v1/invoices/{inv_id}", logger)["data"]

        for it in inv.get("lineItems") or []:
            if it.get("type") == "text":
                continue

            article_id = it.get("id")
            if not looks_like_uuid(article_id):
                continue

            if article_id not in article_cache:
                art = request_json(session, f"{base}/v1/articles/{article_id}", logger)["data"]
                article_cache[article_id] = (
                    art.get("articleNumber"),
                    art.get("title"),
                )

            num, name = article_cache[article_id]
            if not num:
                continue

            key = (num, name)
            agg[key] = agg.get(key, 0) + net_from_item(it)

        if idx % 10 == 0:
            logger.info("processed %s/%s", idx, len(ids))

    rows = [[k[0], k[1], f"{v:.2f}"] for k, v in sorted(agg.items())]

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ArticleNumber", "ArticleName", "NetRevenueEUR"])
        w.writerows(rows)

    report = f"""
CSV C SUCCESS
Month: {args.month}
Rows: {len(rows)}
File: {out}
Log: {log_path}
""".strip() + "\n"

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    email_file = f"email/csv_C_{ts}.txt"
    write_text_file(email_file, report)

    logger.info("done rows=%s", len(rows))


if __name__ == "__main__":
    main()
