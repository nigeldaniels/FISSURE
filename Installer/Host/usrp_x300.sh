#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing USRP X300/X310 host dependencies..."

# Ensure UHD host tools are available
if ! dpkg -l | grep -q uhd-host; then
    echo "[*] Installing UHD host package..."
    sudo apt-get update
    sudo apt-get install -y uhd-host
else
    echo "[✓] UHD host package already installed."
fi

# Download UHD FPGA images
echo "[*] Downloading UHD FPGA images for X300/X310..."
if [ -x /usr/lib/uhd/utils/uhd_images_downloader.py ]; then
    sudo /usr/lib/uhd/utils/uhd_images_downloader.py
elif [ -x /usr/bin/uhd_images_downloader ]; then
    sudo /usr/bin/uhd_images_downloader
else
    echo "[!] UHD image downloader not found after installation."
fi

# Increase socket buffer size for high throughput
echo "[*] Adjusting system network buffers for USRP operation..."
sudo sysctl -w net.core.wmem_max=24862979 || echo "[!] sysctl update failed (non-critical)."

echo "[✓] USRP X300/X310 host configuration complete."
