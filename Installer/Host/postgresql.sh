#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

echo "[*] Installing PostgreSQL host dependencies and Docker components..."
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 postgresql-client libpq-dev python3-pip
sudo python3 -m pip install python-dotenv psycopg2 --break-system-packages
sudo usermod -aG docker ${USER}

echo "[*] Ensuring example.env exists and starting PostgreSQL container..."
cd "$HOST_FISSURE_DIR"
if [ ! -f .env ]; then
    cp example.env .env
fi

bash -c '
    set -e
    set -o allexport
    source .env
    set +o allexport
    export PGPASSWORD=$POSTGRES_PASSWORD
    echo "[*] Starting PostgreSQL container..."
    sudo docker compose up -d
    until pg_isready -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_EXTERNAL_PORT"; do
        echo "Waiting for PostgreSQL to be ready..."
        sleep 2
    done
    echo "[*] Restoring FISSURE database..."
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" -h "$POSTGRES_HOST" -p "$POSTGRES_EXTERNAL_PORT" -v db/fissure_db_dump.sql
    echo "[*] Verifying connection..."
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -h "$POSTGRES_HOST" -p "$POSTGRES_EXTERNAL_PORT" \
         -c "SELECT COUNT(*) FROM pg_tables;"
'

echo "[✓] PostgreSQL host setup complete."
