# OpenShift Alert Webhook

A Flask application that receives alerts from OpenShift Alertmanager and displays them on a web dashboard.

## Requirements

- Python 3.8+
- Flask

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
python app.py
```

The app will start on `http://localhost:5001`

- **Dashboard:** http://localhost:5001/
- **Webhook endpoint:** http://localhost:5001/alertwebhook
- **Health check:** http://localhost:5001/health

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_HOST` | `0.0.0.0` | Host to bind to |
| `APP_PORT` | `5001` | Port to listen on |
| `APP_DEBUG` | `false` | Enable debug mode |
| `APP_USERNAME` | `admin` | Dashboard username |
| `APP_PASSWORD` | `admin123` | Dashboard password |
| `MAX_ALERTS` | `1000` | Maximum alerts to store |

Example:
```bash
APP_USERNAME=myuser APP_PASSWORD=mypass python app.py
```

## Authentication

The dashboard and API endpoints are protected with Basic Auth.

- Default credentials: `admin` / `admin123`

## Features

- 📊 **Real-time Dashboard** - View all alerts with auto-refresh
- 🔄 **Customizable Refresh** - 5s, 10s, 30s, 1m, or no auto-refresh
- 🔍 **Filtering** - Filter by status (firing/resolved) and severity
- 📄 **Pagination** - Browse through many alerts
- 📥 **Export** - Download alerts as CSV
- 🔔 **Webhook Receiver** - Accepts Prometheus Alertmanager webhooks
- 🔒 **Basic Auth** - Protected dashboard
- 🏥 **Health Check** - `/health` endpoint for monitoring
- 🗑️ **Clear Alerts** - Clear all alerts from the dashboard

## Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | Yes | Dashboard (HTML) |
| `/alertwebhook` | POST | No | Webhook receiver |
| `/alerts` | GET | Yes | Alerts as JSON |
| `/alerts?format=csv` | GET | Yes | Export as CSV |
| `/alerts/clear` | POST | Yes | Clear all alerts |
| `/health` | GET | No | Health check |
| `/favicon.ico` | GET | No | Favicon |

## OpenShift Configuration

### Update Alertmanager Config

```bash
oc edit alertmanager main -n openshift-monitoring
```

Add a webhook receiver:

```yaml
receivers:
  - name: webhook
    webhook_configs:
      - url: 'http://<your-webhook-service>:<port>/alertwebhook'
        send_resolved: true
route:
  receiver: webhook
  group_by: ['alertname', 'namespace']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
```

### For External Webhooks (outside cluster)

If running on your local machine:

```bash
# Using ngrok
ngrok http 5001

# Then use the ngrok URL in Alertmanager config
```

## Alert Format

The webhook accepts Prometheus Alertmanager webhook V2 format:

```json
{
  "receiver": "webhook",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighMemoryUsage",
        "namespace": "production",
        "severity": "warning"
      },
      "annotations": {
        "description": "Memory usage is above 90%",
        "summary": "High memory usage alert"
      },
      "startsAt": "2024-01-15T10:00:00Z",
      "endsAt": "0001-01-01T00:00:00Z"
    }
  ]
}
```

## OpenShift 4.16+ Compatibility

This webhook is compatible with OpenShift 4.16+ Alertmanager as it uses the standard Prometheus Alertmanager webhook V2 format.

## Docker

### Build

```bash
docker build -t openshift-alert-webhook .
```

### Run

```bash
docker run -d \
  -p 8080:8080 \
  -e APP_USERNAME=admin \
  -e APP_PASSWORD=yourpassword \
  -e MAX_ALERTS=1000 \
  --name alert-webhook \
  openshift-alert-webhook
```

### Run on OpenShift

```bash
# Build the image
docker build -t openshift-alert-webhook .

# Login to OpenShift
oc login ...
oc new-project alertmonitoring

# Import image
oc import-image ubi9/python-39 --from=registry.access.redhat.com/ubi9/python-39:latest --confirm

# Create application
oc new-app --name alert-webhook openshift-alert-webhook

# Set environment variables
oc set env deployment/alert-webhook APP_USERNAME=admin APP_PASSWORD=secret

# Expose route
oc expose svc alert-webhook
```

### Docker Compose

```yaml
version: '3.8'
services:
  webhook:
    build: .
    ports:
      - "8080:8080"
    environment:
      - APP_USERNAME=admin
      - APP_PASSWORD=admin123
      - MAX_ALERTS=1000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```
