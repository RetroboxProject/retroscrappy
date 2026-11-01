# Packaging notes

Nothing here is built yet; this records how the code is laid out so that
`.deb`, `.rpm` and PyPI packages can be added later without code changes.

## What the code already guarantees

- **Standard `pyproject.toml` (setuptools, `src/` layout).** `python -m build`
  produces an sdist and a wheel; both are what PyPI, `pybuild` (Debian) and
  `%pyproject_*` macros (Fedora) consume.
- **Single version source:** `retroscrappy.__version__`, read by setuptools.
- **Two entry points:** `retroscrappy` (CLI, console script) and
  `retroscrappy-gui` (GUI script). No code runs from the source tree.
- **GUI is optional.** The core and CLI only need `requests`; PySide6 is the
  `gui` extra. Distro packages can split accordingly (see below).
- **No writes to the install prefix.** Settings go to
  `$XDG_CONFIG_HOME/retroscrappy/config.ini` (`%APPDATA%` on Windows), cache
  to `$XDG_CACHE_HOME/retroscrappy`. Bundled data (`platforms.toml`) is read
  with `importlib.resources`, so it works from wheels and zip imports.
- **Desktop integration file** in `data/`, named after the reverse-DNS app id
  `io.github.retroboxproject.retroscrappy`, which the GUI also sets with
  `QGuiApplication.setDesktopFileName`.

## Suggested package split

| Package | Contents | Depends on |
|---|---|---|
| `retroscrappy` (deb) / `python3-retroscrappy` (rpm) | Python package, `retroscrappy` CLI | `python3 (>= 3.11)`, `python3-requests` |
| `retroscrappy-gui` | `retroscrappy-gui`, `.desktop` file, icon | `retroscrappy`, PySide6 (`python3-pyside6.qtwidgets` on Debian, `python3-pyside6` on Fedora) |

PyPI: a single distribution, `pip install retroscrappy` (CLI) or
`pip install 'retroscrappy[gui]'`.

## Still to do when packaging starts

- Add a `LICENSE` file and the `license` field in `pyproject.toml`.
- Add an application icon (`data/icons/hicolor/...`) and an AppStream
  `metainfo.xml`.
- `debian/` directory (dh-python + pybuild-plugin-pyproject) and an RPM
  `.spec` using `%pyproject_wheel` / `%pyproject_install`, plus a GitHub
  Actions workflow like the other RetroboxProject repos.
- Compile Qt translations (`.ts` → `.qm`) at build time once translations exist.
