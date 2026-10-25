# Tisséo for Home Assistant v1.1.1

Fixes for suburban stops such as **Ourliac**, where journeys and departures could show nothing.

## Fixed
- **Journeys with two transfers.** Journeys can now use one or two transfers, for example bus 25 → metro A → metro B from Ourliac to Borderouge. Before, only one transfer was searched, and the index did not hold lines that call at neither end of the journey, so many suburban journeys found nothing. Once a journey is configured, the index also keeps the trunk lines (metro, tram, Linéo, Téléo).
- **"No departures in the next 3 h" now says when the next one is.** Some lines don't run on Sundays or in the evening. `sensor.<stop>_departure_1` gets a `next_service` attribute, and the card shows e.g. *"Next departure: tomorrow 06:19 · 25 Colomiers Gare SNCF"*. The sensor state is unchanged (`unknown`), so existing automations behave the same.
- **Journey fallback.** If no connection leaves within 3 h, the journey sensor shows the first connections of the next service and sets `later: true`.
- **Trip dialog for real-time-only trips.** Trips added by the GTFS-RT feed (e.g. some Téléo, T1 and line 34 trips) used to return "not found". They now open with the stops the feed publishes.

## Upgrade notes
- Install through HACS (or replace `custom_components/tisseo`), then **restart Home Assistant**.
- The timetable index (schema v5) **rebuilds automatically** on the first start; this takes about 5 s.
- **Hard-refresh** your browser (Ctrl+Shift+R) so the 1.1.1 card loads.
- With at least one journey configured, the index grows from about 12 MB to about 32 MB, because the trunk lines are added.

## Known limits
- At most two transfers. The middle leg must be a metro, tram, Linéo or Téléo line, and transfers happen within the same stop area.
- No live metro times (not published by Tisséo) and no live P+R occupancy (not open data).

## Also in this release
- New project presentation: README (EN/FR) with a demo, a feature tour and a FAQ, plus a project page (GitHub Pages, `docs/`), `CHANGELOG.md` and `CONTRIBUTING.md`.

Data © Tisséo, ODbL. Unofficial project, not affiliated with Tisséo.

**Full changelog:** https://github.com/TurbulenceDeterministe/tisseo-ha/blob/v1.1.1/CHANGELOG.md
