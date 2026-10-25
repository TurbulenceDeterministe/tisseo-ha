"""Sensors: next N departures (timestamp) + disruptions for one stop."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_STOP_ID, CONF_STOP_NAME, DOMAIN
from .coordinator import TisseoCoordinator
from .data.const import TZ


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: TisseoCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [TisseoDepartureSensor(coordinator, entry, i)
                                    for i in range(coordinator.count)]
    entities.append(TisseoAlertsSensor(coordinator, entry))
    async_add_entities(entities)


class _Base(CoordinatorEntity[TisseoCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: TisseoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        stop_name = entry.data.get(CONF_STOP_NAME, entry.data[CONF_STOP_ID])
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Tisséo {stop_name}",
            manufacturer="Tisséo (open data)",
            model=entry.data[CONF_STOP_ID],
            entry_type=DeviceEntryType.SERVICE,
        )


class TisseoDepartureSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: TisseoCoordinator, entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator, entry)
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_departure_{index + 1}"
        self._attr_translation_key = "departure"
        self._attr_translation_placeholders = {"index": str(index + 1)}

    @property
    def _dep(self):
        deps = self.coordinator.data.departures if self.coordinator.data else []
        return deps[self._index] if self._index < len(deps) else None

    @property
    def native_value(self) -> datetime | None:
        dep = self._dep
        return dep.expected if dep else None

    @property
    def icon(self) -> str:
        dep = self._dep
        return {"metro": "mdi:subway-variant", "tram": "mdi:tram",
                "aerial_lift": "mdi:gondola"}.get(dep.mode if dep else "", "mdi:bus-clock")

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        now = datetime.now(TZ)
        attrs: dict = {"realtime_feed_ok": bool(data and data.realtime_available)}
        dep = self._dep
        if dep:
            d = dep.as_dict(now)
            attrs.update({
                "line": d["line"], "line_name": d["line_name"], "route_id": d["route_id"],
                "mode": d["mode"], "color": d["color"], "text_color": d["text_color"], "destination": d["destination"],
                "stop_id": d["stop_id"], "stop_name": d["stop_name"],
                "scheduled": d["scheduled"], "expected": d["expected"],
                "minutes": d["minutes"], "realtime": d["realtime"],
                "delay_seconds": d["delay"],
                "delay_minutes": round(d["delay"] / 60, 1) if d["delay"] is not None else None,
                "trip_id": d["trip_id"],
                "realtime_source": d["realtime_source"],
                "live_coverage": d["live_coverage"],
                "line_alerts": [a.header for a in (data.alerts if data else [])
                                if dep.route_id in a.route_ids],
            })
        if self._index == 0 and data:
            attrs["upcoming"] = [
                {k: v for k, v in x.as_dict(now).items()
                 if k in ("line", "destination", "expected", "scheduled", "minutes",
                          "realtime", "delay", "color", "text_color", "mode",
                          "realtime_source", "live_coverage", "trip_id", "route_id",
                          "canceled")}
                for x in data.departures]
            attrs["gtfs_built"] = data.gtfs_version
            attrs["realtime_feed_time"] = data.feed_timestamp.isoformat() if data.feed_timestamp else None
            attrs["realtime_feed_url"] = data.feed_url
            attrs["live_lines"] = data.live_lines
        return attrs


class TisseoAlertsSensor(_Base):
    _attr_icon = "mdi:alert-circle-outline"
    _attr_translation_key = "alerts"
    _attr_native_unit_of_measurement = "alerts"

    def __init__(self, coordinator: TisseoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alerts"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.alerts) if self.coordinator.data else 0

    @property
    def extra_state_attributes(self) -> dict:
        alerts = self.coordinator.data.alerts if self.coordinator.data else []
        return {
            "alerts": [a.as_dict() for a in alerts],
            "headlines": [a.header for a in alerts],
            "line_alerts": sum(1 for a in alerts if not a.network_wide),
        }
