import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.models import Alert, AlertStats, AlertStatus, AlertType

DB_PATH = Path(__file__).parent.parent / "data" / "alerts.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'firing',
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'webhook',
                agent TEXT,
                container TEXT,
                server TEXT,
                queue TEXT,
                metric TEXT,
                count INTEGER,
                threshold INTEGER,
                resolution TEXT,
                metadata_json TEXT,
                raw_payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC)"
        )
        await db.commit()


def _row_to_alert(row: aiosqlite.Row) -> Alert:
    return Alert(
        id=row["id"],
        alert_type=AlertType(row["alert_type"]),
        severity=row["severity"],
        status=AlertStatus(row["status"]),
        title=row["title"],
        message=row["message"],
        source=row["source"],
        agent=row["agent"],
        container=row["container"],
        server=row["server"],
        queue=row["queue"],
        metric=row["metric"],
        count=row["count"],
        threshold=row["threshold"],
        resolution=row["resolution"],
        raw_payload=row["raw_payload"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def insert_alert(alert: Alert) -> Alert:
    now = _now()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO alerts (
                alert_type, severity, status, title, message, source,
                agent, container, server, queue, metric, count, threshold,
                resolution, metadata_json, raw_payload, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.alert_type.value,
                alert.severity.value,
                alert.status.value,
                alert.title,
                alert.message,
                alert.source,
                alert.agent,
                alert.container,
                alert.server,
                alert.queue,
                alert.metric,
                alert.count,
                alert.threshold,
                alert.resolution,
                None,
                alert.raw_payload,
                now,
                now,
            ),
        )
        await db.commit()
        alert.id = cursor.lastrowid
        alert.created_at = now
        alert.updated_at = now
        return alert


async def get_alerts(
    alert_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[Alert]:
    query = "SELECT * FROM alerts WHERE 1=1"
    params: list[object] = []

    if alert_type:
        query += " AND alert_type = ?"
        params.append(alert_type)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_alert(row) for row in rows]


async def get_alert(alert_id: int) -> Alert | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        row = await cursor.fetchone()
        return _row_to_alert(row) if row else None


async def update_alert_status(alert_id: int, status: AlertStatus) -> Alert | None:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, now, alert_id),
        )
        await db.commit()
    return await get_alert(alert_id)


async def get_stats() -> AlertStats:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        total_cursor = await db.execute("SELECT COUNT(*) as c FROM alerts")
        total = (await total_cursor.fetchone())["c"]

        firing_cursor = await db.execute(
            "SELECT COUNT(*) as c FROM alerts WHERE status = 'firing'"
        )
        firing = (await firing_cursor.fetchone())["c"]

        type_cursor = await db.execute(
            "SELECT alert_type, COUNT(*) as c FROM alerts GROUP BY alert_type"
        )
        by_type = {row["alert_type"]: row["c"] for row in await type_cursor.fetchall()}

        sev_cursor = await db.execute(
            "SELECT severity, COUNT(*) as c FROM alerts GROUP BY severity"
        )
        by_severity = {row["severity"]: row["c"] for row in await sev_cursor.fetchall()}

    return AlertStats(
        total=total,
        firing=firing,
        by_type=by_type,
        by_severity=by_severity,
    )
