"""

Насеять за прошлый месяц (январь 2026)

python3 seed.py seed-last-month --count 12 --customers 6 --finalize --complexity medium

Или явно за месяц

python3 seed.py seed-month --month 2026-01 --count 12 --customers 6 --finalize


"""

import os
import json
import time
import random
import argparse
import requests
from dotenv import load_dotenv
from datetime import date, timedelta

DEFAULT_TIMEOUT = 30


def jprint(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


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
        "Content-Type": "application/json",
    })
    return s


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def request_json(session, method, url, params=None, data=None, throttle=0.6, max_retries=5):
    last = None
    for attempt in range(1, max_retries + 1):
        if throttle:
            time.sleep(throttle)

        try:
            if method == "GET":
                r = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            elif method == "POST":
                r = session.post(url, params=params, json=data, timeout=DEFAULT_TIMEOUT)
            else:
                raise ValueError("Unsupported method: " + method)

            if r.status_code in (429, 502, 503, 504):
                wait = min(10, attempt * 1.5)
                print(f"[warn] {r.status_code} retry in {wait}s (attempt {attempt}/{max_retries})")
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
                out["text"] = r.text[:4000]
            return out

        except Exception as e:
            wait = min(10, attempt * 1.5)
            print(f"[warn] exception retry in {wait}s (attempt {attempt}/{max_retries}) -> {e}")
            time.sleep(wait)
            last = str(e)

    return {"ok": False, "status": None, "url": url, "error": last}


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


def prev_month_yyyy_mm(today=None):
    today = today or date.today()
    first = today.replace(day=1)
    last_prev = first - timedelta(days=1)
    return f"{last_prev.year:04d}-{last_prev.month:02d}"


def random_day(start, end):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def create_contact(session, base_url, name, country="DE", city="Hamburg"):
    url = base_url + "/v1/contacts"
    payload = {
        "version": 0,
        "roles": {"customer": {}},
        "company": {"name": name},
        "addresses": {
            "billing": [{
                "street": "Hafenstraße 12",
                "zip": "20457",
                "city": city,
                "countryCode": country
            }]
        }
    }
    return request_json(session, "POST", url, data=payload)


def build_invoice_payload(voucher_date_iso, customer_name, contact_id, line_items, tax_type="net"):
    payload = {
        "voucherDate": voucher_date_iso,
        "address": {
            "contactId": contact_id,
            "name": customer_name,
            "countryCode": "DE"
        },
        "lineItems": line_items,
        "totalPrice": {"currency": "EUR"},
        "taxConditions": {"taxType": tax_type},
        "shippingConditions": {"shippingType": "none"},
    }
    return payload


def create_invoice(session, base_url, payload, finalize=False):
    url = base_url + "/v1/invoices"
    params = {}
    if finalize:
        params["finalize"] = "true"
    return request_json(session, "POST", url, params=params, data=payload)


def make_line_item_custom(name, qty, unit, net_amount, tax_rate=19):
    return {
        "type": "custom",
        "name": name,
        "quantity": float(qty),
        "unitName": unit,
        "unitPrice": {
            "currency": "EUR",
            "netAmount": round(float(net_amount), 2),
            "taxRatePercentage": int(tax_rate)
        }
    }


def german_customers():
    # letters + spaces only (csv_a sanitization will keep it)
    return [
        ("Nordsee Container Handel", "Hamburg"),
        ("Rhein Main Logistik", "Frankfurt am Main"),
        ("Bayerische Lager Solutions", "München"),
        ("Hanseatische Transport Dienste", "Bremen"),
        ("Sachsen Selfstorage", "Leipzig"),
        ("Ruhrgebiet Baustellen Service", "Essen"),
        ("Bodensee Containervermietung", "Konstanz"),
        ("Spreewald Lager und Transport", "Berlin"),
    ]


def line_item_catalog():
    # Каталог позиций с ключевыми словами для маппинга клиента:
    # Rental: miete/vermietung
    # Sales: gebraucht/neuwertig/fabrikneu
    # Transport: transport/anlieferung/rücktransport
    # Storage: selfstorage
    # Additional charges: nebenkosten/service
    return {
        "Sales": [
            ("Gebrauchter Seecontainer 20 Fuß", 1, "Stk", (1800, 3200)),
            ("Neuwertig Shipping Container 40 Fuß", 1, "Stk", (2900, 5200)),
            ("Fabrikneu Bürocontainer 10 Fuß", 1, "Stk", (4200, 7800)),
            ("Gebraucht Container mit Tür", 1, "Stk", (2100, 4100)),
        ],
        "Transport": [
            ("Transport | Kran-LKW", 1, "Leistung", (180, 520)),
            ("Anlieferung zum Kundenstandort", 1, "Leistung", (120, 420)),
            ("Rücktransport zum Depot", 1, "Leistung", (120, 420)),
            ("Transport | Tieflader", 1, "Leistung", (220, 680)),
        ],
        "Rental": [
            ("Miete Container 20 Fuß (Monat)", 1, "Monat", (90, 240)),
            ("Vermietung Lagercontainer 10 Fuß (Monat)", 1, "Monat", (60, 180)),
            ("Containervermietung 40 Fuß (Monat)", 1, "Monat", (140, 320)),
        ],
        "Storage": [
            ("Selfstorage Lagerbox S (Monat)", 1, "Monat", (45, 95)),
            ("Selfstorage Lagerbox M (Monat)", 1, "Monat", (70, 140)),
            ("Selfstorage Stellplatz (Monat)", 1, "Monat", (35, 75)),
        ],
        "Additional charges": [
            ("Nebenkosten | Servicepauschale", 1, "Pauschal", (15, 60)),
            ("Nebenkosten | Reinigung", 1, "Pauschal", (25, 90)),
            ("Service | Schloss und Schlüssel", 1, "Stk", (8, 25)),
            ("Nebenkosten | Verwaltung", 1, "Pauschal", (10, 40)),
        ],
    }


def pick_line_items(rng, complexity="medium"):
    catalog = line_item_catalog()

    if complexity == "easy":
        n = rng.randint(2, 3)
        weights = {
            "Sales": 3,
            "Transport": 2,
            "Rental": 2,
            "Storage": 1,
            "Additional charges": 1,
        }
    else:
        n = rng.randint(3, 5)
        weights = {
            "Sales": 3,
            "Transport": 3,
            "Rental": 2,
            "Storage": 2,
            "Additional charges": 2,
        }

    categories = list(weights.keys())
    probs = [weights[c] for c in categories]

    items = []
    picked_any = set()

    for _ in range(n):
        cat = rng.choices(categories, weights=probs, k=1)[0]
        picked_any.add(cat)
        name, qty, unit, (lo, hi) = rng.choice(catalog[cat])
        amount = round(rng.uniform(lo, hi), 2)

        # иногда делаем количество >1 для "Nebenkosten/Service"
        if cat in ("Additional charges", "Storage", "Rental") and rng.random() < 0.35:
            qty = rng.randint(1, 3)

        items.append(make_line_item_custom(name, qty, unit, amount, tax_rate=19))

    # небольшая гарантия, что иногда будет микс категорий
    if complexity != "easy" and len(picked_any) < 2:
        cat = rng.choice(["Transport", "Additional charges", "Rental"])
        name, qty, unit, (lo, hi) = rng.choice(catalog[cat])
        amount = round(rng.uniform(lo, hi), 2)
        items.append(make_line_item_custom(name, qty, unit, amount, tax_rate=19))

    return items


def cmd_seed_month(session, base_url, args, month_value):
    rng = random.Random(args.seed)
    start, end = month_range(month_value)

    print(f"[info] seeding month={month_value} range={start}..{end} invoices={args.count} finalize={args.finalize} complexity={args.complexity}")

    # contacts
    cust_pool = german_customers()
    rng.shuffle(cust_pool)

    contacts = []
    for i in range(min(args.customers, len(cust_pool))):
        cname, city = cust_pool[i]
        resp = create_contact(session, base_url, cname, city=city)
        if not resp["ok"]:
            print("[error] create_contact failed")
            jprint(resp)
            return
        contacts.append({"id": resp["data"]["id"], "name": cname})
    print(f"[info] contacts created: {len(contacts)}")

    created = []
    for k in range(args.count):
        c = rng.choice(contacts)
        d = random_day(start, end)
        voucher_date_iso = d.isoformat() + "T00:00:00.000+01:00"

        line_items = pick_line_items(rng, complexity=args.complexity)
        payload = build_invoice_payload(voucher_date_iso, c["name"], c["id"], line_items, tax_type="net")
        resp = create_invoice(session, base_url, payload, finalize=args.finalize)
        if not resp["ok"]:
            print("[error] create_invoice failed")
            jprint(resp)
            return

        created.append({
            "invoiceId": resp["data"]["id"],
            "customer": c["name"],
            "voucherDate": voucher_date_iso,
        })
        print(f"[ok] invoice {k+1}/{args.count}: id={resp['data']['id']} customer={c['name']} date={d.isoformat()} items={len(line_items)}")

    print("\n[done] created invoices:")
    jprint(created)


def main():
    load_dotenv()
    token = os.getenv("LEXOFFICE_TOKEN")
    if not token:
        raise SystemExit("LEXOFFICE_TOKEN is missing in .env")

    base_url = normalize_base(os.getenv("LEXOFFICE_BASE_URL"))
    session = build_session(token)

    p = argparse.ArgumentParser(prog="seed_de", description="Seed German invoices for Lexware Office testing")
    p.add_argument("--throttle", type=float, default=0.6, help="sleep seconds before each request (default 0.6)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("seed-month", help="seed invoices for a specific month YYYY-MM")
    s1.add_argument("--month", required=True, help="YYYY-MM, e.g. 2026-01")
    s1.add_argument("--count", type=int, default=10)
    s1.add_argument("--customers", type=int, default=5)
    s1.add_argument("--finalize", action="store_true", help="create invoices as open (finalize=true)")
    s1.add_argument("--seed", type=int, default=42)
    s1.add_argument("--complexity", choices=["easy", "medium"], default="medium")
    s1.set_defaults(func="seed-month")

    s2 = sub.add_parser("seed-last-month", help="seed invoices for previous month automatically")
    s2.add_argument("--count", type=int, default=10)
    s2.add_argument("--customers", type=int, default=5)
    s2.add_argument("--finalize", action="store_true")
    s2.add_argument("--seed", type=int, default=42)
    s2.add_argument("--complexity", choices=["easy", "medium"], default="medium")
    s2.set_defaults(func="seed-last-month")

    args = p.parse_args()

    # inject throttle into request_json via wrapper (same style as твой файл)
    global request_json
    old_request_json = request_json

    def request_json(session, method, url, params=None, data=None, throttle=None, max_retries=5):
        if throttle is None:
            throttle = args.throttle
        return old_request_json(session, method, url, params=params, data=data, throttle=throttle, max_retries=max_retries)

    if args.func == "seed-month":
        cmd_seed_month(session, base_url, args, args.month)
    else:
        month_value = prev_month_yyyy_mm(date(2026, 2, 17))
        cmd_seed_month(session, base_url, args, month_value)


if __name__ == "__main__":
    main()
