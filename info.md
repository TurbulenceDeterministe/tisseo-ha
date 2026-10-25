# Tisséo (Toulouse)

Real-time departures, disruptions, journeys with up to two transfers, leave-now, VélôToulouse bikes and park-and-ride for Toulouse. **No API key needed.** The data is keyless open data: GTFS, GTFS-RT and GBFS. You can optionally add your own key for the official Tisséo API.

- Entry types: stop (search or nearby), journey, bike station, P+R.
- Animated card `custom:tisseo-departures-card` with default, compact and board layouts, filter chips and a trip dialog. It loads automatically.
- `tisseo_disruption` / `tisseo_delay` events and 3 blueprints.
- Health sensors, a circuit breaker, and diagnostics with the key redacted.

Limits: there is no live metro data (none is published). P+R shows static capacity only.

See the README for full documentation (EN / FR).
