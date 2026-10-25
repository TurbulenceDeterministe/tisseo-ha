"""Home Assistant tests with the synthetic feed (no network; API responses are mocked)."""
import json
from datetime import datetime, timedelta

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tisseo.const import DOMAIN, EVENT_DELAY, EVENT_DISRUPTION
from custom_components.tisseo.data.api import SCHEDULES_URL
from custom_components.tisseo.data.const import TZ
from custom_components.tisseo.data.health import FeedHealth
from custom_components.tisseo.data.realtime import SCHEDULED, parse_realtime

from .conftest import make_feed

NOW = datetime(2026, 10, 24, 9, 58, tzinfo=TZ)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeFeeds:
    def __init__(self, store, rt):
        self.store, self._rt, self.rt_error = store, rt, None
        self.rt_source_url = "https://example.invalid/GtfsRt.pb"
        self.health = {"gtfs_rt": FeedHealth("gtfs_rt"), "gtfs": FeedHealth("gtfs")}
        self.required_stops = set()
        self.index_calls = []
        self.trunk_calls = []
        self.trunk = False
        self.index_stats = {"trips_kept": 1}

    async def ensure_gtfs(self, *a, **k):
        self.health["gtfs"].record(True)
        return False

    async def ensure_index(self, stops=None, trunk=None):
        self.index_calls.append(set(stops or []))
        self.trunk_calls.append(trunk)
        return False

    async def realtime(self):
        self.health["gtfs_rt"].record(True)
        return self._rt

    def feed_age(self):
        return 42.0


def _rt(alerts=None):
    return parse_realtime(make_feed(
        trip_updates=[("B1", "line:B", SCHEDULED,
                       [(2, "stop_point:SP_1", NOW.timestamp() + 9 * 60, 120, False)])],
        alerts=alerts if alerts is not None else [("a1", "Ligne B perturbée", ["line:B"], [], []),
                                                  ("a9", "Autre ligne", ["line:99"], [], [])],
        ts=int(NOW.timestamp())))


@pytest.fixture
def feeds(hass, store):
    f = FakeFeeds(store, _rt())
    hass.data.setdefault(DOMAIN, {})["feeds"] = f
    return f


async def _add_stop(hass, extra=None, stop="stop_area:SA_1", query="jeanne", menu="stop_search"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": menu})
    if menu == "stop_search":
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": query})
    assert result["step_id"] == "stop"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_id": stop})
    assert result["step_id"] == "settings"
    data = {"lines": [], "count": 2, "scan_interval": 60, "network_alerts": True}
    data.update(extra or {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    await hass.async_block_till_done()
    return result


def _state(hass, suffix, domain="sensor"):
    return next(s for s in hass.states.async_all(domain) if s.entity_id.endswith(suffix))


async def test_flow_and_sensors(hass, feeds, freezer):
    freezer.move_to(NOW)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "stop_search"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "nowhere"})
    assert result["errors"] == {"query": "no_stop"}
    result = await _add_stop(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jeanne d'Arc" and "api_key" not in result["data"]

    dep1, dep2 = _state(hass, "departure_1"), _state(hass, "departure_2")
    alerts = _state(hass, "disruptions")
    assert dep1.attributes["line"] == "B" and dep1.attributes["realtime"] is True
    assert dep1.attributes["delay_seconds"] == 120
    assert dep1.attributes["realtime_source"] == "gtfs_rt"
    assert dep1.attributes["live_coverage"] == "live"
    assert dep1.attributes["line_alerts"] == ["Ligne B perturbée"]
    assert dep1.attributes["live_lines"] == ["B"]
    assert dep1.attributes["official_api"] == "not_configured"
    assert datetime.fromisoformat(dep1.state) == datetime(2026, 10, 24, 10, 7, tzinfo=TZ)
    assert dep2.attributes["line"] == "15" and dep2.attributes["realtime"] is False
    assert dep2.attributes["live_coverage"] == "not_published"
    assert len(dep1.attributes["upcoming"]) == 3  # all departures in the window (not just `count`)
    assert alerts.state == "1" and alerts.attributes["headlines"] == ["Ligne B perturbée"]
    # lean index requested for the configured stop
    assert feeds.index_calls[-1] == {"stop_area:SA_1"}

    # diagnostics entities
    assert _state(hass, "feed_health").state == "ok"
    assert float(_state(hass, "feed_success_rate").state) == 100.0
    assert _state(hass, "real_time_feed_age").state == "42"
    # timetable change: 2026-10-25 (Sunday, EXTRA service) differs from last/next week
    tt = _state(hass, "timetable_change_tomorrow", "binary_sensor")
    assert tt.attributes["tomorrow"] == "2026-10-25" and "description" in tt.attributes

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"lines": ["line:15"], "count": 2, "scan_interval": 60,
                            "network_alerts": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert _state(hass, "departure_1").attributes["line"] == "15"
    assert _state(hass, "disruptions").state == "0"


async def test_realtime_can_be_disabled(hass, feeds, freezer):
    freezer.move_to(NOW)
    await _add_stop(hass, {"realtime": False})
    dep1 = _state(hass, "departure_1")
    assert dep1.attributes["realtime"] is False and dep1.attributes["live_coverage"] == "disabled"
    assert datetime.fromisoformat(dep1.state) == datetime(2026, 10, 24, 10, 5, tzinfo=TZ)


async def test_leave_now(hass, feeds, freezer):
    freezer.move_to(NOW)  # 09:58; B1 expected 10:07 (RT), T15 10:12, B2 10:25
    await _add_stop(hass, {"walking_time": 5, "buffer": 2})
    leave = _state(hass, "leave_now", "binary_sensor")
    leave_in = _state(hass, "leave_in")
    assert leave.state == "off"
    assert leave.attributes["next_catchable"]["line"] == "B"
    assert leave.attributes["leave_at"].startswith("2026-10-24T10:00:00")
    assert leave_in.state == "2"
    freezer.move_to(NOW + timedelta(minutes=2, seconds=5))
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done()
    assert _state(hass, "leave_now", "binary_sensor").state == "on"
    assert _state(hass, "leave_in").state == "0"


async def test_nearby_flow(hass, feeds, freezer):
    freezer.move_to(NOW)
    hass.config.latitude, hass.config.longitude = 43.61, 1.43
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "nearby"})
    assert result["step_id"] == "stop"
    opts = result["data_schema"].schema["stop_id"].config["options"]
    assert opts[0]["value"] == "stop_area:SA_3" and opts[0]["label"].startswith("Compans – 0 m")
    assert len(opts) <= 10
    hass.config.latitude, hass.config.longitude = 48.85, 2.35  # Paris: nothing nearby
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "nearby"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "no_nearby"


async def test_journey_flow_and_sensor(hass, feeds, freezer):
    freezer.move_to(NOW)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "journey"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin_query": "compans", "destination_query": "jeanne"})
    assert result["step_id"] == "journey_pick"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"origin": "stop_area:SA_3", "destination": "stop_area:SA_1",
                            "count": 3, "min_transfer": 3})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "Compans → Jeanne d'Arc"
    await hass.async_block_till_done()
    s = _state(hass, "next_connection")
    assert s.attributes["transfers"] == 1 and s.attributes["lines"] == ["A", "B"]
    assert s.attributes["duration_min"] == 25 and len(s.attributes["legs"]) == 2
    assert feeds.index_calls[-1] == {"stop_area:SA_3", "stop_area:SA_1"}


async def test_api_key_flow_merge_and_reauth(hass, feeds, freezer, aioclient_mock):
    freezer.move_to(NOW)
    payload = {"departures": {"departure": [
        {"dateTime": "2026-10-24 10:14:00", "realTime": "yes",
         "line": {"id": "line:15", "shortName": "15", "name": "Bus 15", "color": "(160,103,15)"},
         "destination": [{"name": "Etats-Unis"}]}]}}
    aioclient_mock.get(SCHEDULES_URL, text=json.dumps(payload))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "stop_search"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "jeanne"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_id": "stop_area:SA_1"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lines": [], "count": 3, "scan_interval": 60, "network_alerts": True,
                            "api_key": "MYKEY"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["api_key"] == "MYKEY" and "api_key" not in result["options"]
    await hass.async_block_till_done()
    # the key is sent as a query parameter, as documented
    assert any(str(c[1]).find("key=MYKEY") > 0 for c in aioclient_mock.mock_calls)
    up = _state(hass, "departure_1").attributes["upcoming"]
    t15 = next(d for d in up if d["trip_id"] == "T15")
    assert t15["realtime_source"] == "tisseo_api" and t15["delay"] == 120
    assert _state(hass, "departure_1").attributes["official_api"] == "active"

    # diagnostics redact the key
    from custom_components.tisseo.diagnostics import async_get_config_entry_diagnostics
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "MYKEY" not in json.dumps(diag, default=str)
    assert diag["entry"]["data"]["api_key"] == "**REDACTED**"

    # the key gets revoked -> repair issue + reauth flow, open data keeps working
    aioclient_mock.clear_requests()
    aioclient_mock.get(SCHEDULES_URL, status=401)
    coord = hass.data[DOMAIN][entry.entry_id]
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.api_invalid and coord.last_update_success
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"invalid_api_key_{entry.entry_id}")
    flows = [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"]
    assert len(flows) == 1
    assert _state(hass, "departure_1").attributes["official_api"] == "error"
    assert _state(hass, "feed_health").state == "degraded"
    # reauth with an empty key removes it
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert "api_key" not in hass.config_entries.async_entries(DOMAIN)[0].data
    assert not ir.async_get(hass).async_get_issue(DOMAIN, f"invalid_api_key_{entry.entry_id}")


async def test_invalid_key_rejected_in_flow(hass, feeds, freezer, aioclient_mock):
    freezer.move_to(NOW)
    aioclient_mock.get(SCHEDULES_URL, status=403)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "stop_search"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "jeanne"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_id": "stop_area:SA_1"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lines": [], "count": 3, "scan_interval": 60, "api_key": "BAD"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"api_key": "invalid_key"}


async def test_events(hass, feeds, freezer):
    freezer.move_to(NOW)
    disruptions, delays = [], []
    hass.bus.async_listen(EVENT_DISRUPTION, lambda e: disruptions.append(e.data))
    hass.bus.async_listen(EVENT_DELAY, lambda e: delays.append(e.data))
    await _add_stop(hass, {"delay_threshold": 1})
    assert disruptions == []  # existing alerts are not announced at startup
    assert len(delays) == 1 and delays[0]["trip_id"] == "B1" and delays[0]["delay_minutes"] == 2.0
    feeds._rt = _rt(alerts=[("a1", "Ligne B perturbée", ["line:B"], [], []),
                            ("a2", "Ligne 15 déviée", ["line:15"], [], [])])
    coord = hass.data[DOMAIN][hass.config_entries.async_entries(DOMAIN)[0].entry_id]
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert [d["alert_id"] for d in disruptions] == ["a2"] and disruptions[0]["lines"] == ["15"]
    assert len(delays) == 1  # fired once per trip


async def test_trip_stops_ws_and_service(hass, feeds, freezer, hass_ws_client):
    client = await hass_ws_client(hass)  # authenticate before freezing time
    freezer.move_to(NOW)
    await _add_stop(hass)
    await client.send_json({"id": 1, "type": "tisseo/trip_stops", "trip_id": "B1",
                            "stop_id": "stop_area:SA_2", "scheduled": "2026-10-24T10:00:00+02:00"})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert [s["name"] for s in msg["result"]["stops"]] == ["Capitole", "Jeanne d'Arc", "Terminus"]
    assert msg["result"]["stops"][1]["realtime"] is True
    await client.send_json({"id": 2, "type": "tisseo/trip_stops", "trip_id": "nope"})
    msg = await client.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "not_found"
    res = await hass.services.async_call(DOMAIN, "get_trip", {"trip_id": "T15"}, blocking=True,
                                         return_response=True)
    assert res["line"] == "15" and len(res["stops"]) == 2


async def test_bike_and_parkride(hass, freezer, aioclient_mock):
    freezer.move_to(NOW)
    base = "https://api.cyclocity.fr/contracts/toulouse/gbfs/v3/"
    aioclient_mock.get(base + "gbfs.json", json={"data": {"feeds": [
        {"name": "station_information", "url": base + "station_information.json"},
        {"name": "station_status", "url": base + "station_status.json"}]}})
    aioclient_mock.get(base + "station_information.json", json={"data": {"stations": [
        {"station_id": "1", "name": [{"text": "00001 - POIDS DE L'HUILE", "language": "fr"}],
         "lat": 43.6044, "lon": 1.4449, "capacity": 20}]}})
    aioclient_mock.get(base + "station_status.json", json={"last_updated": "2026-10-24T07:57:00Z", "data": {
        "stations": [{"station_id": "1", "num_vehicles_available": 5,
                      "vehicle_types_available": [{"vehicle_type_id": "electrical", "count": 2},
                                                  {"vehicle_type_id": "mechanical", "count": 3}],
                      "num_docks_available": 14, "is_installed": True, "is_renting": True,
                      "is_returning": True}]}})
    from custom_components.tisseo.data.parkride import PARKRIDE_URL
    aioclient_mock.get(PARKRIDE_URL, json={"results": [
        {"id": "31555-P-0024", "nom": "ARENES", "nb_places": 522,
         "geo_point_2d": {"lat": 43.59, "lon": 1.41}}]})
    hass.config.latitude, hass.config.longitude = 43.6045, 1.444
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "bike"})
    assert result["step_id"] == "bike"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"station_id": "1"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    bikes = _state(hass, "bikes_available")
    assert bikes.state == "5" and bikes.attributes["electric"] == 2
    assert _state(hass, "docks_available").state == "14"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "park_ride"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"park_id": "31555-P-0024"})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "P+R Arenes"
    await hass.async_block_till_done()
    cap = _state(hass, "capacity")
    assert cap.state == "522" and cap.attributes["live_availability"] == "not_available_as_open_data"
