#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing Meshtastic host dependencies..."
sudo apt-get update
sudo apt-get install -y python3-serial
sudo apt-get install -y python3-protobuf

echo "[*] Installing Meshtastic Python package..."
sudo python3 -m pip install "meshtastic==2.6.4" --break-system-packages

echo "[*] Applying Meshtastic udev and permission rules..."
# Add user to necessary serial groups
sudo usermod -aG dialout "$USER"
sudo usermod -aG tty "$USER"

# Add udev rule for Meshtastic devices (Silicon Labs CP210x)
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666"' | \
    sudo tee /etc/udev/rules.d/99-meshtastic.rules > /dev/null

sudo udevadm control --reload-rules
sudo udevadm trigger

echo "[✓] Meshtastic host configuration complete."
