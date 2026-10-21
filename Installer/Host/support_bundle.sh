#!/bin/bash
# Bundle metadata is data: it is checked and never sourced as shell code.
validate_support_bundle() {
    local bundle=$1 architecture
    validate_host_platform
    [[ -d "$bundle/packages" && -f "$bundle/SHA256SUMS" && -f "$bundle/bundle.info"
        && -f "$bundle/Packages" && -f "$bundle/package-versions.txt" ]] || {
        host_fail "Incomplete host-support bundle: $bundle"; return 1;
    }
    [[ -z $(find "$bundle" ! -type f ! -type d -print -quit) ]] || {
        host_fail "Host-support bundles may contain only regular files and directories."; return 1;
    }
    validate_bundle_checksums "$bundle"
    architecture=$(dpkg --print-architecture)
    local expected
    expected=$(printf 'format=1\nos=ubuntu\nversion=24.04\narchitecture=%s\n' "$architecture")
    [[ $(cat "$bundle/bundle.info") == "$expected" ]] || {
        host_fail "Bundle format, OS, or architecture does not match this host."; return 1;
    }
    validate_bundle_packages "$bundle" "$architecture"
}

validate_bundle_checksums() {
    local bundle=$1 line
    local pattern='^[0-9a-f]{64}  (bundle.info|Packages|package-versions.txt|packages/[A-Za-z0-9._+%:~\-]+\.deb)$'
    while IFS= read -r line; do
        [[ "$line" =~ $pattern ]] || { host_fail "Invalid bundle checksum entry."; return 1; }
    done < "$bundle/SHA256SUMS"
    # Require exactly one checksum for every payload file, including the index.
    diff -u <(cd "$bundle"; find . -type f ! -path './SHA256SUMS' -printf '%P\n' | LC_ALL=C sort) \
        <(sed 's/^[^ ]*  //' "$bundle/SHA256SUMS" | LC_ALL=C sort) || {
        host_fail "Bundle file inventory does not match its checksums."; return 1;
    }
    (cd "$bundle"; sha256sum --check --strict SHA256SUMS) || {
        host_fail "Host-support bundle checksum failure."; return 1;
    }
}

validate_bundle_packages() {
    local bundle=$1 architecture=$2 package package_arch has_apptainer=false
    local -a packages=("$bundle"/packages/*.deb)
    [[ -f "${packages[0]}" ]] || { host_fail "Bundle contains no Debian packages."; return 1; }
    for package in "${packages[@]}"; do
        package_arch=$(dpkg-deb -f "$package" Architecture)
        [[ "$package_arch" == all || "$package_arch" == "$architecture" ]] || {
            host_fail "Wrong package architecture: $package"; return 1;
        }
        if [[ $(dpkg-deb -f "$package" Package) == "$APPTAINER_PACKAGE" ]]; then has_apptainer=true; fi
    done
    $has_apptainer || { host_fail "Bundle is missing $APPTAINER_PACKAGE."; return 1; }
    # A malformed local index must not introduce a network URL or escape its root.
    awk '/^Filename: / && $2 !~ /^\.?\/packages\/[A-Za-z0-9._+%:~\-]+\.deb$/ {exit 1}' \
        "$bundle/Packages" || { host_fail "Invalid package index path."; return 1; }
}

prepare_offline_apt() {
    local bundle=$1 workspace=$2
    write_isolated_apt_config "$workspace" /var/lib/dpkg/status
    # The private link provides an APT URI without spaces regardless of input path.
    ln -s "$bundle" "$workspace/repository"
    printf 'deb [trusted=yes] file:%s/repository ./\n' "$workspace" > "$workspace/sources.list"
    # Trust applies only to this operator-supplied, checksum-verified local source.
    isolated_apt "$workspace" update
    isolated_apt "$workspace" --simulate --no-remove install "$APPTAINER_PACKAGE"
}

install_apptainer_offline() (
    set -euo pipefail
    local bundle=$1 workspace
    # The package entrypoint validates the bundle before selecting this path.
    workspace=$(mktemp -d /tmp/fissure-offline-apt.XXXXXXXX)
    trap 'rm -rf -- "$workspace"' EXIT
    prepare_offline_apt "$bundle" "$workspace"
    # Populate the private cache from file: only, then forbid any acquisition
    # during installation. Host HTTP sources and apt hooks are not loaded.
    isolated_apt "$workspace" --download-only --no-remove -y install "$APPTAINER_PACKAGE"
    isolated_apt "$workspace" --no-download --no-remove -y install "$APPTAINER_PACKAGE"
    has_setuid_support || { host_fail "Offline installation did not provide Apptainer setuid support."; return 1; }
)

publish_support_bundle() (
    set -euo pipefail
    local source=$1 output=$2 pending
    mkdir -p -- "$(dirname -- "$output")"
    # Publish by rename on the destination filesystem, including when /tmp is
    # a different mount. An interrupted copy must not look like a ready bundle.
    pending=$(mktemp -d "$(dirname -- "$output")/.fissure-support.XXXXXXXX")
    trap 'rm -rf -- "$pending"' EXIT
    cp -a -- "$source/." "$pending/"
    chmod 0755 "$pending"
    mv -T -n -- "$pending" "$output"
    [[ ! -e "$pending" ]] || { host_fail 'Output appeared while building; not replacing it.'; return 1; }
)
