#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Configuring Apptainer Sensor Node launcher and autostart on host..."

mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.config/autostart"

SENSOR_NODE_LAUNCHER="$HOME/.local/bin/fissure-apptainer-sensor-node"

cat <<EOF > "$SENSOR_NODE_LAUNCHER"
#!/bin/bash
set -e

HOST_FISSURE_DIR="$HOST_FISSURE_DIR"
APPTAINER_FISSURE_DIR="$APPTAINER_FISSURE_DIR"
SIF_IMAGE="\$HOME/fissure_apptainer.sif"
SANDBOX_IMAGE="\$HOME/fissure_apptainer"

if [ -f "\$SIF_IMAGE" ]; then
    APPTAINER_IMAGE="\$SIF_IMAGE"
elif [ -d "\$SANDBOX_IMAGE" ]; then
    APPTAINER_IMAGE="\$SANDBOX_IMAGE"
else
    echo "[ERROR] No FISSURE Apptainer image was found."
    echo "        Expected either:"
    echo "          \$SIF_IMAGE"
    echo "          \$SANDBOX_IMAGE"
    exit 1
fi

if [ ! -d "\$HOST_FISSURE_DIR/fissure" ]; then
    echo "[ERROR] FISSURE source was not found at \$HOST_FISSURE_DIR"
    exit 1
fi

APPTAINER_ARGS=(
    exec
    --bind "\$HOST_FISSURE_DIR:\$APPTAINER_FISSURE_DIR"
    --env "PYTHONPATH=\$APPTAINER_FISSURE_DIR"
)

if [ -d /dev/bus/usb ]; then
    APPTAINER_ARGS+=(--bind /dev/bus/usb:/dev/bus/usb)
fi

if [ -d /run/udev ]; then
    APPTAINER_ARGS+=(--bind /run/udev:/run/udev)
fi

for dev in /dev/ttyACM* /dev/ttyUSB*; do
    if [ -e "\$dev" ]; then
        APPTAINER_ARGS+=(--bind "\$dev:\$dev")
    fi
done

exec apptainer "\${APPTAINER_ARGS[@]}" \
    "\$APPTAINER_IMAGE" \
    fissure-sensor-node
EOF

chmod +x "$SENSOR_NODE_LAUNCHER"

cat <<EOF > "$HOME/.config/autostart/fissure-sensor-node.desktop"
[Desktop Entry]
Type=Application
Terminal=true
Name=FISSURE Sensor Node
Comment=Launch the FISSURE Sensor Node through Apptainer
Exec=gnome-terminal -- bash -c 'sleep 1; "$HOME/.local/bin/fissure-apptainer-sensor-node"; exec bash'
X-GNOME-Autostart-enabled=true
EOF

chmod +x "$HOME/.config/autostart/fissure-sensor-node.desktop"

echo "[✓] Apptainer Sensor Node launcher installed at: $SENSOR_NODE_LAUNCHER"
echo "[✓] Sensor Node autostart configured at: $HOME/.config/autostart/fissure-sensor-node.desktop"
echo "[i] Sensor Node autostart runs when the host desktop session starts."
