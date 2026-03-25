import requests
import time
import logging
import os
from dotenv import load_dotenv
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Load .env
load_dotenv()

# =======================
# Configs
# =======================
raw_urls = os.getenv("HEALTH_URLS", "")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "").strip()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
ENV_NAME = os.getenv("ENV_NAME", "TEST ENVIRONMENT")

# =======================
# Logging Setup
# =======================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "monitor.log")

file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
)

stream_handler = logging.StreamHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[file_handler, stream_handler],
)

logger = logging.getLogger()

logger.info("✅ Logger initialized")

# =======================
# Validate URL
# =======================
def is_valid_url(url):
    return url.startswith("http://") or url.startswith("https://")

# =======================
# Parse URLs
# =======================
HEALTH_URLS = {}

for item in raw_urls.split(","):
    item = item.strip()
    if not item:
        continue

    try:
        # format: env:name=url
        if "=" in item and ":" in item.split("=")[0]:
            env_name, url = item.split("=", 1)
            env, name = env_name.split(":", 1)

        # format: name=url
        elif "=" in item:
            env = "default"
            name, url = item.split("=", 1)

        # format: plain url
        else:
            env = "default"
            name = item
            url = item

        url = url.strip()

        if is_valid_url(url):
            HEALTH_URLS.setdefault(env, {})[name.strip()] = url
        else:
            logger.warning(f"Skipping invalid URL: {url}")

    except Exception as e:
        logger.warning(f"Skipping malformed entry: {item} | Error: {e}")

logger.info(f"Parsed HEALTH_URLS: {HEALTH_URLS}")

# =======================
# Track last status
# =======================
last_status = {}

# =======================
# Slack Alert
# =======================
def send_slack_alert(message: str):
    if not SLACK_WEBHOOK:
        return
    try:
        requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=5)
    except Exception as e:
        logger.error(f"Slack alert failed: {e}")

# =======================
# Format Output
# =======================
def format_line(url, status):
    now = datetime.now().strftime("%I:%M %p")
    icon = "✅" if status == 200 else "❌"
    return f"[{now}] {icon} {url} returned {status}"

# =======================
# Monitor Loop
# =======================
def monitor():
    logger.info(f"🚀 Starting health API monitor for {ENV_NAME}...")

    while True:
        output_lines = []
        alert_lines = []

        for env, services in HEALTH_URLS.items():
            for name, url in services.items():
                key = (env, name)

                try:
                    response = requests.get(url, timeout=10)
                    status = response.status_code
                except Exception:
                    status = "ERROR"

                current = "up" if status == 200 else "down"
                prev = last_status.get(key)

                now = datetime.now().strftime("%I:%M %p")

                # 🔴 DOWN / RECOVERY alerts
                if prev is not None and prev != current:
                    if current == "down":
                        alert_lines.append(f"[{now}] ❌ {url} is DOWN ({status})")
                    elif current == "up":
                        alert_lines.append(f"[{now}] 🟢 {url} RECOVERED (200)")

                elif prev is None and current == "down":
                    alert_lines.append(f"[{now}] ❌ {url} is DOWN ({status})")

                last_status[key] = current

                output_lines.append(format_line(url, status))

        # ✅ Log output (console + file)
        final_output = "\n".join(output_lines)
        formatted_output = f"===== {ENV_NAME} =====\n{final_output}"
        logger.info("\n" + formatted_output + "\n")

        # 🔔 Slack alerts
        if alert_lines:
            slack_message = "=====INSURE PROD APP ALERTS =====\n" + "\n".join(alert_lines)
            send_slack_alert(f"```\n{slack_message}\n```")

        logger.info(f"Sleeping for {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)

# =======================
# Main
# =======================
if __name__ == "__main__":
    monitor()
