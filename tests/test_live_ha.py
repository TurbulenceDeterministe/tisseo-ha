"""Opt-in end-to-end test: real HA config flow against the live keyless feeds.

Run with:  TISSEO_LIVE=1 pytest tests/test_live_ha.py -s
"""
import os

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tisseo.const import DOMAIN
from custom_components.tisseo.data.client import TisseoFeeds

pytestmark = pytest.mark.skipif(not os.environ.get("TISSEO_LIVE"), reason="set TISSEO_LIVE=1")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def expected_lingering_timers() -> bool:
    return True


@pytest.mark.parametrize("query,stop_id", [("Capitole", "stop_area:SA_1715"),
                                           ("ile du ramier", "stop_area:SA_998")])
async def test_live_stop(hass, socket_enabled, query, stop_id):
    # The HA test harness' shared aiohttp session is bound to another loop, so inject a
    # real TisseoFeeds with its own session (everything else is the real integration).
    import pytest_socket
    pytest_socket._remove_restrictions()  # HA's harness only allows 127.0.0.1
    session = aiohttp.ClientSession()
    hass.data.setdefault(DOMAIN, {})["feeds"] = TisseoFeeds(
        session, os.path.join(os.path.dirname(__file__), "..", ".cache"),
        run_in_executor=hass.async_add_executor_job)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": query})
    assert result["step_id"] == "stop"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stop_id": stop_id})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lines": [], "count": 3, "scan_interval": 60, "network_alerts": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    print("rt_error:", hass.data[DOMAIN]["feeds"].rt_error)
    for s in sorted(hass.states.async_all("sensor"), key=lambda s: s.entity_id):
        a = s.attributes
        if "headlines" in a:
            print(f"{s.entity_id} = {s.state}  {a['headlines'][:3]}")
        else:
            print(f"{s.entity_id} = {s.state}  line={a.get('line')} dest={a.get('destination')} "
                  f"min={a.get('minutes')} realtime={a.get('realtime')} delay={a.get('delay_seconds')} "
                  f"feed_ok={a.get('realtime_feed_ok')} feed_time={a.get('realtime_feed_time')}")
        assert s.state not in ("unavailable", "unknown")
    await hass.config_entries.async_unload(hass.config_entries.async_entries(DOMAIN)[0].entry_id)
    await hass.async_block_till_done()
    await session.close()
