"""Sensors: departures, disruptions, leave-in, journeys, bikes, park-and-ride, diagnostics."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.sensor import (SensorDeviceClass, SensorEntity,
                                             SensorStateClass)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (ATTRIBUTION, ATTRIBUTION_API, ATTRIBUTION_BIKE, ATTRIBUTION_PARKRIDE,
                    CONF_API_KEY, CONF_ENTRY_TYPE, DOMAIN, TYPE_BIKE, TYPE_JOURNEY,
                    TYPE_PARKRIDE, TYPE_STOP)
from .coordinator import TisseoCoordinator
from .data.const import TZ
from .entity import device_info

UPCOMING_KEYS = ("line", "destination", "expected", "scheduled", "minutes", "realtime", "delay",
                 "color", "text_color", "mode", "realtime_source", "live_coverage", "trip_id",
                 "route_id", "canceled", "stop_id")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    t = entry.data.get(CONF_ENTRY_TYPE, TYPE_STOP)
    entities: list[SensorEntity] = []
    if t == TYPE_STOP:
        entities += [TisseoDepartureSensor(coordinator, entry, i) for i in range(coordinator.count)]
        entities += [TisseoAlertsSensor(coordinator, entry), TisseoLeaveInSensor(coordinator, entry)]
    elif t == TYPE_JOURNEY:
        entities.append(TisseoJourneySensor(coordinator, entry))
    elif t == TYPE_BIKE:
        entities += [BikeSensor(coordinator, entry, "bikes"), BikeSensor(coordinator, entry, "docks")]
    elif t == TYPE_PARKRIDE:
        entities.append(ParkRideSensor(coordinator, entry))
    kinds = ["health", "last_success", "success_rate"]
    if t != TYPE_PARKRIDE:  # P+R data is static capacity: no feed timestamp to age
        kinds.append("feed_age")
    entities += [HealthSensor(coordinator, entry, k) for k in kinds]
    async_add_entities(entities)


class _Base(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = device_info(entry)
        if entry.data.get(CONF_API_KEY):
            self._attr_attribution = ATTRIBUTION_API


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
                "mode": d["mode"], "color": d["color"], "text_color": d["text_color"],
                "destination": d["destination"], "stop_id": d["stop_id"],
                "stop_name": d["stop_name"], "scheduled": d["scheduled"],
                "expected": d["expected"], "minutes": d["minutes"], "realtime": d["realtime"],
                "delay_seconds": d["delay"],
                "delay_minutes": round(d["delay"] / 60, 1) if d["delay"] is not None else None,
                "trip_id": d["trip_id"], "realtime_source": d["realtime_source"],
                "live_coverage": d["live_coverage"],
                "line_alerts": [a.header for a in (data.alerts if data else [])
                                if dep.route_id in a.route_ids],
            })
        if self._index == 0 and data:
            attrs["upcoming"] = [{k: v for k, v in x.as_dict(now).items() if k in UPCOMING_KEYS}
                                 for x in data.all_departures]
            attrs["gtfs_built"] = data.gtfs_version
            attrs["realtime_feed_time"] = data.feed_timestamp.isoformat() if data.feed_timestamp else None
            attrs["realtime_feed_url"] = data.feed_url
            attrs["live_lines"] = data.live_lines
            attrs["official_api"] = "active" if data.api_used else (
                "error" if self._entry.data.get(CONF_API_KEY) else "not_configured")
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


def leave_attrs(info: dict) -> dict:
    d = info["departure"]
    return {
        "walking_time": info["walking_time"], "buffer": info["buffer"],
        "leave_at": info["leave_at"].isoformat() if info["leave_at"] else None,
        "leave_in": info["leave_in"],
        "next_catchable": None if d is None else {
            "line": d.line, "destination": d.destination, "expected": d.expected.isoformat(),
            "realtime": d.realtime, "trip_id": d.trip_id, "color": d.color},
    }


class _Ticking:
    """Re-evaluate every 15 s between coordinator refreshes (leave-now timing)."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_time_interval(
            self.hass, self._tick, timedelta(seconds=15)))

    @callback
    def _tick(self, _now) -> None:
        self.async_write_ha_state()


class TisseoLeaveInSensor(_Ticking, _Base):
    _attr_icon = "mdi:walk"
    _attr_translation_key = "leave_in"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, coordinator: TisseoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_leave_in"

    @property
    def native_value(self):
        return self.coordinator.leave()["leave_in"]

    @property
    def extra_state_attributes(self) -> dict:
        return leave_attrs(self.coordinator.leave())


class TisseoJourneySensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:transit-connection-variant"
    _attr_translation_key = "journey"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_journey"

    @property
    def _first(self):
        conns = self.coordinator.data.connections if self.coordinator.data else []
        return conns[0] if conns else None

    @property
    def native_value(self):
        c = self._first
        return c.departure if c else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        c = self._first
        attrs = {"origin": self._entry.data.get("origin_name"),
                 "destination": self._entry.data.get("destination_name"),
                 "realtime_feed_ok": bool(data and data.realtime_available)}
        if c:
            d = c.as_dict()
            attrs.update({k: d[k] for k in ("departure", "arrival", "duration_min", "transfers",
                                            "lines", "realtime", "transfer_at_risk", "legs")})
        attrs["connections"] = [x.as_dict() for x in (data.connections if data else [])]
        return attrs


class BikeSensor(_Base):
    _attr_attribution = ATTRIBUTION_BIKE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry, kind: str) -> None:
        super().__init__(coordinator, entry)
        self._attr_attribution = ATTRIBUTION_BIKE
        self._kind = kind
        self._attr_unique_id = f"{entry.entry_id}_{kind}"
        self._attr_translation_key = f"bike_{kind}"
        self._attr_icon = "mdi:bicycle" if kind == "bikes" else "mdi:parking"
        self._attr_native_unit_of_measurement = "bikes" if kind == "bikes" else "docks"

    @property
    def available(self) -> bool:
        d = self.coordinator.data
        return super().available and d is not None and d.status is not None

    @property
    def native_value(self):
        st = self.coordinator.data.status
        return st.bikes if self._kind == "bikes" else st.docks

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        st, info = d.status, d.station
        attrs = {
            "station_id": st.station_id, "name": info.name if info else None,
            "address": info.address if info else None,
            "capacity": info.capacity if info else None,
            "latitude": info.lat if info else None, "longitude": info.lon if info else None,
            "installed": st.installed, "renting": st.renting, "returning": st.returning,
            "last_reported": st.last_reported.isoformat() if st.last_reported else None,
            "feed_time": d.feed_time.isoformat() if d.feed_time else None,
        }
        if self._kind == "bikes":
            attrs.update(mechanical=st.mechanical, electric=st.electric, disabled=st.bikes_disabled)
        else:
            attrs.update(disabled=st.docks_disabled)
        return attrs


class ParkRideSensor(_Base):
    _attr_icon = "mdi:car-multiple"
    _attr_translation_key = "parkride_capacity"
    _attr_native_unit_of_measurement = "spaces"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_attribution = ATTRIBUTION_PARKRIDE
        self._attr_unique_id = f"{entry.entry_id}_capacity"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def native_value(self):
        return self.coordinator.data.capacity

    @property
    def extra_state_attributes(self) -> dict:
        p = self.coordinator.data
        return {
            "name": p.name, "address": p.address, "city": p.city, "pmr_spaces": p.pmr,
            "bike_spaces": p.bikes, "ev_spaces": p.ev, "info": p.info,
            "latitude": p.lat, "longitude": p.lon,
            # Live occupancy is not published as keyless open data (only on tisseo.fr).
            "live_availability": "not_available_as_open_data",
        }


class HealthSensor(_Base):
    """Diagnostic sensors: feed health, last success, success rate, GTFS-RT feed age."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry, kind: str) -> None:
        super().__init__(coordinator, entry)
        self._kind = kind
        self._attr_unique_id = f"{entry.entry_id}_{kind}"
        self._attr_translation_key = f"feed_{kind}"
        if kind == "health":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["ok", "degraded", "down"]
            self._attr_icon = "mdi:heart-pulse"
        elif kind == "last_success":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif kind == "success_rate":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:percent"
        else:
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        return True  # health must be visible precisely when updates fail

    def _primary(self):
        h = self.coordinator.health()
        return h.get(self.coordinator.primary_feed)

    @property
    def native_value(self):
        h = self.coordinator.health()
        primary = self._primary()
        if self._kind == "health":
            # feeds never attempted yet (no results) don't count against health
            states = [x.state for x in h.values() if x.results or x.breaker_open]
            # the primary feed decides; a failing secondary feed (e.g. API) degrades
            st = primary.state if primary else "down"
            if st == "ok" and any(s != "ok" for s in states):
                st = "degraded"
            return st
        if primary is None:
            return None
        if self._kind == "last_success":
            return datetime.fromtimestamp(primary.last_success, TZ) if primary.last_success else None
        if self._kind == "success_rate":
            r = primary.success_rate
            return None if r is None else round(r * 100, 1)
        feeds = getattr(self.coordinator, "feeds", None)
        if feeds is not None:
            age = feeds.feed_age()
            return None if age is None else round(age)
        data = self.coordinator.data
        ts = getattr(data, "feed_time", None) if data is not None else None
        return round((datetime.now(TZ) - ts).total_seconds()) if ts else None

    @property
    def extra_state_attributes(self) -> dict:
        if self._kind != "health":
            return {"feed": self.coordinator.primary_feed}
        return {"feeds": {k: v.as_dict() for k, v in self.coordinator.health().items()},
                "primary_feed": self.coordinator.primary_feed}
