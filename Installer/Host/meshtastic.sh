#!/bin/bash
prepare_meshtastic() {
    local host_user=$1
    host_install_packages python3-pip python3-serial python3-protobuf
    host_root python3 -m pip install 'meshtastic==2.6.4' --break-system-packages
    host_root usermod -aG dialout,tty "$host_user"
    printf '%s\n' 'SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666"' |
        host_root tee /etc/udev/rules.d/99-meshtastic.rules >/dev/null
    host_reload_udev
    echo "[✓] Meshtastic serial access prepared."
}
