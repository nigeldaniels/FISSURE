#!/bin/bash
# UHD software and USB access are shared by B2xx and X3xx preparation.
prepare_uhd() {
    local host_user=$1 rules=''
    host_install_packages uhd-host
    for rules in /usr/lib/uhd/utils/uhd-usrp.rules /usr/share/uhd/utils/uhd-usrp.rules; do
        if [[ -f "$rules" ]]; then break; fi
    done
    [[ -f "$rules" ]] || { host_fail "UHD udev rules are missing."; return 1; }
    host_root install -m 0644 "$rules" /etc/udev/rules.d/uhd-usrp.rules
    if ! getent group plugdev >/dev/null; then host_root groupadd plugdev; fi
    host_root usermod -aG plugdev "$host_user"
    host_reload_udev
    # Run as root rather than making the firmware directory world-writable.
    if command -v uhd_images_downloader >/dev/null; then
        host_root uhd_images_downloader
    elif [[ -x /usr/lib/uhd/utils/uhd_images_downloader.py ]]; then
        host_root /usr/lib/uhd/utils/uhd_images_downloader.py
    else
        host_fail "UHD image downloader is missing."; return 1
    fi
    echo "[✓] UHD host support prepared; reconnect USB radios if necessary."
}
