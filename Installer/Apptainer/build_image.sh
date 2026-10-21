#!/bin/bash
# Both builders supply a rendered definition; recipe selection stays with callers.
set -euo pipefail

main() {
    local format=${1:?image format required} output=${2:?output required}
    local definition=${3:?definition required} mode=${4:-root} binary=${5:-apptainer}
    local -a options=(build)
    case "$format" in
        sif) options+=(--force) ;;
        sandbox) options+=(--sandbox) ;;
        *) echo "Unsupported image format: $format" >&2; return 2 ;;
    esac
    case "$mode" in
        fakeroot) options+=(--fakeroot) ;;
        root) ;;
        *) echo "Unsupported build privilege: $mode" >&2; return 2 ;;
    esac
    test -f "$definition" || { echo "Missing definition: $definition" >&2; return 2; }
    command -v "$binary" >/dev/null || { echo "Apptainer is unavailable" >&2; return 1; }
    # exec preserves Apptainer's exit status and forwards interruption directly.
    exec "$binary" "${options[@]}" "$output" "$definition"
}

main "$@"
