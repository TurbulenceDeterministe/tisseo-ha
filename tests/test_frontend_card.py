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
        assert f'[data-layout="{layout}"]' in src, layout
    # row tap -> websocket command that the integration registers
    assert '"tisseo/trip_stops"' in src
    assert '"tisseo/trip_stops"' in (COMP / "services.py").read_text(encoding="utf-8")
    for opt in ("filter_lines", "filter_destinations", "show_filters", "trip_dialog", "layout"):
        assert f'name: "{opt}"' in src, opt
    assert "localStorage" in src  # in-card filter selection persists per card


def test_card_v11_design_is_inlined_and_offline():
    """1.1.0: the v2 design ships inside the one served file, with no external resources."""
    src = CARD.read_text(encoding="utf-8")
    assert "import " not in src.split("const STYLES")[0]  # no ES module imports: one no-build file
    assert not re.search(r"\bimport\s*\(", src)
    assert not re.search(r"\bfetch\s*\(|XMLHttpRequest|WebSocket\(|sendBeacon|@import|url\(", src)
    assert "fonts.googleapis" not in src and "cdn" not in src.lower()
    # the only absolute URL is the documentation link of the card picker
    urls = set(re.findall(r"https?://[^\s\"'`)]+", src))
    assert urls <= {"https://github.com/your-github-user/tisseo-ha"}, urls
    for cls in (".tc-hero", ".tc-row__hit", ".tc-chip[aria-pressed", ".tc-dialog", ".tc-board__cols--split", ".tc-alerts__list"):
        assert cls in src, cls
    for opt in ("max_departures", "group", "hero", "hero_line", "leave_entity", "alerts", "badge_contrast", "board_theme", "show_clock", "timetable_notice"):
        assert f'name: "{opt}"' in src, opt
    # 1.0 option names still accepted
    assert "config.max != null" in src and "config.show_alerts === false" in src
    # HA 2026 scoped-registry workaround and a single card-picker entry
    assert "window.__tisseoCardTimer" in src and 'customCards.some((x) => x.type === "tisseo-departures-card")' in src
    # reduced motion / contrast / forced colours
    for q in ("prefers-reduced-motion", "prefers-contrast", "forced-colors"):
        assert q in src, q


def test_card_reads_real_companion_attributes():
    """Companion sensors the card reads (alerts, leave-in, feed health, timetable change) publish those keys."""
    src = CARD.read_text(encoding="utf-8")
    code = "".join((COMP / f).read_text(encoding="utf-8") for f in ("sensor.py", "binary_sensor.py", "data/timetable.py"))
    for key in ("headlines", "alerts", "walking_time", "buffer", "next_catchable", "leave_at", "feeds",
                "tomorrow_departures", "reference_departures", "upcoming", "live_lines", "stop_name"):
        assert key in src, key
        assert f'"{key}"' in code, key
    rt = (COMP / "data" / "realtime.py").read_text(encoding="utf-8")
    for key in ("header", "description", "url", "effect", "lines", "network_wide"):
        assert f'"{key}"' in rt, key
