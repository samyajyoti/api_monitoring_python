#!/usr/bin/env python3
"""Seed sample alerts for demo/testing."""

import asyncio

from app.database import init_db, insert_alert
from app.parsers import parse_slack_text

SAMPLES = [
    """Found 'uWSGI error' in logs.
Total occurrences: 332.
Message: {"log":"Sun Aug 30 14:02:11 2026 - *** uWSGI listen queue of socket \\":8019\\" (fd: 3) full !!! (101/100) ***\\n","stream":"stderr","time":"2026-08-30T14:02:11.353591152Z"}
Agent: demapp3
Container: dem2
RESOLUTION: Please restart demapp3 prod instance DEM Container dem2""",
    """Queue:
device_callback_queueServer:
demapp1Current count:
1706Consumers:
2Previous count:
0Consecutive Alerts:
1Action:
Investigate processing""",
    """ALERT: NOTIFICATION SERVICE PROD Error counts exceeding the threshold in the last 1 hour:
404 = 579 (exceeds threshold of 400)""",
]


async def main() -> None:
    await init_db()
    for text in SAMPLES:
        alert = parse_slack_text(text, source="sample")
        saved = await insert_alert(alert)
        print(f"  + [{saved.alert_type.value}] {saved.title}")
    print("\nDone. Run: uvicorn app.main:app --reload")


if __name__ == "__main__":
    asyncio.run(main())
