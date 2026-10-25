"""Tisséo (Toulouse) departures, journeys, disruptions, bikes and park-and-ride."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (CONF_DESTINATION, CONF_ENTRY_TYPE, CONF_ORIGIN, CONF_STOP_ID, DOMAIN,
                    GTFS_MAX_AGE, PLATFORMS, TYPE_BIKE, TYPE_JOURNEY, TYPE_PARKRIDE, TYPE_STOP)
from .data.bikes import GbfsClient
from .data.client import TisseoFeeds
from .data.health import FeedHealth

_LOGGER = logging.getLogger(__name__)

CARD_FILE = "tisseo-departures-card.js"
CARD_URL_BASE = "/tisseo_static"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _card_version() -> str:
    manifest = Path(__file__).parent / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8")).get("version", "0")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Websocket command + service, and the bundled Lovelace card."""
    from .services import async_setup_services
    async_setup_services(hass)
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


def entry_type(entry: ConfigEntry) -> str:
    return entry.data.get(CONF_ENTRY_TYPE, TYPE_STOP)


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


def get_gbfs(hass: HomeAssistant) -> tuple[GbfsClient, FeedHealth]:
    data = hass.data.setdefault(DOMAIN, {})
    if "gbfs" not in data:
        data["gbfs"] = (GbfsClient(async_get_clientsession(hass)), FeedHealth("gbfs", stale_after=900))
    return data["gbfs"]


def get_parkride_health(hass: HomeAssistant) -> FeedHealth:
    data = hass.data.setdefault(DOMAIN, {})
    return data.setdefault("parkride_health", FeedHealth("parkride", stale_after=3 * 86400))


def required_stops(hass: HomeAssistant, exclude: str | None = None) -> set[str]:
    """Stops whose trips the lean GTFS index must contain (union over all entries)."""
    out: set[str] = set()
    for e in hass.config_entries.async_entries(DOMAIN):
        if e.entry_id == exclude:
            continue
        t = entry_type(e)
        if t == TYPE_STOP and e.data.get(CONF_STOP_ID):
            out.add(e.data[CONF_STOP_ID])
        elif t == TYPE_JOURNEY:
            out.update(x for x in (e.data.get(CONF_ORIGIN), e.data.get(CONF_DESTINATION)) if x)
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import (BikeCoordinator, JourneyCoordinator, ParkRideCoordinator,
                              TisseoCoordinator)
    t = entry_type(entry)
    if t in (TYPE_STOP, TYPE_JOURNEY):
        feeds = get_feeds(hass)
        feeds.required_stops = required_stops(hass)
        try:
            await feeds.ensure_gtfs(GTFS_MAX_AGE)
            await feeds.ensure_index(feeds.required_stops)
        except Exception as err:  # noqa: BLE001
            raise ConfigEntryNotReady(f"Tisséo GTFS unavailable: {err}") from err
        coordinator = (TisseoCoordinator if t == TYPE_STOP else JourneyCoordinator)(hass, entry, feeds)
    elif t == TYPE_BIKE:
        client, health = get_gbfs(hass)
        coordinator = BikeCoordinator(hass, entry, client, health)
    elif t == TYPE_PARKRIDE:
        coordinator = ParkRideCoordinator(hass, entry, get_parkride_health(hass))
    else:
        _LOGGER.error("Unknown Tisséo entry type %s", t)
        return False
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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Shrink the lean index when a stop / journey is removed."""
    from homeassistant.helpers import issue_registry as ir
    from .coordinator import issue_id_invalid_key
    ir.async_delete_issue(hass, DOMAIN, issue_id_invalid_key(entry.entry_id))
    if entry_type(entry) not in (TYPE_STOP, TYPE_JOURNEY):
        return
    feeds = hass.data.get(DOMAIN, {}).get("feeds")
    if feeds is None:
        return
    try:
        await feeds.ensure_index(required_stops(hass, exclude=entry.entry_id))
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Index shrink after removal failed: %s", err)
