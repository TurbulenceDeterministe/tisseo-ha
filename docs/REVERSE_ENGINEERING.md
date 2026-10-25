# How the official Tisséo app and site get their data

Analysed on 2026-10-25: `fr.tisseo.android` **6.2.10** (versionCode 2878), XAPK from APKPure.
SHA-256 of the base APK: `c92a938a7a9cf90e53cd852af9ae2c5fd2a65b7c715315c7eb69edefe29901ec`.
Tools: jadx 1.5.3 (Java sources) and apktool 3.0.3 (resources). Kotlin + Retrofit/OkHttp + Moshi; R8-obfuscated.
Embedded keys are **redacted** below. None of them is used by this integration.

## App backends (Retrofit interfaces in `fr/tisseo/android/api/`)

| Base URL | Interface / data source | Purpose | Auth |
|---|---|---|---|
| `https://api-kraken.tisseo.fr` | `KrakenApi`, `KrakenDataSource`, `repository/stop_schedule/NextDeparturesNetworkDataSource`, `GetSchedulesWorker` | Real-time next departures, lines, stops, traffic messages, journeys | `?key=` query param. The key is a hard-coded literal (32 hex chars after a `t`) in 12 classes, e.g. `NextDeparturesNetworkDataSource.getSchedules`. **Off-limits.** |
| `https://pieuvre.tisseo.fr/api/v2/` | `PieuvreApi`, `PieuvreDataSource` | Customer account: CO2, certificates, Clubeo, e-mail/phone/password | `apikey:` header (hard-coded literal) and `Authorization: Bearer <user token>`. **Off-limits.** |
| `https://authentification-client.tisseo.fr/auth/realms/ceic/...` | `AuthApi` | Keycloak OpenID Connect login (realm `ceic`) | User credentials |
| `https://api-client.tisseo.fr` | `FederationApi` | Ticketing and federation links | User bearer token |
| `https://tad.tisseo.fr/tadhub/api/v1/` | `TadApi` | On-demand transport booking | OAuth2 password grant |
| `https://emeus.tisseo.fr/v1/` | `EmeusApi` | Push-notification topic registration | – |
| `https://tisseo.fr/rss/actualites.rss` | `RssApi` | News | `Authorization` header. Returns 403 (WAF) to curl. |
| `https://comp.tisseo.fr/com/com2.json` | `CompApi.getCommunication` | In-app promo banner | **Keyless (200).** Not useful. |
| `https://tileserver.tisseo.fr/files/*.geojson` | `GeoJsonApi` | Line, zone and bike geometries | **Keyless (200).** Not needed. |

Network security config (`res/xml/network_security_config.xml`): system CAs only, no cleartext, no certificate pinning.

### Kraken endpoints (`KrakenApi.java`, all `GET`, all with `key`)
- `v1/stops_schedules.json`: `stopsList`, `lineId`, `maxDays`, `datetime`, `timetableByArea`, `firstAndLastOfDay`, `number`, `widget`, `displayVehicleCode`. These are the next departures.
- `v1/lines.json` (`displayMessages`, `displayOutages`), `v1/stop_areas.json`, `v1/stop_points.json`, `v1/places.json`
- `v1/messages.json?contentFormat=html` (traffic info), `v1/access_outages.json`, `v1/unavailable_entrances.json`
- `v1/journeys.json`, `karos/multimodalJourneys`, `v1/park_and_ride.json`, `v1/velo_toulouse_stations_infos.json`, `v1/citiz/station/vehicle/available`

Response model (`fr/tisseo/common/model/`): `StopSchedules{departures{stopAreas[StopAreaSch{id,name,cityName,schedules[Schedule{line LineSch{id,shortName,name,color,bgXmlColor,fgXmlColor,network}, destination{id,name,cityName,way}, stop{id,name,operatorCode,handicappedCompliance}, journeys[JourneySch{dateTime, realTime, vehicle_code, waiting_time}]}]}]}, expirationDate}`. This is the same format as the public Tisséo API v2, which needs a key you request from Tisséo.

Checked without a key on 2026-10-25:
`GET https://api-kraken.tisseo.fr/v1/stops_schedules.json?stopsList=stop_point:SP_1912` returns `401 "No key provided"`. The same holds for `messages.json` and `lines.json`. `https://api.tisseo.fr/v2/stops_schedules.json` also returns 401.

## Website
- `www.tisseo.fr` returned **403** to non-browser clients (WAF). We did not try to get around it.
- `plan-interactif.tisseo.fr` is the official interactive map. It is a single-page app (`assets/main.*.js`) with its own `/api/*` proxy and needs **no key**:
  - `GET /api/schedules?stop=stop_point:SP_1912&count=5` or `?area=stop_area:SA_1715&count=10` returns `[{"route_id":"line:61_b","date_times":[{"date_time":"20261025T095033","data_freshness":"base_schedule","destination":"Basso Cambo (TOULOUSE)"}],...}]`. Times are Europe/Paris local. `data_freshness` is `base_schedule` or `realtime` (Navitia style).
  - `GET /api/disruptions` returns `[{"id","severity","status","title","message"(html),...}]`
  - Also present: `/api/autocomplete`, `/api/around`, `/api/timetable?line=`, `/api/stations?id=`.
  - Re-checked 2026-10-25, 4 samples over 5 min:
    - Metro routes (`line:61_*`, `line:69_*`) were always `base_schedule`, with times equal to the GTFS.
    - Bus `realtime` values were equal to GTFS-RT TripUpdates within ±1 s, so it is the same upstream feed.
    - The JS bundle (`assets/main.*.js`) also references `/api/availability`, `/api/stations`, `/api/around`, `/api/timetable`, `/api/data-in-town`, `/api/init-config` and `/api/init-application`. These cover parking, bikes, POIs and configuration; none of them gives vehicle positions or metro waiting times.
    - About 40–50% of TLS handshakes from the test box fail with "unexpected eof" right after ClientHello. The same happens for `api.tisseo.fr`, while data.gouv.fr succeeds 100%. HTTP/1.1, TLS 1.2 and IPv4 all failed at similar rates. The box reaches the internet through an egress tunnel (every host resolves to 198.18.0.1), so the cause could not be pinned on Tisséo; an external fetch succeeded.
  - In testing it often failed: TLS handshake EOF or timeouts on many requests. It is undocumented, and it is an internal backend of a web app, so it comes with no terms of use. It is **documented here but not used**. Everything it returned (metro = `base_schedule`) is also in the open GTFS and GTFS-RT feeds.

## Keyless open data (what the integration uses)
| Feed | URL | Verified |
|---|---|---|
| GTFS static (daily) | `https://www.data.gouv.fr/api/1/datasets/r/64318177-f5b5-4144-a6be-2d0f22d26c77` (302 to `data.toulouse-metropole.fr/.../tisseo-gtfs/files/.../download/`) and fallback `https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/tisseo-gtfs/alternative_exports/utf_8tisseo_gtfs_v2_zip` | 200, 14.2 MB zip, files dated 2026-10-25 05:30 |
| GTFS-RT (trip updates and alerts) | `https://api.tisseo.fr/opendata/gtfsrt/GtfsRt.pb` (also via `https://www.data.gouv.fr/api/1/datasets/r/b2343456-4e73-4e5e-bf0f-e8cab63357a8`) | 200, about 590 KB, ~670 TripUpdates and 67 Alerts, header timestamp ~5 s old |
| NeTEx | `https://www.data.gouv.fr/api/1/datasets/r/e9cab154-e833-44b9-9bb4-6c0188ebec41` | listed, not used |

What GTFS-RT covers (one sample): TripUpdates for bus lines, Linéo, T1, AERO and TELEO. **No metro A/B trip updates**, so the metro is schedule-only. 155 trips CANCELED and 121 ADDED (TELEO trips are ADDED and are not in the static GTFS). Alerts are 63 route-scoped and 4 network-wide. Some fetches return no alerts block, so the integration keeps the last alerts for 10 minutes.
