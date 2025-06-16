# OpenHSI Switcher

A web-based service controller for managing OpenHSI (Hyperspectral Imaging) services on Raspberry Pi and similar devices. This application provides a dashboard for monitoring and controlling services like WebGUI and Jupyter with real-time resource monitoring.

## Features

- **Service Management**: Start, stop, and restart systemd services through a web interface
- **Resource Monitoring**: Real-time CPU, memory, disk, and network usage tracking with interactive charts
- **Nginx Integration**: Automatic proxy configuration management for services
- **Mutually Exclusive Services**: Automatic handling of services that cannot run simultaneously
- **Web Dashboard**: Clean, responsive interface with real-time updates

## Supported Services

- **OpenHSI WebGUI**: Simple web controller interface (Port 5000)
- **Jupyter Server**: OpenHSI Jupyter environment (Port 8888)

## Quick Start

### Prerequisites

- Python 3.6+ with pip
- Systemd-based Linux system
- Nginx (for proxy functionality)
- Sudo privileges for service management

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd openhsi-switcher
```

2. Install Python dependencies:
```bash
pip install flask psutil
```

3. Run the setup script as root to configure system services:
```bash
sudo chmod +x setup-script.sh
sudo ./setup-script.sh
```

### Usage

#### Running Locally (Development)
```bash
python openhsi-switcher.py
```
Access the dashboard at `http://localhost:5001`

#### Running as System Service
```bash
# Start the service
sudo systemctl start openhsi-switcher

# Enable auto-start on boot
sudo systemctl enable openhsi-switcher

# Check service status
sudo systemctl status openhsi-switcher
```

## API Endpoints

### Service Management
- `GET /api/services/status` - Get status of all services
- `POST /api/services/{service}/start` - Start a service
- `POST /api/services/{service}/stop` - Stop a service
- `POST /api/services/{service}/restart` - Restart a service
- `GET /api/services/{service}/status` - Get status of specific service

### Resource Monitoring
- `GET /api/resources/stats` - Get current system and service resource usage

## Configuration

The application configuration is defined in `openhsi-switcher.py`:

```python
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
```

## File Structure

```
openhsi-switcher/
├── openhsi-switcher.py          # Main Flask application
├── setup-script.sh             # System setup and installation script
├── CLAUDE.md                    # Development guidelines
├── README.md                    # This file
└── templates/
    ├── nginx/                   # Nginx configuration templates
    │   ├── openhsi-jupyter
    │   ├── openhsi-switcher
    │   └── openhsi-web-controller
    ├── sudoers/                 # Sudo configuration
    │   └── openhsi
    └── systemd/                 # Systemd service files
        ├── openhsi-jupyter.service
        └── openhsi-switcher.service
```

## System Requirements

- **OS**: Linux with systemd
- **Python**: 3.6+
- **Memory**: 512MB+ recommended
- **Network**: Port 5001 for the controller interface
- **Permissions**: Sudo access for service management

## Security

The application includes several security measures:
- Dedicated system user (`openhsi-user`)
- Restricted sudo permissions for specific systemctl commands
- No shell access for the service user
- Nginx proxy configuration for secure access

## Troubleshooting

### Service Logs
```bash
# View controller logs
sudo journalctl -u openhsi-switcher -f

# View specific service logs
sudo journalctl -u simple-web-controller -f
sudo journalctl -u openhsi-jupyter -f
```

### Common Issues

1. **Permission Denied**: Ensure the setup script was run with sudo privileges
2. **Service Won't Start**: Check systemd service files are properly installed
3. **Nginx Errors**: Verify nginx configuration files are in place
4. **Resource Monitoring Issues**: Ensure psutil is installed and functioning

### Manual Service Management
```bash
# Check if services are installed
systemctl list-unit-files | grep openhsi

# Manually start/stop services
sudo systemctl start openhsi-switcher
sudo systemctl stop simple-web-controller
```

## Development

### Local Development
1. Install dependencies: `pip install flask psutil`
2. Run: `python openhsi-switcher.py`
3. Access dashboard: `http://localhost:5001`

### Adding New Services
1. Add service configuration to the `SERVICES` dictionary
2. Create corresponding nginx configuration template
3. Update setup script to install new service files

## Contributing

When making changes to the codebase, please follow the guidelines in `CLAUDE.md` and ensure:
- Code follows existing conventions
- Resource monitoring continues to function
- Service management remains secure
- Web interface remains responsive

## License

[License information to be added]