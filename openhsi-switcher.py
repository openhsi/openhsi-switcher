"""
OpenHSI Service Controller
A web service to manage other services like simple-web-controller, Jupyter, etc.
"""

import subprocess
import json
import os
import psutil
import time
from collections import defaultdict, deque
from threading import Thread, Lock
from flask import Flask, jsonify, request, render_template_string

# from flask_cors import CORS
import logging

app = Flask(__name__)
# CORS(app)  # Enable CORS for API access

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service configurations
SERVICES = {
    "webgui": {
        "name": "OpenHSI WebGUI",
        "systemd_unit": "simple-web-controller.service",
        "port": 5000,
        "nginx_config": "/etc/nginx/sites-available/openhsi-web-controller",
        "mutually_exclusive_with": ["jupyter"],
    },
    "jupyter": {
        "name": "Jupyter Server",
        "systemd_unit": "openhsi-jupyter.service",
        "port": 8888,
        "nginx_config": "/etc/nginx/sites-available/openhsi-jupyter",
        "mutually_exclusive_with": ["webgui"],
    },
}

# Resource monitoring configuration
MONITOR_HISTORY_SIZE = 60  # Keep 60 data points (5 minutes at 5-second intervals)
resource_history = defaultdict(
    lambda: {
        "cpu": deque(maxlen=MONITOR_HISTORY_SIZE),
        "memory": deque(maxlen=MONITOR_HISTORY_SIZE),
        "timestamps": deque(maxlen=MONITOR_HISTORY_SIZE),
    }
)
resource_lock = Lock()

# System-wide resource tracking
system_history = {
    "cpu": deque(maxlen=MONITOR_HISTORY_SIZE),
    "memory": deque(maxlen=MONITOR_HISTORY_SIZE),
    "disk": deque(maxlen=MONITOR_HISTORY_SIZE),
    "network_sent": deque(maxlen=MONITOR_HISTORY_SIZE),
    "network_recv": deque(maxlen=MONITOR_HISTORY_SIZE),
    "timestamps": deque(maxlen=MONITOR_HISTORY_SIZE),
}

# HTML template for the control panel
CONTROL_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>OpenHSI Service Controller</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .full-width {
            grid-column: 1 / -1;
        }
        .card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .service-card {
            margin-bottom: 20px;
        }
        .service-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .service-name {
            font-size: 1.2em;
            font-weight: bold;
        }
        .status {
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 0.9em;
        }
        .status.active {
            background-color: #4CAF50;
            color: white;
        }
        .status.inactive {
            background-color: #f44336;
            color: white;
        }
        .status.starting {
            background-color: #ff9800;
            color: white;
        }
        .status.ready {
            background-color: #4CAF50;
            color: white;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }
        .controls {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }
        button {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
        }
        button.start {
            background-color: #4CAF50;
            color: white;
        }
        button.stop {
            background-color: #f44336;
            color: white;
        }
        button.restart {
            background-color: #ff9800;
            color: white;
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .info {
            margin-top: 10px;
            font-size: 0.9em;
            color: #666;
        }
        .error {
            color: #f44336;
            margin-top: 10px;
        }
        .chart-container {
            height: 200px;
            margin-top: 15px;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        .metric {
            text-align: center;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
        .metric-value {
            font-size: 1.5em;
            font-weight: bold;
            color: #333;
        }
        .metric-label {
            font-size: 0.9em;
            color: #666;
            margin-top: 5px;
        }
        .resource-chart {
            margin-top: 10px;
        }
        canvas {
            max-height: 200px;
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h1>OpenHSI Service Controller</h1>
        <a href="/" style="background-color: #2196F3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-weight: bold;">
            Go to Active Service →
        </a>
    </div>
    
    <div class="container">
        <!-- System Overview -->
        <div class="card full-width">
            <h2>System Overview</h2>
            <div class="metrics" id="system-metrics">
                <div class="metric">
                    <div class="metric-value" id="cpu-usage">-</div>
                    <div class="metric-label">CPU Usage</div>
                </div>
                <div class="metric">
                    <div class="metric-value" id="memory-usage">-</div>
                    <div class="metric-label">Memory Usage</div>
                </div>
                <div class="metric">
                    <div class="metric-value" id="disk-usage">-</div>
                    <div class="metric-label">Disk Usage</div>
                </div>
                <div class="metric">
                    <div class="metric-value" id="network-rate">-</div>
                    <div class="metric-label">Network I/O</div>
                </div>
            </div>
            <div class="resource-chart">
                <canvas id="system-chart"></canvas>
            </div>
        </div>
        
        <!-- Services -->
        <div class="full-width">
            <h2>Services</h2>
            <div id="services"></div>
        </div>
    </div>
    
    <script>
        // Chart.js configuration
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom'
                }
            }
        };

        // Initialize system chart
        const systemCtx = document.getElementById('system-chart').getContext('2d');
        const systemChart = new Chart(systemCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'CPU %',
                        data: [],
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.1)',
                        tension: 0.1
                    },
                    {
                        label: 'Memory %',
                        data: [],
                        borderColor: 'rgb(54, 162, 235)',
                        backgroundColor: 'rgba(54, 162, 235, 0.1)',
                        tension: 0.1
                    }
                ]
            },
            options: chartOptions
        });


        async function fetchServiceStatus() {
            try {
                const response = await fetch('/api/services/status');
                const data = await response.json();
                updateUI(data);
            } catch (error) {
                console.error('Error fetching status:', error);
            }
        }

        async function fetchResourceStats() {
            try {
                const response = await fetch('/api/resources/stats');
                const data = await response.json();
                updateResourceUI(data);
            } catch (error) {
                console.error('Error fetching resources:', error);
            }
        }

        async function controlService(service, action) {
            try {
                // Update UI to show starting state
                if (action === 'start') {
                    updateServiceStatus(service, 'starting', 'Starting...');
                }
                
                const response = await fetch(`/api/services/${service}/${action}`, {
                    method: 'POST'
                });
                const data = await response.json();
                if (data.error) {
                    alert(`Error: ${data.error}`);
                } else {
                    // Wait a moment for service to fully start, then check status
                    if (action === 'start') {
                        setTimeout(() => {
                            fetchServiceStatus();
                            // Show "ready" status after service is confirmed active
                            setTimeout(() => {
                                const activeServices = document.querySelectorAll('.status.active');
                                activeServices.forEach(status => {
                                    if (status.textContent === 'Active') {
                                        status.className = 'status ready';
                                        status.textContent = 'Ready';
                                        // Reset to normal after 3 seconds
                                        setTimeout(() => {
                                            status.className = 'status active';
                                            status.textContent = 'Active';
                                        }, 3000);
                                    }
                                });
                            }, 1000);
                        }, 2000);
                    } else {
                        fetchServiceStatus();
                    }
                }
            } catch (error) {
                console.error('Error controlling service:', error);
                alert('Failed to control service');
                fetchServiceStatus(); // Refresh to show actual state
            }
        }
        
        function updateServiceStatus(serviceName, statusClass, statusText) {
            const services = document.querySelectorAll('.service-card');
            services.forEach(card => {
                const nameElement = card.querySelector('.service-name');
                if (nameElement && nameElement.textContent.includes(serviceName)) {
                    const statusElement = card.querySelector('.status');
                    if (statusElement) {
                        statusElement.className = `status ${statusClass}`;
                        statusElement.textContent = statusText;
                    }
                }
            });
        }

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        function updateResourceUI(data) {
            // Update system metrics
            document.getElementById('cpu-usage').textContent = data.system.cpu.toFixed(1) + '%';
            document.getElementById('memory-usage').textContent = data.system.memory.percent.toFixed(1) + '%';
            document.getElementById('disk-usage').textContent = data.system.disk.percent.toFixed(1) + '%';
            document.getElementById('network-rate').textContent = 
                '↓' + formatBytes(data.system.network.bytes_recv) + '/s ' +
                '↑' + formatBytes(data.system.network.bytes_sent) + '/s';

            // Update system chart
            if (data.system.history) {
                const labels = data.system.history.timestamps.map(ts => {
                    const date = new Date(ts * 1000);
                    return date.toLocaleTimeString();
                });
                
                systemChart.data.labels = labels;
                systemChart.data.datasets[0].data = data.system.history.cpu;
                systemChart.data.datasets[1].data = data.system.history.memory;
                systemChart.update('none');
            }

        }

        function updateUI(services) {
            const container = document.getElementById('services');
            container.innerHTML = '';
            
            for (const [key, service] of Object.entries(services)) {
                const card = document.createElement('div');
                card.className = 'service-card card';
                
                const statusClass = service.active ? 'active' : 'inactive';
                const statusText = service.active ? 'Active' : 'Inactive';
                
                card.innerHTML = `
                    <div class="service-header">
                        <div class="service-name">${service.name}</div>
                        <div class="status ${statusClass}">${statusText}</div>
                    </div>
                    <div class="info">
                        Port: ${service.port} | 
                        Systemd Unit: ${service.systemd_unit}
                        ${service.active ? ' | <strong>Service is ready and accessible at <a href="/" target="_blank">root URL</a></strong>' : ''}
                    </div>
                    <div class="controls">
                        <button class="start" onclick="controlService('${key}', 'start')" 
                                ${service.active ? 'disabled' : ''}>Start</button>
                        <button class="stop" onclick="controlService('${key}', 'stop')" 
                                ${!service.active ? 'disabled' : ''}>Stop</button>
                        <button class="restart" onclick="controlService('${key}', 'restart')"
                                ${!service.active ? 'disabled' : ''}>Restart</button>
                    </div>
                `;
                
                container.appendChild(card);
            }
        }

        // Fetch status on load
        fetchServiceStatus();
        fetchResourceStats();
        
        // Update every 5 seconds
        setInterval(() => {
            fetchServiceStatus();
            fetchResourceStats();
        }, 5000);
    </script>
</body>
</html>
"""


def run_systemctl(action, service_unit):
    """Run systemctl command and return success status"""
    try:
        cmd = ["sudo", "systemctl", action, service_unit]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stderr
    except Exception as e:
        return False, str(e)


def toggle_nginx_site(nginx_config_path, enable=True):
    """Enable or disable an nginx site"""
    try:
        # Extract site name from config path
        site_name = os.path.basename(nginx_config_path)
        sites_enabled_path = f"/etc/nginx/sites-enabled/{site_name}"
        
        if enable:
            # Enable site by creating symlink
            cmd = ["sudo", "ln", "-sf", nginx_config_path, sites_enabled_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return False, f"Failed to enable nginx site: {result.stderr}"
        else:
            # Disable site by removing symlink
            cmd = ["sudo", "rm", "-f", sites_enabled_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return False, f"Failed to disable nginx site: {result.stderr}"
        
        # Reload nginx configuration
        reload_cmd = ["sudo", "nginx", "-s", "reload"]
        reload_result = subprocess.run(reload_cmd, capture_output=True, text=True)
        if reload_result.returncode != 0:
            return False, f"Failed to reload nginx: {reload_result.stderr}"
            
        return True, "Nginx site toggled successfully"
        
    except Exception as e:
        return False, str(e)


def get_service_status(service_unit):
    """Check if a systemd service is active"""
    try:
        cmd = ["systemctl", "is-active", service_unit]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip() == "active"
    except:
        return False


def get_service_pid(service_unit):
    """Get the main PID of a systemd service"""
    try:
        cmd = ["systemctl", "show", service_unit, "--property=MainPID"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            pid = result.stdout.strip().split("=")[1]
            return int(pid) if pid and pid != "0" else None
    except:
        return None


def get_process_resources(pid):
    """Get resource usage for a specific process"""
    try:
        process = psutil.Process(pid)

        # Get all child processes
        children = process.children(recursive=True)
        processes = [process] + children

        # Calculate total resources
        cpu_percent = sum(p.cpu_percent(interval=0.1) for p in processes)
        memory_info = sum(p.memory_info().rss for p in processes)
        memory_percent = sum(p.memory_percent() for p in processes)

        return {
            "cpu": cpu_percent,
            "memory": memory_info,
            "memory_percent": memory_percent,
            "num_processes": len(processes),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def get_system_resources():
    """Get system-wide resource usage"""
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # Memory usage
    memory = psutil.virtual_memory()

    # Disk usage
    disk = psutil.disk_usage("/")

    # Network I/O
    net_io = psutil.net_io_counters()

    return {
        "cpu": cpu_percent,
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "percent": memory.percent,
        },
        "disk": {"total": disk.total, "used": disk.used, "percent": disk.percent},
        "network": {"bytes_sent": net_io.bytes_sent, "bytes_recv": net_io.bytes_recv},
    }


# Background thread for resource monitoring
def monitor_resources():
    """Background thread to continuously monitor resources"""
    last_net_sent = 0
    last_net_recv = 0

    while True:
        try:
            # Get system resources
            sys_resources = get_system_resources()

            # Calculate network rates
            net_sent_rate = sys_resources["network"]["bytes_sent"] - last_net_sent
            net_recv_rate = sys_resources["network"]["bytes_recv"] - last_net_recv
            last_net_sent = sys_resources["network"]["bytes_sent"]
            last_net_recv = sys_resources["network"]["bytes_recv"]

            # Update system history
            with resource_lock:
                timestamp = time.time()
                system_history["cpu"].append(sys_resources["cpu"])
                system_history["memory"].append(sys_resources["memory"]["percent"])
                system_history["disk"].append(sys_resources["disk"]["percent"])
                system_history["network_sent"].append(net_sent_rate)
                system_history["network_recv"].append(net_recv_rate)
                system_history["timestamps"].append(timestamp)

            # Monitor each active service
            for service_key, service_config in SERVICES.items():
                if get_service_status(service_config["systemd_unit"]):
                    pid = get_service_pid(service_config["systemd_unit"])
                    if pid:
                        resources = get_process_resources(pid)
                        if resources:
                            with resource_lock:
                                resource_history[service_key]["cpu"].append(
                                    resources["cpu"]
                                )
                                resource_history[service_key]["memory"].append(
                                    resources["memory_percent"]
                                )
                                resource_history[service_key]["timestamps"].append(
                                    timestamp
                                )

            time.sleep(5)  # Monitor every 5 seconds

        except Exception as e:
            logger.error(f"Error in resource monitoring: {e}")
            time.sleep(5)


# Start monitoring thread
monitor_thread = Thread(target=monitor_resources, daemon=True)
monitor_thread.start()


@app.route("/")
def index():
    """Serve the control panel UI"""
    return render_template_string(CONTROL_PANEL_HTML)


@app.route("/api/services/status")
def get_all_service_status():
    """Get status of all configured services"""
    status = {}
    for key, service in SERVICES.items():
        status[key] = {
            "name": service["name"],
            "active": get_service_status(service["systemd_unit"]),
            "systemd_unit": service["systemd_unit"],
            "port": service["port"],
        }
    return jsonify(status)


@app.route("/api/services/<service>/start", methods=["POST"])
def start_service(service):
    """Start a specific service"""
    if service not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    service_config = SERVICES[service]
    
    # Stop mutually exclusive services first
    if "mutually_exclusive_with" in service_config:
        for exclusive_service in service_config["mutually_exclusive_with"]:
            if exclusive_service in SERVICES:
                exclusive_config = SERVICES[exclusive_service]
                logger.info(f"Stopping mutually exclusive service: {exclusive_service}")
                stop_success, stop_error = run_systemctl("stop", exclusive_config["systemd_unit"])
                if stop_success:
                    # Disable nginx proxy for the stopped service
                    nginx_success, nginx_error = toggle_nginx_site(exclusive_config["nginx_config"], enable=False)
                    if not nginx_success:
                        logger.warning(f"Stopped {exclusive_service} but nginx toggle failed: {nginx_error}")
                else:
                    logger.warning(f"Failed to stop {exclusive_service}: {stop_error}")
    
    # Start the requested service
    success, error = run_systemctl("start", service_config["systemd_unit"])

    if success:
        # Enable nginx proxy for this service
        nginx_success, nginx_error = toggle_nginx_site(service_config["nginx_config"], enable=True)
        if not nginx_success:
            logger.warning(f"Service started but nginx toggle failed: {nginx_error}")
        return jsonify({"status": "started", "service": service})
    else:
        return jsonify({"error": error}), 500


@app.route("/api/services/<service>/stop", methods=["POST"])
def stop_service(service):
    """Stop a specific service"""
    if service not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    service_config = SERVICES[service]
    success, error = run_systemctl("stop", service_config["systemd_unit"])

    if success:
        # Disable nginx proxy for this service
        nginx_success, nginx_error = toggle_nginx_site(service_config["nginx_config"], enable=False)
        if not nginx_success:
            logger.warning(f"Service stopped but nginx toggle failed: {nginx_error}")
        return jsonify({"status": "stopped", "service": service})
    else:
        return jsonify({"error": error}), 500


@app.route("/api/services/<service>/restart", methods=["POST"])
def restart_service(service):
    """Restart a specific service"""
    if service not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    service_config = SERVICES[service]
    success, error = run_systemctl("restart", service_config["systemd_unit"])

    if success:
        return jsonify({"status": "restarted", "service": service})
    else:
        return jsonify({"error": error}), 500


@app.route("/api/services/<service>/status")
def get_service_status_api(service):
    """Get status of a specific service"""
    if service not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    service_config = SERVICES[service]
    active = get_service_status(service_config["systemd_unit"])

    return jsonify(
        {
            "service": service,
            "name": service_config["name"],
            "active": active,
            "port": service_config["port"],
        }
    )


@app.route("/api/resources/stats")
def get_resource_stats():
    """Get current resource statistics for system and services"""
    stats = {"system": {}, "services": {}}

    # Get current system resources
    sys_resources = get_system_resources()

    # Calculate network rates (per second)
    with resource_lock:
        if len(system_history["network_sent"]) >= 2:
            net_sent_rate = system_history["network_sent"][-1]
            net_recv_rate = system_history["network_recv"][-1]
        else:
            net_sent_rate = 0
            net_recv_rate = 0

    stats["system"] = {
        "cpu": sys_resources["cpu"],
        "memory": sys_resources["memory"],
        "disk": sys_resources["disk"],
        "network": {"bytes_sent": net_sent_rate, "bytes_recv": net_recv_rate},
        "history": {
            "cpu": list(system_history["cpu"]),
            "memory": list(system_history["memory"]),
            "disk": list(system_history["disk"]),
            "network_sent": list(system_history["network_sent"]),
            "network_recv": list(system_history["network_recv"]),
            "timestamps": list(system_history["timestamps"]),
        },
    }

    # Get service-specific resources
    for service_key, service_config in SERVICES.items():
        if get_service_status(service_config["systemd_unit"]):
            pid = get_service_pid(service_config["systemd_unit"])
            if pid:
                resources = get_process_resources(pid)
                if resources:
                    with resource_lock:
                        history_data = {
                            "cpu": list(resource_history[service_key]["cpu"]),
                            "memory": list(resource_history[service_key]["memory"]),
                            "timestamps": list(
                                resource_history[service_key]["timestamps"]
                            ),
                        }

                    stats["services"][service_key] = {
                        "pid": pid,
                        "cpu": resources["cpu"],
                        "memory": resources["memory"],
                        "memory_percent": resources["memory_percent"],
                        "num_processes": resources["num_processes"],
                        "history": history_data,
                    }

    return jsonify(stats)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
