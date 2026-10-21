#!/bin/bash
prepare_hackrf() {
    local source_root=$1
    local rules="$source_root/Tools/53-hackrf.rules"
    [[ -f "$rules" ]] || { host_fail "HackRF udev rules are missing: $rules"; return 1; }
    host_install_packages hackrf libhackrf-dev
    host_root install -m 0644 "$rules" /etc/udev/rules.d/53-hackrf.rules
    host_reload_udev
    command -v hackrf_info >/dev/null || { host_fail "hackrf_info is missing."; return 1; }
    # Installing support does not require a plugged-in radio.
    hackrf_info || echo "[i] HackRF detection failed; check power and USB connection."
}
