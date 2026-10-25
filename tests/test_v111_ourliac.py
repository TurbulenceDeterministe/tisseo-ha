"""1.1.1 regressions, reproduced on a synthetic suburban feed modelled on Ourliac.

* Journeys from a suburban stop need two changes (bus -> metro A -> metro B); metro A
  calls at neither end, so a lean index without the trunk lines could not find it.
* The only line at the stop has no Sunday service: the departure sensor must say when
  the next one runs, and the journey sensor must fall back to the next service.
* Trips added by the GTFS-RT feed (not in the timetable) must still open in the trip dialog.
"""
import zipfile
from datetime import datetime, timedelta

import pytest

from .conftest import make_feed

from tisseo_data.const import TZ

FEED = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nnetwork:1,Tisséo,http://www.tisseo.fr,Europe/Paris\n",
    "stops.txt": (
        "stop_id,stop_code,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
        "stop_area:SA_O,,Ourliac,43.57,1.37,1,\n"
        "stop_point:SP_O1,4731,Ourliac,43.57,1.37,0,stop_area:SA_O\n"
        "stop_area:SA_BC,,Basso Cambo,43.57,1.39,1,\n"
        "stop_point:SP_BC1,500,Basso Cambo,43.57,1.39,0,stop_area:SA_BC\n"
        "stop_point:SP_BC2,501,Basso Cambo,43.57,1.39,0,stop_area:SA_BC\n"
        "stop_area:SA_JJ,,Jean Jaurès,43.60,1.45,1,\n"
        "stop_point:SP_JJ1,600,Jean Jaurès,43.60,1.45,0,stop_area:SA_JJ\n"
        "stop_point:SP_JJ2,601,Jean Jaurès,43.60,1.45,0,stop_area:SA_JJ\n"
        "stop_area:SA_BO,,Borderouge,43.64,1.45,1,\n"
        "stop_point:SP_BO1,700,Borderouge,43.64,1.45,0,stop_area:SA_BO\n"
    ),
    "routes.txt": (
        "route_id,agency_id,route_short_name,route_long_name,route_color,route_text_color,route_type\n"
        "line:25,network:1,25,Bus 25,6c3483,ffffff,3\n"
        "line:A,network:1,A,Balma / Basso Cambo,e2001a,ffffff,1\n"
        "line:B,network:1,B,Borderouge / Ramonville,ffdd00,000000,1\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "WKD,1,1,1,1,1,0,0,20261019,20261108\n"
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,direction_id,trip_headsign\n"
        "line:25,WKD,B25_EARLY,0,Basso Cambo\n"
        "line:25,WKD,B25_0905,0,Basso Cambo\n"
        "line:A,WKD,MA_0925,0,Balma\n"
        "line:B,WKD,MB_0945,0,Borderouge\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,pickup_type,drop_off_type,stop_sequence\n"
        "B25_EARLY,06:19:00,06:19:00,stop_point:SP_O1,0,0,1\n"
        "B25_EARLY,06:34:00,06:34:00,stop_point:SP_BC1,1,0,2\n"
        "B25_0905,09:05:00,09:05:00,stop_point:SP_O1,0,0,1\n"
        "B25_0905,09:20:00,09:20:00,stop_point:SP_BC1,1,0,2\n"
        "MA_0925,09:25:00,09:25:00,stop_point:SP_BC2,0,0,1\n"
        "MA_0925,09:40:00,09:40:00,stop_point:SP_JJ1,1,0,2\n"
        "MB_0945,09:45:00,09:45:00,stop_point:SP_JJ2,0,0,1\n"
        "MB_0945,09:55:00,09:55:00,stop_point:SP_BO1,1,0,2\n"
    ),
}
ENDS = ["stop_area:SA_O", "stop_point:SP_O1", "stop_area:SA_BO", "stop_point:SP_BO1"]
MONDAY_9 = datetime(2026, 10, 26, 9, 0, tzinfo=TZ)
SUNDAY_16 = datetime(2026, 10, 25, 16, 0, tzinfo=TZ)


@pytest.fixture(scope="module")
def zpath(tmp_path_factory):
    p = tmp_path_factory.mktemp("ourliac") / "gtfs.zip"
    with zipfile.ZipFile(p, "w") as zf:
        for name, body in FEED.items():
            zf.writestr(name, body)
    return str(p)


def _index(tmp_path_factory, zpath, trunk):
    from tisseo_data.static import GtfsStore, build_index
    db = tmp_path_factory.mktemp("idx") / "gtfs.sqlite"
    build_index(zpath, str(db), "test", stop_ids=ENDS, trunk=trunk)
    return GtfsStore(str(db))


@pytest.fixture(scope="module")
def lean(tmp_path_factory, zpath):
    return _index(tmp_path_factory, zpath, trunk=False)


@pytest.fixture(scope="module")
def trunk(tmp_path_factory, zpath):
    return _index(tmp_path_factory, zpath, trunk=True)


def test_stops_key_and_schema():
    from tisseo_data.static import SCHEMA_VERSION, is_trunk, stops_key
    assert SCHEMA_VERSION >= 5  # 1.1.1 indexes must be rebuilt
    assert stops_key(["b", "a"]) == "a,b"
    assert stops_key(["b", "a"], True) == "a,b|trunk"
    assert stops_key(None, True) == "*"
    assert is_trunk(1, "A") and is_trunk(0, "T1") and is_trunk(3, "L6")
    assert not is_trunk(3, "25") and not is_trunk(3, "LA")


def test_trunk_index_meta(lean, trunk):
    assert lean.stops_key().endswith("SP_O1") and not lean.stops_key().endswith("|trunk")
    assert trunk.stops_key().endswith("|trunk")


def test_two_changes_need_the_trunk_lines(lean, trunk):
    from tisseo_data.journeys import find_connections
    # Before 1.1.1: one change at most, and metro A was not in the lean index.
    assert find_connections(lean, None, "stop_area:SA_O", "stop_area:SA_BO", now=MONDAY_9) == []
    assert find_connections(trunk, None, "stop_area:SA_O", "stop_area:SA_BO", now=MONDAY_9,
                            max_transfers=1) == []
    res = find_connections(trunk, None, "stop_area:SA_O", "stop_area:SA_BO", now=MONDAY_9)
    assert len(res) == 1
    c = res[0]
    assert c.transfers == 2 and [lg.line for lg in c.legs] == ["25", "A", "B"]
    assert c.departure == MONDAY_9.replace(minute=5)
    assert c.arrival == MONDAY_9.replace(minute=55)
    d = c.as_dict()
    assert d["transfers"] == 2 and len(d["legs"]) == 3


def test_tight_middle_change_is_rejected(trunk):
    from tisseo_data.journeys import find_connections
    # 09:20 at Basso Cambo + 6 min > 09:25 metro: no connection.
    assert find_connections(trunk, None, "stop_area:SA_O", "stop_area:SA_BO", now=MONDAY_9,
                            min_transfer=timedelta(minutes=6)) == []


def test_next_scheduled_skips_a_day_without_service(trunk):
    nxt = trunk.next_scheduled(trunk.child_stop_ids("stop_area:SA_O"), SUNDAY_16)
    assert nxt["trip_id"] == "B25_EARLY" and nxt["route_id"] == "line:25"
    assert nxt["dep"] == datetime(2026, 10, 26, 6, 19, tzinfo=TZ)
    assert nxt["headsign"] == "Basso Cambo" and nxt["stop_id"] == "stop_point:SP_O1"
    assert trunk.next_scheduled(["stop_point:SP_O1"], SUNDAY_16, {"line:A"}) is None


def test_journey_falls_back_to_next_service(trunk):
    from tisseo_data.journeys import search_with_fallback
    conns, later = search_with_fallback(trunk, None, "stop_area:SA_O", "stop_area:SA_BO",
                                        now=MONDAY_9)
    assert not later and conns[0].departure.hour == 9
    # Sunday 16:00: no bus until Monday. The 06:19 bus has no onward metro in this feed
    # within its 3 h window, so the search moves on and finds the 09:05 one.
    conns, later = search_with_fallback(trunk, None, "stop_area:SA_O", "stop_area:SA_BO",
                                        now=SUNDAY_16)
    assert later and conns[0].departure == datetime(2026, 10, 26, 9, 5, tzinfo=TZ)
    # Monday 10:00: no more buses that day nor anything that reaches Borderouge.
    conns, later = search_with_fallback(trunk, None, "stop_area:SA_O", "stop_area:SA_BO",
                                        now=MONDAY_9.replace(hour=10))
    assert later and conns[0].departure == datetime(2026, 10, 27, 9, 5, tzinfo=TZ)


def test_trip_dialog_for_a_trip_added_by_the_realtime_feed(trunk):
    from tisseo_data.realtime import ADDED, parse_realtime
    from tisseo_data.trips import trip_stops
    t0 = MONDAY_9.timestamp()
    rt = parse_realtime(make_feed(trip_updates=[("EXTRA_A", "line:A", ADDED, [
        (1, "stop_point:SP_BC2", t0 - 600, None, False),
        (2, "stop_point:SP_JJ1", t0 + 300, 60, False),
    ])], ts=int(t0)))
    assert trunk.trip_calls("EXTRA_A") == []
    res = trip_stops(trunk, rt, "EXTRA_A", stop_id="stop_area:SA_JJ", now=MONDAY_9)
    assert res is not None and res["added"] and res["line"] == "A"
    assert [s["name"] for s in res["stops"]] == ["Basso Cambo", "Jean Jaurès"]
    assert res["headsign"] == "Jean Jaurès"
    assert [s["past"] for s in res["stops"]] == [True, False] and res["next_index"] == 1
    assert [s["is_selected"] for s in res["stops"]] == [False, True]
    assert all(s["scheduled"] is None and s["realtime"] for s in res["stops"])
    assert trip_stops(trunk, rt, "UNKNOWN", now=MONDAY_9) is None
