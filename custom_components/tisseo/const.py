"""Constants for the Tisséo integration."""
from datetime import timedelta

DOMAIN = "tisseo"
PLATFORMS = ["sensor", "binary_sensor"]

CONF_ENTRY_TYPE = "entry_type"
TYPE_STOP = "stop"
TYPE_JOURNEY = "journey"
TYPE_BIKE = "bike"
TYPE_PARKRIDE = "park_ride"

CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_LINES = "lines"
CONF_COUNT = "count"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NETWORK_ALERTS = "network_alerts"
CONF_REALTIME = "realtime"
CONF_QUERY = "query"
CONF_API_KEY = "api_key"
CONF_CLEAR_API_KEY = "clear_api_key"
CONF_WALK = "walking_time"
CONF_BUFFER = "buffer"
CONF_DELAY_THRESHOLD = "delay_threshold"
CONF_ORIGIN = "origin"
CONF_ORIGIN_NAME = "origin_name"
CONF_DESTINATION = "destination"
CONF_DESTINATION_NAME = "destination_name"
CONF_ORIGIN_QUERY = "origin_query"
CONF_DESTINATION_QUERY = "destination_query"
CONF_MIN_TRANSFER = "min_transfer"
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_PARK_ID = "park_id"
CONF_PARK_NAME = "park_name"

DEFAULT_COUNT = 3
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30
DEFAULT_WALK = 0
DEFAULT_BUFFER = 2
DEFAULT_DELAY_THRESHOLD = 5  # minutes, 0 = off
DEFAULT_MIN_TRANSFER = 3
FETCH_DEPARTURES = 12  # computed per refresh (sensors show the first `count`)
GTFS_MAX_AGE = timedelta(hours=24)
NEARBY_LIMIT = 10

EVENT_DISRUPTION = "tisseo_disruption"
EVENT_DELAY = "tisseo_delay"

ATTRIBUTION = "Data: Tisséo open data (GTFS / GTFS-RT, ODbL) via transport.data.gouv.fr"
ATTRIBUTION_API = "Data: Tisséo API v2 (user key) + Tisséo open data (GTFS / GTFS-RT, ODbL)"
ATTRIBUTION_BIKE = "Data: VélôToulouse GBFS (JCDecaux Open Licence)"
ATTRIBUTION_PARKRIDE = "Data: Toulouse Métropole open data, parkings-relais (Licence Ouverte v2.0)"
