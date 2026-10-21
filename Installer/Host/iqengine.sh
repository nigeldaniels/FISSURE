#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing and preparing IQEngine Docker environment..."

# Ensure Docker is installed (only docker.io)
if ! command -v docker > /dev/null 2>&1; then
    echo "[*] Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo usermod -aG docker ${USER}
    echo "[✓] Docker installed. (Reboot may be required for group changes.)"
else
    echo "[✓] Docker already installed."
fi

# Clone IQEngine once
mkdir -p "$HOME/Installed_by_FISSURE"
cd "$HOME/Installed_by_FISSURE"

if [ ! -d IQEngine ]; then
    git clone https://github.com/IQEngine/IQEngine.git
else
    echo "[!] IQEngine directory already exists — skipping clone."
fi

cd "$HOME/Installed_by_FISSURE/IQEngine"
cp -n example.env .env

# Pull IQEngine image
echo "[*] Pulling IQEngine image..."
sudo docker pull ghcr.io/iqengine/iqengine:pre

# Verify IQEngine container existence
echo "[*] Verifying IQEngine container existence..."
if sudo docker ps -a --filter "ancestor=ghcr.io/iqengine/iqengine:pre" --format '{{.ID}} {{.Status}} {{.Names}}' | grep -q .; then
    echo "[✓] IQEngine container exists (running or stopped)."
else
    echo "[!] IQEngine container not found on host."
    echo "    You can start one manually with:"
    echo "    sudo docker run --env-file .env -v '$HOST_FISSURE_DIR/IQ Recordings':/tmp/myrecordings -p 3001:3000 -d ghcr.io/iqengine/iqengine:pre"
fi

# Quick Docker sanity check
echo "[*] Running Docker hello-world check..."
sudo docker run --rm hello-world >/dev/null && echo "[✓] Docker daemon working." || echo "[!] Docker test failed."

echo "[✓] IQEngine host setup complete."
