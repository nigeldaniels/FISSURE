#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing Xpra 6.5.2 host support..."

sudo apt-get update

sudo apt-get install -y build-essential
sudo apt-get install -y python3-dev
sudo apt-get install -y python3-setuptools
sudo apt-get install -y python3-pip
sudo apt-get install -y cython3
sudo apt-get install -y pkg-config
sudo apt-get install -y wget
sudo apt-get install -y xterm
sudo apt-get install -y xvfb
sudo apt-get install -y xauth
sudo apt-get install -y openssh-client
sudo apt-get install -y libxxhash-dev
sudo apt-get install -y libgtk-3-dev
sudo apt-get install -y libx11-dev
sudo apt-get install -y libxext-dev
sudo apt-get install -y libxfixes-dev
sudo apt-get install -y libxdamage-dev
sudo apt-get install -y libxcomposite-dev
sudo apt-get install -y libxrandr-dev
sudo apt-get install -y libxtst-dev
sudo apt-get install -y libxi-dev
sudo apt-get install -y libxcursor-dev
sudo apt-get install -y libxkbfile-dev
sudo apt-get install -y libxres-dev
sudo apt-get install -y libgirepository1.0-dev
sudo apt-get install -y python3-gi
sudo apt-get install -y python-gi-dev
sudo apt-get install -y python3-cairo-dev
sudo apt-get install -y libx264-dev
sudo apt-get install -y libvpx-dev

# A remote Sensor Node must accept SSH connections from Dashboard.
# Install/enable the server when this host is intended to run a
# Sensor Node. Dashboard-only hosts only need openssh-client.
if [[ "$MODE" == "SensorNode" || "$MODE" == "full" ]] || $AUTO_LAUNCH_SENSOR_NODE; then
    sudo apt-get install -y openssh-server
    sudo systemctl enable --now ssh
fi

xpra_install_dir="$HOME/Installed_by_FISSURE/xpra"
mkdir -p "$xpra_install_dir"

rm -rf "$xpra_install_dir/xpra-6.5.2"
rm -f "$xpra_install_dir/xpra-6.5.2.tar.gz"

cd "$xpra_install_dir"

wget https://github.com/Xpra-org/xpra/archive/refs/tags/v6.5.2.tar.gz \
    -O xpra-6.5.2.tar.gz

tar -xzf xpra-6.5.2.tar.gz
cd xpra-6.5.2

python3 setup.py build
sudo python3 setup.py install --prefix=/usr/local

hash -r

cd "$HOME"
rm -rf "$xpra_install_dir/xpra-6.5.2"
rm -f "$xpra_install_dir/xpra-6.5.2.tar.gz"

echo "[*] Verifying Xpra host installation..."
if [ ! -x /usr/local/bin/xpra ]; then
    echo "[ERROR] /usr/local/bin/xpra was not installed."
    exit 1
fi

if ! /usr/local/bin/xpra --version 2>&1 | grep -q '6\.5\.2'; then
    echo "[ERROR] Xpra 6.5.2 verification failed."
    /usr/local/bin/xpra --version || true
    exit 1
fi

echo "[✓] Xpra 6.5.2 host support installed."
