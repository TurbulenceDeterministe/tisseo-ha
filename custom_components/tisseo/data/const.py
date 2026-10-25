"""Endpoints and constants for the Tisséo open-data feeds."""
from zoneinfo import ZoneInfo

# Stable data.gouv.fr resource ids (redirect to the current file); second URL is the
# Toulouse Métropole open-data portal "latest file" fallback.
GTFS_URLS = (
    "https://www.data.gouv.fr/api/1/datasets/r/64318177-f5b5-4144-a6be-2d0f22d26c77",
    "https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/tisseo-gtfs/alternative_exports/utf_8tisseo_gtfs_v2_zip",
)
GTFS_RT_URLS = (
    "https://api.tisseo.fr/opendata/gtfsrt/GtfsRt.pb",
    "https://www.data.gouv.fr/api/1/datasets/r/b2343456-4e73-4e5e-bf0f-e8cab63357a8",
)
TZ = ZoneInfo("Europe/Paris")
USER_AGENT = "tisseo-ha (Home Assistant custom integration; +https://github.com/)"

ROUTE_TYPE_NAMES = {
    0: "tram", 1: "metro", 2: "rail", 3: "bus", 4: "ferry",
    5: "cable_tram", 6: "aerial_lift", 7: "funicular", 11: "trolleybus", 12: "monorail",
}
