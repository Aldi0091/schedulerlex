import os
import argparse
import mimetypes
import smtplib
from email.message import EmailMessage
from datetime import datetime

from dotenv import load_dotenv


DEFAULT_PATTERNS = {
    "csv": [".csv"],
    "logs": [".log"],
}

REPORT_ORDER_PREFIX = ["csv_A_", "csv_B_", "csv_C_"]


def _read_recipients_from_env():
    raw = (os.getenv("EMAIL_TO") or "").strip()
    if not raw:
        return []
    parts = []
    for p in raw.replace(";", ",").split(","):
        p = (p or "").strip()
        if p:
            parts.append(p)

    uniq = []
    seen = set()
    for p in parts:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq[:20]


def _guess_attachment_mime(path):
    mt, _ = mimetypes.guess_type(path)
    if not mt or "/" not in mt:
        return "application", "octet-stream"
    a, b = mt.split("/", 1)
    return a, b


def _split_subject_body(text):
    lines = (text or "").splitlines()
    subject = ""
    body_lines = lines[:]

    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip()
        body_lines = lines[1:]
        if body_lines and body_lines[0].strip() == "":
            body_lines = body_lines[1:]

    if not subject:
        subject = "[Lexoffice] Report " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body = "\n".join(body_lines).strip() + "\n"
    return subject, body


def _is_allowed_file(path, allowed_exts):
    if not allowed_exts:
        return True
    low = path.lower()
    for ext in allowed_exts:
        if low.endswith(ext):
            return True
    return False


def _list_files_with_meta(dir_path, allowed_exts=None):
    items = []
    if not os.path.isdir(dir_path):
        return items

    for name in os.listdir(dir_path):
        if not name or name.startswith("."):
            continue
        path = os.path.join(dir_path, name)
        if not os.path.isfile(path):
            continue
        if allowed_exts is not None and not _is_allowed_file(path, allowed_exts):
            continue
        try:
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
        except Exception:
            continue
        items.append((os.path.abspath(path), name, mtime, size))

    items.sort(key=lambda x: x[2], reverse=True)  # newest first
    return items


def collect_attachments(dirs, patterns_map, extra_paths, max_files=30, max_total_mb=20, newest_first=True):
    candidates = []

    for d in dirs:
        if not d:
            continue
        d = d.strip()
        if not d or not os.path.isdir(d):
            continue

        allowed_exts = patterns_map.get(d, None)
        for ap, name, mtime, size in _list_files_with_meta(d, allowed_exts=allowed_exts):
            candidates.append((ap, mtime, size))

    for p in extra_paths or []:
        if not p:
            continue
        p = p.strip()
        if not p:
            continue
        if os.path.isfile(p):
            try:
                mtime = os.path.getmtime(p)
                size = os.path.getsize(p)
            except Exception:
                mtime = 0
                size = 0
            candidates.append((os.path.abspath(p), mtime, size))

    seen = set()
    uniq = []
    for ap, mtime, size in candidates:
        if ap in seen:
            continue
        seen.add(ap)
        uniq.append((ap, mtime, size))

    uniq.sort(key=lambda x: x[1], reverse=bool(newest_first))

    max_total_bytes = int(max_total_mb * 1024 * 1024)
    picked = []
    total = 0

    for ap, mtime, size in uniq:
        if len(picked) >= int(max_files):
            break
        if size <= 0:
            continue
        if total + size > max_total_bytes:
            continue
        picked.append(ap)
        total += size

    return picked, total


def collect_email_bodies_ordered(email_dir="email"):
    # Body order: A -> B -> C (each: newest matching file)
    # If multiple of same type exist, we include all of them (newest first) under that section.
    if not os.path.isdir(email_dir):
        return "", None

    txts = _list_files_with_meta(email_dir, allowed_exts=[".txt"])
    if not txts:
        return "", None

    # group by prefix
    buckets = {p: [] for p in REPORT_ORDER_PREFIX}
    others = []

    for ap, name, mtime, size in txts:
        placed = False
        for pref in REPORT_ORDER_PREFIX:
            if name.startswith(pref):
                buckets[pref].append((ap, name, mtime))
                placed = True
                break
        if not placed:
            others.append((ap, name, mtime))

    # sort each bucket newest first already by listing, but just to be safe:
    for k in buckets:
        buckets[k].sort(key=lambda x: x[2], reverse=True)
    others.sort(key=lambda x: x[2], reverse=True)

    # subject: from newest available among A/B/C/others (in that priority A->B->C if exists, else newest other)
    subject = None

    parts = []
    def append_bucket(title, items):
        if not items:
            return
        parts.append("=== %s ===" % title)
        for ap, name, mtime in items:
            try:
                with open(ap, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue

            subj, body = _split_subject_body(text)

            nonlocal subject
            if subject is None and subj:
                subject = subj

            parts.append("FILE: %s" % name)
            parts.append("TIME: %s" % datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"))
            parts.append("")
            parts.append(body.strip())
            parts.append("")

        parts.append("-" * 60)
        parts.append("")

    append_bucket("CSV A", buckets["csv_A_"])
    append_bucket("CSV B", buckets["csv_B_"])
    append_bucket("CSV C", buckets["csv_C_"])

    # append "others" at the end (if any)
    if others:
        append_bucket("OTHER REPORTS", others)

    full_body = "\n".join([x for x in parts if x is not None]).strip() + "\n"

    if not subject:
        subject = "[Lexoffice] Report " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return full_body, subject


def build_combined_log(log_dir="logs", out_name=None):
    # Combine all .log files into one log named logging_<timestamp>.log
    if not os.path.isdir(log_dir):
        return None

    logs = _list_files_with_meta(log_dir, allowed_exts=[".log"])
    if not logs:
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = out_name or ("logging_%s.log" % ts)
    out_path = os.path.join(log_dir, out_name)

    header = []
    header.append("Combined log created: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    header.append("Source files (newest first):")
    for ap, name, mtime, size in logs:
        header.append("- %s | %s" % (name, datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")))
    header.append("")
    header_text = "\n".join(header) + "\n"

    try:
        with open(out_path, "w", encoding="utf-8") as out:
            out.write(header_text)
            for ap, name, mtime, size in logs:
                out.write("\n" + ("=" * 80) + "\n")
                out.write("FILE: %s | MTIME: %s\n" % (name, datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")))
                out.write(("=" * 80) + "\n")
                try:
                    with open(ap, "r", encoding="utf-8", errors="replace") as f:
                        out.write(f.read())
                except Exception as e:
                    out.write("\n[ERROR reading file %s: %s]\n" % (name, e))
    except Exception:
        return None

    return os.path.abspath(out_path)


def send_email(subject, body, attachments, dry_run=False):
    mail_address = (os.getenv("MAIL_ADDRESS") or "").strip()
    mail_app_password = (os.getenv("MAIL_APP_PASSWORD") or "").strip()
    smtp_host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT") or "587")

    recipients = _read_recipients_from_env()

    if not mail_address or not mail_app_password:
        raise SystemExit("Missing MAIL_ADDRESS or MAIL_APP_PASSWORD in .env")

    if not recipients:
        raise SystemExit("Missing EMAIL_TO in .env")

    if not subject:
        subject = "[Lexoffice] Report " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not body:
        body = "No email reports found in ./email\n"

    msg = EmailMessage()
    msg["From"] = mail_address
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    attached = []
    for path in attachments:
        if not path or not os.path.isfile(path):
            continue

        with open(path, "rb") as f:
            data = f.read()

        maintype, subtype = _guess_attachment_mime(path)
        filename = os.path.basename(path)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
        attached.append(path)

    if dry_run:
        print("DRY RUN: would send email")
        print("From:", mail_address)
        print("To:", ", ".join(recipients))
        print("Subject:", subject)
        print("Attachments:", attached)
        print("Body chars:", len(body))
        return

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(mail_address, mail_app_password)
        server.send_message(msg)

    print("OK: sent to:", ", ".join(recipients))
    print("Subject:", subject)
    print("Attachments:", attached)


def main():
    load_dotenv()

    p = argparse.ArgumentParser(description="Send email: body from email/*.txt (A->B->C), attach csv/*.csv + combined log")
    p.add_argument("--dry-run", action="store_true", help="Do not send, just print what would happen")

    p.add_argument("--csv-dir", default="csv", help="CSV directory to attach from (default: csv)")
    p.add_argument("--logs-dir", default="logs", help="Logs directory to combine (default: logs)")
    p.add_argument("--email-dir", default="email", help="Directory with .txt reports for email body (default: email)")

    p.add_argument("--max-csv-files", type=int, default=30, help="Max number of CSV attachments (default: 30)")
    p.add_argument("--max-mb", type=float, default=20, help="Max total attachment size in MB (default: 20)")
    p.add_argument("--oldest-first", action="store_true", help="Attach oldest CSV first (default newest first)")

    p.add_argument("--attach", action="append", default=[], help="Extra attachment path (repeatable)")
    args = p.parse_args()

    # 1) body in A->B->C order
    body, subject = collect_email_bodies_ordered(email_dir=args.email_dir)

    # 2) build combined log file
    combined_log = build_combined_log(log_dir=args.logs_dir)
    extra_paths = list(args.attach or [])
    if combined_log:
        extra_paths.append(combined_log)

    # 3) attach CSV files (and combined log via extra_paths)
    patterns_map = {"csv": [".csv"]}

    picked_csv, total_bytes = collect_attachments(
        dirs=[args.csv_dir],
        patterns_map=patterns_map,
        extra_paths=[],  # only csv here
        max_files=args.max_csv_files,
        max_total_mb=args.max_mb,
        newest_first=(not args.oldest_first),
    )

    attachments = []
    attachments.extend(picked_csv)

    # add combined log + extra attachments (respect max_mb budget is already mostly for csv;
    # combined log is usually small, but if you want strict budget add check here)
    for pth in extra_paths:
        if pth and os.path.isfile(pth):
            ap = os.path.abspath(pth)
            if ap not in attachments:
                attachments.append(ap)

    if args.dry_run:
        print("Email subject:", subject)
        print("Email body chars:", len(body))
        print("Combined log:", combined_log)
        print("CSV attachments:", len(picked_csv))
        print("Total CSV size (MB):", round(total_bytes / (1024 * 1024), 2))
        for pth in attachments:
            print(" -", pth)

    send_email(subject=subject, body=body, attachments=attachments, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
