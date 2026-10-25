"""Diagnostics download (the API key is redacted)."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DOMAIN

TO_REDACT = {CONF_API_KEY, "key"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coord = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    feeds = hass.data.get(DOMAIN, {}).get("feeds")
    out: dict = {
        "entry": {"title": entry.title, "data": async_redact_data(dict(entry.data), TO_REDACT),
                  "options": async_redact_data(dict(entry.options), TO_REDACT)},
        "health": {k: v.as_dict() for k, v in (coord.health().items() if coord else [])},
    }
    if feeds is not None:
        meta = await hass.async_add_executor_job(feeds.store.meta) if await hass.async_add_executor_job(
            feeds.store.is_valid) else {}
        out["gtfs"] = {"index_meta": meta, "index_stats": feeds.index_stats,
                       "required_stops": sorted(feeds.required_stops or []),
                       "trunk_lines_indexed": feeds.trunk,
                       "realtime_source": feeds.rt_source_url, "realtime_error": feeds.rt_error,
                       "feed_age_s": feeds.feed_age()}
    data = getattr(coord, "data", None)
    if data is not None and hasattr(data, "all_departures"):
        out["departures"] = [d.as_dict() for d in data.all_departures]
        out["alerts"] = [a.as_dict() for a in data.alerts]
        out["api_used"] = data.api_used
        out["api_error"] = data.api_error
        out["timetable"] = data.timetable
    elif data is not None and hasattr(data, "connections"):
        out["connections"] = [c.as_dict() for c in data.connections]
    return async_redact_data(out, TO_REDACT)
