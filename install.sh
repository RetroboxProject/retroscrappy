#!/usr/bin/env bash
# Install Retroscrappy without the distribution's package manager.
#
# Meant for immutable systems (Fedora Atomic, SteamOS, Bazzite...) and any
# distribution without the .deb/.rpm dependencies. Everything goes into a
# private Python virtual environment, so the system Python is not touched.
#
#   ./install.sh                     install for the current user (~/.local)
#   sudo ./install.sh --system       install for all users (/opt/retroscrappy)
#   ./install.sh --version v0.4.0    install a given release
#   ./install.sh --ref main          install a branch or commit
#   ./install.sh --no-gui            command line only (skips PySide6)
#   ./install.sh --uninstall         remove a previous install.sh installation
#
# Run it from a clone to install that working tree, or on its own
# (curl ... | bash -s -- [options]) to download the latest release.
set -euo pipefail

readonly APP_NAME="retroscrappy"
readonly APP_ID="io.github.retroboxproject.retroscrappy"
readonly REPO="RetroboxProject/retroscrappy"
readonly MIN_PYTHON="3.11"
readonly MARKER=".installed-by-install-sh"

SCOPE=""
REF=""
WITH_GUI=1
ACTION="install"
WORK_DIR=""
SOURCE_DIR=""

log() {
    local tag="$1"
    shift
    printf '%s %s %s\n' "${tag}" "$(date '+%Y-%m-%d_%H:%M:%S')" "$*" >&2
}
log_info() { log "[INFO]" "$@"; }
log_ok() { log "[ OK ]" "$@"; }
log_warn() { log "[WARN]" "$@"; }
log_error() { log "[ERR ]" "$@"; }

die() {
    log_error "$@"
    exit 1
}

cleanup() {
    if [[ -n "${WORK_DIR}" && -d "${WORK_DIR}" ]]; then
        rm -rf "${WORK_DIR}"
    fi
}
trap cleanup EXIT

usage() {
    sed -n '2,17s/^# \{0,1\}//p' "${BASH_SOURCE[0]}" 2> /dev/null \
        || echo "Usage: install.sh [--user|--system] [--version TAG|--ref REF] [--no-gui] [--uninstall]"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --user) SCOPE="user" ;;
            --system) SCOPE="system" ;;
            --version | --ref)
                [[ $# -ge 2 ]] || die "$1 needs a value"
                REF="$2"
                shift
                ;;
            --no-gui) WITH_GUI=0 ;;
            --uninstall) ACTION="uninstall" ;;
            -h | --help)
                usage
                exit 0
                ;;
            *) die "Unknown option: $1 (see --help)" ;;
        esac
        shift
    done
    if [[ -z "${SCOPE}" ]]; then
        if [[ "${EUID}" -eq 0 ]]; then SCOPE="system"; else SCOPE="user"; fi
    fi
    if [[ "${SCOPE}" == "system" && "${EUID}" -ne 0 ]]; then
        die "--system needs root (run it with sudo)"
    fi
}

set_paths() {
    if [[ "${SCOPE}" == "system" ]]; then
        PREFIX="/opt/${APP_NAME}"
        BIN_DIR="/usr/local/bin"
        SHARE_DIR="/usr/local/share"
    else
        local data_home="${XDG_DATA_HOME:-${HOME}/.local/share}"
        PREFIX="${data_home}/${APP_NAME}"
        BIN_DIR="${HOME}/.local/bin"
        SHARE_DIR="${data_home}"
    fi
    readonly PREFIX BIN_DIR SHARE_DIR
    readonly MANIFEST="${PREFIX}/${MARKER}"
}

find_python() {
    local candidate
    for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
        if command -v "${candidate}" > /dev/null 2>&1 \
            && "${candidate}" -c "import sys; sys.exit(sys.version_info < (${MIN_PYTHON/./, }))" \
            && "${candidate}" -c "import venv, ensurepip" > /dev/null 2>&1; then
            command -v "${candidate}"
            return 0
        fi
    done
    return 1
}

# Set SOURCE_DIR to a source tree: this clone, or a downloaded archive.
fetch_source() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2> /dev/null && pwd)" || here=""
    if [[ -z "${REF}" && -n "${here}" && -f "${here}/pyproject.toml" \
        && -d "${here}/src/${APP_NAME}" ]]; then
        log_info "Installing from the local tree ${here}"
        SOURCE_DIR="${here}"
        return 0
    fi
    command -v curl > /dev/null || die "curl is needed to download ${APP_NAME}"
    command -v tar > /dev/null || die "tar is needed to unpack ${APP_NAME}"

    local ref="${REF}" url
    if [[ -z "${ref}" ]]; then
        ref="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" 2> /dev/null \
            | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1 || true)"
        if [[ -z "${ref}" ]]; then
            log_warn "No published release found; using the main branch"
            ref="main"
        fi
    fi
    url="https://github.com/${REPO}/archive/${ref}.tar.gz"
    WORK_DIR="$(mktemp -d)"
    log_info "Downloading ${ref}"
    curl -fsSL "${url}" | tar -xz -C "${WORK_DIR}" || die "Cannot download ${url}"
    SOURCE_DIR="$(find "${WORK_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [[ -f "${SOURCE_DIR}/pyproject.toml" ]] || die "Unexpected archive layout in ${url}"
}

record() {
    printf '%s\n' "$1" >> "${MANIFEST}"
}

install_desktop_files() {
    local src="$1" apps="${SHARE_DIR}/applications" icons="${SHARE_DIR}/icons/hicolor"
    mkdir -p "${apps}" "${SHARE_DIR}/metainfo"

    sed "s|^Exec=.*|Exec=${PREFIX}/venv/bin/${APP_NAME}-gui|" \
        "${src}/packaging/linux/${APP_ID}.desktop" > "${apps}/${APP_ID}.desktop"
    record "${apps}/${APP_ID}.desktop"
    install -m 0644 "${src}/packaging/linux/${APP_ID}.metainfo.xml" "${SHARE_DIR}/metainfo/"
    record "${SHARE_DIR}/metainfo/${APP_ID}.metainfo.xml"

    local icon rel
    while IFS= read -r -d '' icon; do
        rel="${icon#"${src}/packaging/linux/icons/hicolor/"}"
        install -D -m 0644 "${icon}" "${icons}/${rel}"
        record "${icons}/${rel}"
    done < <(find "${src}/packaging/linux/icons/hicolor" -type f -print0)

    refresh_desktop_caches
}

refresh_desktop_caches() {
    if command -v gtk-update-icon-cache > /dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f "${SHARE_DIR}/icons/hicolor" 2> /dev/null || true
    fi
    if command -v update-desktop-database > /dev/null 2>&1; then
        update-desktop-database -q "${SHARE_DIR}/applications" 2> /dev/null || true
    fi
}

do_install() {
    if [[ -d "${PREFIX}" && ! -f "${MANIFEST}" ]]; then
        die "${PREFIX} exists but was not created by install.sh (a .deb/.rpm package?)"
    fi
    local python src extra=""
    python="$(find_python)" \
        || die "Python >= ${MIN_PYTHON} with the venv module is required (python3-venv on Debian)"
    fetch_source
    src="${SOURCE_DIR}"
    [[ "${WITH_GUI}" -eq 1 ]] && extra="[gui]"

    if [[ -f "${MANIFEST}" ]]; then
        log_info "Replacing the previous installation in ${PREFIX}"
        do_uninstall quiet
    fi
    mkdir -p "${PREFIX}" "${BIN_DIR}"
    : > "${MANIFEST}"

    log_info "Creating the virtual environment in ${PREFIX}/venv"
    "${python}" -m venv "${PREFIX}/venv"
    log_info "Installing ${APP_NAME}${extra} and its dependencies (this can take a while)"
    "${PREFIX}/venv/bin/python" -m pip install --quiet --disable-pip-version-check \
        "${src}${extra}"

    local command
    for command in "${APP_NAME}" "${APP_NAME}-gui"; do
        [[ "${WITH_GUI}" -eq 0 && "${command}" == *-gui ]] && continue
        ln -sf "${PREFIX}/venv/bin/${command}" "${BIN_DIR}/${command}"
        record "${BIN_DIR}/${command}"
    done
    [[ "${WITH_GUI}" -eq 1 ]] && install_desktop_files "${src}"

    log_ok "$("${PREFIX}/venv/bin/${APP_NAME}" --version) installed in ${PREFIX}"
    case ":${PATH}:" in
        *":${BIN_DIR}:"*) ;;
        *) log_warn "${BIN_DIR} is not in your PATH; add it to run '${APP_NAME}' from a terminal" ;;
    esac
}

do_uninstall() {
    local quiet="${1:-}"
    if [[ ! -f "${MANIFEST}" ]]; then
        [[ -n "${quiet}" ]] && return 0
        die "No install.sh installation found in ${PREFIX}"
    fi
    local path
    while IFS= read -r path; do
        [[ -n "${path}" ]] && rm -f -- "${path}"
    done < "${MANIFEST}"
    rm -rf -- "${PREFIX}"
    refresh_desktop_caches
    [[ -n "${quiet}" ]] || log_ok "${APP_NAME} removed from ${PREFIX}"
}

main() {
    parse_args "$@"
    set_paths
    if [[ "${ACTION}" == "uninstall" ]]; then
        do_uninstall
    else
        do_install
    fi
}

main "$@"
