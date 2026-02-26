
import os
import sys
import subprocess
import logging

def setup_logging():
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        filename=os.path.join("logs", "run_monthly.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

def run_step(name, script):
    logging.info("START %s", name)
    p = subprocess.run([sys.executable, script])
    if p.returncode != 0:
        logging.error("FAIL %s rc=%s", name, p.returncode)
        return False
    logging.info("DONE %s", name)
    return True

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    setup_logging()
    logging.info("Workdir=%s", os.getcwd())

    if not os.path.isfile(".env"):
        logging.error(".env not found in %s", os.getcwd())
        return 1

    os.makedirs("csv", exist_ok=True)
    os.makedirs("email", exist_ok=True)

    ok = True
    ok = run_step("CSV A", "csv_a.py") and ok
    ok = run_step("CSV B", "csv_b.py") and ok
    ok = run_step("CSV C", "csv_c.py") and ok

    send_email_after = os.getenv("SEND_EMAIL_AFTER", "1").strip() != "0"
    purge_after = os.getenv("PURGE_AFTER", "1").strip() != "0"

    email_ok = False
    if send_email_after:
        email_ok = run_step("SEND EMAIL", "send_email.py")
        ok = email_ok and ok

    if purge_after and email_ok:
        ok = run_step("PURGE", "purge.py") and ok

    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
