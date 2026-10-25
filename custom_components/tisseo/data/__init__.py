"""Pure-python data layer for Tisséo (no Home Assistant imports).

Sources (all keyless, open data, ODbL):
  * GTFS static  : Tisséo dataset on transport.data.gouv.fr / data.toulouse-metropole.fr
  * GTFS-RT      : https://api.tisseo.fr/opendata/gtfsrt/GtfsRt.pb (trip updates + alerts)
"""
from .const import GTFS_URLS, GTFS_RT_URLS, TZ  # noqa: F401
from .static import GtfsStore, StopInfo, RouteInfo  # noqa: F401
from .realtime import RealtimeSnapshot, parse_realtime  # noqa: F401
from .departures import Departure, next_departures, alerts_for  # noqa: F401
