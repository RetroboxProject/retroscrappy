#!/usr/bin/env bash
# Build dist/retroscrappy_<version>-<release>_all.deb with dpkg-deb.
# Environment: PACKAGE_RELEASE (default 1), PACKAGE_MAINTAINER.
set -euo pipefail
# shellcheck source=packaging/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

main() {
    command -v dpkg-deb > /dev/null || die "dpkg-deb not found"
    local version release root
    version="$(package_version)"
    release="${PACKAGE_RELEASE:-1}"
    root="${BUILD_DIR}/deb/${APP_NAME}_${version}-${release}_all"

    stage_tree
    rm -rf "${root}"
    mkdir -p "${root}/DEBIAN" "${root}/usr/share/doc/${APP_NAME}"
    cp -a "${STAGE_DIR}/." "${root}/"

    sed -e "s|@VERSION@|${version}-${release}|" \
        -e "s|@MAINTAINER@|${PACKAGE_MAINTAINER:-${DEFAULT_MAINTAINER}}|" \
        -e "s|@INSTALLED_SIZE@|$(du -sk --exclude=DEBIAN "${root}" | cut -f1)|" \
        "${REPO_ROOT}/packaging/deb/control.in" > "${root}/DEBIAN/control"
    install -m 0755 "${REPO_ROOT}/packaging/deb/postinst" "${root}/DEBIAN/postinst"
    install -m 0755 "${REPO_ROOT}/packaging/deb/prerm" "${root}/DEBIAN/prerm"
    install -m 0644 "${REPO_ROOT}/packaging/deb/copyright" \
        "${root}/usr/share/doc/${APP_NAME}/copyright"

    (cd "${root}" && find . -path ./DEBIAN -prune -o -type f -printf '%P\0' \
        | sort -z | xargs -0 md5sum > DEBIAN/md5sums)
    chmod 0644 "${root}/DEBIAN/md5sums"

    mkdir -p "${DIST_DIR}"
    dpkg-deb --root-owner-group -Zxz --build "${root}" "${DIST_DIR}/" > /dev/null
    log_ok "Built ${DIST_DIR}/${APP_NAME}_${version}-${release}_all.deb"
}

main "$@"
