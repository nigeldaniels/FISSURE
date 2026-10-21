#!/bin/bash
# Public installer contract: explicit feature names, never interactive selection.
HOST_RECIPE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$HOST_RECIPE_DIR/common.sh"
source "$HOST_RECIPE_DIR/uhd.sh"
source "$HOST_RECIPE_DIR/usrp_x300.sh"
source "$HOST_RECIPE_DIR/hackrf.sh"
source "$HOST_RECIPE_DIR/rtlsdr.sh"
source "$HOST_RECIPE_DIR/wifi.sh"
source "$HOST_RECIPE_DIR/meshtastic.sh"

validate_hardware() {
    local selection=$1 feature
    [[ -n "$selection" && "$selection" != *, && "$selection" != ,* && "$selection" != *,,* ]] || {
        host_fail "Hardware selection must be a comma-separated list or none."; return 1;
    }
    [[ "$selection" == none ]] && return 0
    local -a features
    IFS=, read -r -a features <<< "$selection"
    for feature in "${features[@]}"; do
        case "$feature" in
            uhd|usrp-x300|hackrf|rtlsdr|wifi|meshtastic) ;;
            *) host_fail "Unsupported hardware: $feature"; return 1 ;;
        esac
    done
}

prepare_hardware() {
    local selection=$1 host_user=$2 source_root=$3
    validate_hardware "$selection"
    [[ "$selection" == none ]] && return 0
    # Refresh once per run; individual recipes reuse installed packages.
    if [[ "$selection" != rtlsdr ]]; then host_root apt-get update; fi
    if [[ ",$selection," == *,uhd,* || ",$selection," == *,usrp-x300,* ]]; then
        prepare_uhd "$host_user"
    fi
    if [[ ",$selection," == *,usrp-x300,* ]]; then prepare_usrp_x300; fi
    if [[ ",$selection," == *,hackrf,* ]]; then prepare_hackrf "$source_root"; fi
    if [[ ",$selection," == *,rtlsdr,* ]]; then prepare_rtlsdr; fi
    if [[ ",$selection," == *,wifi,* ]]; then prepare_wifi "$host_user"; fi
    if [[ ",$selection," == *,meshtastic,* ]]; then prepare_meshtastic "$host_user"; fi
}
