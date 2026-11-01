"""Build the enabled, configured providers from settings."""

from __future__ import annotations

from retroscrappy.core.items import METADATA_KEY, MediaKind
from retroscrappy.core.settings import Settings
from retroscrappy.providers.base import Provider
from retroscrappy.providers.igdb import IGDBProvider
from retroscrappy.providers.screenscraper import ScreenScraperProvider
from retroscrappy.providers.steamgriddb import SteamGridDBProvider

PROVIDER_CLASSES: dict[str, type[Provider]] = {
    cls.key: cls for cls in (ScreenScraperProvider, SteamGridDBProvider, IGDBProvider)
}
PROVIDER_LABELS = {key: cls.label for key, cls in PROVIDER_CLASSES.items()}


def providers_for(priority_key: str) -> list[str]:
    """Provider keys able to supply a priority-table key (``metadata`` or a media kind)."""
    if priority_key == METADATA_KEY:
        return [key for key, cls in PROVIDER_CLASSES.items() if cls.fields]
    return [key for key, cls in PROVIDER_CLASSES.items() if MediaKind(priority_key) in cls.media]


def build_provider(key: str, settings: Settings) -> Provider:
    """Instantiate one provider regardless of whether it is enabled."""
    if key == ScreenScraperProvider.key:
        return ScreenScraperProvider(
            settings.screenscraper, settings.region, settings.scrape.hash_max_mb
        )
    if key == SteamGridDBProvider.key:
        return SteamGridDBProvider(settings.steamgriddb)
    if key == IGDBProvider.key:
        return IGDBProvider(settings.igdb, settings.region)
    raise KeyError(key)


def build_providers(settings: Settings) -> dict[str, Provider]:
    """Providers that are enabled and have credentials."""
    accounts = {
        ScreenScraperProvider.key: settings.screenscraper,
        SteamGridDBProvider.key: settings.steamgriddb,
        IGDBProvider.key: settings.igdb,
    }
    return {
        key: build_provider(key, settings)
        for key, account in accounts.items()
        if account.enabled and account.configured
    }
