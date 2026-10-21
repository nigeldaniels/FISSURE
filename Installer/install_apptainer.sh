#!/bin/bash
set -e

#############################################
#          FISSURE Apptainer Installer      #
#############################################
# Example usage:
#   ./install_apptainer.sh \
#       --host-os "Ubuntu 24.04" \
#       --apptainer-os "Ubuntu 24.04" \
#       --mode base \
#       --build-apptainer \
#       --install-host-deps \
#       --install-fissure-cmd \
#       --db --meshtastic --uhd --hackrf --wifi --usrp-x300 --iqengine --takserver --xpra
#
# Common modes:
#   full       - Includes every installer item enabled by default
#   base       - Core FISSURE dependencies and shared components
#   custom     - Uses the installer items listed in Modes/custom.py
#   Dashboard  - Dashboard-focused installation
#   HIPRFISR   - HIPRFISR-focused installation
#   SensorNode - Sensor Node-focused installation
#############################################

# Detect where the script lives (Installer) and use its parent as the host FISSURE directory
SCRIPT_PATH="$(realpath "$0")"
INSTALLER_DIR="$(dirname "$SCRIPT_PATH")"
HOST_FISSURE_DIR="$(dirname "$INSTALLER_DIR")"
SANDBOX_DIR="$HOME/fissure_apptainer"
DEF_FILE="$INSTALLER_DIR/fissure_apptainer.def"

# Default paths and settings
APPTAINER_FISSURE_DIR="/opt/FISSURE"
HOST_OS="Ubuntu 24.04"
APPTAINER_OS="Ubuntu 24.04"
MODE="full"
BUILD_APPTAINER=true
INSTALL_HOST_DEPS=true
INSTALL_FISSURE_CMD=true
DB=true 
AUTO_LAUNCH_SENSOR_NODE=false
MESHTASTIC=true
UHD=true
RTLSDR=true
HACKRF=true
WIFI=true
USRP_X300=true
IQENGINE=true
TAKSERVER=false
XPRA=true


#############################################
#              Parse arguments              #
#############################################
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --host-os) HOST_OS="$2"; shift ;;
        --apptainer-os) APPTAINER_OS="$2"; shift ;;
        --mode) MODE="$2"; shift ;;
        --build-apptainer) BUILD_APPTAINER=true ;;
        --install-host-deps) INSTALL_HOST_DEPS=true ;;
        --install-fissure-cmd) INSTALL_FISSURE_CMD=true ;;
        --auto-launch-sensor-node)
            AUTO_LAUNCH_SENSOR_NODE=true ;;
        --db) DB=true ;;
        --meshtastic) MESHTASTIC=true ;;
        --uhd) UHD=true ;;
        --rtlsdr) RTLSDR=true ;;
        --hackrf) HACKRF=true ;;
        --wifi) WIFI=true ;;
        --usrp-x300)
            USRP_X300=true ;;
        --iqengine) IQENGINE=true ;;
        --takserver) TAKSERVER=true ;;
        --xpra) XPRA=true ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo
            echo "Options:"
            echo "  --host-os 'Ubuntu 24.04'       Host operating system label"
            echo "  --apptainer-os 'Ubuntu 24.04'  Apptainer container OS base"
            echo "  --mode MODE                    full, base, custom, Dashboard, HIPRFISR, or SensorNode"
            echo "  --build-apptainer              Build the writable Apptainer sandbox"
            echo "  --install-host-deps            Install host dependencies (drivers, Docker, etc.)"
            echo "  --auto-launch-sensor-node      Launch the Apptainer Sensor Node after graphical login"
            echo "  --db                           Configure PostgreSQL host environment"
            echo "  --meshtastic                   Configure Meshtastic host environment"
            echo "  --uhd                          Configure UHD (USRP) host drivers"
            echo "  --rtlsdr                       Configure RTL-SDR host setup"
            echo "  --hackrf                       Configure HackRF host drivers"
            echo "  --wifi                         Configure Wi-Fi capture host setup"
            echo "  --usrp-x300                    Configure USRP X300 Series host setup"
            echo "  --iqengine                     Configure IQ Engine Docker setup"
            echo "  --takserver                    Configure local TAK Server Docker setup"
            echo "  --xpra                        Configure Xpra remote GUI support on the host"
            echo "  -h, --help                     Show this help message and exit"
            exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
    shift
done

#############################################
#       Validate and normalize mode         #
#############################################
case "${MODE,,}" in
    full)
        MODE="full"
        ;;
    base)
        MODE="base"
        ;;
    custom)
        MODE="custom"
        ;;
    dashboard)
        MODE="Dashboard"
        ;;
    hiprfisr)
        MODE="HIPRFISR"
        ;;
    sensor|sensor-node|sensor_node|sensornode)
        MODE="SensorNode"
        ;;
    *)
        echo "[ERROR] Unsupported install mode: $MODE"
        echo "        Supported modes: full, base, custom, Dashboard, HIPRFISR, SensorNode"
        exit 1
        ;;
esac

echo "[*] FISSURE install mode: $MODE"

#############################################
# Verify FISSURE repo location
#############################################
if [ ! -d "$HOST_FISSURE_DIR/fissure" ]; then
    echo "[!] Could not find FISSURE source in $HOST_FISSURE_DIR"
    echo "    Please clone the repository first:"
    echo "    sudo git clone https://github.com/ainfosec/FISSURE.git /opt/FISSURE"
    exit 1
fi

echo "[*] Host FISSURE directory: $HOST_FISSURE_DIR"
echo "[*] Apptainer FISSURE directory: $APPTAINER_FISSURE_DIR"

#############################################
# Install Apptainer Software
#############################################
if command -v apptainer >/dev/null 2>&1 &&
   apptainer buildcfg 2>/dev/null |
   grep -q '^APPTAINER_SUID_INSTALL=1$'; then
    "$INSTALLER_DIR/install_apptainer_package.sh"
else
    sudo "$INSTALLER_DIR/install_apptainer_package.sh"
fi

#############################################
#          Host Preparation (optional)      #
#############################################
if $INSTALL_HOST_DEPS; then
    echo "[*] Preparing host environment for FISSURE on $HOST_OS..."

    # Check and Install pip3
    if command -v pip3 >/dev/null 2>&1; then
        echo "[✓] pip3 is already installed."
    else
        echo "[*] pip3 not found — installing..."
        sudo apt-get update
        sudo apt-get install -y python3-pip
        if command -v pip3 >/dev/null 2>&1; then
            echo "[✓] pip3 installed successfully."
        else
            echo "[!] pip3 installation failed. Please check your package sources."
        fi
    fi

    if [[ "$HOST_OS" == "Ubuntu 24.04" ]]; then
        # ---------- Auto-Launch Sensor Node ----------
        if $AUTO_LAUNCH_SENSOR_NODE; then
            bash "$INSTALLER_DIR/Host/desktop_autostart.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End Auto-Launch Sensor Node ----------

        # ---------- Meshtastic Host Setup ----------
        if $MESHTASTIC; then
            bash "$INSTALLER_DIR/Host/meshtastic.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End Meshtastic Host Setup ----------

        # ---------- PostgreSQL Host Setup ----------
        if $DB; then
            bash "$INSTALLER_DIR/Host/postgresql.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End PostgreSQL Host Setup ----------

        # ---------- UHD Host Setup ----------
        if $UHD; then
            bash "$INSTALLER_DIR/Host/uhd.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End UHD Host Setup ----------
        
        # ---------- RTL-SDR Host Setup ----------
        if $RTLSDR; then
            bash "$INSTALLER_DIR/Host/rtlsdr.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End RTL-SDR Host Setup ----------

        # ---------- HackRF Host Setup ----------
        if $HACKRF; then
            bash "$INSTALLER_DIR/Host/hackrf.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End HackRF Host Setup ----------

        # ---------- Wi-Fi Host Setup (rtl8812au via aircrack-ng) ----------
        if $WIFI; then
            bash "$INSTALLER_DIR/Host/wifi.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End Wi-Fi Host Setup ----------

        # ---------- USRP X300/X310 Host Setup ----------
        if $USRP_X300; then
            bash "$INSTALLER_DIR/Host/usrp_x300.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End USRP X300/X310 Host Setup ----------

        # ---------- IQEngine Host Setup ----------
        if $IQENGINE; then
            bash "$INSTALLER_DIR/Host/iqengine.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End IQEngine Host Setup ----------

        # ---------- TAK Server Setup ----------
        if $TAKSERVER; then
            bash "$INSTALLER_DIR/Host/takserver.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End TAK Server Setup ----------

        # ---------- Xpra Host Setup ----------
        if $XPRA; then
            bash "$INSTALLER_DIR/Host/xpra.sh" \
                "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$MODE" "$AUTO_LAUNCH_SENSOR_NODE"

        fi
        # ---------- End Xpra Host Setup ----------

        echo "[✓] Host preparation complete for Ubuntu 24.04."

    else
        echo "[!] Unsupported host OS: $HOST_OS"
    fi
fi

#############################################
#           Build the Apptainer             #
#############################################
if $BUILD_APPTAINER; then
    bash "$INSTALLER_DIR/Apptainer/build_local.sh" \
        "$INSTALLER_DIR" "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" \
        "$APPTAINER_OS" "$MODE" "$SANDBOX_DIR" "$DEF_FILE"

else
    echo "[!] No build flag provided. Use --build-apptainer to build the image."
fi

#############################################
#     Generate Host Network Certificates    #
#############################################
bash "$INSTALLER_DIR/Apptainer/certificates.sh" \
    "$HOST_FISSURE_DIR" "$APPTAINER_FISSURE_DIR" "$SANDBOX_DIR"

#############################################
#        Install fissure-apptainer Cmd       #
#############################################
if [[ "$INSTALL_FISSURE_CMD" == true ]]; then
    bash "$INSTALLER_DIR/Apptainer/launcher.sh" "$INSTALLER_DIR" "$HOST_FISSURE_DIR" "$MODE"

fi


echo "[✓] Done."
