# Packaging

Retroscrappy is pure Python, so a single architecture-independent package
(`_all.deb`, `.noarch.rpm`) serves every Debian, Ubuntu and Fedora release
that ships the dependencies.

## Layout on disk

Both packages install the same files:

| Path | Contents |
|---|---|
| `/opt/retroscrappy/lib/retroscrappy/` | Python package (byte-compiled on install) |
| `/usr/bin/retroscrappy`, `/usr/bin/retroscrappy-gui` | launchers using the system `python3` |
| `/usr/share/applications/io.github.retroboxproject.retroscrappy.desktop` | menu entry |
| `/usr/share/icons/hicolor/*/apps/io.github.retroboxproject.retroscrappy.*` | icon (SVG + PNG sizes) |
| `/usr/share/metainfo/io.github.retroboxproject.retroscrappy.metainfo.xml` | AppStream data |

The code lives in `/opt` rather than in the distribution's Python path
because Fedora's `site-packages` path includes the Python version; with
`/opt` one `.rpm` keeps working across Fedora upgrades.

## Dependencies

| | Debian / Ubuntu | Fedora |
|---|---|---|
| Required | `python3 (>= 3.11)`, `python3-requests`, `python3-pyside6.qtcore`, `python3-pyside6.qtgui`, `python3-pyside6.qtwidgets` | `python3 >= 3.11`, `python3-requests`, `python3-pyside6` |
| Recommended | `qt6-wayland` | `qt6-qtwayland` |

PySide6 is packaged in Debian 13 (trixie) and later, Ubuntu after 24.04 and
current Fedora. On older releases, or on immutable systems, use
[`install.sh`](../install.sh) instead.

## Building locally

```bash
packaging/build-deb.sh   # needs dpkg-deb  → dist/retroscrappy_<ver>-1_all.deb
packaging/build-rpm.sh   # needs rpmbuild  → dist/retroscrappy-<ver>-1.noarch.rpm
```

`PACKAGE_RELEASE` (default `1`) and `PACKAGE_MAINTAINER` can be set in the
environment. The version always comes from `src/retroscrappy/__init__.py`.

## Releases (GitHub Actions)

`.github/workflows/packages.yml` runs on every push and pull request:

1. pylint, pytest and shellcheck;
2. builds the `.deb` and `.rpm`;
3. installs them with `apt` in `debian:trixie` (and, informatively,
   `ubuntu:rolling`) and with `dnf` in `fedora:latest`, opens the main
   window off-screen and uninstalls them again.

Pushing a tag `vX.Y.Z` that matches `__version__` also publishes a GitHub
release with both packages and a `SHA256SUMS` file. The maintainer field
can be changed with the repository variable `PACKAGE_MAINTAINER`.

## Icon

The master is `linux/icons/hicolor/scalable/apps/io.github.retroboxproject.retroscrappy.svg`.
After editing it, run `packaging/render-icons.sh` (needs `rsvg-convert`) to
regenerate the PNG sizes and the copy bundled in the Python package, which
the window uses when the theme icon is not installed.

## PyPI

`pyproject.toml` is complete (`python -m build` gives an sdist and a wheel);
the wheel includes the platform table and the window icon.
