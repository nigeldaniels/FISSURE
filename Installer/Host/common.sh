#!/bin/bash
# Shared primitives for the Ubuntu host recipes. Sourcing performs no installation.
host_root() {
    if (( EUID == 0 )); then "$@"; else sudo -- "$@"; fi
}

host_fail() { echo "[!] $*" >&2; return 1; }

validate_host_platform() {
    local ID='' VERSION_ID=''
    source /etc/os-release
    [[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || {
        host_fail "Host preparation supports Ubuntu 24.04."; return 1;
    }
    case "$(dpkg --print-architecture)" in
        amd64|arm64) ;;
        *) host_fail "Host preparation supports amd64 and arm64."; return 1 ;;
    esac
}

host_install_packages() {
    local package
    local -a missing=()
    for package in "$@"; do
        if [[ $(dpkg-query -W -f '${Status}' "$package" 2>/dev/null) != 'install ok installed' ]]; then
            missing+=("$package")
        fi
    done
    if (( ${#missing[@]} )); then
        host_root env DEBIAN_FRONTEND=noninteractive apt-get install --no-remove -y "${missing[@]}"
    fi
}

host_reload_udev() {
    host_root udevadm control --reload-rules
    host_root udevadm trigger
}
