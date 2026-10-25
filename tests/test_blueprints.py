"""The shipped blueprints are valid and work end-to-end with the integration's events."""
import shutil
from pathlib import Path

import pytest
from homeassistant.components.blueprint import models
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

BP = Path(__file__).parents[1] / "blueprints" / "automation" / "tisseo"


@pytest.mark.parametrize("name", sorted(p.name for p in BP.glob("*.yaml")))
def test_blueprint_schema(name):
    data = load_yaml(str(BP / name))
    bp = models.Blueprint(data, schema=__import__(
        "homeassistant.components.automation.config", fromlist=["AUTOMATION_BLUEPRINT_SCHEMA"]
    ).AUTOMATION_BLUEPRINT_SCHEMA)
    assert bp.domain == "automation" and bp.inputs


async def _setup(hass, path, inputs):
    dst = Path(hass.config.path("blueprints/automation/tisseo"))
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(BP / path, dst / path)
    assert await async_setup_component(hass, "automation", {"automation": [
        {"alias": "t", "use_blueprint": {"path": f"tisseo/{path}", "input": inputs}}]})
    await hass.async_block_till_done()


async def test_delay_blueprint_runs(hass):
    calls = []
    hass.services.async_register("test", "record", lambda c: calls.append(c.data))
    await _setup(hass, "delay_notify.yaml", {
        "lines": ["L1"], "min_delay": 3,
        "actions": [{"action": "test.record", "data": {"msg": "{{ line }} +{{ delay_minutes }}"}}]})
    base = {"stop_name": "Jeanne d'Arc", "destination": "X", "expected": "2026-10-25T13:30:00+01:00"}
    hass.bus.async_fire("tisseo_delay", {**base, "line": "L1", "delay_minutes": 2.0})
    hass.bus.async_fire("tisseo_delay", {**base, "line": "B", "delay_minutes": 9.0})
    hass.bus.async_fire("tisseo_delay", {**base, "line": "L1", "delay_minutes": 4.5})
    await hass.async_block_till_done()
    assert calls == [{"msg": "L1 +4.5"}]


async def test_disruption_blueprint_runs(hass):
    calls = []
    hass.services.async_register("test", "record", lambda c: calls.append(c.data))
    await _setup(hass, "disruption_notify.yaml", {
        "lines": ["B"], "include_network": False,
        "actions": [{"action": "test.record", "data": {"h": "{{ header }}"}}]})
    ev = {"stop_name": "Jeanne d'Arc", "description": "", "url": None}
    hass.bus.async_fire("tisseo_disruption", {**ev, "header": "B partiel", "lines": ["B"], "network_wide": False})
    hass.bus.async_fire("tisseo_disruption", {**ev, "header": "L9 dévié", "lines": ["L9"], "network_wide": False})
    hass.bus.async_fire("tisseo_disruption", {**ev, "header": "Réseau", "lines": [], "network_wide": True})
    await hass.async_block_till_done()
    assert calls == [{"h": "B partiel"}]


async def test_leave_now_blueprint_runs(hass, freezer):
    freezer.move_to("2026-10-26 15:00:00+00:00")  # Monday 08:00 in the test time zone (US/Pacific)
    calls = []
    hass.services.async_register("test", "record", lambda c: calls.append(c.data))
    hass.states.async_set("binary_sensor.tisseo_x_leave_now", "off")
    await _setup(hass, "leave_now_notify.yaml", {
        "leave_sensor": "binary_sensor.tisseo_x_leave_now",
        "actions": [{"action": "test.record", "data": {"m": "{{ line }} {{ destination }} {{ realtime }}"}}]})
    hass.states.async_set("binary_sensor.tisseo_x_leave_now", "on", {"next_catchable": {
        "line": "B", "destination": "Ramonville", "expected": "2026-10-26T16:10:00+00:00", "realtime": False}})
    await hass.async_block_till_done()
    assert calls == [{"m": "B Ramonville False"}]
