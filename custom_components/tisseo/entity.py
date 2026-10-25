"""Shared entity helpers (device info per config entry)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import (CONF_API_KEY, CONF_DESTINATION, CONF_DESTINATION_NAME, CONF_ENTRY_TYPE,
                    CONF_ORIGIN, CONF_ORIGIN_NAME, CONF_PARK_ID, CONF_PARK_NAME,
                    CONF_STATION_ID, CONF_STATION_NAME, CONF_STOP_ID, CONF_STOP_NAME, DOMAIN,
                    TYPE_BIKE, TYPE_JOURNEY, TYPE_PARKRIDE, TYPE_STOP)


def device_info(entry: ConfigEntry) -> DeviceInfo:
    t = entry.data.get(CONF_ENTRY_TYPE, TYPE_STOP)
    if t == TYPE_JOURNEY:
        name = f"Tisséo {entry.data.get(CONF_ORIGIN_NAME)} → {entry.data.get(CONF_DESTINATION_NAME)}"
        model = f"{entry.data[CONF_ORIGIN]} → {entry.data[CONF_DESTINATION]}"
        manufacturer = "Tisséo (open data)"
    elif t == TYPE_BIKE:
        name = f"VélôToulouse {entry.data.get(CONF_STATION_NAME)}"
        model, manufacturer = f"station {entry.data[CONF_STATION_ID]}", "VélôToulouse (GBFS)"
    elif t == TYPE_PARKRIDE:
        name = f"Tisséo P+R {entry.data.get(CONF_PARK_NAME)}"
        model, manufacturer = entry.data[CONF_PARK_ID], "Toulouse Métropole open data"
    else:
        name = f"Tisséo {entry.data.get(CONF_STOP_NAME, entry.data.get(CONF_STOP_ID))}"
        model = entry.data[CONF_STOP_ID]
        manufacturer = "Tisséo (API v2 + open data)" if entry.data.get(CONF_API_KEY) else "Tisséo (open data)"
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=name,
                      manufacturer=manufacturer, model=model, entry_type=DeviceEntryType.SERVICE)
