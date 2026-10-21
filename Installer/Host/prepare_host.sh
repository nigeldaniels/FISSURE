#!/bin/bash
set -euo pipefail
HOST_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$HOST_SCRIPT_DIR/hardware.sh"

main() {
    local hardware=none host_user=${SUDO_USER:-$(id -un)}
    local source_root check_only=false allow_install=true offline=false bundle=""
    local -a package_options=()
    source_root=$(cd "$HOST_SCRIPT_DIR/../.." && pwd)
    for argument in "$@"; do
        case "$argument" in
            --hardware=*) hardware=${argument#*=} ;;
            --user=*) host_user=${argument#*=} ;;
            --source-root=*) source_root=${argument#*=} ;;
            --offline) offline=true ;;
            --host-support=*) bundle=${argument#*=}; offline=true ;;
            --check-only) check_only=true ;;
            --no-install-apptainer) allow_install=false ;;
            --help|-h) show_help; return 0 ;;
            *) host_fail "Unknown host preparation option: $argument"; return 2 ;;
        esac
    done
    validate_hardware "$hardware"
    if $offline && [[ "$hardware" != none ]]; then
        host_fail "Offline hardware preparation is not supported yet; use --hardware=none."; return 2
    fi
    if $check_only && [[ -n "$bundle" ]]; then
        host_fail "--check-only cannot consume a host-support bundle."; return 2
    fi
    $offline && package_options+=(--offline)
    if [[ -n "$bundle" ]]; then package_options+=("--host-support=$bundle"); fi
    if $check_only && [[ "$hardware" != none ]]; then
        host_fail "--check-only cannot select hardware."; return 2
    fi
    id -- "$host_user" >/dev/null || { host_fail "Unknown host user: $host_user"; return 2; }
    if [[ ",$hardware," == *,hackrf,* && ! -f "$source_root/Tools/53-hackrf.rules" ]]; then
        host_fail "HackRF udev rules are missing from source-root."; return 2
    fi
    if $check_only || ! $allow_install; then
        bash "$HOST_SCRIPT_DIR/../install_apptainer_package.sh" --check-only "${package_options[@]}"
    else
        validate_host_platform
        host_root bash "$HOST_SCRIPT_DIR/../install_apptainer_package.sh" "${package_options[@]}"
    fi
    if ! $check_only && [[ "$hardware" != none ]]; then
        validate_host_platform
        prepare_hardware "$hardware" "$host_user" "$source_root"
    fi
    echo "[✓] Host prerequisites passed for $host_user."
}

show_help() {
    echo "Usage: prepare_host.sh [--hardware=uhd,usrp-x300,hackrf,rtlsdr,wifi,meshtastic|none]"
    echo "                       [--user=USER] [--source-root=PATH]"
    echo "                       [--no-install-apptainer] [--check-only]"
    echo "                       [--offline] [--host-support=DIRECTORY]"
}

main "$@"
