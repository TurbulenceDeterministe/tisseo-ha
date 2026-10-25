"""Polling coordinators: stops, journeys, bike stations and park-and-ride."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (CONF_API_KEY, CONF_BUFFER, CONF_COUNT, CONF_DELAY_THRESHOLD,
                    CONF_DESTINATION, CONF_LINES, CONF_MIN_TRANSFER, CONF_NETWORK_ALERTS,
                    CONF_ORIGIN, CONF_PARK_ID, CONF_REALTIME, CONF_SCAN_INTERVAL,
                    CONF_STATION_ID, CONF_STOP_ID, CONF_STOP_NAME, CONF_WALK, DEFAULT_BUFFER,
                    DEFAULT_COUNT, DEFAULT_DELAY_THRESHOLD, DEFAULT_MIN_TRANSFER,
                    DEFAULT_SCAN_INTERVAL, DEFAULT_WALK, DOMAIN, EVENT_DELAY, EVENT_DISRUPTION,
                    FETCH_DEPARTURES, GTFS_MAX_AGE, MIN_SCAN_INTERVAL)
from .data.api import ApiError, InvalidApiKey, fetch_stop_schedules
from .data.bikes import BikeStation, BikeStatus, GbfsClient
from .data.client import TisseoFeeds
from .data.const import TZ
from .data.departures import Departure, alerts_for, live_routes, merge_api, next_departures
from .data.health import FeedHealth
from .data.const import ROUTE_TYPE_NAMES
from .data.journeys import Connection, search_with_fallback
from .data.parkride import ParkRide, fetch_parkride
from .data.realtime import Alert
from .data.timetable import timetable_change

_LOGGER = logging.getLogger(__name__)


def opt(entry: ConfigEntry, key: str, default=None):
    return entry.options.get(key, entry.data.get(key, default))


def issue_id_invalid_key(entry_id: str) -> str:
    return f"invalid_api_key_{entry_id}"


@dataclass
class TisseoData:
    departures: list[Departure] = field(default_factory=list)  # first `count`
    all_departures: list[Departure] = field(default_factory=list)  # up to FETCH_DEPARTURES
    alerts: list[Alert] = field(default_factory=list)
    realtime_available: bool = False
    feed_timestamp: datetime | None = None
    gtfs_version: str | None = None
    feed_url: str | None = None
    # Lines serving this stop that currently have live (GTFS-RT) predictions.
    live_lines: list[str] = field(default_factory=list)
    api_used: bool = False
    api_error: str | None = None
    timetable: dict | None = None
    # First scheduled departure after the look-ahead window, when there is none in it
    # (no evening / weekend / holiday service on the configured lines).
    next_service: dict | None = None


def leave_info(deps: list[Departure], walk_min: float, buffer_min: float,
               now: datetime | None = None) -> dict:
    """Next departure you can still catch when walking `walk_min` to the stop.

    leave_at = expected - walk - buffer. "Leave now" is on once leave_at is reached
    (and the departure is still catchable)."""
    now = now or datetime.now(TZ)
    walk, buf = timedelta(minutes=walk_min), timedelta(minutes=buffer_min)
    for d in deps:
        if d.canceled or d.expected < now + walk:
            continue
        leave_at = d.expected - walk - buf
        secs = (leave_at - now).total_seconds()
        return {
            "departure": d, "leave_at": leave_at, "leave_in": max(0, int(secs // 60)),
            "leave_now": secs <= 0, "walking_time": walk_min, "buffer": buffer_min,
        }
    return {"departure": None, "leave_at": None, "leave_in": None, "leave_now": False,
            "walking_time": walk_min, "buffer": buffer_min}


class _BaseCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, name, interval: timedelta) -> None:
        super().__init__(hass, _LOGGER, name=name, update_interval=interval,
                         config_entry=entry)
        self.entry = entry

    def health(self) -> dict[str, FeedHealth]:
        return {}

    @property
    def primary_feed(self) -> str:
        return next(iter(self.health()), "")


class TisseoCoordinator(_BaseCoordinator):
    """One stop: departures (GTFS + GTFS-RT [+ official API]), alerts, events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, feeds: TisseoFeeds) -> None:
        interval = max(MIN_SCAN_INTERVAL, int(opt(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        super().__init__(hass, entry, f"{DOMAIN}_{entry.data[CONF_STOP_ID]}",
                         timedelta(seconds=interval))
        self.feeds = feeds
        self.stop_id: str = entry.data[CONF_STOP_ID]
        self.stop_name: str = entry.data.get(CONF_STOP_NAME, self.stop_id)
        self.route_ids: set[str] = set(opt(entry, CONF_LINES, []) or [])
        self.count: int = int(opt(entry, CONF_COUNT, DEFAULT_COUNT))
        self.network_alerts: bool = bool(opt(entry, CONF_NETWORK_ALERTS, True))
        self.use_realtime: bool = bool(opt(entry, CONF_REALTIME, True))
        self.walk: float = float(opt(entry, CONF_WALK, DEFAULT_WALK) or 0)
        self.buffer: float = float(opt(entry, CONF_BUFFER, DEFAULT_BUFFER) or 0)
        self.delay_threshold: float = float(opt(entry, CONF_DELAY_THRESHOLD, DEFAULT_DELAY_THRESHOLD) or 0)
        self.api_key: str | None = entry.data.get(CONF_API_KEY) or None
        self.api_health = FeedHealth("api", stale_after=900)
        self.api_invalid = False
        self._stop_ids: set[str] | None = None
        self._stop_routes: set[str] | None = None
        self._seen_alerts: set[str] | None = None
        self._delay_fired: dict[str, float] = {}
        self._timetable_key: tuple | None = None
        self._timetable: dict | None = None

    def health(self) -> dict[str, FeedHealth]:
        h = {"gtfs_rt": self.feeds.health["gtfs_rt"], "gtfs": self.feeds.health["gtfs"]}
        if self.api_key:
            h["api"] = self.api_health
        return h

    async def _fetch_api(self, routes) -> list | None:
        if not self.api_key or self.api_invalid or not self.api_health.allow():
            return None
        try:
            res = await fetch_stop_schedules(async_get_clientsession(self.hass), self.api_key,
                                             self.stop_id, number=FETCH_DEPARTURES)
        except InvalidApiKey:
            self.api_invalid = True
            self.api_health.record(False, "invalid key")
            _LOGGER.warning("Tisséo API key rejected for %s; falling back to open data", self.stop_name)
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id_invalid_key(self.entry.entry_id), is_fixable=False,
                severity=ir.IssueSeverity.ERROR, translation_key="invalid_api_key",
                translation_placeholders={"title": self.entry.title})
            self.entry.async_start_reauth(self.hass)
            return None
        except ApiError as err:  # message is sanitised (never contains the key)
            self.api_health.record(False, str(err))
            _LOGGER.debug("Tisséo API error for %s: %s", self.stop_name, err)
            return None
        self.api_health.record(True)
        return res

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
        use_rt = rt if self.use_realtime else None
        try:
            deps = await self.hass.async_add_executor_job(
                lambda: next_departures(store, use_rt, self.stop_id,
                                        route_ids=self.route_ids or None,
                                        count=max(self.count, FETCH_DEPARTURES)))
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Could not compute departures: {err}") from err
        if not self.use_realtime:
            for dep in deps:
                dep.live_coverage = "disabled"
        routes = await self.hass.async_add_executor_job(store.routes)
        live = (live_routes(rt) if self.use_realtime else set()) & (self.route_ids or self._stop_routes or set())
        api_used = False
        if self.api_key and self.use_realtime:
            api_deps = await self._fetch_api(routes)
            if api_deps is not None:
                api_used = True
                deps = merge_api(deps, api_deps, routes, live, self._stop_routes,
                                 self.route_ids or None, stop_name=self.stop_name,
                                 stop_id=self.stop_id)
        alerts = alerts_for(rt, self._stop_ids, self.route_ids or self._stop_routes or set(),
                            include_network=self.network_alerts)
        meta = await self.hass.async_add_executor_job(store.meta)
        today = datetime.now(TZ).date()
        key = (today, meta.get("built"))
        if key != self._timetable_key:
            lang = (self.hass.config.language or "en").split("-")[0]
            try:
                self._timetable = await self.hass.async_add_executor_job(
                    lambda: timetable_change(store, sorted(self._stop_ids), today,
                                             self.route_ids or None, lang))
                self._timetable_key = key
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Timetable comparison failed: %s", err)
        next_service = None
        if not deps:
            try:
                next_service = await self.hass.async_add_executor_job(
                    self._next_service, store, routes)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Next service lookup failed: %s", err)
        data = TisseoData(
            next_service=next_service,
            feed_url=self.feeds.rt_source_url if rt is not None else None,
            live_lines=sorted(routes[r].short_name if r in routes else r for r in live),
            departures=deps[: self.count], all_departures=deps[:FETCH_DEPARTURES],
            alerts=alerts, realtime_available=rt is not None,
            feed_timestamp=datetime.fromtimestamp(rt.timestamp, TZ) if rt and rt.timestamp else None,
            gtfs_version=meta.get("built"), api_used=api_used,
            api_error=self.api_health.last_error if self.api_key and not api_used else None,
            timetable=self._timetable,
        )
        self._fire_events(data, routes)
        return data

    def _next_service(self, store, routes) -> dict | None:
        """Next scheduled departure (any day in the coming week) for the configured lines."""
        nxt = store.next_scheduled(sorted(self._stop_ids), datetime.now(TZ),
                                   self.route_ids or None)
        if not nxt:
            return None
        r = routes.get(nxt["route_id"])
        return {"scheduled": nxt["dep"].isoformat(), "line": r.short_name if r else nxt["route_id"],
                "route_id": nxt["route_id"], "destination": nxt["headsign"],
                "stop_id": nxt["stop_id"], "trip_id": nxt["trip_id"],
                "mode": ROUTE_TYPE_NAMES.get(r.type, "bus") if r else "bus",
                "color": f"#{r.color}" if r and r.color else "",
                "text_color": f"#{r.text_color}" if r and r.text_color else ""}

    def _fire_events(self, data: TisseoData, routes) -> None:
        ids = {a.id for a in data.alerts}
        if self._seen_alerts is None:
            self._seen_alerts = ids  # no burst of events at startup
        else:
            for a in data.alerts:
                if a.id in self._seen_alerts:
                    continue
                self.hass.bus.async_fire(EVENT_DISRUPTION, {
                    "entry_id": self.entry.entry_id, "stop_id": self.stop_id,
                    "stop_name": self.stop_name, "alert_id": a.id, "header": a.header,
                    "description": a.description, "url": a.url, "cause": a.cause,
                    "effect": a.effect, "network_wide": a.network_wide,
                    "lines": sorted(routes[r].short_name if r in routes else r for r in a.route_ids),
                })
            self._seen_alerts = ids
        if self.delay_threshold <= 0:
            return
        now = datetime.now(TZ).timestamp()
        current = set()
        for d in data.all_departures:
            if not d.trip_id or d.delay is None:
                continue
            current.add(d.trip_id)
            if d.delay >= self.delay_threshold * 60 and d.trip_id not in self._delay_fired:
                self._delay_fired[d.trip_id] = now
                self.hass.bus.async_fire(EVENT_DELAY, {
                    "entry_id": self.entry.entry_id, "stop_id": self.stop_id,
                    "stop_name": self.stop_name, "line": d.line, "route_id": d.route_id,
                    "destination": d.destination, "trip_id": d.trip_id,
                    "scheduled": d.scheduled.isoformat() if d.scheduled else None,
                    "expected": d.expected.isoformat(), "delay_minutes": round(d.delay / 60, 1),
                    "realtime_source": d.realtime_source,
                })
        for t in [t for t, ts in self._delay_fired.items() if t not in current and now - ts > 3 * 3600]:
            self._delay_fired.pop(t, None)

    def leave(self, now: datetime | None = None) -> dict:
        deps = self.data.all_departures if self.data else []
        return leave_info(deps, self.walk, self.buffer, now)


@dataclass
class JourneyData:
    connections: list[Connection] = field(default_factory=list)
    realtime_available: bool = False
    # True when nothing leaves within the look-ahead window and the connections
    # shown are the first ones of the next service (e.g. tomorrow morning).
    later: bool = False


class JourneyCoordinator(_BaseCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, feeds: TisseoFeeds) -> None:
        interval = max(MIN_SCAN_INTERVAL, int(opt(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        super().__init__(hass, entry, f"{DOMAIN}_journey_{entry.entry_id}", timedelta(seconds=interval))
        self.feeds = feeds
        self.origin = entry.data[CONF_ORIGIN]
        self.destination = entry.data[CONF_DESTINATION]
        self.count = int(opt(entry, CONF_COUNT, DEFAULT_COUNT))
        self.min_transfer = float(opt(entry, CONF_MIN_TRANSFER, DEFAULT_MIN_TRANSFER))
        self.use_realtime = bool(opt(entry, CONF_REALTIME, True))

    def health(self) -> dict[str, FeedHealth]:
        return {"gtfs_rt": self.feeds.health["gtfs_rt"], "gtfs": self.feeds.health["gtfs"]}

    async def _async_update_data(self) -> JourneyData:
        try:
            await self.feeds.ensure_gtfs(GTFS_MAX_AGE)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("GTFS refresh failed: %s", err)
        rt = await self.feeds.realtime() if self.use_realtime else None
        try:
            conns, later = await self.hass.async_add_executor_job(self._search, rt)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Could not compute journeys: {err}") from err
        return JourneyData(conns, rt is not None, later)

    def _search(self, rt) -> tuple[list[Connection], bool]:
        """Connections in the next 3 h; if none, the first ones of the next service."""
        return search_with_fallback(self.feeds.store, rt, self.origin, self.destination,
                                    count=self.count, min_transfer=timedelta(minutes=self.min_transfer))


@dataclass
class BikeData:
    station: BikeStation | None
    status: BikeStatus | None
    feed_time: datetime | None


class BikeCoordinator(_BaseCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: GbfsClient,
                 health: FeedHealth) -> None:
        interval = max(MIN_SCAN_INTERVAL, int(opt(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        super().__init__(hass, entry, f"{DOMAIN}_bike_{entry.data[CONF_STATION_ID]}",
                         timedelta(seconds=interval))
        self.client = client
        self.station_id = entry.data[CONF_STATION_ID]
        self._health = health

    def health(self) -> dict[str, FeedHealth]:
        return {"gbfs": self._health}

    async def _async_update_data(self) -> BikeData:
        try:
            stations = await self.client.stations()
            status, ts = await self.client.status()
        except Exception as err:  # noqa: BLE001
            self._health.record(False, type(err).__name__)
            raise UpdateFailed(f"VélôToulouse GBFS unavailable: {err}") from err
        self._health.record(True)
        return BikeData(stations.get(self.station_id), status.get(self.station_id), ts)


class ParkRideCoordinator(_BaseCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, health: FeedHealth) -> None:
        super().__init__(hass, entry, f"{DOMAIN}_pr_{entry.data[CONF_PARK_ID]}", timedelta(hours=24))
        self.park_id = entry.data[CONF_PARK_ID]
        self._health = health

    def health(self) -> dict[str, FeedHealth]:
        return {"parkride": self._health}

    async def _async_update_data(self) -> ParkRide | None:
        try:
            parks = await fetch_parkride(async_get_clientsession(self.hass))
        except Exception as err:  # noqa: BLE001
            self._health.record(False, type(err).__name__)
            if self.data is not None:
                return self.data  # static data: keep the last value
            raise UpdateFailed(f"Park-and-ride dataset unavailable: {err}") from err
        self._health.record(True)
        return parks.get(self.park_id)
