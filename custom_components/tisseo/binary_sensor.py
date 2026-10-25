"""Binary sensors: 'leave now' and 'timetable change tomorrow' per stop."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_ENTRY_TYPE, DOMAIN, TYPE_STOP
from .entity import device_info
from .sensor import _Ticking, leave_attrs


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_ENTRY_TYPE, TYPE_STOP) != TYPE_STOP:
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LeaveNowSensor(coordinator, entry), TimetableChangeSensor(coordinator, entry)])


class _Base(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = device_info(entry)


class LeaveNowSensor(_Ticking, _Base):
    _attr_translation_key = "leave_now"
    _attr_icon = "mdi:walk"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_leave_now"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.leave()["leave_now"])

    @property
    def extra_state_attributes(self) -> dict:
        return leave_attrs(self.coordinator.leave())


class TimetableChangeSensor(_Base):
    _attr_translation_key = "timetable_change"
    _attr_icon = "mdi:calendar-alert"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_timetable_change"

    @property
    def is_on(self) -> bool | None:
        t = self.coordinator.data.timetable if self.coordinator.data else None
        return None if t is None else bool(t["changed"])

    @property
    def extra_state_attributes(self) -> dict:
        t = self.coordinator.data.timetable if self.coordinator.data else None
        return dict(t or {})
