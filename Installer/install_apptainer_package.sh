#!/bin/bash
set -euo pipefail
APPTAINER_INSTALL_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$APPTAINER_INSTALL_DIR/Host/common.sh"
source "$APPTAINER_INSTALL_DIR/Host/apptainer_packages.sh"
source "$APPTAINER_INSTALL_DIR/Host/support_bundle.sh"

main() {
    local check_only=false offline=false bundle='' argument
    for argument in "$@"; do
        case "$argument" in
            --check-only) check_only=true ;;
            --offline) offline=true ;;
            --host-support=*) bundle=${argument#*=}; offline=true ;;
            *) host_fail "Unknown Apptainer installer option: $argument"; return 2 ;;
        esac
    done
    if [[ -n "$bundle" ]]; then
        bundle=$(realpath -- "$bundle")
        validate_support_bundle "$bundle"
    fi
    if has_setuid_support; then
        echo '[✓] Existing Apptainer installation has setuid support.'; return 0
    fi
    if $check_only; then host_fail 'Apptainer with setuid support is required.'; return 1; fi
    (( EUID == 0 )) || { host_fail 'Run the Apptainer package installer as root.'; return 1; }
    if $offline; then
        [[ -n "$bundle" ]] || { host_fail 'Offline installation requires --host-support.'; return 1; }
        install_apptainer_offline "$bundle"
    else
        validate_host_platform
        install_apptainer_online
    fi
    has_setuid_support || { host_fail 'Installation did not provide Apptainer setuid support.'; return 1; }
    echo "[✓] $(apptainer version)"
}

main "$@"
