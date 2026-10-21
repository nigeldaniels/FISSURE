#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing HackRF host dependencies and udev rules..."
sudo apt-get update
sudo apt-get install -y hackrf libhackrf-dev

# Install udev rule if present in FISSURE Tools
if [ -f "$HOST_FISSURE_DIR/Tools/53-hackrf.rules" ]; then
    echo "[*] Copying HackRF udev rule to /etc/udev/rules.d/..."
    sudo cp "$HOST_FISSURE_DIR/Tools/53-hackrf.rules" /etc/udev/rules.d/53-hackrf.rules
else
    echo "[!] HackRF udev rule not found at $HOST_FISSURE_DIR/Tools/53-hackrf.rules"
    echo "    Skipping rule installation (non-critical)."
fi

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Verify device access and version
echo "[*] Verifying HackRF installation..."
if command -v hackrf_info >/dev/null 2>&1; then
    hackrf_info || echo "[!] HackRF device not detected (may not be plugged in)."
else
    echo "[!] hackrf_info not found — check that hackrf-tools installed correctly."
fi

echo "[✓] HackRF host configuration complete."
