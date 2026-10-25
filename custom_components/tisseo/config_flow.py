"""Config flow: search a stop by name/ID, pick it, then (optionally) filter lines."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (BooleanSelector, NumberSelector,
                                            NumberSelectorConfig, NumberSelectorMode,
                                            SelectOptionDict, SelectSelector,
                                            SelectSelectorConfig, SelectSelectorMode,
                                            TextSelector)

from . import get_feeds
from .const import (CONF_COUNT, CONF_LINES, CONF_NETWORK_ALERTS, CONF_QUERY, CONF_REALTIME,
                    CONF_SCAN_INTERVAL, CONF_STOP_ID, CONF_STOP_NAME, DEFAULT_COUNT,
                    DEFAULT_SCAN_INTERVAL, DOMAIN, GTFS_MAX_AGE, MIN_SCAN_INTERVAL)

_LOGGER = logging.getLogger(__name__)


def _settings_schema(routes, defaults: dict) -> vol.Schema:
    options = [SelectOptionDict(value=r.route_id,
                                label=f"{r.short_name} – {r.long_name}" if r.long_name else r.short_name)
               for r in routes]
    return vol.Schema({
        vol.Optional(CONF_LINES, default=defaults.get(CONF_LINES, [])): SelectSelector(
            SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)),
        vol.Optional(CONF_COUNT, default=defaults.get(CONF_COUNT, DEFAULT_COUNT)): NumberSelector(
            NumberSelectorConfig(min=1, max=10, step=1, mode=NumberSelectorMode.BOX)),
        vol.Optional(CONF_SCAN_INTERVAL,
                     default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): NumberSelector(
            NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=600, step=5,
                                 unit_of_measurement="s", mode=NumberSelectorMode.BOX)),
        vol.Optional(CONF_NETWORK_ALERTS,
                     default=defaults.get(CONF_NETWORK_ALERTS, True)): BooleanSelector(),
        vol.Optional(CONF_REALTIME,
                     default=defaults.get(CONF_REALTIME, True)): BooleanSelector(),
    })


def _clean(user_input: dict) -> dict:
    out = dict(user_input)
    out[CONF_COUNT] = int(out.get(CONF_COUNT, DEFAULT_COUNT))
    out[CONF_SCAN_INTERVAL] = int(out.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    out[CONF_LINES] = list(out.get(CONF_LINES) or [])
    return out


class TisseoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._matches: dict[str, str] = {}
        self._stop_id: str | None = None
        self._stop_name: str | None = None
        self._routes = []

    async def _ensure_store(self):
        feeds = get_feeds(self.hass)
        await feeds.ensure_gtfs(GTFS_MAX_AGE)  # first run: download + index (~10-60 s)
        return feeds.store

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                store = await self._ensure_store()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not prepare the Tisséo GTFS index")
                errors["base"] = "cannot_connect"
            else:
                query = user_input[CONF_QUERY]
                results = await self.hass.async_add_executor_job(store.search_stops, query, 25)
                if not results:
                    errors[CONF_QUERY] = "no_stop"
                else:
                    self._matches = {}
                    for stop, lines in results:
                        kind = "stop area" if stop.is_area else f"stop point {stop.code}".strip()
                        self._matches[stop.stop_id] = (
                            f"{stop.name} ({kind}) – lines: {', '.join(lines) or '?'}")
                        if stop.is_area and len(results) <= 3:
                            # Offer the individual platforms (one direction each) too.
                            for kid in await self.hass.async_add_executor_job(
                                    store.child_stop_ids, stop.stop_id):
                                if kid == stop.stop_id:
                                    continue
                                routes = await self.hass.async_add_executor_job(
                                    store.routes_for_stop, kid)
                                self._matches[kid] = (
                                    f"  └ {stop.name} platform {kid.split(':')[-1]} – lines: "
                                    f"{', '.join(r.short_name for r in routes)}")
                    return await self.async_step_stop()
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_QUERY): TextSelector()}))

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
        if user_input is not None:
            data = _clean(user_input)
            await self.async_set_unique_id(
                f"{self._stop_id}|{','.join(sorted(data[CONF_LINES]))}")
            self._abort_if_unique_id_configured()
            title = self._stop_name
            if data[CONF_LINES]:
                names = [r.short_name for r in self._routes if r.route_id in data[CONF_LINES]]
                title = f"{self._stop_name} ({', '.join(names)})"
            return self.async_create_entry(
                title=title,
                data={CONF_STOP_ID: self._stop_id, CONF_STOP_NAME: self._stop_name},
                options=data)
        return self.async_show_form(step_id="settings",
                                    data_schema=_settings_schema(self._routes, {}),
                                    description_placeholders={"stop": self._stop_name or ""})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TisseoOptionsFlow()


class TisseoOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=_clean(user_input))
        store = get_feeds(self.hass).store
        routes = await self.hass.async_add_executor_job(
            store.routes_for_stop, self.config_entry.data[CONF_STOP_ID])
        return self.async_show_form(step_id="init",
                                    data_schema=_settings_schema(routes, dict(self.config_entry.options)))
