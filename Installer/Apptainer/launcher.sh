#!/bin/bash
set -e

INSTALLER_DIR=$1
HOST_FISSURE_DIR=$2
MODE=$3

echo "[*] Preparing fissure-apptainer launcher..."

DEST_PATH="$HOME/.local/bin"
SRC_FILE="$INSTALLER_DIR/fissure-apptainer.sh"
DEST_FILE="$DEST_PATH/fissure-apptainer"

# Ensure bin directory exists
mkdir -p "$DEST_PATH"

# Add ~/.local/bin to PATH if missing
if grep -Fq "~/.local/bin" ~/.bashrc; then
    echo "~/.local/bin already present in ~/.bashrc"
else
    printf "\n%s\n" 'if [ -d "$HOME/.local/bin" ]; then PATH="$PATH:$HOME/.local/bin"; fi' >> ~/.bashrc
    echo "[+] Added ~/.local/bin to PATH in ~/.bashrc"
fi

# Ensure source file exists
if [[ ! -f "$SRC_FILE" ]]; then
    echo "[!] fissure-apptainer.sh not found in $INSTALLER_DIR"
else
    cp "$SRC_FILE" "$DEST_FILE"

    # Replace placeholders only in the installed copy
    sed -i "s|__FISSURE_DIR__|$HOST_FISSURE_DIR|g" "$DEST_FILE"
    sed -i "s|__FISSURE_MODE__|$MODE|g" "$DEST_FILE"

    chmod +x "$DEST_FILE"
    echo "[✓] fissure-apptainer command installed at $DEST_FILE"
fi
