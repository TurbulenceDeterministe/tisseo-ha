"""Config flow: stop (search or nearby), journey, bike station, park-and-ride; reauth."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (BooleanSelector, NumberSelector,
                                            NumberSelectorConfig, NumberSelectorMode,
                                            SelectOptionDict, SelectSelector,
                                            SelectSelectorConfig, SelectSelectorMode,
                                            TextSelector, TextSelectorConfig, TextSelectorType)

from . import get_feeds, get_gbfs
from .const import (CONF_API_KEY, CONF_BUFFER, CONF_CLEAR_API_KEY, CONF_COUNT,
                    CONF_DELAY_THRESHOLD, CONF_DESTINATION, CONF_DESTINATION_NAME,
                    CONF_DESTINATION_QUERY, CONF_ENTRY_TYPE, CONF_LINES, CONF_MIN_TRANSFER,
                    CONF_NETWORK_ALERTS, CONF_ORIGIN, CONF_ORIGIN_NAME, CONF_ORIGIN_QUERY,
                    CONF_PARK_ID, CONF_PARK_NAME, CONF_QUERY, CONF_REALTIME,
                    CONF_SCAN_INTERVAL, CONF_STATION_ID, CONF_STATION_NAME, CONF_STOP_ID,
                    CONF_STOP_NAME, CONF_WALK, DEFAULT_BUFFER, DEFAULT_COUNT,
                    DEFAULT_DELAY_THRESHOLD, DEFAULT_MIN_TRANSFER, DEFAULT_SCAN_INTERVAL,
                    DEFAULT_WALK, DOMAIN, GTFS_MAX_AGE, MIN_SCAN_INTERVAL, NEARBY_LIMIT,
                    TYPE_BIKE, TYPE_JOURNEY, TYPE_PARKRIDE, TYPE_STOP)
from .data.api import ApiError, InvalidApiKey, fetch_stop_schedules
from .data.bikes import nearest
from .data.parkride import fetch_parkride
from .data.static import haversine_m

_LOGGER = logging.getLogger(__name__)


def _num(min_, max_, step=1, unit=None):
    cfg = {"min": min_, "max": max_, "step": step, "mode": NumberSelectorMode.BOX}
    if unit:
        cfg["unit_of_measurement"] = unit
    return NumberSelector(NumberSelectorConfig(**cfg))


def _settings_schema(routes, defaults: dict, with_clear: bool = False) -> vol.Schema:
    options = [SelectOptionDict(value=r.route_id,
                                label=f"{r.short_name} – {r.long_name}" if r.long_name else r.short_name)
               for r in routes]
    schema = {
        vol.Optional(CONF_LINES, default=defaults.get(CONF_LINES, [])): SelectSelector(
            SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)),
        vol.Optional(CONF_COUNT, default=defaults.get(CONF_COUNT, DEFAULT_COUNT)): _num(1, 10),
        vol.Optional(CONF_SCAN_INTERVAL,
                     default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
            _num(MIN_SCAN_INTERVAL, 600, 5, "s"),
        vol.Optional(CONF_NETWORK_ALERTS, default=defaults.get(CONF_NETWORK_ALERTS, True)): BooleanSelector(),
        vol.Optional(CONF_REALTIME, default=defaults.get(CONF_REALTIME, True)): BooleanSelector(),
        vol.Optional(CONF_WALK, default=defaults.get(CONF_WALK, DEFAULT_WALK)): _num(0, 60, 1, "min"),
        vol.Optional(CONF_BUFFER, default=defaults.get(CONF_BUFFER, DEFAULT_BUFFER)): _num(0, 15, 1, "min"),
        vol.Optional(CONF_DELAY_THRESHOLD,
                     default=defaults.get(CONF_DELAY_THRESHOLD, DEFAULT_DELAY_THRESHOLD)): _num(0, 60, 1, "min"),
        vol.Optional(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
    if with_clear:
        schema[vol.Optional(CONF_CLEAR_API_KEY, default=False)] = BooleanSelector()
    return vol.Schema(schema)


def _clean(user_input: dict) -> dict:
    out = {k: v for k, v in user_input.items() if k not in (CONF_API_KEY, CONF_CLEAR_API_KEY)}
    out[CONF_COUNT] = int(out.get(CONF_COUNT, DEFAULT_COUNT))
    out[CONF_SCAN_INTERVAL] = int(out.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    out[CONF_LINES] = list(out.get(CONF_LINES) or [])
    for k, d in ((CONF_WALK, DEFAULT_WALK), (CONF_BUFFER, DEFAULT_BUFFER),
                 (CONF_DELAY_THRESHOLD, DEFAULT_DELAY_THRESHOLD)):
        out[k] = int(out.get(k, d))
    return out


async def validate_api_key(hass, key: str, stop_id: str) -> str | None:
    """None if the key works, else an error code. The key is never logged."""
    try:
        await fetch_stop_schedules(async_get_clientsession(hass), key, stop_id, number=1)
    except InvalidApiKey:
        return "invalid_key"
    except ApiError:
        return "api_unreachable"
    return None


def _km(m: float) -> str:
    return f"{m:.0f} m" if m < 1000 else f"{m / 1000:.1f} km"


class TisseoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._matches: dict[str, str] = {}
        self._stop_id: str | None = None
        self._stop_name: str | None = None
        self._routes = []
        self._journey: dict[str, Any] = {}
        self._choices: dict[str, str] = {}

    async def _ensure_store(self):
        feeds = get_feeds(self.hass)
        await feeds.ensure_gtfs(GTFS_MAX_AGE)  # first run: download + index (~10-60 s)
        return feeds.store

    # ---------------- menu ----------------
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(step_id="user", menu_options=[
            "stop_search", "nearby", "journey", "bike", "park_ride"])

    # ---------------- stop by search ----------------
    async def _matches_for(self, store, query: str, expand: bool = True) -> dict[str, str]:
        results = await self.hass.async_add_executor_job(store.search_stops, query, 25)
        out: dict[str, str] = {}
        for stop, lines in results:
            kind = "stop area" if stop.is_area else f"stop point {stop.code}".strip()
            out[stop.stop_id] = f"{stop.name} ({kind}) – lines: {', '.join(lines) or '?'}"
            if expand and stop.is_area and len(results) <= 3:
                for kid in await self.hass.async_add_executor_job(store.child_stop_ids, stop.stop_id):
                    if kid == stop.stop_id:
                        continue
                    routes = await self.hass.async_add_executor_job(store.routes_for_stop, kid)
                    out[kid] = (f"  └ {stop.name} platform {kid.split(':')[-1]} – lines: "
                                f"{', '.join(r.short_name for r in routes)}")
        return out

    async def async_step_stop_search(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                store = await self._ensure_store()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not prepare the Tisséo GTFS index")
                errors["base"] = "cannot_connect"
            else:
                self._matches = await self._matches_for(store, user_input[CONF_QUERY])
                if not self._matches:
                    errors[CONF_QUERY] = "no_stop"
                else:
                    return await self.async_step_stop()
        return self.async_show_form(
            step_id="stop_search", errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_QUERY): TextSelector()}))

    async def async_step_nearby(self, user_input: dict[str, Any] | None = None):
        """Stop areas closest to the Home Assistant home location (top 10)."""
        try:
            store = await self._ensure_store()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not prepare the Tisséo GTFS index")
            return self.async_abort(reason="cannot_connect")
        lat, lon = self.hass.config.latitude, self.hass.config.longitude
        near = await self.hass.async_add_executor_job(store.nearby_stops, lat, lon, NEARBY_LIMIT)
        if not near:
            return self.async_abort(reason="no_nearby")
        self._matches = {s.stop_id: f"{s.name} – {_km(d)} – lines: {', '.join(lines)}"
                         for s, d, lines in near}
        return await self.async_step_stop()

    async def async_step_stop(self, user_input: dict[str, Any] | None = None):
        if user_input is not None and CONF_STOP_ID in user_input:
            self._stop_id = user_input[CONF_STOP_ID]
            store = get_feeds(self.hass).store
            stop = await self.hass.async_add_executor_job(store.get_stop, self._stop_id)
            self._stop_name = stop.name if stop else self._stop_id
            self._routes = await self.hass.async_add_executor_job(store.routes_for_stop, self._stop_id)
            return await self.async_step_settings()
        options = [SelectOptionDict(value=k, label=v) for k, v in self._matches.items()]
        return self.async_show_form(step_id="stop", data_schema=vol.Schema({
            vol.Required(CONF_STOP_ID, default=options[0]["value"]): SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)),
        }))

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            key = (user_input.get(CONF_API_KEY) or "").strip()
            if key:
                err = await validate_api_key(self.hass, key, self._stop_id)
                if err:
                    errors[CONF_API_KEY] = err
            if not errors:
                options = _clean(user_input)
                await self.async_set_unique_id(
                    f"{self._stop_id}|{','.join(sorted(options[CONF_LINES]))}")
                self._abort_if_unique_id_configured()
                title = self._stop_name
                if options[CONF_LINES]:
                    names = [r.short_name for r in self._routes if r.route_id in options[CONF_LINES]]
                    title = f"{self._stop_name} ({', '.join(names)})"
                data = {CONF_ENTRY_TYPE: TYPE_STOP, CONF_STOP_ID: self._stop_id,
                        CONF_STOP_NAME: self._stop_name}
                if key:
                    data[CONF_API_KEY] = key
                return self.async_create_entry(title=title, data=data, options=options)
        defaults = {k: v for k, v in (user_input or {}).items() if k != CONF_API_KEY}
        return self.async_show_form(step_id="settings", errors=errors,
                                    data_schema=_settings_schema(self._routes, defaults),
                                    description_placeholders={"stop": self._stop_name or ""})

    # ---------------- journey ----------------
    async def async_step_journey(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                store = await self._ensure_store()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not prepare the Tisséo GTFS index")
                errors["base"] = "cannot_connect"
            else:
                o = await self._matches_for(store, user_input[CONF_ORIGIN_QUERY], expand=False)
                d = await self._matches_for(store, user_input[CONF_DESTINATION_QUERY], expand=False)
                if not o:
                    errors[CONF_ORIGIN_QUERY] = "no_stop"
                if not d:
                    errors[CONF_DESTINATION_QUERY] = "no_stop"
                if not errors:
                    self._journey = {"o": dict(list(o.items())[:10]), "d": dict(list(d.items())[:10])}
                    return await self.async_step_journey_pick()
        return self.async_show_form(step_id="journey", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_ORIGIN_QUERY): TextSelector(),
            vol.Required(CONF_DESTINATION_QUERY): TextSelector()}))

    async def async_step_journey_pick(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            o, d = user_input[CONF_ORIGIN], user_input[CONF_DESTINATION]
            store = get_feeds(self.hass).store
            so = await self.hass.async_add_executor_job(store.get_stop, o)
            sd = await self.hass.async_add_executor_job(store.get_stop, d)
            if (so.parent or so.stop_id) == (sd.parent or sd.stop_id):
                errors["base"] = "same_stop"
            else:
                await self.async_set_unique_id(f"journey|{o}|{d}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{so.name} → {sd.name}",
                    data={CONF_ENTRY_TYPE: TYPE_JOURNEY, CONF_ORIGIN: o, CONF_ORIGIN_NAME: so.name,
                          CONF_DESTINATION: d, CONF_DESTINATION_NAME: sd.name},
                    options={CONF_COUNT: int(user_input.get(CONF_COUNT, DEFAULT_COUNT)),
                             CONF_MIN_TRANSFER: int(user_input.get(CONF_MIN_TRANSFER, DEFAULT_MIN_TRANSFER)),
                             CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL, CONF_REALTIME: True})
        oo = [SelectOptionDict(value=k, label=v) for k, v in self._journey["o"].items()]
        dd = [SelectOptionDict(value=k, label=v) for k, v in self._journey["d"].items()]
        return self.async_show_form(step_id="journey_pick", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_ORIGIN, default=oo[0]["value"]): SelectSelector(
                SelectSelectorConfig(options=oo, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_DESTINATION, default=dd[0]["value"]): SelectSelector(
                SelectSelectorConfig(options=dd, mode=SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_COUNT, default=DEFAULT_COUNT): _num(1, 6),
            vol.Optional(CONF_MIN_TRANSFER, default=DEFAULT_MIN_TRANSFER): _num(0, 20, 1, "min"),
        }))

    # ---------------- bike station ----------------
    async def async_step_bike(self, user_input: dict[str, Any] | None = None):
        client, health = get_gbfs(self.hass)
        if user_input is not None:
            sid = user_input[CONF_STATION_ID]
            await self.async_set_unique_id(f"bike|{sid}")
            self._abort_if_unique_id_configured()
            name = self._choices.get(sid, sid).split(" – ")[0]
            return self.async_create_entry(title=f"VélôToulouse {name}", data={
                CONF_ENTRY_TYPE: TYPE_BIKE, CONF_STATION_ID: sid, CONF_STATION_NAME: name},
                options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL})
        try:
            stations = await client.stations()
            status, _ = await client.status()
        except Exception:  # noqa: BLE001
            health.record(False, "setup")
            return self.async_abort(reason="cannot_connect_gbfs")
        health.record(True)
        usable = {k: v for k, v in stations.items()
                  if not (k in status and not status[k].installed)}
        near = nearest(usable, self.hass.config.latitude, self.hass.config.longitude, 15)
        self._choices = {}
        for dist, s in near:
            st = status.get(s.station_id)
            extra = f" – {st.bikes} bikes / {st.docks} docks" if st else ""
            self._choices[s.station_id] = f"{s.name} – {_km(dist)}{extra}"
        opts = [SelectOptionDict(value=k, label=v) for k, v in self._choices.items()]
        return self.async_show_form(step_id="bike", data_schema=vol.Schema({
            vol.Required(CONF_STATION_ID, default=opts[0]["value"]): SelectSelector(
                SelectSelectorConfig(options=opts, mode=SelectSelectorMode.LIST))}))

    # ---------------- park-and-ride ----------------
    async def async_step_park_ride(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            pid = user_input[CONF_PARK_ID]
            await self.async_set_unique_id(f"pr|{pid}")
            self._abort_if_unique_id_configured()
            name = self._choices.get(pid, pid).split(" – ")[0]
            return self.async_create_entry(title=f"P+R {name}", data={
                CONF_ENTRY_TYPE: TYPE_PARKRIDE, CONF_PARK_ID: pid, CONF_PARK_NAME: name})
        try:
            parks = await fetch_parkride(async_get_clientsession(self.hass))
        except Exception:  # noqa: BLE001
            return self.async_abort(reason="cannot_connect_parkride")
        lat, lon = self.hass.config.latitude, self.hass.config.longitude
        ranked = sorted(parks.values(), key=lambda p: haversine_m(lat, lon, p.lat or 0, p.lon or 0))
        self._choices = {p.id: f"{p.name} – {_km(haversine_m(lat, lon, p.lat or 0, p.lon or 0))}"
                                f" – {p.capacity} spaces" for p in ranked}
        opts = [SelectOptionDict(value=k, label=v) for k, v in self._choices.items()]
        return self.async_show_form(step_id="park_ride", data_schema=vol.Schema({
            vol.Required(CONF_PARK_ID, default=opts[0]["value"]): SelectSelector(
                SelectSelectorConfig(options=opts, mode=SelectSelectorMode.LIST))}))

    # ---------------- reauth (invalid / revoked API key) ----------------
    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            key = (user_input.get(CONF_API_KEY) or "").strip()
            if key:
                err = await validate_api_key(self.hass, key, entry.data[CONF_STOP_ID])
                if err:
                    errors[CONF_API_KEY] = err
            if not errors:
                data = {k: v for k, v in entry.data.items() if k != CONF_API_KEY}
                if key:
                    data[CONF_API_KEY] = key
                from .coordinator import issue_id_invalid_key
                ir.async_delete_issue(self.hass, DOMAIN, issue_id_invalid_key(entry.entry_id))
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm", errors=errors,
            description_placeholders={"title": entry.title},
            data_schema=vol.Schema({vol.Optional(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD))}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TisseoOptionsFlow()


class TisseoOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        entry = self.config_entry
        t = entry.data.get(CONF_ENTRY_TYPE, TYPE_STOP)
        if t == TYPE_JOURNEY:
            return await self.async_step_journey(user_input)
        if t in (TYPE_BIKE, TYPE_PARKRIDE):
            return await self.async_step_simple(user_input)
        errors: dict[str, str] = {}
        if user_input is not None:
            key = (user_input.get(CONF_API_KEY) or "").strip()
            if key:
                err = await validate_api_key(self.hass, key, entry.data[CONF_STOP_ID])
                if err:
                    errors[CONF_API_KEY] = err
            if not errors:
                data = dict(entry.data)
                if user_input.get(CONF_CLEAR_API_KEY):
                    data.pop(CONF_API_KEY, None)
                elif key:
                    data[CONF_API_KEY] = key
                if data != dict(entry.data):
                    # the key lives in entry.data (not options); the reload follows the options save
                    self.hass.config_entries.async_update_entry(entry, data=data)
                    from .coordinator import issue_id_invalid_key
                    ir.async_delete_issue(self.hass, DOMAIN, issue_id_invalid_key(entry.entry_id))
                return self.async_create_entry(title="", data=_clean(user_input))
        store = get_feeds(self.hass).store
        routes = await self.hass.async_add_executor_job(store.routes_for_stop, entry.data[CONF_STOP_ID])
        return self.async_show_form(step_id="init", errors=errors,
                                    data_schema=_settings_schema(routes, dict(entry.options), True),
                                    description_placeholders={
                                        "api": "✔" if entry.data.get(CONF_API_KEY) else "–"})

    async def async_step_journey(self, user_input: dict[str, Any] | None = None):
        o = self.config_entry.options
        if user_input is not None:
            return self.async_create_entry(title="", data={
                CONF_COUNT: int(user_input[CONF_COUNT]),
                CONF_MIN_TRANSFER: int(user_input[CONF_MIN_TRANSFER]),
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_REALTIME: bool(user_input[CONF_REALTIME])})
        return self.async_show_form(step_id="journey", data_schema=vol.Schema({
            vol.Optional(CONF_COUNT, default=o.get(CONF_COUNT, DEFAULT_COUNT)): _num(1, 6),
            vol.Optional(CONF_MIN_TRANSFER, default=o.get(CONF_MIN_TRANSFER, DEFAULT_MIN_TRANSFER)):
                _num(0, 20, 1, "min"),
            vol.Optional(CONF_SCAN_INTERVAL, default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
                _num(MIN_SCAN_INTERVAL, 600, 5, "s"),
            vol.Optional(CONF_REALTIME, default=o.get(CONF_REALTIME, True)): BooleanSelector()}))

    async def async_step_simple(self, user_input: dict[str, Any] | None = None):
        o = self.config_entry.options
        if user_input is not None:
            return self.async_create_entry(title="", data={
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])})
        return self.async_show_form(step_id="simple", data_schema=vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
                _num(MIN_SCAN_INTERVAL, 3600, 5, "s")}))
