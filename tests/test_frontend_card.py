"""The bundled Lovelace card ships with the integration and matches its version."""
import json
import re
from pathlib import Path

COMP = Path(__file__).parents[1] / "custom_components" / "tisseo"
CARD = COMP / "frontend" / "tisseo-departures-card.js"


def test_card_is_bundled_and_versioned():
    src = CARD.read_text(encoding="utf-8")
    version = json.loads((COMP / "manifest.json").read_text())["version"]
    assert f'TDC_VERSION = "{version}"' in src
    assert "customElements.define(tag, cls)" in src and '["tisseo-departures-card", TisseoDeparturesCard]' in src
    assert "getConfigElement" in src and "getStubConfig" in src
    assert "prefers-reduced-motion" in src


def test_card_reads_only_published_attributes():
    """Every departure key the card uses must be published in `upcoming`."""
    src = CARD.read_text(encoding="utf-8")
    sensor = (COMP / "sensor.py").read_text(encoding="utf-8")
    used = set(re.findall(r"\bd\.([a-z_]+)", src))
    for key in used:
        assert f'"{key}"' in sensor, key


def test_card_has_no_secrets():
    src = CARD.read_text(encoding="utf-8").lower()
    for word in ("apikey", "api_key", "token", "bearer", "authorization"):
        assert word not in src


def test_card_v1_features_are_wired():
    src = CARD.read_text(encoding="utf-8")
    for layout in ("compact", "board"):
        assert f"ha-card.{layout}" in src
    # row tap -> websocket command that the integration registers
    assert '"tisseo/trip_stops"' in src
    assert '"tisseo/trip_stops"' in (COMP / "services.py").read_text(encoding="utf-8")
    for opt in ("filter_lines", "filter_destinations", "show_filters", "trip_dialog", "layout"):
        assert f'name: "{opt}"' in src, opt
    assert "localStorage" in src  # in-card filter selection persists per card
