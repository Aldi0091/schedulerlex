import os
import csv
import argparse
import re
import unicodedata
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from dotenv import load_dotenv

from abstract import (
    compact_json, ALLOWED_INVOICE_STATUSES,
    ensure_dir, write_text_file, prev_month_yyyy_mm, month_range, parse_date_ddmmyyyy,
    normalize_base, build_session, request_json, pad5,
    E_CONFIG, E_HTTP, E_SCHEMA, E_MAPPING, E_WRITE, E_RUNTIME,
    format_amount, 
)


def setup_logger(log_file=None, level="INFO"):
    level = (level or "INFO").upper()
    level_value = getattr(logging, level, logging.INFO)

    logger = logging.getLogger("lex_csv_b")
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



def fetch_voucherlist(session, base_url, logger, voucher_types, voucher_statuses, throttle, size=250,
                     voucher_date_from=None, voucher_date_to=None):
    url = base_url + "/v1/voucherlist"
    params = {
        "voucherType": ",".join(voucher_types),
        "voucherStatus": ",".join(voucher_statuses),
        "size": int(size),
        "page": 0,
    }

    # monthly filter (optional)
    if voucher_date_from:
        params["voucherDateFrom"] = voucher_date_from
    if voucher_date_to:
        params["voucherDateTo"] = voucher_date_to

    all_rows = []
    while True:
        resp = request_json(session, "GET", url, logger, params=params, throttle=throttle)
        if not resp["ok"]:
            raise RuntimeError("%s voucherlist_failed status=%s url=%s" % (E_HTTP, resp.get("status"), resp.get("url")))

        data = resp["data"] or {}
        content = data.get("content") or []
        all_rows.extend(content)

        logger.info("voucherlist page=%s got=%s total=%s types=%s status=%s dateFrom=%s dateTo=%s",
                    params["page"], len(content), len(all_rows), params["voucherType"], params["voucherStatus"],
                    params.get("voucherDateFrom"), params.get("voucherDateTo"))

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
    for key in ("totalNetAmount", "netTotal", "netAmount"):
        if key in tp and tp[key] is not None:
            try:
                return float(tp[key])
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

    return fetch_voucher_detail_net(session, base_url, logger, vid, throttle)


def build_csv_rows(session, base_url, logger, vouchers, throttle):
    contact_cache = {}
    rows = []

    for i, v in enumerate(vouchers, 1):
        voucher_type = (v.get("voucherType") or "").lower()
        kind = classify_kind(voucher_type)

        if voucher_type not in ("invoice", "purchaseinvoice"):
            continue

        partner_name = sanitize_partner_name(v.get("contactName") or "")
        invoice_id = v.get("voucherNumber") or v.get("id") or ""

        creation_date = parse_date_ddmmyyyy(v.get("createdDate") or "")
        due_date = parse_date_ddmmyyyy(v.get("dueDate") or "")

        contact_id = v.get("contactId")
        partner_number = fetch_contact_number(session, base_url, logger, contact_id, kind, contact_cache, throttle)

        total_net = resolve_total_net(session, base_url, logger, v, throttle)
        if total_net is None:
            logger.warning("cannot resolve net amount voucherType=%s id=%s voucherNumber=%s",
                           v.get("voucherType"), v.get("id"), v.get("voucherNumber"))
            total_net = 0.0

        rows.append([
            partner_number,
            partner_name,
            invoice_id,
            creation_date,
            due_date,
            kind.capitalize(),
            format_amount(total_net),
        ])

        if i % 25 == 0:
            logger.info("processed=%s/%s rows=%s", i, len(vouchers), len(rows))

    return rows


def write_csv(path, rows, delimiter=",", logger=None):
    header = [
        "PartnerNumber",
        "PartnerName",
        "InvoiceID",
        "CreationDate",
        "DueDate",
        "ReceivableOrPayable",
        "TotalNetAmountEUR",
    ]
    try:
        ensure_dir(os.path.dirname(path))
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


def build_email_report(status, error_code, log_file, out_csv, email_report_file, month, summary_lines, hint_items=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subj_status = "SUCCESS" if status == "SUCCESS" else "FAILED"
    subject = "[Lexoffice CSV B] %s (%s) %s" % (subj_status, error_code, ts)

    lines = []
    lines.append("Subject: %s" % subject)
    lines.append("")
    lines.append("Execution status: %s" % subj_status)
    lines.append("Time: %s" % ts)
    if month:
        lines.append("Period: %s" % month)

    lines.append("Job: CSV B (Open Items: Receivables & Payables) [MONTH-FILTERED]")
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

    token = os.getenv("LEXOFFICE_TOKEN")
    if not token:
        raise SystemExit("%s LEXOFFICE_TOKEN missing in .env" % E_CONFIG)

    base_url = normalize_base(os.getenv("LEXOFFICE_BASE_URL"))

    p = argparse.ArgumentParser(description="CSV B: Open Items (Receivables & Payables) - monthly filter")
    p.add_argument("--month", default=None, help="YYYY-MM (default: previous month)")
    p.add_argument("--out", default=None, help="output CSV path")
    p.add_argument("--delimiter", default=";", help="CSV delimiter (; recommended for German Excel)")
    p.add_argument("--throttle", type=float, default=0.6, help="sleep seconds before each request")
    p.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    p.add_argument("--log-file", default=None, help="path to log file; default logs/csv_b_YYYYmmdd_HHMMSS.log")
    args = p.parse_args()

    month = args.month or prev_month_yyyy_mm()

    start, end = month_range(month)
    voucher_date_from = start.isoformat()
    voucher_date_to = end.isoformat()

    if not args.log_file:
        ensure_dir("logs")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.log_file = os.path.join("logs", "csv_b_%s.log" % ts)

    logger = setup_logger(args.log_file, level=args.log_level)

    ensure_dir("email")
    ts_for_email = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    email_report_file = os.path.join("email", "csv_B_%s.txt" % ts_for_email)

    out = args.out
    if not out:
        ensure_dir("csv")
        out = os.path.join("csv", "csv_B_open_items_%s.csv" % month)

    logger.info("start csv_b month=%s out=%s base_url=%s dateFrom=%s dateTo=%s",
                month, out, base_url, voucher_date_from, voucher_date_to)

    session = build_session(token)

    try:
        open_statuses = ["open", "sepadebit"]
        voucher_types = ["invoice", "purchaseinvoice"]

        v_open = fetch_voucherlist(
            session, base_url, logger, voucher_types, open_statuses,
            throttle=args.throttle, voucher_date_from=voucher_date_from, voucher_date_to=voucher_date_to
        )
        v_overdue = fetch_voucherlist(
            session, base_url, logger, voucher_types, ["overdue"],
            throttle=args.throttle, voucher_date_from=voucher_date_from, voucher_date_to=voucher_date_to
        )

        combined = v_open + v_overdue
        seen = set()
        unique = []

        for v in combined:
            vid = v.get("id")
            if vid and vid not in seen:
                seen.add(vid)
                unique.append(v)

        combined = unique
        logger.info("voucherlist combined total=%s (open=%s overdue=%s)", len(combined), len(v_open), len(v_overdue))

        rows = build_csv_rows(session, base_url, logger, combined, throttle=args.throttle)
        write_csv(out, rows, delimiter=args.delimiter, logger=logger)

        email_report = build_email_report(
            status="SUCCESS",
            error_code="OK",
            log_file=args.log_file,
            out_csv=out,
            email_report_file=email_report_file,
            month=month,
            summary_lines=[
                "CSV generated successfully",
                "Rows exported: %s" % len(rows),
                "Filter: voucherDateFrom=%s voucherDateTo=%s" % (voucher_date_from, voucher_date_to),
                "Included: open receivables + open payables + overdue (within month)",
            ],
            hint_items=None
        )

        write_text_file(email_report_file, email_report)
        logger.info("email report written: %s", email_report_file)

        print("\n" + "=" * 60 + "\n" + email_report + "\n" + "=" * 60 + "\n")
        logger.info("done ok out=%s rows=%s log=%s", out, len(rows), args.log_file)

    except Exception as e:
        logger.error("%s failure: %s", E_RUNTIME, e)

        hints = [
            "If DNS/network: check server internet/DNS/proxy rules",
            "Try again in 1-2 minutes (temporary network failures happen)",
            "Check LEXOFFICE_TOKEN and LEXOFFICE_BASE_URL in .env",
            "If rate limit: increase --throttle (e.g. 1.0) and retry",
        ]

        email_report = build_email_report(
            status="FAILED",
            error_code=E_RUNTIME,
            log_file=args.log_file,
            out_csv=out,
            email_report_file=email_report_file,
            month=month,
            summary_lines=[
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
