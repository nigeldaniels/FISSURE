#!/bin/bash
prepare_wifi() {
    local host_user=$1 home_dir source_dir
    home_dir=$(getent passwd "$host_user" | cut -d: -f6)
    [[ "$home_dir" == /* ]] || { host_fail "Cannot resolve home for $host_user"; return 1; }
    source_dir="$home_dir/Installed_by_FISSURE/rtl8812au"
    host_install_packages dkms git build-essential "linux-headers-$(uname -r)"
    host_root mkdir -p "$(dirname "$source_dir")"
    if [[ ! -d "$source_dir/.git" ]]; then
        host_root git clone https://github.com/aircrack-ng/rtl8812au "$source_dir"
    fi
    # Use the existing driver recipe, leaving working installations in place.
    if ! dkms status | grep -Eq '^(rtl)?8812au[/,].*: installed'; then
        host_root make -C "$source_dir" dkms_install
    fi
    host_root modprobe 8812au
    echo "[✓] rtl8812au Wi-Fi host support prepared."
}
