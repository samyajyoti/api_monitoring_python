import json
import re
from typing import Any

from app.models import Alert, AlertSeverity, AlertType


def _extract_field(text: str, field: str) -> str | None:
    pattern = rf"{re.escape(field)}:\s*(.+?)(?:\n|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_int(text: str, field: str) -> int | None:
    value = _extract_field(text, field)
    if not value:
        return None
    digits = re.search(r"\d+", value)
    return int(digits.group()) if digits else None


def parse_uwsgi_alert(text: str, source: str = "webhook") -> Alert:
    occurrences = _extract_int(text, "Total occurrences")
    agent = _extract_field(text, "Agent")
    container = _extract_field(text, "Container")
    resolution = _extract_field(text, "RESOLUTION")

    message_match = re.search(r"Message:\s*(\{.*\})", text, re.DOTALL)
    log_message = message_match.group(1).strip() if message_match else text

    severity = AlertSeverity.CRITICAL if (occurrences or 0) >= 100 else AlertSeverity.WARNING

    return Alert(
        alert_type=AlertType.UWSGI,
        severity=severity,
        title=f"uWSGI listen queue full — {agent or 'unknown agent'}",
        message=log_message,
        source=source,
        agent=agent,
        container=container,
        count=occurrences,
        resolution=resolution,
        raw_payload=text,
    )


def _extract_concatenated_fields(text: str, field_names: list[str]) -> dict[str, str]:
    """Parse alerts where field labels run together without newlines."""
    result: dict[str, str] = {}
    for index, field in enumerate(field_names):
        next_labels = field_names[index + 1 :]
        if next_labels:
            next_pattern = "|".join(re.escape(label) for label in next_labels)
            pattern = rf"{re.escape(field)}:\s*(.+?)(?=(?:{next_pattern}):|$)"
        else:
            pattern = rf"{re.escape(field)}:\s*(.+)$"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            result[field] = match.group(1).strip()
    return result


def parse_rabbitmq_alert(text: str, source: str = "webhook") -> Alert:
    fields = _extract_concatenated_fields(
        text,
        [
            "Queue",
            "Server",
            "Current count",
            "Consumers",
            "Previous count",
            "Consecutive Alerts",
            "Action",
        ],
    )

    queue = fields.get("Queue") or _extract_field(text, "Queue")
    server = fields.get("Server") or _extract_field(text, "Server")
    current_raw = fields.get("Current count") or _extract_field(text, "Current count")
    consumers_raw = fields.get("Consumers") or _extract_field(text, "Consumers")
    consecutive_raw = fields.get("Consecutive Alerts") or _extract_field(text, "Consecutive Alerts")
    action = fields.get("Action") or _extract_field(text, "Action")

    current_count = int(re.search(r"\d+", current_raw).group()) if current_raw and re.search(r"\d+", current_raw) else _extract_int(text, "Current count")
    consumers = int(re.search(r"\d+", consumers_raw).group()) if consumers_raw and re.search(r"\d+", consumers_raw) else _extract_int(text, "Consumers")
    consecutive = int(re.search(r"\d+", consecutive_raw).group()) if consecutive_raw and re.search(r"\d+", consecutive_raw) else _extract_int(text, "Consecutive Alerts")

    severity = AlertSeverity.CRITICAL if (current_count or 0) >= 1000 else AlertSeverity.WARNING

    return Alert(
        alert_type=AlertType.RABBITMQ,
        severity=severity,
        title=f"Queue backlog — {queue or 'unknown queue'}",
        message=(
            f"Current count: {current_count}, Consumers: {consumers}, "
            f"Consecutive alerts: {consecutive}. {action or ''}"
        ).strip(),
        source=source,
        server=server,
        queue=queue,
        count=current_count,
        resolution=action,
        raw_payload=text,
    )


def parse_http_error_alert(text: str, source: str = "webhook") -> Alert:
    service_match = re.search(
        r"ALERT:\s*(.+?)\s+Error counts exceeding",
        text,
        re.IGNORECASE,
    )
    service = service_match.group(1).strip() if service_match else "Unknown service"

    metric_match = re.search(r"(\d{3})\s*=\s*(\d+)\s*\(exceeds threshold of (\d+)\)", text)
    metric, count, threshold = (
        (metric_match.group(1), int(metric_match.group(2)), int(metric_match.group(3)))
        if metric_match
        else (None, None, None)
    )

    severity = AlertSeverity.CRITICAL if metric == "500" else AlertSeverity.WARNING

    return Alert(
        alert_type=AlertType.HTTP_ERROR,
        severity=severity,
        title=f"HTTP {metric} threshold exceeded — {service}",
        message=text.strip(),
        source=source,
        metric=metric,
        count=count,
        threshold=threshold,
        raw_payload=text,
    )


def parse_grafana_alert(payload: dict[str, Any], source: str = "grafana") -> Alert:
    status = payload.get("status", "firing")
    alerts = payload.get("alerts") or [{}]
    first = alerts[0] if alerts else {}

    labels = first.get("labels") or payload.get("labels") or {}
    annotations = first.get("annotations") or payload.get("annotations") or {}

    alertname = labels.get("alertname") or payload.get("title") or "Grafana Alert"
    summary = annotations.get("summary") or annotations.get("description") or payload.get("message") or alertname
    severity_label = labels.get("severity", "warning").lower()

    severity_map = {
        "critical": AlertSeverity.CRITICAL,
        "warning": AlertSeverity.WARNING,
        "info": AlertSeverity.INFO,
    }
    severity = severity_map.get(severity_label, AlertSeverity.WARNING)

    return Alert(
        alert_type=AlertType.GRAFANA,
        severity=severity,
        title=alertname,
        message=summary,
        source=source,
        agent=labels.get("instance") or labels.get("host"),
        raw_payload=json.dumps(payload),
    )


def detect_alert_type(text: str) -> AlertType:
    lower = text.lower()
    if "uwsgi" in lower or "listen queue" in lower:
        return AlertType.UWSGI
    if "queue:" in lower and ("current count" in lower or "consumers" in lower):
        return AlertType.RABBITMQ
    if "error counts exceeding" in lower or re.search(r"\d{3}\s*=\s*\d+\s*\(exceeds threshold", text):
        return AlertType.HTTP_ERROR
    return AlertType.GENERIC


def parse_slack_text(text: str, source: str = "slack") -> Alert:
    alert_type = detect_alert_type(text)
    if alert_type == AlertType.UWSGI:
        return parse_uwsgi_alert(text, source=source)
    if alert_type == AlertType.RABBITMQ:
        return parse_rabbitmq_alert(text, source=source)
    if alert_type == AlertType.HTTP_ERROR:
        return parse_http_error_alert(text, source=source)

    return Alert(
        alert_type=AlertType.GENERIC,
        severity=AlertSeverity.INFO,
        title="Generic Alert",
        message=text.strip(),
        source=source,
        raw_payload=text,
    )


def parse_webhook(body: dict[str, Any] | str, source: str = "webhook") -> Alert:
    if isinstance(body, str):
        return parse_slack_text(body, source=source)

    if "alerts" in body or body.get("receiver") or body.get("status") in ("firing", "resolved"):
        return parse_grafana_alert(body, source=source)

    text = body.get("text") or body.get("message") or body.get("body") or ""
    if not text and body.get("metadata"):
        text = json.dumps(body["metadata"])

    explicit_type = body.get("alert_type")
    if explicit_type:
        type_map = {
            "uwsgi": AlertType.UWSGI,
            "rabbitmq": AlertType.RABBITMQ,
            "http_error": AlertType.HTTP_ERROR,
            "grafana": AlertType.GRAFANA,
        }
        mapped = type_map.get(explicit_type.lower())
        if mapped == AlertType.UWSGI:
            return parse_uwsgi_alert(text or json.dumps(body), source=source)
        if mapped == AlertType.RABBITMQ:
            return parse_rabbitmq_alert(text or json.dumps(body), source=source)
        if mapped == AlertType.HTTP_ERROR:
            return parse_http_error_alert(text or json.dumps(body), source=source)

    if text:
        return parse_slack_text(text, source=source)

    return Alert(
        alert_type=AlertType.GENERIC,
        severity=AlertSeverity.INFO,
        title=body.get("title") or "Webhook Alert",
        message=json.dumps(body),
        source=source,
        raw_payload=json.dumps(body),
    )
