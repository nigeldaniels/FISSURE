#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing UHD host dependencies and configuring USB access..."
sudo apt-get update
sudo apt-get install -y uhd-host

# Copy udev rule if present
if [ -f /usr/lib/uhd/utils/uhd-usrp.rules ]; then
    sudo cp /usr/lib/uhd/utils/uhd-usrp.rules /etc/udev/rules.d/
elif [ -f /usr/share/uhd/utils/uhd-usrp.rules ]; then
    sudo cp /usr/share/uhd/utils/uhd-usrp.rules /etc/udev/rules.d/
else
    echo "[!] UHD udev rule not found — continuing anyway."
fi

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Ensure plugdev group exists and user has access
if ! getent group plugdev >/dev/null; then
    sudo groupadd plugdev
fi
HOST_USER="${SUDO_USER:-$USER}"
sudo usermod -aG plugdev "$HOST_USER"

echo "[*] Downloading UHD FPGA images..."
sudo mkdir -p /usr/share/uhd
sudo chmod -R 777 /usr/share/uhd
uhd_images_downloader || echo "[!] UHD image download failed (check network)."

echo "[✓] UHD host configuration complete."
