from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AlertType(str, Enum):
    UWSGI = "uwsgi"
    RABBITMQ = "rabbitmq"
    HTTP_ERROR = "http_error"
    GRAFANA = "grafana"
    GENERIC = "generic"


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class Alert(BaseModel):
    id: int | None = None
    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.WARNING
    status: AlertStatus = AlertStatus.FIRING
    title: str
    message: str
    source: str = "webhook"
    agent: str | None = None
    container: str | None = None
    server: str | None = None
    queue: str | None = None
    metric: str | None = None
    count: int | None = None
    threshold: int | None = None
    resolution: str | None = None
    raw_payload: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class WebhookPayload(BaseModel):
    text: str | None = None
    message: str | None = None
    alert_type: str | None = None
    source: str = "webhook"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertStats(BaseModel):
    total: int
    firing: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
