# Retroscrappy

Metadata and artwork scraper for **EmulationStation** as used by
**Batocera**, **RetroBat** and **Retrobox**. It reads your `roms/` folder,
fills each system's `gamelist.xml` and downloads media into the folders
those frontends expect.

- Works with **any platform** in your ROM folder: known systems are
  recognised by folder name (or from `es_systems.cfg`), unknown ones are
  scraped by name.
- Three sources, tried in an order you choose per item:
  - **ScreenScraper**: identifies ROMs by file name, size and hash, so
    matches are exact. Best for consoles and arcade.
  - **SteamGridDB**: covers, logos and heroes. Best for PC launchers
    (Steam, Heroic, Lutris).
  - **IGDB**: metadata, covers, screenshots and artwork.
- Only fills what is missing unless you ask it to overwrite.
- Graphical interface (PySide6) and a command line for unattended runs.

## Install

Requires Python 3.11+.

```bash
pip install .            # CLI only
pip install '.[gui]'     # CLI + graphical interface
```

For development: `pip install -e '.[gui,dev]'`.

## Graphical interface

```bash
retroscrappy-gui
```

The window goes from general to specific:

1. **Systems** (left): every system found in your ROM folder. Tick the
   ones you want to scrape.
2. **Games** (middle): games of the highlighted system with a ✔ for each
   piece of data they already have. Filter by name or show only incomplete
   games. Games in *italics* are on disk but not in `gamelist.xml` yet.
3. **Game editor** (right): media and metadata of the selected game.
   - Click any media box (box art, logo, screenshot, video...) to fetch it
     from a source, pick a file from your computer, open it or remove it.
     Media changes are written immediately.
   - Every text field can be edited by hand; the ⟳ button next to it fills
     it from a source, and *Fetch all text* fills every field at once.
     Press **Save** to write text changes to `gamelist.xml`.

**Scrape…** opens one dialog with three questions: which games (selected,
current system or ticked systems), what to fetch (tick only *Screenshot* to
fetch only screenshots, for instance), and how many questions to ask
(*Automatic*, *Ask when unsure*, *Always ask*). Progress and the log are
shown at the bottom.

**Settings** holds everything that is configured once: library location,
accounts, source order, description languages and regions, and scrape
defaults.

## Command line

```bash
retroscrappy systems                       # systems, ROM counts and coverage
retroscrappy scrape                        # scrape with your defaults
retroscrappy scrape -s snes -s megadrive --media thumbnail,marquee --mode auto
retroscrappy scrape -s psx --game "Final Fantasy VII.m3u" --overwrite
retroscrappy check                         # test credentials
retroscrappy config                        # where settings live (secrets masked)
```

Without a terminal attached (cron, systemd) the scrape runs in automatic mode.

## Configuration

Settings are stored in `~/.config/retroscrappy/config.ini`
(`%APPDATA%\retroscrappy\config.ini` on Windows) with owner-only
permissions, as it contains API credentials. Settings from the previous
version (`~/.config/sgdb-scraper/config.ini`) are imported on first run.

### Credentials

| Source | What you need |
|---|---|
| ScreenScraper | Developer id/password (ask on the screenscraper.fr forum) and, optionally, your user account for higher quotas |
| SteamGridDB | API key from your SteamGridDB profile |
| IGDB | Twitch application client id and secret (dev.twitch.tv) |

### Source order

Every text field and media kind has its own ordered list of sources
(*Settings → Sources*, drag to reorder). Sources are tried top to bottom
until one has the item; each source is queried at most once per game.
Videos and manuals come from ScreenScraper only. Description languages and
regions are ordered the same way.

### Platforms

The bundled table (`src/retroscrappy/data/platforms.toml`) maps folder
names to ScreenScraper and IGDB ids and ROM extensions. Add or override
platforms in `~/.config/retroscrappy/platforms.toml` using the same format.

## Files written

For a ROM `roms/snes/Game (USA).sfc`:

| Item | File | `gamelist.xml` tag |
|---|---|---|
| Screenshot | `images/Game (USA)-image.png` | `<image>` |
| Box art | `images/Game (USA)-thumb.png` | `<thumbnail>` |
| Logo | `images/Game (USA)-marquee.png` | `<marquee>` |
| Title screen | `images/Game (USA)-titleshot.png` | `<titleshot>` |
| Fan art | `images/Game (USA)-fanart.jpg` | `<fanart>` |
| Box back | `images/Game (USA)-boxback.png` | `<boxback>` |
| Video | `videos/Game (USA)-video.mp4` | `<video>` |
| Manual | `manuals/Game (USA)-manual.pdf` | `<manual>` |

Entries are matched by `<path>`; other tags (favourites, play counts...)
are preserved. Before the first change in a run, the original is copied to
`gamelist.xml.bak`.

## Project layout

```
src/retroscrappy/
├── core/        library model: settings, platforms, gamelist.xml, ROM discovery
├── providers/   ScreenScraper, SteamGridDB, IGDB behind one interface
├── pipeline/    scrape runner (no UI code; talks to the UI through protocols)
├── gui/         PySide6 interface (optional)
├── data/        bundled platform table
└── cli.py       command line
tests/           pytest suite (no network)
packaging/       notes for future deb/rpm/PyPI packages
data/            desktop entry
```

Code checks: `pylint src/retroscrappy` and `pytest`.
