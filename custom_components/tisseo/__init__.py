"""Tisséo (Toulouse) next departures & disruptions, from keyless open data."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, GTFS_MAX_AGE, PLATFORMS
from .coordinator import TisseoCoordinator
from .data.client import TisseoFeeds

_LOGGER = logging.getLogger(__name__)

CARD_FILE = "tisseo-departures-card.js"
CARD_URL_BASE = "/tisseo_static"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _card_version() -> str:
    manifest = Path(__file__).parent / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8")).get("version", "0")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the bundled Lovelace card and load it in the frontend automatically."""
    if getattr(hass, "http", None) is None:  # e.g. unit tests without the http component
        _LOGGER.debug("http not loaded; Tisséo card not registered")
        return True
    try:
        from homeassistant.components import frontend
        from homeassistant.components.http import StaticPathConfig

        version = await hass.async_add_executor_job(_card_version)
        await hass.http.async_register_static_paths([StaticPathConfig(
            CARD_URL_BASE, str(Path(__file__).parent / "frontend"), True)])
        frontend.add_extra_js_url(hass, f"{CARD_URL_BASE}/{CARD_FILE}?v={version}")
    except Exception as err:  # noqa: BLE001 - the card is optional, sensors must still work
        _LOGGER.warning("Could not register the Tisséo Lovelace card: %s", err)
    return True


def get_feeds(hass: HomeAssistant) -> TisseoFeeds:
    """One shared feed manager (GTFS index + GTFS-RT snapshot) for all entries."""
    data = hass.data.setdefault(DOMAIN, {})
    if "feeds" not in data:
        data["feeds"] = TisseoFeeds(
            async_get_clientsession(hass),
            hass.config.path(".storage", "tisseo"),
            run_in_executor=hass.async_add_executor_job,
        )
    return data["feeds"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    feeds = get_feeds(hass)
    try:
        await feeds.ensure_gtfs(GTFS_MAX_AGE)
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Tisséo GTFS unavailable: {err}") from err
    coordinator = TisseoCoordinator(hass, entry, feeds)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
