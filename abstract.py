import os
import time
import requests
import json
from datetime import datetime, date, timedelta



DEFAULT_TIMEOUT = 30
ALLOWED_INVOICE_STATUSES = "open,paid" # or any

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


def prev_month_yyyy_mm(today=None):
    today = today or date.today()
    first = date(today.year, today.month, 1)
    prev_last = first - timedelta(days=1)
    return "%04d-%02d" % (prev_last.year, prev_last.month)


def pad5(n):
    try:
        return str(int(n)).zfill(5)
    except Exception:
        return "00000"


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



def format_amount(x):
    try:
        val = float(x)
        s = f"{val:,.2f}"          # 123,456.78
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return s                   # 123.456,78
    except Exception:
        return "0,00"


def compact_json(data, limit=4000):
    try:
        s = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        s = str(data)

    if limit and len(s) > limit:
        return s[:limit] + "...<truncated>"
    return s


def fetch_contact_number(session, base_url, logger, contact_id, cache, throttle):
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

    num = ((roles.get("customer") or {}).get("number")) or ((roles.get("vendor") or {}).get("number"))
    cache[contact_id] = pad5(num)
    return cache[contact_id]
