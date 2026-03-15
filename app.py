#!/usr/bin/env python3
"""
OpenShift Alertmanager Webhook Receiver
Accepts alerts from OpenShift Alertmanager and displays them on a dashboard.
Compatible with OpenShift 4.16+
"""

import os
import io
import csv
import logging
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, make_response
from datetime import datetime
import threading

# Configuration
APP_HOST = os.environ.get('APP_HOST', '0.0.0.0')
APP_PORT = int(os.environ.get('APP_PORT', 5001))
APP_DEBUG = os.environ.get('APP_DEBUG', 'false').lower() == 'true'
APP_USERNAME = os.environ.get('APP_USERNAME', 'admin')
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'admin123')
MAX_ALERTS = int(os.environ.get('MAX_ALERTS', 1000))

app = Flask(__name__)

# Disable Flask debug logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

# In-memory storage for alerts
alerts = []
alerts_lock = threading.Lock()

# Basic auth decorator
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != APP_USERNAME or auth.password != APP_PASSWORD:
            return make_response('Authentication required', 401, 
                {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated

# HTML template for the dashboard
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenShift Alerts Dashboard</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🚨</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #21262d;
            flex-wrap: wrap;
            gap: 15px;
        }
        h1 { color: #f85149; font-size: 1.8rem; display: flex; align-items: center; gap: 10px; }
        
        .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .btn {
            padding: 8px 16px;
            border-radius: 6px;
            border: 1px solid #30363d;
            background: #21262d;
            color: #c9d1d9;
            cursor: pointer;
            font-size: 0.9rem;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }
        .btn:hover { background: #30363d; border-color: #8b949e; }
        .btn-danger { border-color: #f85149; color: #f85149; }
        .btn-danger:hover { background: rgba(248, 81, 73, 0.15); }
        .btn-primary { background: #238636; border-color: #238636; color: #fff; }
        .btn-primary:hover { background: #2ea043; }
        
        .refresh-select {
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid #30363d;
            background: #0d1117;
            color: #c9d1d9;
            font-size: 0.9rem;
        }
        
        .refresh-info { color: #8b949e; font-size: 0.85rem; }
        
        .stats {
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        .stat-card {
            background: #161b22;
            padding: 15px 25px;
            border-radius: 8px;
            border: 1px solid #21262d;
            text-align: center;
            flex: 1;
            min-width: 120px;
        }
        .stat-value { font-size: 1.8rem; font-weight: bold; }
        .stat-label { color: #8b949e; margin-top: 5px; font-size: 0.85rem; }
        .firing { color: #f85149; }
        .resolved { color: #3fb950; }
        .total { color: #d29922; }
        
        .filters {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        .filter-group { display: flex; align-items: center; gap: 8px; }
        .filter-label { color: #8b949e; font-size: 0.85rem; }
        .filter-select {
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid #30363d;
            background: #0d1117;
            color: #c9d1d9;
            font-size: 0.85rem;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            background: #161b22;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #21262d;
        }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #21262d; }
        th {
            background: #21262d;
            color: #c9d1d9;
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tr:hover { background: #1c2128; }
        tr:last-child td { border-bottom: none; }
        
        .status-badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .status-firing {
            background: rgba(248, 81, 73, 0.15);
            color: #f85149;
            border: 1px solid rgba(248, 81, 73, 0.4);
        }
        .status-resolved {
            background: rgba(63, 185, 80, 0.15);
            color: #3fb950;
            border: 1px solid rgba(63, 185, 80, 0.4);
        }
        
        .alertname { color: #58a6ff; font-weight: 600; }
        .timestamp { color: #8b949e; font-size: 0.8rem; }
        .annotations { color: #8b949e; font-size: 0.85rem; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        
        .labels { display: flex; flex-wrap: wrap; gap: 4px; max-width: 200px; }
        .label {
            background: #21262d;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.7rem;
            color: #8b949e;
        }
        .label-alertname { color: #58a6ff; }
        
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            color: #8b949e;
        }
        .empty-state svg { width: 64px; height: 64px; margin-bottom: 20px; opacity: 0.4; }
        .empty-state h2 { color: #c9d1d9; margin-bottom: 10px; }
        
        .pagination {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin-top: 20px;
        }
        .pagination-info { color: #8b949e; font-size: 0.85rem; }
        
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #238636;
            color: #fff;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 0.9rem;
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.3s;
            z-index: 1000;
        }
        .toast.show { opacity: 1; transform: translateY(0); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚨 OpenShift Alerts</h1>
            <div class="controls">
                <select class="refresh-select" id="refreshInterval" onchange="updateRefresh()">
                    <option value="5" {% if refresh==5 %}selected{% endif %}>Refresh: 5s</option>
                    <option value="10" {% if refresh==10 %}selected{% endif %}>Refresh: 10s</option>
                    <option value="30" {% if refresh==30 %}selected{% endif %}>Refresh: 30s</option>
                    <option value="60" {% if refresh==60 %}selected{% endif %}>Refresh: 1m</option>
                    <option value="0" {% if refresh==0 %}selected{% endif %}>No auto-refresh</option>
                </select>
                <a href="/alerts?format=json" class="btn" target="_blank">📄 JSON</a>
                <a href="/alerts?format=csv" class="btn">📥 Export CSV</a>
                <button class="btn btn-danger" onclick="clearAlerts()">🗑️ Clear All</button>
            </div>
        </header>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value total">{{ alerts|length }}</div>
                <div class="stat-label">Total Alerts</div>
            </div>
            <div class="stat-card">
                <div class="stat-value firing">{{ firing_count }}</div>
                <div class="stat-label">🔴 Firing</div>
            </div>
            <div class="stat-card">
                <div class="stat-value resolved">{{ resolved_count }}</div>
                <div class="stat-label">🟢 Resolved</div>
            </div>
        </div>
        
        <div class="filters">
            <div class="filter-group">
                <span class="filter-label">Status:</span>
                <select class="filter-select" id="statusFilter" onchange="applyFilters()">
                    <option value="all">All</option>
                    <option value="firing" {% if status_filter=='firing' %}selected{% endif %}>Firing</option>
                    <option value="resolved" {% if status_filter=='resolved' %}selected{% endif %}>Resolved</option>
                </select>
            </div>
            <div class="filter-group">
                <span class="filter-label">Severity:</span>
                <select class="filter-select" id="severityFilter" onchange="applyFilters()">
                    <option value="all">All</option>
                    <option value="critical" {% if severity_filter=='critical' %}selected{% endif %}>Critical</option>
                    <option value="warning" {% if severity_filter=='warning' %}selected{% endif %}>Warning</option>
                    <option value="info" {% if severity_filter=='info' %}selected{% endif %}>Info</option>
                </select>
            </div>
            <span class="refresh-info">Showing {{ alerts|length }} of {{ total_alerts }} alerts</span>
        </div>
        
        {% if alerts %}
        <table>
            <thead>
                <tr>
                    <th style="width:80px">Status</th>
                    <th>Alert Name</th>
                    <th>Labels</th>
                    <th>Annotations</th>
                    <th style="width:150px">Time</th>
                </tr>
            </thead>
            <tbody>
                {% for alert in alerts %}
                <tr>
                    <td>
                        <span class="status-badge {% if alert.status == 'firing' %}status-firing{% else %}status-resolved{% endif %}">
                            {{ alert.status|upper }}
                        </span>
                    </td>
                    <td class="alertname">{{ alert.labels.get('alertname', 'N/A') }}</td>
                    <td>
                        <div class="labels">
                            {% for key, value in alert.labels.items() %}
                            <span class="label {% if key == 'alertname' %}label-alertname{% endif %}">{{ key }}:{{ value }}</span>
                            {% endfor %}
                        </div>
                    </td>
                    <td class="annotations" title="{{ alert.annotations.get('description', alert.annotations.get('summary', '')) }}">
                        {{ alert.annotations.get('description', alert.annotations.get('summary', '')) }}
                    </td>
                    <td class="timestamp">{{ alert.timestamp }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        
        {% if total_pages > 1 %}
        <div class="pagination">
            {% if page > 1 %}
            <a href="?page={{ page-1 }}&status={{ status_filter }}&severity={{ severity_filter }}&refresh={{ refresh }}" class="btn">← Prev</a>
            {% endif %}
            <span class="pagination-info">Page {{ page }} of {{ total_pages }}</span>
            {% if page < total_pages %}
            <a href="?page={{ page+1 }}&status={{ status_filter }}&severity={{ severity_filter }}&refresh={{ refresh }}" class="btn">Next →</a>
            {% endif %}
        </div>
        {% endif %}
        
        {% else %}
        <div class="empty-state">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <h2>No Alerts</h2>
            <p>Send alerts to <code>/alertwebhook</code> to see them here</p>
        </div>
        {% endif %}
    </div>
    
    <div id="toast" class="toast">Action completed</div>
    
    <script>
        const refreshInterval = {{ refresh }};
        
        if (refreshInterval > 0) {
            setTimeout(function() {
                window.location.reload();
            }, refreshInterval * 1000);
        }
        
        function updateRefresh() {
            const interval = document.getElementById('refreshInterval').value;
            const url = new URL(window.location.href);
            url.searchParams.set('refresh', interval);
            window.location.href = url.toString();
        }
        
        function applyFilters() {
            const status = document.getElementById('statusFilter').value;
            const severity = document.getElementById('severityFilter').value;
            const url = new URL(window.location.href);
            url.searchParams.set('status', status);
            url.searchParams.set('severity', severity);
            url.searchParams.set('page', '1');
            window.location.href = url.toString();
        }
        
        function clearAlerts() {
            if (confirm('Are you sure you want to clear all alerts?')) {
                fetch('/alerts/clear', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        showToast('All alerts cleared');
                        setTimeout(() => window.location.reload(), 500);
                    });
            }
        }
        
        function showToast(msg) {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2000);
        }
    </script>
</body>
</html>
'''


@app.route('/favicon.ico')
def favicon():
    """Serve favicon"""
    return '', 204


@app.route('/alertwebhook', methods=['POST'])
def alertwebhook():
    """Accept Alertmanager webhook notifications."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON payload'}), 400
        
        alerts_data = data.get('alerts', [])
        
        with alerts_lock:
            for alert in alerts_data:
                status = alert.get('status', 'firing')
                labels = {k: v for k, v in alert.get('labels', {}).items() 
                         if k not in ('__tenant_id__', '__alerts_provider__')}
                annotations = alert.get('annotations', {})
                starts_at = alert.get('startsAt', '')
                ends_at = alert.get('endsAt', '')
                
                if status == 'firing' and starts_at:
                    timestamp = starts_at.replace('T', ' ').replace('Z', '')[:19]
                elif status == 'resolved' and ends_at:
                    timestamp = ends_at.replace('T', ' ').replace('Z', '')[:19]
                else:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                alert_entry = {
                    'status': status,
                    'labels': labels,
                    'annotations': annotations,
                    'timestamp': timestamp,
                    'startsAt': starts_at,
                    'endsAt': ends_at,
                    'received_at': datetime.now().isoformat()
                }
                
                alerts.insert(0, alert_entry)
            
            # Trim to max alerts
            while len(alerts) > MAX_ALERTS:
                alerts.pop()
        
        return jsonify({
            'status': 'success',
            'message': f'Received {len(alerts_data)} alert(s)',
            'total_alerts': len(alerts)
        }), 200
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/', methods=['GET'])
@require_auth
def dashboard():
    """Display the alerts dashboard"""
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    severity_filter = request.args.get('severity', 'all')
    page = int(request.args.get('page', 1))
    refresh = int(request.args.get('refresh', 10))
    per_page = 50
    
    with alerts_lock:
        # Apply filters
        filtered_alerts = list(alerts)
        
        if status_filter != 'all':
            filtered_alerts = [a for a in filtered_alerts if a['status'] == status_filter]
        
        if severity_filter != 'all':
            filtered_alerts = [a for a in filtered_alerts 
                             if a['labels'].get('severity', '').lower() == severity_filter]
        
        total_alerts = len(filtered_alerts)
        
        # Paginate
        total_pages = max(1, (total_alerts + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        page_alerts = filtered_alerts[start:end]
        
        firing_count = sum(1 for a in alerts if a['status'] == 'firing')
        resolved_count = sum(1 for a in alerts if a['status'] == 'resolved')
    
    return render_template_string(
        DASHBOARD_HTML,
        alerts=page_alerts,
        total_alerts=total_alerts,
        firing_count=firing_count,
        resolved_count=resolved_count,
        status_filter=status_filter,
        severity_filter=severity_filter,
        page=page,
        total_pages=total_pages,
        refresh=refresh
    )


@app.route('/alerts', methods=['GET'])
@require_auth
def get_alerts_json():
    """Return alerts as JSON/CSV"""
    fmt = request.args.get('format', 'json')
    
    with alerts_lock:
        if fmt == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Status', 'Alert Name', 'Severity', 'Namespace', 'Description', 'Timestamp'])
            for a in alerts:
                writer.writerow([
                    a['status'],
                    a['labels'].get('alertname', ''),
                    a['labels'].get('severity', ''),
                    a['labels'].get('namespace', ''),
                    a['annotations'].get('description', ''),
                    a['timestamp']
                ])
            
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = 'attachment; filename=alerts.csv'
            return response
        
        return jsonify({
            'alerts': alerts,
            'count': len(alerts),
            'firing': sum(1 for a in alerts if a['status'] == 'firing'),
            'resolved': sum(1 for a in alerts if a['status'] == 'resolved')
        })


@app.route('/alerts/clear', methods=['POST'])
@require_auth
def clear_alerts():
    """Clear all alerts"""
    with alerts_lock:
        alerts.clear()
    return jsonify({'status': 'success', 'message': 'All alerts cleared'})


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    with alerts_lock:
        return jsonify({
            'status': 'healthy',
            'alerts_count': len(alerts),
            'firing': sum(1 for a in alerts if a['status'] == 'firing'),
            'resolved': sum(1 for a in alerts if a['status'] == 'resolved')
        })


if __name__ == '__main__':
    print("🚀 OpenShift Alert Webhook")
    print(f"   Dashboard: http://localhost:{APP_PORT}/")
    print(f"   Webhook:   http://localhost:{APP_PORT}/alertwebhook")
    print(f"   Health:    http://localhost:{APP_PORT}/health")
    print(f"   Auth:      {APP_USERNAME} / {APP_PASSWORD}")
    print(f"   Max Alerts: {MAX_ALERTS}")
    app.run(host=APP_HOST, port=APP_PORT, debug=APP_DEBUG)
