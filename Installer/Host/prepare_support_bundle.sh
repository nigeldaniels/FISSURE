#!/bin/bash
set -euo pipefail
SUPPORT_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$SUPPORT_SCRIPT_DIR/common.sh"
source "$SUPPORT_SCRIPT_DIR/apptainer_packages.sh"
source "$SUPPORT_SCRIPT_DIR/support_bundle.sh"

main() (
    local output='' argument workspace architecture
    for argument in "$@"; do
        case "$argument" in
            --output=*) output=${argument#*=} ;;
            --help|-h) echo 'Usage: prepare_support_bundle.sh --output=DIRECTORY'; return 0 ;;
            *) host_fail "Unknown bundle option: $argument"; return 2 ;;
        esac
    done
    [[ -n "$output" && ! -e "$output" ]] || { host_fail 'Use a new --output directory.'; return 2; }
    validate_host_platform
    for argument in apt-get curl gpg dpkg-deb dpkg-scanpackages sha256sum; do
        command -v "$argument" >/dev/null || { host_fail "Required tool missing: $argument"; return 1; }
    done
    architecture=$(dpkg --print-architecture)
    workspace=$(mktemp -d /tmp/fissure-support-build.XXXXXXXX)
    trap 'rm -rf -- "$workspace"' EXIT
    # An empty status database includes dependencies already installed on the
    # producer, preventing incomplete bundles built on well-equipped workstations.
    touch "$workspace/status"
    write_isolated_apt_config "$workspace" "$workspace/status"
    write_download_sources "$workspace" "$architecture"
    isolated_apt "$workspace" update
    isolated_apt "$workspace" --download-only --no-remove -y install "$APPTAINER_PACKAGE"
    assemble_support_bundle "$workspace" "$architecture"
    publish_support_bundle "$workspace/bundle" "$output"
    echo "[✓] Offline Apptainer host support written to $output"
)

assemble_support_bundle() {
    local workspace=$1 architecture=$2 package
    mkdir -p "$workspace/bundle/packages"
    mv "$workspace"/archives/*.deb "$workspace/bundle/packages/"
    (
        cd "$workspace/bundle"
        printf 'format=1\nos=ubuntu\nversion=24.04\narchitecture=%s\n' "$architecture" > bundle.info
        dpkg-scanpackages packages /dev/null > Packages
        # dpkg-scanpackages emits packages/foo.deb; make paths explicit for validation.
        sed -i 's|^Filename: packages/|Filename: ./packages/|' Packages
        for package in packages/*.deb; do
            dpkg-deb -f "$package" Package Version Architecture
        done > package-versions.txt
        find . -type f ! -name SHA256SUMS -printf '%P\0' | LC_ALL=C sort -z |
            xargs -0 sha256sum > SHA256SUMS
    )
}

main "$@"
