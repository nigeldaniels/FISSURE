#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Setting up RTL-SDR host device access..."

echo 'blacklist dvb_usb_rtl28xxu' \
    | sudo tee /etc/modprobe.d/rtl-sdr.conf >/dev/null

sudo rm -f /etc/udev/rules.d/20.rtlsdr.rules

echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE:="0666"' \
    | sudo tee /etc/udev/rules.d/99-fissure-rtlsdr.rules >/dev/null

sudo udevadm control --reload-rules
sudo udevadm trigger

echo "[✓] RTL-SDR host device access configured."
echo "[!] Unplug and reconnect the RTL-SDR. A reboot may be required if the DVB driver is already loaded."
