#!/bin/bash
# Setup script for OpenHSI Service Controller

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}OpenHSI Service Controller Setup${NC}"
echo "=================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}" 
   exit 1
fi

# Detect conda installation from the original user
if [[ -n "$SUDO_USER" ]]; then
    # Get the original user's home directory
    ORIG_HOME=$(eval echo ~$SUDO_USER)
    # Common conda installation paths
    CONDA_PATHS=(
        "$ORIG_HOME/miniconda3"
        "$ORIG_HOME/anaconda3"
        "$ORIG_HOME/miniforge3"
        "/opt/miniconda3"
        "/opt/anaconda3"
        "/usr/local/miniconda3"
        "/usr/local/anaconda3"
    )
    
    CONDA_BASE=""
    for path in "${CONDA_PATHS[@]}"; do
        if [[ -d "$path" && -f "$path/bin/conda" ]]; then
            CONDA_BASE="$path"
            break
        fi
    done
    
    if [[ -z "$CONDA_BASE" ]]; then
        echo -e "${RED}Conda installation not found. Please install Miniconda or Anaconda first.${NC}"
        echo "Checked paths: ${CONDA_PATHS[*]}"
        exit 1
    fi
else
    # Not running with sudo, try to find conda normally
    if ! command -v conda &> /dev/null; then
        echo -e "${RED}Conda is not installed. Please install Miniconda or Anaconda first.${NC}"
        exit 1
    fi
    CONDA_BASE=$(conda info --base)
fi

echo -e "${GREEN}Found conda at: $CONDA_BASE${NC}"

# Create user and directories
echo -e "${YELLOW}Creating openhsi user and directories...${NC}"
useradd -r -s /bin/bash openhsi || true
mkdir -p /opt/openhsi/controller
chown -R openhsi:openhsi /opt/openhsi

# # Install system dependencies
# echo -e "${YELLOW}Installing system dependencies...${NC}"
# apt-get update
# apt-get install -y nginx

# Create conda environments
echo -e "${YELLOW}Setting up conda environments...${NC}"
CONDA_BIN="$CONDA_BASE/bin/conda"

# Check if conda environments already exist
if ! $CONDA_BIN env list | grep -q "openhsi-switcher"; then
    echo -e "${YELLOW}Creating openhsi-switcher conda environment...${NC}"
    $CONDA_BIN create -y -n openhsi-switcher python=3.10 flask psutil
fi

if ! $CONDA_BIN env list | grep -q "openhsi"; then
    echo -e "${YELLOW}Creating openhsi conda environment...${NC}"
    $CONDA_BIN create -y -n openhsi python=3.10 jupyterlab notebook
fi

# Copy controller script
echo -e "${YELLOW}Installing controller script...${NC}"
cp openhsi-switcher.py /opt/openhsi/controller/
chown -R openhsi:openhsi /opt/openhsi

# Install systemd service
echo -e "${YELLOW}Installing systemd service...${NC}"
sed "s|CONDA_BASE|$CONDA_BASE|g" templates/systemd/openhsi-switcher.service > /etc/systemd/system/openhsi-switcher.service

# Setup sudoers for openhsi user to control services
echo -e "${YELLOW}Configuring sudo permissions...${NC}"
cp templates/sudoers/openhsi /etc/sudoers.d/openhsi

# Setup nginx
echo -e "${YELLOW}Configuring nginx...${NC}"
# Create nginx config directory if it doesn't exist
mkdir -p /etc/nginx/sites-available
mkdir -p /etc/nginx/sites-enabled

# Create nginx configuration for the controller
cp templates/nginx/openhsi-switcher /etc/nginx/sites-available/openhsi-switcher

# Create nginx configs for managed services
cp templates/nginx/openhsi-web-controller /etc/nginx/sites-available/openhsi-web-controller
cp templates/nginx/openhsi-jupyter /etc/nginx/sites-available/openhsi-jupyter

# Note: nginx sites are now managed by the controller
# The controller will enable/disable service sites as needed
# The controller itself is accessible at /controller/ when any service is running

# Create example service files for managed services
echo -e "${YELLOW}Creating example service files...${NC}"

# # Example WebGUI service using conda
# sed "s|CONDA_BASE|$CONDA_BASE|g" templates/systemd/openhsi-webgui.service > /etc/systemd/system/openhsi-webgui.service

# Example Jupyter service using conda
sed "s|CONDA_BASE|$CONDA_BASE|g" templates/systemd/openhsi-jupyter.service > /etc/systemd/system/openhsi-jupyter.service

# Reload systemd
systemctl daemon-reload

# Enable and start the controller service
echo -e "${YELLOW}Starting OpenHSI Controller service...${NC}"
systemctl enable openhsi-switcher
systemctl start openhsi-switcher

# Reload nginx
nginx -s reload

echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "The OpenHSI Controller is now running at:"
echo "  http://localhost:5001 (direct)"
echo ""
echo "To access services:"
echo "  1. Start a service via the controller"
echo "  2. The service will be available at http://localhost/ (root URL)"
echo "  3. The controller will be accessible at http://localhost/controller/"
echo ""
echo "Services are mutually exclusive - starting one will stop the other."
echo "Available services: WebGUI, Jupyter"
echo ""
echo "You can manage services through the web interface or API."