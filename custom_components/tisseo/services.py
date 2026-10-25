"""Websocket command and service returning the calls of one trip (card trip dialog)."""
from __future__ import annotations

from datetime import datetime

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .data.trips import trip_stops

SERVICE_GET_TRIP = "get_trip"
GET_TRIP_SCHEMA = vol.Schema({
    vol.Required("trip_id"): cv.string,
    vol.Optional("stop_id"): cv.string,
    vol.Optional("scheduled"): cv.string,
})


async def async_trip_stops(hass: HomeAssistant, trip_id: str, stop_id: str | None = None,
                           scheduled: str | None = None) -> dict | None:
    feeds = hass.data.get(DOMAIN, {}).get("feeds")
    if feeds is None:
        raise HomeAssistantError("No Tisséo stop is configured")
    sched = None
    if scheduled:
        try:
            sched = datetime.fromisoformat(scheduled)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid scheduled time: {scheduled}") from err
    rt = feeds._rt  # noqa: SLF001 - last shared GTFS-RT snapshot, no extra download
    return await hass.async_add_executor_job(trip_stops, feeds.store, rt, trip_id, stop_id, sched)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_trip_stops)

    async def _get_trip(call: ServiceCall) -> ServiceResponse:
        res = await async_trip_stops(hass, call.data["trip_id"], call.data.get("stop_id"),
                                     call.data.get("scheduled"))
        if res is None:
            raise HomeAssistantError(f"Trip {call.data['trip_id']} is not in the index")
        return res

    if not hass.services.has_service(DOMAIN, SERVICE_GET_TRIP):
        hass.services.async_register(DOMAIN, SERVICE_GET_TRIP, _get_trip, schema=GET_TRIP_SCHEMA,
                                     supports_response=SupportsResponse.ONLY)


@websocket_api.websocket_command({
    vol.Required("type"): "tisseo/trip_stops",
    vol.Required("trip_id"): str,
    vol.Optional("stop_id"): str,
    vol.Optional("scheduled"): str,
})
@websocket_api.async_response
async def ws_trip_stops(hass: HomeAssistant, connection, msg) -> None:
    try:
        res = await async_trip_stops(hass, msg["trip_id"], msg.get("stop_id"), msg.get("scheduled"))
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "unavailable", str(err))
        return
    if res is None:
        connection.send_error(msg["id"], "not_found", "Trip not in the index")
        return
    connection.send_result(msg["id"], res)
