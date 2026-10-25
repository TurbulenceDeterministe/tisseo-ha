"""Home Assistant tests: config flow + sensor setup with the synthetic feed (no network)."""
from datetime import datetime

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tisseo.const import DOMAIN
from custom_components.tisseo.data.const import TZ
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

    async def ensure_gtfs(self, *a, **k):
        return False

    async def realtime(self):
        return self._rt


@pytest.fixture
def feeds(hass, store):
    rt = parse_realtime(make_feed(
        trip_updates=[("B1", "line:B", SCHEDULED,
                       [(2, "stop_point:SP_1", NOW.timestamp() + 9 * 60, 120, False)])],
        alerts=[("a1", "Ligne B perturbée", ["line:B"], [], []),
                ("a9", "Autre ligne", ["line:99"], [], [])],
        ts=int(NOW.timestamp())))
    f = FakeFeeds(store, rt)
    hass.data.setdefault(DOMAIN, {})["feeds"] = f
    return f


async def test_flow_and_sensors(hass, feeds, freezer):
    freezer.move_to(NOW)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "nowhere"})
    assert result["errors"] == {"query": "no_stop"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "jeanne"})
    assert result["step_id"] == "stop"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stop_id": "stop_area:SA_1"})
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lines": [], "count": 2, "scan_interval": 60, "network_alerts": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jeanne d'Arc"
    await hass.async_block_till_done()

    states = {s.entity_id: s for s in hass.states.async_all("sensor")}
    dep1 = next(s for e, s in states.items() if e.endswith("departure_1"))
    dep2 = next(s for e, s in states.items() if e.endswith("departure_2"))
    alerts = next(s for e, s in states.items() if e.endswith("disruptions"))
    assert dep1.attributes["line"] == "B" and dep1.attributes["realtime"] is True
    assert dep1.attributes["delay_seconds"] == 120
    assert dep1.attributes["realtime_source"] == "gtfs_rt"
    assert dep1.attributes["live_coverage"] == "live"
    assert dep1.attributes["line_alerts"] == ["Ligne B perturbée"]
    assert dep1.attributes["live_lines"] == ["B"]
    assert dep1.attributes["realtime_feed_url"] == "https://example.invalid/GtfsRt.pb"
    assert datetime.fromisoformat(dep1.state) == datetime(2026, 10, 24, 10, 7, tzinfo=TZ)
    assert dep2.attributes["line"] == "15" and dep2.attributes["realtime"] is False
    assert dep2.attributes["realtime_source"] == "timetable"
    assert dep2.attributes["live_coverage"] == "not_published"
    assert len(dep1.attributes["upcoming"]) == 2
    assert alerts.state == "1" and alerts.attributes["headlines"] == ["Ligne B perturbée"]

    # options flow: filter on line 15 only
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"lines": ["line:15"], "count": 2, "scan_interval": 60,
                            "network_alerts": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    dep1 = hass.states.get(dep1.entity_id)
    assert dep1.attributes["line"] == "15"
    assert hass.states.get(alerts.entity_id).state == "0"


async def test_realtime_can_be_disabled(hass, feeds, freezer):
    freezer.move_to(NOW)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "jeanne"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stop_id": "stop_area:SA_1"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lines": [], "count": 2, "scan_interval": 60,
                            "network_alerts": True, "realtime": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    dep1 = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("departure_1"))
    assert dep1.attributes["realtime"] is False and dep1.attributes["live_coverage"] == "disabled"
    assert datetime.fromisoformat(dep1.state) == datetime(2026, 10, 24, 10, 5, tzinfo=TZ)
