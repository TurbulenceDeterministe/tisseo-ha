# Changelog

All notable changes to this project. Versions follow [semantic versioning](https://semver.org/). The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [1.1.1] – 2026-10-25
Fixes for suburban stops such as Ourliac (bug report: "no information on the itinerary").
- **Journeys with two transfers** (e.g. 25 → metro A → metro B to Borderouge). Before, the search allowed one transfer only, and the lean index had no line that called at neither end. So many trips from a suburban stop found nothing. Once a journey is configured, the index now also keeps the trunk lines (metro, tram, Linéo, Téléo).
- **Next service when the 3 h window is empty.** Some lines have no Sunday or evening service (at Ourliac, only line 87 runs on Sunday). `departure_1` now has a `next_service` attribute, and the card shows "Next departure: tomorrow 06:19 · 25 Colomiers Gare SNCF". The state stays `unknown`, so automations behave as before.
- **Journey fallback.** If no connection leaves within 3 h, the sensor shows the first connections of the next service and sets `later: true`.
- **Trip dialog for real-time-only trips.** Trips added by the GTFS-RT feed (not in the timetable, e.g. Téléo) used to return "not found". They now open with the calls the feed publishes.
- Index schema v5: the index is rebuilt automatically on the first start after the upgrade.

### Docs
- New project presentation: README (EN/FR) with banner, demo GIF, feature grid, data-flow diagram, card options table and FAQ; GitHub Pages site in `docs/`; CONTRIBUTING and release notes. GitHub links now point to `TurbulenceDeterministe/tisseo-ha`.

## [1.1.0] – 2026-10-25
- **New card design** (v2), integrated into the bundled card as one file: a "next departure" hero with leave-now, departures grouped by direction with "then" times, delay chips with a 90 s threshold, mode-specific badge shapes with automatic AA contrast, a collapsed disruptions banner, notices for missing live data and tomorrow's timetable change, a dark departure board with metro / bus & tram panels and a paged disruptions footer, and a native `<dialog>` trip timeline.
- New card options: `max_departures`, `group`, `hero`, `hero_line`, `leave_entity`, `alerts`, `timetable_notice`, `show_clock`, `badge_contrast`, `board_theme`. The 1.0 options keep working (`max`, `show_alerts`, filters, `trip_dialog`).
- One shared ticker per card (second-aligned, paused off screen), keyed row updates, and a regroup every 30 s so departed trips drop out between sensor updates.
- The card follows Home Assistant's 12 h / 24 h time setting.

## [1.0.0]
- New entry types: **nearby stops**, **journeys with one transfer** (two since 1.1.1), **VélôToulouse stations** and **P+R**.
- New stop entities: **leave now / leave in** and **timetable change tomorrow**.
- New `tisseo_disruption` / `tisseo_delay` events, with 3 blueprints.
- **Optional user API key** (Tisséo API v2 `stops_schedules`), with validation, a repair issue and reauth.
- **Reliability:** backoff, circuit breaker, health sensors, and diagnostics with the key redacted.
- **Lean index** (schema v4) that also stores full trips.
- `tisseo.get_trip` service and `tisseo/trip_stops` WebSocket command.
- **Card:** compact and board layouts, filter chips, trip dialog, and a schema-based visual editor (en/fr).
- **Packaging:** HACS metadata, brand icon, CI workflows (hassfest, HACS, pytest), issue templates, and a French README.

## [0.3.0]
- Animated card. 0.2.0 added real-time attribution and 0.1.x the first release (see git history).

## Index size
Measured on the 2026-10 GTFS, on an x86 box.

| Index | Build | Size |
|---|---|---|
| 0.3.0 (all stop_times, without trips) | 5.1 s | 26.1 MB |
| 1.0.0 full (all trips, needed for journeys and trip details) | 6.0 s | 47.0 MB |
| 1.0.0 **lean**, 3 stops (25,063 trips) | 4.5 s | 25.7 MB |
| 1.0.0 lean, Capitole only | 3.9 s | 10.6 MB |
| 1.0.0 lean, Île du Ramier only | 3.9 s | 7.0 MB |
| 1.1.1 lean, Ourliac + Capitole, no journey | 4.2 s | 12.3 MB |
| 1.1.1 lean + trunk lines (any journey configured), Ourliac + Capitole | 5.0 s | 32.4 MB |
| 1.1.1 lean + trunk lines, test install (5 stop areas, 3 journeys) | — | 34.5 MB |

Adding a stop that is not covered yet rebuilds the index automatically. Once a journey is configured, every metro, tram, Linéo and Téléo trip is also kept, so that two-transfer journeys can change between them.
