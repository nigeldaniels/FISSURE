#!/bin/bash
set -e

# Extracted local installer recipe; arguments replace caller-owned shell state.
HOST_FISSURE_DIR=$1
APPTAINER_FISSURE_DIR=$2
MODE=$3
AUTO_LAUNCH_SENSOR_NODE=$4

# Create TAK.gov account and download TAKSERVER-DOCKER-#.#-RELEASE-##.ZIP from https://tak.gov/products/tak-server
# Place ZIP file in ~/Installed_by_FISSURE folder and then run this installer item!

if command -v docker > /dev/null 2>&1; then
    echo "Docker is installed."
else
    echo "Docker is not installed."
    sudo apt-get install -y docker.io
    #sudo systemctl start docker
    #sudo systemctl enable docker
    sudo usermod -aG docker ${USER}  # Reboot computer to use docker commands without sudo
    #newgrp docker
fi

mkdir -p ~/Installed_by_FISSURE
cd ~/Installed_by_FISSURE

# Unzip and move into the extracted directory
unzip takserver-docker-*.zip
if [ -n "$(find . -maxdepth 1 -type d -name 'takserver-docker-*' -print -quit)" ]; then
    cd takserver-docker-*/

    # Ensure CoreConfig.xml exists
    [ ! -f tak/CoreConfig.xml ] && cp tak/CoreConfig.example.xml tak/CoreConfig.xml

    # Set database password
    sed -i 's/password=""/password="atakatak"/' tak/CoreConfig.xml

    # Build and start the database
    sudo docker build -t takserver-db:"$(cat tak/version.txt)" -f docker/Dockerfile.takserver-db .
    sudo docker network create takserver-"$(cat tak/version.txt)"

    # Set executable permissions for necessary scripts
    chmod +x tak/db-utils/configureInDocker.sh
    chmod +x tak/certs/makeRootCa.sh
    chmod +x tak/certs/makeCert.sh

    sudo docker run -d \
        -v $(pwd)/tak:/opt/tak:z \
        -p 5432:5432 \
        --network takserver-"$(cat tak/version.txt)" \
        --network-alias tak-database \
        --name takserver-db-"$(cat tak/version.txt)" \
        takserver-db:"$(cat tak/version.txt)"

    # Wait for the database to be fully ready
    echo "Waiting for PostgreSQL to be ready..."
    until sudo docker exec takserver-db-"$(cat tak/version.txt)" psql -U martiuser -d cot -c "SELECT 1;" &>/dev/null; do
        sleep 3
        echo "Waiting for database..."
    done
    echo "Database is ready!"

    # Build and start TAK Server
    sudo docker build -t takserver:"$(cat tak/version.txt)" -f docker/Dockerfile.takserver .
    sudo docker run -d \
        -v $(pwd)/tak:/opt/tak:z \
        -p 8089:8089 -p 8443:8443 -p 8444:8444 -p 8446:8446 -p 9000:9000 -p 9001:9001 \
        --network takserver-"$(cat tak/version.txt)" \
        --name takserver-"$(cat tak/version.txt)" \
        takserver:"$(cat tak/version.txt)"

    # Modify certificate metadata
    sed -i 's/^STATE=.*/STATE="test_state"/' tak/certs/cert-metadata.sh
    sed -i 's/^CITY=.*/CITY="test_city"/' tak/certs/cert-metadata.sh
    sed -i 's/^ORGANIZATIONAL_UNIT=.*/ORGANIZATIONAL_UNIT="test_organization"/' tak/certs/cert-metadata.sh
    sed -i 's/^ORGANIZATION=.*/ORGANIZATION="test_org"/' tak/certs/cert-metadata.sh

    # Generate Root CA
    sudo docker exec takserver-"$(cat tak/version.txt)" bash -c "cd /opt/tak/certs && ./makeRootCa.sh"

    # Ensure CA certificate exists before continuing
    sudo docker exec takserver-"$(cat tak/version.txt)" bash -c "test -f /opt/tak/certs/files/ca.pem || (echo 'CA generation failed!' && exit 1)"

    # Generate Certificates
    sudo docker exec takserver-"$(cat tak/version.txt)" bash -c "cd /opt/tak/certs && ./makeCert.sh server takserver"
    sudo docker exec takserver-"$(cat tak/version.txt)" bash -c "cd /opt/tak/certs && ./makeCert.sh client admin"
    sudo docker exec takserver-"$(cat tak/version.txt)" bash -c "cd /opt/tak/certs && ./makeCert.sh client webadmin"

    # Ensure directories have correct permissions
    sudo find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -type d -exec chmod 755 {} +

    sudo openssl rsa -in "$(find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -name 'takserver.key' | head -n 1)" \
        -out "$(find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -type d | head -n 1)/takserver.key.unencrypted" \
        -passin pass:"atakatak"

    sudo mv "$(ls -d ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files | head -n 1)/takserver.key.unencrypted" \
        "$(ls -d ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files | head -n 1)/takserver.key"

    # Set ownership for all certificate-related files to the current user
    sudo find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -type f -exec chown $USER:$USER {} +
    sudo find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -type d -exec chown $USER:$USER {} +

    # Set proper permissions for private keys
    sudo find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -type f -name "*.key" -exec chmod 644 {} +

    # Set correct permissions for other certificate files
    sudo find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -type f -not -name "*.key" -exec chmod 644 {} +

    # Restart TAK Server to apply changes
    sudo docker restart takserver-"$(cat tak/version.txt)"

    # Copy takserver.key and takserver.pem to FISSURE Config Files
    cd """ + fissure_directory + """
    PYTHONPATH=""" + fissure_directory + """ python3 fissure/utils/tak_yaml_key_insert.py \
    "$(find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -name 'takserver.key' | head -n 1)" \
    "$(find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -name 'takserver.pem' | head -n 1)" \
    "$(find ~/Installed_by_FISSURE/takserver-docker-*/tak/certs/files/ -name 'webadmin.p12' | head -n 1)" \
    "$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' takserver-5.3-RELEASE-24)"

    # Install pytak library
    python3 -m pip install pytak --break-system-packages

    # Import webadmin.p12:

    # Google Chrome/Edge
    # Open chrome://settings/certificates in your browser.
    # Go to the "Your certificates" tab.
    # Click "Import".
    # Select /home/cups-pk-helper/webadmin.p12.
    # Enter the password (default: atakatak, unless changed).
    # Complete the import and restart your browser.

    # Mozilla Firefox
    # Open about:preferences#privacy in the Firefox address bar.
    # Scroll down to Certificates and click "View Certificates".
    # Go to the "Your Certificates" tab.
    # Click "Import".
    # Select /home/cups-pk-helper/webadmin.p12 and enter the password (atakatak).
    # Restart Firefox.

    # To Remove TAK:
    # docker ps -a | grep takserver
    # docker rm -f $(docker ps -aq --filter "name=takserver")
    # docker rm -f $(docker ps -aq --filter "name=takserver-db")
    # docker ps -a
    # docker images | grep takserver
    # docker rmi -f $(docker images -q takserver)
    # docker rmi -f $(docker images -q takserver-db)
    # docker images
    # docker network ls | grep takserver
    # docker network rm $(docker network ls --filter "name=takserver" -q)
    # sudo rm -rf ~/Installed_by_FISSURE/takserver-docker-*/

    echo ""
    echo "TAK Server setup complete! Import webadmin.p12 certificate via browser. Access WebTAK at https://localhost:8443"
    echo ""
else
    echo "TAK Server zip extraction failed or extracted folder not found. Exiting."
fi
