"""Polling coordinator: one per configured stop, sharing the feeds."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (CONF_COUNT, CONF_LINES, CONF_NETWORK_ALERTS, CONF_REALTIME, CONF_SCAN_INTERVAL,
                    CONF_STOP_ID, DEFAULT_COUNT, DEFAULT_SCAN_INTERVAL, DOMAIN,
                    GTFS_MAX_AGE, MIN_SCAN_INTERVAL)
from .data.client import TisseoFeeds
from .data.const import TZ
from .data.departures import Departure, alerts_for, live_routes, next_departures
from .data.realtime import Alert

_LOGGER = logging.getLogger(__name__)


@dataclass
class TisseoData:
    departures: list[Departure] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    realtime_available: bool = False
    feed_timestamp: datetime | None = None
    gtfs_version: str | None = None
    feed_url: str | None = None
    # Lines serving this stop that currently have live (GTFS-RT) predictions.
    live_lines: list[str] = field(default_factory=list)


def opt(entry: ConfigEntry, key: str, default=None):
    return entry.options.get(key, entry.data.get(key, default))


class TisseoCoordinator(DataUpdateCoordinator[TisseoData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, feeds: TisseoFeeds) -> None:
        interval = max(MIN_SCAN_INTERVAL, int(opt(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{entry.data[CONF_STOP_ID]}",
                         update_interval=timedelta(seconds=interval))
        self.entry = entry
        self.feeds = feeds
        self.stop_id: str = entry.data[CONF_STOP_ID]
        self.route_ids: set[str] = set(opt(entry, CONF_LINES, []) or [])
        self.count: int = int(opt(entry, CONF_COUNT, DEFAULT_COUNT))
        self.network_alerts: bool = bool(opt(entry, CONF_NETWORK_ALERTS, True))
        self.use_realtime: bool = bool(opt(entry, CONF_REALTIME, True))
        self._stop_ids: set[str] | None = None
        self._stop_routes: set[str] | None = None

    async def _async_update_data(self) -> TisseoData:
        try:
            await self.feeds.ensure_gtfs(GTFS_MAX_AGE)
        except Exception as err:  # noqa: BLE001 - keep serving the cached index
            _LOGGER.warning("GTFS refresh failed: %s", err)
        store = self.feeds.store
        if self._stop_ids is None:
            kids = await self.hass.async_add_executor_job(store.child_stop_ids, self.stop_id)
            self._stop_ids = set(kids) | {self.stop_id}
            routes = await self.hass.async_add_executor_job(store.routes_for_stop, self.stop_id)
            self._stop_routes = {r.route_id for r in routes}
        rt = await self.feeds.realtime()
        try:
            deps = await self.hass.async_add_executor_job(
                lambda: next_departures(store, rt if self.use_realtime else None, self.stop_id, route_ids=self.route_ids or None,
                                        count=self.count))
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Could not compute departures: {err}") from err
        if not self.use_realtime:
            for dep in deps:
                dep.live_coverage = "disabled"
        alerts = alerts_for(rt, self._stop_ids, self.route_ids or self._stop_routes or set(),
                            include_network=self.network_alerts)
        meta = await self.hass.async_add_executor_job(store.meta)
        routes = await self.hass.async_add_executor_job(store.routes)
        live = (live_routes(rt) if self.use_realtime else set()) & (self.route_ids or self._stop_routes or set())
        return TisseoData(
            feed_url=self.feeds.rt_source_url if rt is not None else None,
            live_lines=sorted(routes[r].short_name if r in routes else r for r in live),
            departures=deps, alerts=alerts, realtime_available=rt is not None,
            feed_timestamp=datetime.fromtimestamp(rt.timestamp, TZ) if rt and rt.timestamp else None,
            gtfs_version=meta.get("built"),
        )
