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
