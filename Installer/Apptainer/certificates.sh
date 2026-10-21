#!/bin/bash
set -e

HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
SANDBOX_DIR=$3

CERT_DIR="$HOST_FISSURE_DIR/certificates"

if [ ! -f "$CERT_DIR/server/server.key" ] ||
   [ ! -f "$CERT_DIR/server/server.key_secret" ] ||
   [ ! -f "$CERT_DIR/clients/client_0.key" ] ||
   [ ! -f "$CERT_DIR/clients/client_0.key_secret" ]; then

    echo "[*] Generating FISSURE network certificates in the host checkout..."

    apptainer exec \
        --bind "$HOST_FISSURE_DIR:$APPTAINER_FISSURE_DIR" \
        --env PYTHONPATH="$APPTAINER_FISSURE_DIR" \
        "$SANDBOX_DIR" \
        bash -c "
            cd '$APPTAINER_FISSURE_DIR'
            python3 ./fissure/generate_certificates.py
        "

    ########## Verify ##########
    test -f "$CERT_DIR/server/server.key" &&
    test -f "$CERT_DIR/server/server.key_secret" &&
    test -f "$CERT_DIR/clients/client_0.key" &&
    test -f "$CERT_DIR/clients/client_0.key_secret"

    echo "[✓] FISSURE network certificates generated in $CERT_DIR"
else
    echo "[✓] Existing FISSURE network certificates found in $CERT_DIR"
fi
