import os
import csv
import argparse
import re
import logging
from datetime import datetime

from dotenv import load_dotenv

from abstract import (
    ALLOWED_INVOICE_STATUSES,
    ensure_dir, write_text_file, prev_month_yyyy_mm, month_range,
    normalize_base, build_session, request_json,
    format_amount, 
)

# =========================
# helpers
# =========================

NO_ARTICLE_NUMBER = "No Number"
NO_ARTICLE_NAME = "Other"


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
            "GET",
            base + "/v1/voucherlist",
            logger,
            params={
                "voucherType": "invoice",
                "voucherStatus": ALLOWED_INVOICE_STATUSES,
                "voucherDateFrom": start.isoformat(),
                "voucherDateTo": end.isoformat(),
                "size": 250,
                "page": page,
            },
            throttle=args.throttle,
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
        inv_resp = request_json(session, "GET", f"{base}/v1/invoices/{inv_id}", logger, throttle=args.throttle)
        if not inv_resp["ok"]:
            raise SystemExit(inv_resp)
        inv = inv_resp["data"]

        for it in inv.get("lineItems") or []:
            if it.get("type") == "text":
                continue

            article_id = it.get("id")

            if looks_like_uuid(article_id):

                if article_id not in article_cache:
                    art_resp = request_json(session, "GET", f"{base}/v1/articles/{article_id}", logger, throttle=args.throttle)
                    if not art_resp["ok"]:
                        raise SystemExit(art_resp)
                    art = art_resp["data"]
                    article_cache[article_id] = (
                        art.get("articleNumber"),
                        art.get("title"),
                    )

                num, name = article_cache[article_id]

                if not num:
                    num = NO_ARTICLE_NUMBER
                if not name:
                    name = NO_ARTICLE_NAME

            else:
                num = NO_ARTICLE_NUMBER
                name = NO_ARTICLE_NAME

            key = (num, name)
            agg[key] = agg.get(key, 0) + net_from_item(it)

        if idx % 10 == 0:
            logger.info("processed %s/%s", idx, len(ids))

    rows = [[k[0], k[1], format_amount(v)] for k, v in sorted(agg.items())]

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ArticleNumber", "ArticleName", "NetRevenueEUR"])
        w.writerows(rows)

    report = f"""
CSV C SUCCESS
Month: {args.month}
Rows: {len(rows)}
File: {out}
""".strip() + "\n"

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    email_file = f"email/csv_C_{ts}.txt"
    write_text_file(email_file, report)

    logger.info("done rows=%s", len(rows))


if __name__ == "__main__":
    main()
