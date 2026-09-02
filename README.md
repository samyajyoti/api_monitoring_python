# Mon Dashboard

A lightweight alert dashboard with a **Python (FastAPI) backend** and a **web frontend**. Ingest alerts via a single Slack-style incoming webhook. Alerts are auto-classified: uWSGI, RabbitMQ, HTTP errors, Grafana.

## Docker (recommended)

```bash
docker compose up -d --build
```

Dashboard: **http://localhost:8081**  
Webhook: **http://localhost:8081/webhook**

```bash
# View logs
docker compose logs -f

# Load sample alerts
docker compose exec dashboard python seed_samples.py

# Stop
docker compose down
```

Optional webhook token — create a `.env` file:

```bash
WEBHOOK_TOKEN=my-secret-token
```

Then post alerts to `http://localhost:8081/webhook/my-secret-token`.

Alert data persists in the `dashboard-data` Docker volume (SQLite).

### Login credentials

Set in `.env` or `docker-compose.yml`:

```bash
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=your-secure-password
SECRET_KEY=random-secret-string
```

Default (change in production): `admin` / `admin`

The webhook endpoint stays public — scripts don't need login.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed_samples.py   # optional
uvicorn app.main:app --reload --host 0.0.0.0 --port 8081
```

## Incoming webhook (Slack-style)

```
POST http://your-host:8081/webhook
Content-Type: application/json

{"text": "your alert message here"}
```

Response: `ok` (HTTP 200), just like Slack.

### Send alongside Slack

```python
import requests

payload = {"text": alert_message}
requests.post("http://your-dashboard:8081/webhook", json=payload, timeout=5)
```

### curl examples

```bash
curl -X POST http://localhost:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{"text": "Found uWSGI error\nAgent: demapp3\nContainer: dem2"}'
```

## Alert type detection

| Pattern in `text` | Type |
|---|---|
| `uWSGI`, `listen queue` | uWSGI |
| `Queue:`, `Current count`, `Consumers` | RabbitMQ |
| `Error counts exceeding`, `404 = N` | HTTP Error |
| Grafana webhook JSON | Grafana |

## API

- `GET /api/alerts` — list alerts (`?alert_type=uwsgi&status=firing`)
- `GET /api/stats` — counts by type
- `PATCH /api/alerts/{id}/status` — `{"status": "resolved"}`
