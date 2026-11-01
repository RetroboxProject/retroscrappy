#!/usr/bin/env bash
# Build dist/retroscrappy-<version>-<release>.noarch.rpm with rpmbuild.
# Environment: PACKAGE_RELEASE (default 1), PACKAGE_MAINTAINER.
set -euo pipefail
# shellcheck source=packaging/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

main() {
    command -v rpmbuild > /dev/null || die "rpmbuild not found"
    local version release topdir
    version="$(package_version)"
    release="${PACKAGE_RELEASE:-1}"
    topdir="${BUILD_DIR}/rpm"

    stage_tree
    rm -rf "${topdir}"
    mkdir -p "${topdir}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

    rpmbuild -bb --quiet \
        --define "_topdir ${topdir}" \
        --define "pkg_version ${version}" \
        --define "pkg_release ${release}" \
        --define "pkg_packager ${PACKAGE_MAINTAINER:-${DEFAULT_MAINTAINER}}" \
        --define "stage_dir ${STAGE_DIR}" \
        --define "license_file ${REPO_ROOT}/LICENSE" \
        "${REPO_ROOT}/packaging/rpm/${APP_NAME}.spec"

    mkdir -p "${DIST_DIR}"
    find "${topdir}/RPMS" -name '*.rpm' -exec cp {} "${DIST_DIR}/" \;
    log_ok "Built ${DIST_DIR}/${APP_NAME}-${version}-${release}.noarch.rpm"
}

main "$@"
