# Tisséo (Toulouse) for Home Assistant

A custom integration that shows **next departures** (real-time when available) and **disruptions** for the Tisséo stops and lines you choose. It runs only on **keyless open data**, so you **don't need to request a Tisséo API key**:

- GTFS static: Tisséo dataset on transport.data.gouv.fr / data.toulouse-metropole.fr (ODbL). Downloaded once, indexed into SQLite (~26 MB), and checked again every 24 h with conditional GET.
- GTFS-Realtime: `https://api.tisseo.fr/opendata/gtfsrt/GtfsRt.pb` (trip updates and service alerts). One shared download per poll for all configured stops.

See [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) for what the official app and website use, and why those APIs are not used here (they need Tisséo's key).

## Install
### HACS (custom repository)
1. Push this folder to a GitHub repo. In HACS, open ⋮ → *Custom repositories*, add the repo URL with category **Integration**.
2. Install **Tisséo (Toulouse public transport)** and restart Home Assistant.
### Manual
Copy `custom_components/tisseo` to `<config>/custom_components/tisseo` and restart. HA installs the dependency `gtfs-realtime-bindings` automatically.

## Configure
*Settings → Devices & services → Add integration → Tisséo*
1. Type a stop name (accents and case don't matter: `capitole`, `jeanne d arc`), a GTFS id (`stop_area:SA_1715`, `stop_point:SP_1912`) or a stop code (`40110`). The first setup downloads and indexes the GTFS, which takes about 10 s on a PC and longer on a Raspberry Pi.
2. Pick the stop area (all directions) or a single platform (stop point).
3. Optional: pick a line filter, the number of departure sensors (1–10), the poll interval (≥30 s, default 60 s), and whether to include network-wide alerts. You can change these later under *Configure*.

Add the integration once per stop or line set.

## Entities (per configured stop)
| Entity | State | Attributes |
|---|---|---|
| `sensor.tisseo_<stop>_departure_1..N` | timestamp of expected departure | `line`, `line_name`, `mode`, `color`, `destination`, `stop_name`, `scheduled`, `expected`, `minutes`, `realtime`, `delay_seconds`, `delay_minutes`, `trip_id`, `realtime_source` (`gtfs_rt`/`timetable`), `live_coverage` (`live`/`not_published`/`feed_unavailable`/`disabled`), `line_alerts` (active alerts for that line). On `departure_1` only: `upcoming` (list), `gtfs_built`, `realtime_feed_time`, `realtime_feed_url`, `live_lines` (lines at this stop that currently have live predictions) |
| `sensor.tisseo_<stop>_disruptions` | number of active alerts | `alerts` (header, description, url, cause, effect, lines, stops), `headlines`, `line_alerts` |

Example Markdown card:
```yaml
type: markdown
content: >
  {% for d in state_attr('sensor.tisseo_capitole_departure_1','upcoming') %}
  **{{ d.line }}** → {{ d.destination }} : {{ d.minutes }} min{% if d.realtime %} 📡{% endif %}
  {% endfor %}
```

## Dashboard card (`custom:tisseo-departures-card`)

The integration ships an animated Lovelace card and loads it automatically. It is served at
`/tisseo_static/tisseo-departures-card.js` and added to the frontend, so you do **not**
need to add a resource. After installing or upgrading, reload the browser once.

```yaml
type: custom:tisseo-departures-card
entity: sensor.tisseo_capitole_departure_1   # any sensor of the stop (the card finds its siblings)
title: Capitole        # optional, defaults to the stop name
max: 5                 # optional, rows shown (limited by the "departures" option of the stop)
show_alerts: true      # optional, scrolling ticker of the stop's disruptions
# alerts_entity: sensor.tisseo_capitole_disruptions   # optional, auto-detected
```

What it shows:

- Line badges in the official GTFS line colours: circle for the metro, rounded square for the tram, pill for buses.
- The destination and a big countdown that ticks every second in the browser, with `m:ss` underneath.
- A pulsing **📡 live** dot for GTFS-RT predictions and a muted 🕒 *timetable* label otherwise.
- Delay chips: `+N min` in red when late, `−N min` in green when early, "on time" otherwise.
- An "imminent" pulse when a departure is ≤ 1 min away, and a progress bar filling up over the last 10 min before the next departure.
- New departures slide in and departed ones slide out.
- A scrolling marquee of the alerts. Alerts for the lines shown come first; hover to pause.
- It follows the HA theme (light or dark) and turns off all animation with `prefers-reduced-motion`.
- It has a visual editor and appears in the card picker as "Tisséo departures".

**Standalone / HACS frontend use.** The card is a single dependency-free file, `custom_components/tisseo/frontend/tisseo-departures-card.js`. You can also copy it to `<config>/www/` and add `/local/tisseo-departures-card.js` as a *JavaScript module* dashboard resource. It still needs the Tisséo sensors to read from.

## How real-time is merged
Static departures are computed from `stop_times` and `calendar(_dates)`. Service days use the GTFS "noon − 12 h" origin, so the DST changes and the 24:xx trips after midnight come out right. Then GTFS-RT is applied:
- an explicit time or delay at the stop
- or the delay from the last earlier stop, carried forward
- CANCELED trips and SKIPPED stops are dropped
- ADDED trips that only exist in RT (e.g. TELEO) are added
- an RT time more than 3 h from the schedule is ignored, so a trip id's update is not applied to the wrong day

If the RT feed is unreachable, the last snapshot is kept for 5 min, then the sensors fall back to schedule (`realtime: false`).

## Live data: what exists for each mode (checked 2026-10-25)
| Source (all keyless) | Bus / Linéo / T1 | Metro A/B |
|---|---|---|
| GTFS-RT `api.tisseo.fr/opendata/gtfsrt/GtfsRt.pb` (used) | ✅ TripUpdates (~670 trips) + Alerts | ❌ 0 trip updates for `line:61` / `line:69` in every sample |
| `plan-interactif.tisseo.fr/api/schedules` (official map backend, undocumented) | `data_freshness: realtime`, **identical to GTFS-RT within ±1 s** | `base_schedule` only, same times as the GTFS |
| transport.data.gouv.fr (Tisséo dataset) | GTFS, NeTEx, the GTFS-RT above (`trip_updates`, `service_alerts`). No VehiclePositions, no SIRI | — |
| data.toulouse-metropole.fr | static datasets only. The "API Temps Réel Tisséo" there needs an API key from opendata@tisseo.fr | — |

So **no keyless public source publishes live metro predictions**. Metro departures stay on the timetable (`realtime_source: timetable`, `live_coverage: not_published`), and live metro *status* comes from the alerts (`line_alerts`, disruptions sensor). The plan-interactif backend adds no live information over GTFS-RT, so it is not used. If you get your own key from Tisséo, their official API is the only possible route to more data, and this integration does not use it.

The real-time layer is optional (option *Use live GTFS-RT predictions*, on by default). It uses a 20 s timeout, 4 attempts across two URLs, one shared download for all stops (rate-limited to 25 s), and falls back to the timetable.

## Why an integration and not an add-on
An integration runs inside HA. It works on every install type (OS, Container, Core), gives native entities with a config flow, and needs no MQTT or REST glue. An add-on only runs on HA OS or Supervised and would have to push data back through MQTT or the REST API, for no data advantage. So there is no add-on wrapper.

## Limitations
- **Metro A/B are schedule-only.** Tisséo's GTFS-RT has no metro trip updates. Metro times come from the timetable, which for the metro is frequency-based. Bus, Linéo, tram T1, AERO and TELEO get real-time when Tisséo publishes it.
- Real-time quality depends on Tisséo's feed. `delay +0s` means the feed reported "on time".
- During testing, about half of the TLS handshakes to `api.tisseo.fr` failed (EOF after ~8 s), possibly because of the test network. The integration retries via the data.gouv redirect and keeps stale data briefly, but some polls will miss real-time.
- Alerts are matched by line or stop as published. Network-wide alerts (agency-scoped) are included unless you turn that off.
- The first GTFS import holds about 75 MB of CSV in streaming mode. Disk use is ~14 MB zip plus ~26 MB SQLite in `<config>/.storage/tisseo/`.
- Data © Tisséo, ODbL. Not affiliated with Tisséo.

## Development
```bash
pip install gtfs-realtime-bindings aiohttp pytest pytest-asyncio
python scripts/live_demo.py "Capitole"            # live data, prints next departures
python scripts/live_demo.py "jeanne d arc" --lines B,L1
pytest tests/test_data_layer.py                   # unit tests (synthetic feed)
pip install pytest-homeassistant-custom-component
pytest tests                                      # + HA config flow / sensor tests
TISSEO_LIVE=1 pytest tests/test_live_ha.py -s     # real HA flow against the live feeds
```

## Changelog
### 0.3.0
- New animated dashboard card `custom:tisseo-departures-card`. It is bundled and registered automatically through a static path and `add_extra_js_url`. It has a visual editor and handles the theme and reduced motion.
- Departure sensors expose `text_color` (GTFS `route_text_color`), and `upcoming` items include `route_id`, `text_color` and `canceled`.
- `CONFIG_SCHEMA` is now config-entry-only.
- **0.2.0** – Real-time attribution and coverage.
  - New per-departure attributes: `realtime_source`, `live_coverage`, `line_alerts`. On `departure_1`: `live_lines` and `realtime_feed_url`.
  - New option to turn the GTFS-RT layer off.
  - Documented the live-data survey: no keyless live metro source exists.
- **0.1.1** – Tested on a real Home Assistant 2026.10.4 instance.
  - GTFS download file I/O now runs in the executor; HA had flagged a blocking `open()` in the event loop.
  - Trips that arrive at their terminus stop area are no longer listed as departures from it. For example, bus 45 "→ Jeanne d'Arc" was shown at Jeanne d'Arc. The index schema went to v3, so the index is rebuilt automatically.
- **0.1.0** – First release.
