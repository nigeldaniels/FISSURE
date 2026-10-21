#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing Wi-Fi host dependencies and driver (rtl8812au) on host..."

sudo apt-get update
sudo apt-get -y install dkms git build-essential

mkdir -p "$HOME/Installed_by_FISSURE"
cd "$HOME/Installed_by_FISSURE"

if [ -d rtl8812au ]; then
    echo "[*] rtl8812au repository already exists — using existing clone."
else
    git clone https://github.com/aircrack-ng/rtl8812au
fi

cd rtl8812au
sudo make dkms_install

########## Verify ##########
sudo modprobe 8812au && echo "[✓] rtl8812au module loaded successfully" || echo "[!] rtl8812au module load failed"
