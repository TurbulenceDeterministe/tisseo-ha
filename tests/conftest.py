"""Shared fixtures: a tiny synthetic GTFS feed + helpers to build GTFS-RT messages."""
import importlib.util
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "custom_components", "tisseo", "data")
if "tisseo_data" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "tisseo_data", os.path.join(PKG, "__init__.py"), submodule_search_locations=[PKG])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tisseo_data"] = mod
    spec.loader.exec_module(mod)

FILES = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nnetwork:1,Tisséo,http://www.tisseo.fr,Europe/Paris\n",
    "stops.txt": (
        "stop_id,stop_code,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
        "stop_area:SA_1,,Jeanne d'Arc,43.6,1.44,1,\n"
        "stop_point:SP_1,101,Jeanne d'Arc,43.6,1.44,0,stop_area:SA_1\n"
        "stop_point:SP_2,102,Jeanne d'Arc,43.6,1.44,0,stop_area:SA_1\n"
        "stop_area:SA_2,,Capitole,43.6,1.44,1,\n"
        "stop_point:SP_3,201,Capitole,43.6,1.44,0,stop_area:SA_2\n"
        "stop_point:SP_9,901,Terminus,43.6,1.44,0,\n"
        "stop_area:SA_3,,Compans,43.61,1.43,1,\n"
        "stop_point:SP_4,301,Compans,43.61,1.43,0,stop_area:SA_3\n"
    ),
    "routes.txt": (
        "route_id,agency_id,route_short_name,route_long_name,route_color,route_text_color,route_type\n"
        "line:B,network:1,B,Borderouge / Ramonville,ffdd00,000000,1\n"
        "line:15,network:1,15,Bus 15,a0670f,ffffff,3\n"
        "line:A,network:1,A,Balma / Basso Cambo,e2001a,ffffff,1\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "WK,1,1,1,1,1,1,1,20261020,20261031\n"
    ),
    "calendar_dates.txt": "service_id,date,exception_type\nEXTRA,20261025,1\nWK,20261026,2\n",
    "trips.txt": (
        "route_id,service_id,trip_id,direction_id,trip_headsign\n"
        "line:B,WK,B1,0,Ramonville\n"
        "line:B,WK,B2,0,Ramonville\n"
        "line:15,WK,T15,1,Etats-Unis\n"
        "line:15,EXTRA,X15,1,Fondeyre\n"
        "line:15,WK,NIGHT,1,Etats-Unis\n"
        "line:15,WK,ARR,0,Jeanne d'Arc\n"
        "line:A,WK,A1,0,Capitole\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,pickup_type,drop_off_type,stop_sequence\n"
        "B1,10:00:00,10:00:00,stop_point:SP_3,0,0,1\n"
        "B1,10:05:00,10:05:00,stop_point:SP_1,0,0,2\n"
        "B1,10:10:00,10:10:00,stop_point:SP_9,1,0,3\n"
        "B2,10:20:00,10:20:00,stop_point:SP_3,0,0,1\n"
        "B2,10:25:00,10:25:00,stop_point:SP_1,0,0,2\n"
        "B2,10:30:00,10:30:00,stop_point:SP_9,1,0,3\n"
        "T15,10:12:00,10:12:00,stop_point:SP_2,0,0,1\n"
        "T15,10:17:00,10:17:00,stop_point:SP_9,1,0,2\n"
        "X15,10:40:00,10:40:00,stop_point:SP_2,0,0,1\n"
        "X15,10:45:00,10:45:00,stop_point:SP_9,1,0,2\n"
        "ARR,10:50:00,10:50:00,stop_point:SP_3,0,0,1\n"
        "ARR,10:55:00,10:55:00,stop_point:SP_2,0,0,2\n"
        "ARR,10:56:00,10:56:00,stop_point:SP_1,1,0,3\n"
        "A1,10:00:00,10:00:00,stop_point:SP_4,0,0,1\n"
        "A1,10:04:00,10:04:00,stop_point:SP_3,0,0,2\n"
        "NIGHT,24:30:00,24:30:00,stop_point:SP_2,0,0,1\n"
        "NIGHT,24:40:00,24:40:00,stop_point:SP_9,1,0,2\n"
    ),
}


def write_zip(path) -> str:
    with zipfile.ZipFile(path, "w") as zf:
        for name, body in FILES.items():
            zf.writestr(name, body)
    return str(path)


@pytest.fixture(scope="session")
def gtfs_zip(tmp_path_factory):
    return write_zip(tmp_path_factory.mktemp("gtfszip") / "gtfs.zip")


@pytest.fixture(scope="session")
def store(tmp_path_factory, gtfs_zip):
    from tisseo_data.static import GtfsStore, build_index
    d = tmp_path_factory.mktemp("gtfs")
    db = d / "gtfs.sqlite"
    build_index(gtfs_zip, str(db), "test")
    return GtfsStore(str(db))


def make_feed(trip_updates=(), alerts=(), ts=0) -> bytes:
    """trip_updates: (trip_id, route_id, relationship, [(seq, stop_id, time, delay, skipped)])
    alerts: (id, header, [route_ids], [stop_ids], [(start, end)])"""
    from google.transit import gtfs_realtime_pb2 as g
    f = g.FeedMessage()
    f.header.gtfs_realtime_version = "2.0"
    f.header.timestamp = ts
    for trip_id, route_id, rel, stus in trip_updates:
        e = f.entity.add(id=f"tu-{trip_id}")
        e.trip_update.trip.trip_id = trip_id
        e.trip_update.trip.route_id = route_id
        e.trip_update.trip.schedule_relationship = rel
        for seq, stop_id, t, delay, skipped in stus:
            s = e.trip_update.stop_time_update.add()
            if seq is not None:
                s.stop_sequence = seq
            s.stop_id = stop_id
            if t is not None:
                s.departure.time = int(t)
            if delay is not None:
                s.departure.delay = delay
            if skipped:
                s.schedule_relationship = 1
    for aid, header, routes, stops, periods in alerts:
        e = f.entity.add(id=aid)
        e.alert.header_text.translation.add(text=header)
        e.alert.description_text.translation.add(text=f"<p>{header}<br/>details &amp; more</p>")
        for r in routes:
            e.alert.informed_entity.add(route_id=r)
        for s in stops:
            e.alert.informed_entity.add(stop_id=s)
        if not routes and not stops:
            e.alert.informed_entity.add(agency_id="network:1")
        for start, end in periods:
            p = e.alert.active_period.add()
            if start:
                p.start = start
            if end:
                p.end = end
    return f.SerializeToString()
