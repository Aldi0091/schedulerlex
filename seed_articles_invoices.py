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


def create_article(session, base_url, title, article_number, net_price, tax_rate=19, article_type="PRODUCT"):
    url = base_url + "/v1/articles"
    payload = {
        "title": title,
        "type": article_type,
        "articleNumber": article_number,
        "unitName": "Stk",
        "price": {
            "netPrice": float(net_price),
            "grossPrice": round(float(net_price) * (1.0 + tax_rate / 100.0), 2),
            "leadingPrice": "NET",
            "taxRate": int(tax_rate),
        }
    }
    return request_json(session, "POST", url, data=payload)


def make_line_item_article(article_id, name, qty, unit, net_amount, tax_rate=19, item_type="material"):
    # Важно: для material/service нужен id (ссылка на article)
    return {
        "type": item_type,
        "id": article_id,
        "name": name,
        "quantity": float(qty),
        "unitName": unit,
        "unitPrice": {
            "currency": "EUR",
            "netAmount": round(float(net_amount), 2),
            "taxRatePercentage": int(tax_rate)
        }
    }


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


def german_customers():
    return [
        ("Nordsee Container Handel", "Hamburg"),
        ("Rhein Main Logistik", "Frankfurt am Main"),
        ("Bayerische Lager Solutions", "München"),
        ("Hanseatische Transport Dienste", "Bremen"),
        ("Sachsen Selfstorage", "Leipzig"),
    ]


def seed_articles(session, base_url, seed, count):
    rnd = random.Random(seed)

    titles = [
        "Gebrauchter Seecontainer 20 Fuß",
        "Neuwertig Shipping Container 40 Fuß",
        "Selfstorage Lagerbox M (Monat)",
        "Containervermietung 20 Fuß (Monat)",
        "Transport | Kran-LKW",
        "Nebenkosten | Servicepauschale",
        "Rücktransport zum Depot",
        "Anlieferung zum Kundenstandort",
    ]

    # формируем articleNumber вида VA04 (2 буквы + 2 цифры)
    # фиксируем префикс VA и номеруем 01..99
    created = []
    for i in range(count):
        anum = f"VA{i+1:02d}"
        title = titles[i % len(titles)]
        net = round(rnd.uniform(25, 350), 2)
        t = 19
        a_type = "PRODUCT"
        if "Transport" in title or "Service" in title or "Nebenkosten" in title or "Anlieferung" in title or "Rücktransport" in title:
            a_type = "SERVICE"

        resp = create_article(session, base_url, title, anum, net, tax_rate=t, article_type=a_type)
        if not resp["ok"]:
            print("[error] create_article failed")
            jprint(resp)
            raise SystemExit(1)
        created.append({
            "id": resp["data"]["id"],
            "articleNumber": anum,
            "title": title,
            "netPrice": net,
            "type": a_type,
        })
        print(f"[ok] article {i+1}/{count}: {anum} id={resp['data']['id']} title={title}")

    return created


def cmd_seed_month(session, base_url, args, month_value):
    rnd = random.Random(args.seed)
    start, end = month_range(month_value)

    print(f"[info] month={month_value} range={start}..{end} invoices={args.count} articles={args.articles} finalize={args.finalize}")

    # contacts
    customers = german_customers()
    rnd.shuffle(customers)
    contacts = []
    for i in range(min(args.customers, len(customers))):
        cname, city = customers[i]
        resp = create_contact(session, base_url, cname, city=city)
        if not resp["ok"]:
            print("[error] create_contact failed")
            jprint(resp)
            raise SystemExit(1)
        contacts.append({"id": resp["data"]["id"], "name": cname})
        print(f"[ok] contact {i+1}/{min(args.customers, len(customers))}: id={resp['data']['id']} name={cname}")

    # articles
    arts = seed_articles(session, base_url, args.seed + 100, args.articles)

    created = []
    for k in range(args.count):
        c = rnd.choice(contacts)
        d = random_day(start, end)
        voucher_date_iso = d.isoformat() + "T00:00:00.000+01:00"

        n_items = rnd.randint(2, 5)
        line_items = []

        # минимум 1 article line item, чтобы CSV C не был пустой
        art = rnd.choice(arts)
        qty = rnd.randint(1, 3)
        line_items.append(make_line_item_article(
            art["id"], art["title"], qty, "Stk", art["netPrice"], 19,
            item_type="service" if art["type"] == "SERVICE" else "material"
        ))

        for _ in range(n_items - 1):
            if rnd.random() < args.article_ratio:
                art = rnd.choice(arts)
                qty = rnd.randint(1, 4)
                line_items.append(make_line_item_article(
                    art["id"], art["title"], qty, "Stk", art["netPrice"], 19,
                    item_type="service" if art["type"] == "SERVICE" else "material"
                ))
            else:
                # немного custom шума (реализм)
                custom_titles = [
                    "Hinweis: Lieferung nach Absprache",
                    "Zusatzleistung vor Ort",
                    "Pauschale Aufwandsentschädigung",
                ]
                line_items.append(make_line_item_custom(rnd.choice(custom_titles), 1, "Pauschal", round(rnd.uniform(10, 60), 2), 19))

        payload = build_invoice_payload(voucher_date_iso, c["name"], c["id"], line_items, tax_type="net")
        resp = create_invoice(session, base_url, payload, finalize=args.finalize)
        if not resp["ok"]:
            print("[error] create_invoice failed")
            jprint(resp)
            raise SystemExit(1)

        created.append({"invoiceId": resp["data"]["id"], "customer": c["name"], "date": d.isoformat()})
        print(f"[ok] invoice {k+1}/{args.count}: id={resp['data']['id']} items={len(line_items)} date={d.isoformat()}")

    print("\n[done] created:")
    jprint(created)


def main():
    load_dotenv()
    token = os.getenv("LEXOFFICE_TOKEN")
    if not token:
        raise SystemExit("LEXOFFICE_TOKEN is missing in .env")

    base_url = normalize_base(os.getenv("LEXOFFICE_BASE_URL"))
    session = build_session(token)

    p = argparse.ArgumentParser(prog="seed_articles_invoices", description="Seed Articles + Invoices for CSV C")
    p.add_argument("--throttle", type=float, default=0.6)
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("seed-month")
    s1.add_argument("--month", required=True, help="YYYY-MM")
    s1.add_argument("--count", type=int, default=8)
    s1.add_argument("--customers", type=int, default=3)
    s1.add_argument("--articles", type=int, default=8)
    s1.add_argument("--article-ratio", type=float, default=0.85, help="share of invoice items that are article-based (0..1)")
    s1.add_argument("--finalize", action="store_true")
    s1.add_argument("--seed", type=int, default=42)
    s1.set_defaults(mode="month")

    s2 = sub.add_parser("seed-last-month")
    s2.add_argument("--count", type=int, default=8)
    s2.add_argument("--customers", type=int, default=3)
    s2.add_argument("--articles", type=int, default=8)
    s2.add_argument("--article-ratio", type=float, default=0.85)
    s2.add_argument("--finalize", action="store_true")
    s2.add_argument("--seed", type=int, default=42)
    s2.set_defaults(mode="last")

    args = p.parse_args()

    # inject throttle
    global request_json
    old_request_json = request_json

    def request_json(session, method, url, params=None, data=None, throttle=None, max_retries=5):
        if throttle is None:
            throttle = args.throttle
        return old_request_json(session, method, url, params=params, data=data, throttle=throttle, max_retries=max_retries)

    if args.mode == "month":
        cmd_seed_month(session, base_url, args, args.month)
    else:
        # фиксируем под текущий контекст: 17.02.2026 -> прошлый месяц 2026-01
        cmd_seed_month(session, base_url, args, "2026-01")


if __name__ == "__main__":
    """
    Примеры:
      python3 seed_articles_invoices.py seed-last-month --count 10 --customers 4 --articles 12 --finalize
      python3 seed_articles_invoices.py seed-month --month 2026-01 --count 10 --customers 4 --articles 12 --finalize
    """
    main()
