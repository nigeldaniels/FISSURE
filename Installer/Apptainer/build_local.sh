#!/bin/bash
set -e

INSTALLER_DIR=$1
HOST_FISSURE_DIR=$2
APPTAINER_FISSURE_DIR=$3
APPTAINER_OS=$4
MODE=$5
SANDBOX_DIR=$6
DEF_FILE=$7

echo "[*] Building new writable FISSURE Apptainer sandbox for $APPTAINER_OS..."
echo "[*] Using host source: $HOST_FISSURE_DIR"
echo "[*] Copying into container destination: $APPTAINER_FISSURE_DIR"

# Check if DEF_FILE is already defined, if not, set it
if [ -z "$DEF_FILE" ]; then
    DEF_FILE="$INSTALLER_DIR/fissure_apptainer.def"  # permanent source (now in Installer)
fi
DEF_TEMP="$INSTALLER_DIR/fissure_build.def"  # temporary build version

# Determine base image name based on OS
case "$APPTAINER_OS" in
    "Ubuntu 22.04")
        BASE_IMAGE="ubuntu:22.04" ;;
    "Ubuntu 24.04")
        BASE_IMAGE="ubuntu:24.04" ;;
    "Parrot 6.1")
        BASE_IMAGE="parrot:6.1" ;;
    *)
        echo "[!] Unsupported Apptainer OS: $APPTAINER_OS"
        exit 1 ;;
esac

# Generate temporary definition file with replaced placeholders
sed \
    -e "s|__BASE_IMAGE__|$BASE_IMAGE|g" \
    -e "s|__OS_LABEL__|$APPTAINER_OS|g" \
    -e "s|__HOST_FISSURE_DIR__|$HOST_FISSURE_DIR|g" \
    -e "s|__INSTALL_MODE__|$MODE|g" \
    "$DEF_FILE" > "$DEF_TEMP"

echo "[*] Verifying generated FISSURE install mode..."
grep -n -- "--mode" "$DEF_TEMP"

# Remove old sandbox if it exists
if [ -d "$SANDBOX_DIR" ]; then
    echo "[!] Removing old sandbox: $SANDBOX_DIR"
    sudo rm -rf "$SANDBOX_DIR"
fi

# Build writable sandbox container
echo "[*] Running: sudo apptainer build --sandbox $SANDBOX_DIR $DEF_TEMP"
sudo bash "$INSTALLER_DIR/Apptainer/build_image.sh" sandbox "$SANDBOX_DIR" "$DEF_TEMP"

# Clean up temp def file
rm -f "$DEF_TEMP"

echo "[✓] Writable container sandbox created at: $SANDBOX_DIR"
echo
