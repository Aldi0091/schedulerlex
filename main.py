import os
import json
import time
import argparse
import requests
from dotenv import load_dotenv

DEFAULT_TIMEOUT = 30

def jprint(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def build_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    })
    return s

def request_json(session, method, url, params=None, data=None, timeout=DEFAULT_TIMEOUT, max_retries=5, sleep_seconds=0.6):
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            if sleep_seconds:
                time.sleep(sleep_seconds)

            if method == "GET":
                r = session.get(url, params=params, timeout=timeout)
            elif method == "POST":
                r = session.post(url, params=params, json=data, timeout=timeout)
            elif method == "PUT":
                r = session.put(url, params=params, json=data, timeout=timeout)
            elif method == "PATCH":
                r = session.patch(url, params=params, json=data, timeout=timeout)
            elif method == "DELETE":
                r = session.delete(url, params=params, timeout=timeout)
            else:
                raise ValueError("Unsupported method: " + method)

            # rate limit / temporary issues
            if r.status_code in (429, 502, 503, 504):
                wait = min(10, attempt * 1.5)
                print(f"[warn] {r.status_code} retry in {wait}s (attempt {attempt}/{max_retries})")
                time.sleep(wait)
                last_err = (r.status_code, r.text)
                continue

            # normal error
            if r.status_code >= 400:
                return {
                    "ok": False,
                    "status": r.status_code,
                    "url": r.url,
                    "error": safe_json(r),
                    "text": r.text[:5000],
                }

            return {
                "ok": True,
                "status": r.status_code,
                "url": r.url,
                "data": safe_json(r),
            }

        except Exception as e:
            last_err = str(e)
            wait = min(10, attempt * 1.5)
            print(f"[warn] exception retry in {wait}s (attempt {attempt}/{max_retries}) -> {e}")
            time.sleep(wait)

    return {"ok": False, "status": None, "url": url, "error": last_err}

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}

def normalize_base(base_url):
    base_url = (base_url or "").strip()
    if not base_url:
        return "https://api.lexware.io"
    return base_url.rstrip("/")

def cmd_ping(session, base_url, args):
    # ping через voucherlist: он требует обязательные параметры voucherType/voucherStatus
    url = base_url + "/v1/voucherlist"
    params = {"voucherType": args.voucher_type, "voucherStatus": args.voucher_status}
    out = request_json(session, "GET", url, params=params, sleep_seconds=args.throttle)
    jprint(out)

def cmd_voucherlist(session, base_url, args):
    url = base_url + "/v1/voucherlist"
    params = {
        "voucherType": args.voucher_type,
        "voucherStatus": args.voucher_status,
    }
    if args.voucher_date_from:
        params["voucherDateFrom"] = args.voucher_date_from
    if args.voucher_date_to:
        params["voucherDateTo"] = args.voucher_date_to
    if args.page is not None:
        params["page"] = args.page
    if args.size is not None:
        params["size"] = args.size

    out = request_json(session, "GET", url, params=params, sleep_seconds=args.throttle)
    jprint(out)

def cmd_invoice(session, base_url, args):
    url = base_url + "/v1/invoices/" + args.id
    out = request_json(session, "GET", url, sleep_seconds=args.throttle)
    jprint(out)

def cmd_contacts(session, base_url, args):
    # самый частый путь: /v1/contacts (в доках есть раздел contacts)
    url = base_url + "/v1/contacts"
    params = {}
    if args.page is not None:
        params["page"] = args.page
    if args.size is not None:
        params["size"] = args.size
    out = request_json(session, "GET", url, params=params, sleep_seconds=args.throttle)
    jprint(out)

def cmd_articles(session, base_url, args):
    # часто нужен для “Article Revenue”
    url = base_url + "/v1/articles"
    params = {}
    if args.page is not None:
        params["page"] = args.page
    if args.size is not None:
        params["size"] = args.size
    out = request_json(session, "GET", url, params=params, sleep_seconds=args.throttle)
    jprint(out)

def cmd_raw(session, base_url, args):
    path = args.path.strip()
    if not path.startswith("/"):
        path = "/" + path
    url = base_url + path

    params = {}
    if args.query:
        for kv in args.query:
            if "=" not in kv:
                raise SystemExit("Bad --query item, expected key=value, got: " + kv)
            k, v = kv.split("=", 1)
            params[k] = v

    data = None
    if args.json:
        data = json.loads(args.json)

    out = request_json(session, args.method.upper(), url, params=params, data=data, sleep_seconds=args.throttle)
    jprint(out)

def main():
    load_dotenv()

    token = os.getenv("LEXOFFICE_TOKEN")
    if not token:
        raise SystemExit("LEXOFFICE_TOKEN is missing in .env")

    base_url = normalize_base(os.getenv("LEXOFFICE_BASE_URL"))

    parser = argparse.ArgumentParser(prog="lexcli", description="Lexware Office (Lexoffice) Public API CLI")
    parser.add_argument("--throttle", type=float, default=0.6, help="sleep seconds before each request (default 0.6)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ping = sub.add_parser("ping", help="quick check (voucherlist with required params)")
    p_ping.add_argument("--voucher-type", default="invoice", help="voucherType (default: invoice)")
    p_ping.add_argument("--voucher-status", default="any", help="voucherStatus (default: any)")
    p_ping.set_defaults(func=cmd_ping)

    p_vl = sub.add_parser("voucherlist", help="list vouchers (requires voucherType & voucherStatus)")
    p_vl.add_argument("--voucher-type", default="invoice", help="voucherType (default: invoice)")
    p_vl.add_argument("--voucher-status", default="any", help="voucherStatus (default: any)")
    p_vl.add_argument("--voucher-date-from", default=None, help="voucherDateFrom YYYY-MM-DD")
    p_vl.add_argument("--voucher-date-to", default=None, help="voucherDateTo YYYY-MM-DD")
    p_vl.add_argument("--page", type=int, default=None, help="page number")
    p_vl.add_argument("--size", type=int, default=None, help="page size")
    p_vl.set_defaults(func=cmd_voucherlist)

    p_inv = sub.add_parser("invoice", help="get invoice by id")
    p_inv.add_argument("id", help="invoice id")
    p_inv.set_defaults(func=cmd_invoice)

    p_contacts = sub.add_parser("contacts", help="list contacts")
    p_contacts.add_argument("--page", type=int, default=None)
    p_contacts.add_argument("--size", type=int, default=None)
    p_contacts.set_defaults(func=cmd_contacts)

    p_articles = sub.add_parser("articles", help="list articles")
    p_articles.add_argument("--page", type=int, default=None)
    p_articles.add_argument("--size", type=int, default=None)
    p_articles.set_defaults(func=cmd_articles)

    p_raw = sub.add_parser("raw", help="call any path, e.g. raw --path /v1/invoices/ID")
    p_raw.add_argument("--method", default="GET", help="HTTP method (GET/POST/PUT/PATCH/DELETE)")
    p_raw.add_argument("--path", required=True, help="API path starting with /v1/...")
    p_raw.add_argument("--query", action="append", default=None, help="query param: key=value (repeatable)")
    p_raw.add_argument("--json", default=None, help="json body as string")
    p_raw.set_defaults(func=cmd_raw)

    args = parser.parse_args()

    session = build_session(token)
    args.func(session, base_url, args)

if __name__ == "__main__":
    """
# Список инвойсов за период (прошлый месяц руками)
python3 main.py voucherlist --voucher-type invoice --voucher-status any \
--voucher-date-from 2025-12-01 --voucher-date-to 2025-12-31

    """
    main()


