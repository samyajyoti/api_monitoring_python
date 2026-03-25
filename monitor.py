import requests
import time
import logging
import os
from dotenv import load_dotenv
from datetime import datetime

# Load .env
load_dotenv()

# Configs
raw_urls = os.getenv("HEALTH_URLS", "")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "").strip()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
ENV_NAME = os.getenv("ENV_NAME", "TEST ENVIRONMENT")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()

# Validate URL
def is_valid_url(url):
    return url.startswith("http://") or url.startswith("https://")

# Parse URLs
HEALTH_URLS = {}

for item in raw_urls.split(","):
    item = item.strip()
    if not item:
        continue

    if ":" in item and "=" in item:
        try:
            env, rest = item.split(":", 1)
            name, url = rest.split("=", 1)
            env, name, url = env.strip(), name.strip(), url.strip()

            if is_valid_url(url):
                HEALTH_URLS.setdefault(env, {})[name] = url
            else:
                logger.warning(f"Skipping invalid URL: {url}")

        except Exception:
            logger.warning(f"Skipping malformed entry: {item}")

    elif "=" in item:
        try:
            name, url = item.split("=", 1)
            name, url = name.strip(), url.strip()

            if is_valid_url(url):
                HEALTH_URLS.setdefault("default", {})[name] = url
            else:
                logger.warning(f"Skipping invalid URL: {url}")

        except Exception:
            logger.warning(f"Skipping malformed entry: {item}")

    else:
        if is_valid_url(item):
            HEALTH_URLS.setdefault("default", {})[item] = item
        else:
            logger.warning(f"Skipping invalid URL: {item}")

# Track last status
last_status = {}

def send_slack_alert(message: str):
    if not SLACK_WEBHOOK:
        return
    try:
        requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=5)
    except Exception as e:
        logger.error(f"Slack alert failed: {e}")

def format_line(url, status):
    now = datetime.now().strftime("%I:%M %p")
    icon = "✅" if status == 200 else "❌"
    return f"[{now}] {icon} {url} returned {status}"

def monitor():
    logger.info(f"🚀 Starting health API monitor for {ENV_NAME}...")

    while True:
        output_lines = []
        alert_lines = []
        has_failure = False

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

                # 🔴 DOWN alert (state change)
                if prev is not None and prev != current:
                    if current == "down":
                        alert_lines.append(f"[{now}] ❌ {url} is DOWN ({status})")

                    elif current == "up":
                        alert_lines.append(f"[{now}] 🟢 {url} RECOVERED (200)")

                # First-time DOWN detection
                elif prev is None and current == "down":
                    alert_lines.append(f"[{now}] ❌ {url} is DOWN ({status})")

                last_status[key] = current

                if status != 200:
                    has_failure = True

                # Output line
                output_lines.append(format_line(url, status))

        # 🖥️ Console Output
        final_output = "\n".join(output_lines)
        formatted_output = f"===== {ENV_NAME} =====\n{final_output}"

        print("\n" + formatted_output + "\n")

        # 🔔 Slack Alerts (only on change)
        if alert_lines:
            slack_message = "===== TEST ALERTS =====\n" + "\n".join(alert_lines)
            send_slack_alert(f"```\n{slack_message}\n```")

        logger.info(f"Sleeping for {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor()
