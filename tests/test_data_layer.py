"""Unit tests for the pure-python data layer (synthetic GTFS + GTFS-RT)."""
from datetime import datetime, timedelta

from tisseo_data.const import TZ
from tisseo_data.departures import alerts_for, next_departures, service_day_origin
from tisseo_data.realtime import ADDED, CANCELED, SCHEDULED, parse_realtime

from .conftest import make_feed

NOW = datetime(2026, 10, 24, 9, 58, tzinfo=TZ)  # a Saturday, CEST


def ts(h, m, s=0, day=24):
    return datetime(2026, 10, day, h, m, s, tzinfo=TZ).timestamp()


def test_search_is_accent_and_case_insensitive(store):
    res = store.search_stops("jeanne d arc")
    assert res[0][0].stop_id == "stop_area:SA_1"
    assert set(res[0][1]) == {"B", "15"}
    assert store.search_stops("stop_point:SP_2")[0][0].stop_id == "stop_point:SP_2"
    assert store.search_stops("101")[0][0].stop_id == "stop_point:SP_1"  # stop_code


def test_terminus_pickup_type_1_is_not_a_departure(store):
    assert store.routes_for_stop("stop_point:SP_9") == []


def test_dst_service_day_origin():
    # 2026-10-25 is the CEST->CET switch; GTFS 08:00:00 must be 08:00 local wall time.
    o = service_day_origin(datetime(2026, 10, 25).date())
    assert o + timedelta(hours=8) == datetime(2026, 10, 25, 8, 0, tzinfo=TZ)


def test_schedule_only(store):
    deps = next_departures(store, None, "stop_area:SA_1", now=NOW, count=10)
    assert [(d.line, d.expected.strftime("%H:%M")) for d in deps] == [
        ("B", "10:05"), ("15", "10:12"), ("B", "10:25")]
    assert all(not d.realtime and d.delay is None for d in deps)
    assert deps[0].destination == "Ramonville" and deps[0].mode == "metro"


def test_line_filter(store):
    deps = next_departures(store, None, "stop_area:SA_1", now=NOW, route_ids={"line:15"})
    assert [d.line for d in deps] == ["15"]


def test_calendar_dates_add_and_remove(store):
    sun = datetime(2026, 10, 25, 10, 30, tzinfo=TZ)
    assert [d.trip_id for d in next_departures(store, None, "stop_point:SP_2", now=sun)] == ["X15"]
    mon = datetime(2026, 10, 26, 9, 0, tzinfo=TZ)  # WK removed on 26/10
    assert next_departures(store, None, "stop_area:SA_1", now=mon) == []


def test_after_midnight_trip_belongs_to_previous_service_day(store):
    late = datetime(2026, 10, 25, 0, 20, tzinfo=TZ)
    deps = next_departures(store, None, "stop_point:SP_2", now=late)
    assert deps[0].trip_id == "NIGHT"
    assert deps[0].expected == datetime(2026, 10, 25, 0, 30, tzinfo=TZ)


def test_realtime_merge(store):
    feed = make_feed(trip_updates=[
        # explicit time at our stop
        ("B1", "line:B", SCHEDULED, [(2, "stop_point:SP_1", ts(10, 7), 120, False)]),
        # delay at an earlier stop only -> propagated
        ("B2", "line:B", SCHEDULED, [(1, "stop_point:SP_3", None, 180, False)]),
        ("T15", "line:15", CANCELED, []),
        ("NEW1", "line:15", ADDED, [(1, "stop_point:SP_2", ts(10, 15), None, False),
                                    (2, "stop_point:SP_9", ts(10, 20), None, False)]),
    ])
    rt = parse_realtime(feed)
    deps = next_departures(store, rt, "stop_area:SA_1", now=NOW, count=10)
    got = [(d.trip_id, d.expected.strftime("%H:%M"), d.delay, d.realtime) for d in deps]
    assert got == [
        ("B1", "10:07", 120, True),
        ("NEW1", "10:15", None, True),
        ("B2", "10:28", 180, True),
    ]
    assert deps[1].destination == "Terminus" and deps[1].scheduled is None
    with_canceled = next_departures(store, rt, "stop_area:SA_1", now=NOW, count=10,
                                    include_canceled=True)
    assert any(d.trip_id == "T15" and d.canceled for d in with_canceled)


def test_skipped_stop_is_dropped(store):
    rt = parse_realtime(make_feed(trip_updates=[
        ("B1", "line:B", SCHEDULED, [(2, "stop_point:SP_1", None, None, True)])]))
    assert "B1" not in [d.trip_id for d in next_departures(store, rt, "stop_area:SA_1", now=NOW)]


def test_absurd_rt_shift_is_ignored(store):
    rt = parse_realtime(make_feed(trip_updates=[
        ("B1", "line:B", SCHEDULED, [(2, "stop_point:SP_1", ts(10, 5, day=25), None, False)])]))
    d = next_departures(store, rt, "stop_area:SA_1", now=NOW)[0]
    assert d.trip_id == "B1" and not d.realtime and d.expected.strftime("%H:%M") == "10:05"


def test_alerts(store):
    rt = parse_realtime(make_feed(alerts=[
        ("a1", "Ligne B perturbée", ["line:B"], [], []),
        ("a2", "Réseau: horaires vacances", [], [], []),
        ("a3", "Arrêt déplacé", [], ["stop_point:SP_2"], []),
        ("a4", "Expirée", ["line:B"], [], [(int(ts(1, 0)), int(ts(2, 0)))]),
        ("a5", "Autre ligne", ["line:99"], [], []),
    ]))
    stops = {"stop_area:SA_1", "stop_point:SP_1", "stop_point:SP_2"}
    ids = [a.id for a in alerts_for(rt, stops, {"line:B", "line:15"}, now=NOW)]
    assert ids == ["a1", "a2", "a3"]
    ids = [a.id for a in alerts_for(rt, stops, {"line:B"}, include_network=False, now=NOW)]
    assert ids == ["a1", "a3"]
    a = rt.alerts[0]
    assert a.description == "Ligne B perturbée\ndetails & more"


def test_arrival_at_terminus_area_is_not_a_departure(store):
    """A trip ending in a stop area (even via two of its platforms) does not depart from it."""
    at_terminus = next_departures(store, None, "stop_area:SA_1", now=NOW, count=20)
    assert "ARR" not in [d.trip_id for d in at_terminus]
    at_origin = next_departures(store, None, "stop_area:SA_2", now=NOW, count=20)
    assert "ARR" in [d.trip_id for d in at_origin]


def test_realtime_source_and_live_coverage(store):
    """Line 15 is in the feed (live); metro B is not (timetable, not_published)."""
    from tisseo_data.departures import live_routes
    rt = parse_realtime(make_feed(trip_updates=[
        ("T15", "line:15", SCHEDULED, [(1, "stop_point:SP_2", ts(10, 13), 60, False)])]))
    assert live_routes(rt) == {"line:15"}
    deps = {d.trip_id: d for d in next_departures(store, rt, "stop_area:SA_1", now=NOW, count=10)}
    assert deps["T15"].realtime_source == "gtfs_rt" and deps["T15"].live_coverage == "live"
    assert deps["B1"].realtime_source == "timetable" and deps["B1"].live_coverage == "not_published"
    offline = next_departures(store, None, "stop_area:SA_1", now=NOW, count=10)
    assert {d.live_coverage for d in offline} == {"feed_unavailable"}
    assert {d.realtime_source for d in offline} == {"timetable"}
