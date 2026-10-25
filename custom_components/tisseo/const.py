"""Constants for the Tisséo integration."""
from datetime import timedelta

DOMAIN = "tisseo"
PLATFORMS = ["sensor"]

CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_LINES = "lines"
CONF_COUNT = "count"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NETWORK_ALERTS = "network_alerts"
CONF_REALTIME = "realtime"
CONF_QUERY = "query"

DEFAULT_COUNT = 3
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30
GTFS_MAX_AGE = timedelta(hours=24)

ATTRIBUTION = "Data: Tisséo open data (GTFS / GTFS-RT, ODbL) via transport.data.gouv.fr"
