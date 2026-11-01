#!/usr/bin/env bash
# Render the PNG icon sizes (and the in-app window icon) from the SVG master.
# Run after editing the SVG; the results are committed. Requires rsvg-convert
# (librsvg2-bin on Debian, librsvg2-tools on Fedora).
set -euo pipefail

readonly APP_ID="io.github.retroboxproject.retroscrappy"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT
readonly HICOLOR="${ROOT}/packaging/linux/icons/hicolor"
readonly SVG="${HICOLOR}/scalable/apps/${APP_ID}.svg"
readonly SIZES=(16 24 32 48 64 128 256 512)

for size in "${SIZES[@]}"; do
    dir="${HICOLOR}/${size}x${size}/apps"
    mkdir -p "${dir}"
    rsvg-convert --width "${size}" --height "${size}" "${SVG}" --output "${dir}/${APP_ID}.png"
done
cp "${HICOLOR}/256x256/apps/${APP_ID}.png" "${ROOT}/src/retroscrappy/data/icons/retroscrappy.png"
echo "[ OK ] Icons rendered from ${SVG}"
