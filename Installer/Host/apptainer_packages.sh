#!/bin/bash
# The online installer and offline producer share the package/source choice.
APPTAINER_PACKAGE=apptainer-suid
APPTAINER_PPA=ppa:apptainer/ppa
APPTAINER_PPA_URL=https://ppa.launchpadcontent.net/apptainer/ppa/ubuntu
# Published by https://api.launchpad.net/1.0/~apptainer/+archive/ubuntu/ppa
APPTAINER_SIGNING_KEY=F6B0F5193D4F3301EF491FF0AFE36534FC6218AE

has_setuid_support() {
    command -v apptainer >/dev/null 2>&1 &&
        apptainer buildcfg 2>/dev/null | grep '^APPTAINER_SUID_INSTALL=1$' >/dev/null
}

install_apptainer_online() {
    echo "[*] Installing Apptainer from the official Ubuntu PPA..."
    apt-get update
    env DEBIAN_FRONTEND=noninteractive apt-get install -y software-properties-common
    if ! grep -Rqs 'ppa.launchpadcontent.net/apptainer/ppa' \
        /etc/apt/sources.list /etc/apt/sources.list.d 2>/dev/null; then
        add-apt-repository -y "$APPTAINER_PPA"
    fi
    apt-get update
    env DEBIAN_FRONTEND=noninteractive apt-get install --no-remove -y "$APPTAINER_PACKAGE"
}

write_isolated_apt_config() {
    local workspace=$1 status_file=$2
    mkdir -p "$workspace/lists/partial" "$workspace/archives/partial" "$workspace/empty"
    touch "$workspace/empty.conf"
    # Do not inherit host sources, hooks, caches, or package preferences.
    cat > "$workspace/apt.conf" <<EOF
Dir::Etc::main "$workspace/empty.conf";
Dir::Etc::parts "$workspace/empty";
Dir::Etc::sourcelist "$workspace/sources.list";
Dir::Etc::sourceparts "$workspace/empty";
Dir::Etc::preferences "$workspace/empty.conf";
Dir::Etc::preferencesparts "$workspace/empty";
Dir::State::lists "$workspace/lists";
Dir::State::status "$status_file";
Dir::State::extended_states "$workspace/extended_states";
Dir::Cache::archives "$workspace/archives";
Dir::Cache::pkgcache "";
Dir::Cache::srcpkgcache "";
Dir::Log "$workspace";
APT::Sandbox::User "$(id -un)";
Acquire::Retries "2";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
EOF
}

isolated_apt() {
    local workspace=$1
    shift
    APT_CONFIG="$workspace/apt.conf" DEBIAN_FRONTEND=noninteractive apt-get "$@"
}

write_download_sources() {
    local workspace=$1 architecture=$2 archive_url key_fingerprint
    archive_url=https://archive.ubuntu.com/ubuntu
    [[ "$architecture" != arm64 ]] || archive_url=https://ports.ubuntu.com/ubuntu-ports
    curl --fail --silent --show-error --location --retry 2 --connect-timeout 10 --max-time 60 \
        "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$APPTAINER_SIGNING_KEY" \
        -o "$workspace/apptainer.asc"
    key_fingerprint=$(gpg --batch --no-options --homedir "$workspace" --with-colons \
        --show-keys "$workspace/apptainer.asc" | awk -F: '$1=="fpr" {print $10; exit}')
    [[ "$key_fingerprint" == "$APPTAINER_SIGNING_KEY" ]] || {
        echo 'Apptainer PPA signing key mismatch.' >&2; return 1;
    }
    gpg --batch --yes --dearmor -o "$workspace/apptainer.gpg" "$workspace/apptainer.asc"
    : > "$workspace/sources.list"
    local suite
    for suite in noble noble-updates noble-security; do
        printf 'deb [arch=%s signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] %s %s main universe\n' \
            "$architecture" "$archive_url" "$suite" >> "$workspace/sources.list"
    done
    printf 'deb [arch=%s signed-by=%s/apptainer.gpg] %s noble main\n' \
        "$architecture" "$workspace" "$APPTAINER_PPA_URL" >> "$workspace/sources.list"
}
