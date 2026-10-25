"""Data-layer tests for 1.0.0: lean index, journeys, trip stops, timetable change,
API merge (mocked responses only), health/backoff, GBFS and park-and-ride parsing."""
import asyncio
import json
import random
from datetime import date, datetime, timedelta

import pytest

from tisseo_data.const import TZ

NOW = datetime(2026, 10, 24, 9, 50, tzinfo=TZ)


# ---------------- lean index ----------------
def test_lean_index_keeps_only_relevant_trips(tmp_path, gtfs_zip, store):
    from tisseo_data.static import GtfsStore, build_index
    full = store
    stats = build_index(gtfs_zip, str(tmp_path / "lean.sqlite"), "t", ["stop_area:SA_3"])
    lean = GtfsStore(str(tmp_path / "lean.sqlite"))
    assert stats["trips_kept"] == 1  # only A1 calls at Compans
    assert lean.stops_key() == "stop_area:SA_3"
    assert full.stops_key() == "*"
    with lean._con() as con:
        assert {r[0] for r in con.execute("SELECT trip_id FROM trips")} == {"A1"}
    # search, stop lines and nearby still work for unconfigured stops
    assert lean.search_stops("capitole")[0][0].stop_id == "stop_area:SA_2"
    assert [r.short_name for r in lean.routes_for_stop("stop_area:SA_1")] == \
        [r.short_name for r in full.routes_for_stop("stop_area:SA_1")]
    # a configured stop point pulls in its whole stop area
    stats2 = build_index(gtfs_zip, str(tmp_path / "lean2.sqlite"), "t", ["stop_point:SP_2"])
    assert stats2["trips_kept"] == 6  # B1 B2 T15 X15 ARR NIGHT (via SP_1/SP_2 of SA_1)
    assert stats["bytes"] > 0 and stats["seconds"] >= 0


def test_terminus_and_pickup_rules_kept(store):
    assert store.routes_for_stop("stop_point:SP_9") == []


def test_nearby_sorted(store):
    near = store.nearby_stops(43.61, 1.43, limit=10)
    assert near[0][0].stop_id == "stop_area:SA_3"
    assert near[0][1] < 5
    assert [n[0].stop_id for n in near[1:]] and all(
        near[i][1] <= near[i + 1][1] for i in range(len(near) - 1))
    assert near[0][2] == ["A"]


# ---------------- journeys ----------------
def test_direct_journey(store):
    from tisseo_data.journeys import find_connections
    res = find_connections(store, None, "stop_area:SA_2", "stop_area:SA_1", now=NOW, count=5)
    assert [(c.departure.strftime("%H:%M"), c.arrival.strftime("%H:%M"), c.transfers) for c in res] \
        == [("10:00", "10:05", 0), ("10:20", "10:25", 0), ("10:50", "10:55", 0)]
    d = res[0].as_dict()
    assert d["duration_min"] == 5 and d["legs"][0]["line"] == "B"
    assert d["legs"][0]["from"] == "Capitole" and d["legs"][0]["to"] == "Jeanne d'Arc"


def test_one_transfer_journey(store):
    from tisseo_data.journeys import find_connections
    res = find_connections(store, None, "stop_area:SA_3", "stop_area:SA_1", now=NOW, count=3)
    assert len(res) >= 1
    c = res[0]
    assert c.transfers == 1 and [lg.line for lg in c.legs] == ["A", "B"]
    # A1 arrives 10:04 at Capitole; B1 (10:00) is gone, so B2 10:20 with >= 3 min transfer
    assert c.legs[1].departure.strftime("%H:%M") == "10:20"
    assert c.arrival.strftime("%H:%M") == "10:25"
    # a big minimum transfer makes it impossible
    none = find_connections(store, None, "stop_area:SA_3", "stop_area:SA_1", now=NOW,
                            min_transfer=timedelta(hours=2))
    assert none == []


def test_journey_realtime_delay(store):
    from .conftest import make_feed
    from tisseo_data.journeys import find_connections
    from tisseo_data.realtime import parse_realtime
    rt = parse_realtime(make_feed([("B1", "line:B", 0, [(1, "stop_point:SP_3", None, 120, False)])]))
    res = find_connections(store, rt, "stop_area:SA_2", "stop_area:SA_1", now=NOW)
    first = res[0]
    assert first.legs[0].realtime and first.legs[0].delay == 120
    assert first.departure.strftime("%H:%M") == "10:02"
    assert first.arrival.strftime("%H:%M") == "10:07"  # delay propagated


# ---------------- trip stops ----------------
def test_trip_stops(store):
    from tisseo_data.trips import trip_stops
    sched = datetime(2026, 10, 24, 10, 0, tzinfo=TZ)
    t = trip_stops(store, None, "B1", "stop_area:SA_2", sched, now=NOW + timedelta(minutes=12))
    assert t["line"] == "B" and t["headsign"] == "Ramonville"
    assert [s["name"] for s in t["stops"]] == ["Capitole", "Jeanne d'Arc", "Terminus"]
    assert [s["past"] for s in t["stops"]] == [True, False, False]
    assert t["stops"][0]["is_selected"] and t["next_index"] == 1
    assert trip_stops(store, None, "nope") is None
    # without a pinned departure the running service day is guessed
    t2 = trip_stops(store, None, "B2", now=NOW)
    assert t2["stops"][0]["scheduled"].startswith("2026-10-24T10:20")


# ---------------- timetable change ----------------
def test_timetable_change(store):
    from tisseo_data.timetable import timetable_change
    # 2026-10-26: service WK removed -> no departures tomorrow
    r = timetable_change(store, store.child_stop_ids("stop_area:SA_1"), date(2026, 10, 25))
    assert r["changed"] and r["tomorrow_departures"] == 0 and "No departures" in r["description"]
    fr = timetable_change(store, store.child_stop_ids("stop_area:SA_1"), date(2026, 10, 25), lang="fr")
    assert "Aucun départ" in fr["description"]
    # 2026-10-24 -> 25: EXTRA adds X15 on Sunday the 25th
    r2 = timetable_change(store, store.child_stop_ids("stop_area:SA_1"), date(2026, 10, 24))
    assert r2["tomorrow_departures"] == r2["today_departures"] + 1
    r3 = timetable_change(store, store.child_stop_ids("stop_area:SA_1"), date(2026, 10, 21))
    assert not r3["changed"]


# ---------------- official API (mocked) ----------------
API_PAYLOAD = {
    "expirationDate": "2026-10-24 10:01",
    "departures": {"departure": [
        {"dateTime": "2026-10-24 10:13:00", "realTime": "yes",
         "line": {"id": "line:15", "shortName": "15", "name": "Bus 15", "color": "(160,103,15)"},
         "destination": [{"name": "Etats-Unis", "cityName": "TOULOUSE"}]},
        {"dateTime": "2026-10-24 10:33:00", "realTime": "yes",
         "line": {"shortName": "15", "name": "Bus 15", "color": "(160,103,15)"},
         "destination": [{"name": "Fondeyre", "cityName": "TOULOUSE"}]},
        {"dateTime": "2026-10-24 10:05:00", "realTime": "no",
         "line": {"id": "line:B", "shortName": "B", "name": "Ligne B", "color": "(255,221,0)"},
         "destination": [{"name": "Ramonville", "cityName": "RAMONVILLE"}]},
    ]},
}


def test_parse_api_payload():
    from tisseo_data.api import parse_schedules, sanitize
    deps = parse_schedules(API_PAYLOAD)
    assert len(deps) == 3 and deps[0].realtime and not deps[2].realtime
    assert deps[0].color == "#A0670F" and deps[0].destination == "Etats-Unis"
    assert deps[0].when == datetime(2026, 10, 24, 10, 13, tzinfo=TZ)
    assert sanitize("GET https://x/y.json?a=1&key=SECRET123 failed", "SECRET123").count("SECRET") == 0


def test_merge_api(store):
    from tisseo_data.api import parse_schedules
    from tisseo_data.departures import merge_api, next_departures
    deps = next_departures(store, None, "stop_area:SA_1", now=NOW, count=12)
    merged = merge_api(deps, parse_schedules(API_PAYLOAD), store.routes(), live=set(),
                       stop_routes={"line:15", "line:B"}, route_filter=None, now=NOW,
                       stop_name="Jeanne d'Arc", stop_id="stop_area:SA_1")
    t15 = next(d for d in merged if d.trip_id == "T15")
    assert t15.realtime and t15.realtime_source == "tisseo_api" and t15.delay == 60
    added = [d for d in merged if d.realtime_source == "tisseo_api" and not d.trip_id]
    assert len(added) == 1 and added[0].destination == "Fondeyre"
    b1 = next(d for d in merged if d.trip_id == "B1")
    assert not b1.realtime  # API "realTime=no" never overrides the timetable
    # GTFS-RT wins: a line with live GTFS-RT data is left untouched
    deps2 = next_departures(store, None, "stop_area:SA_1", now=NOW, count=12)
    merged2 = merge_api(deps2, parse_schedules(API_PAYLOAD), store.routes(), live={"line:15"},
                        stop_routes=None, route_filter=None, now=NOW)
    assert not any(d.realtime_source == "tisseo_api" for d in merged2)


class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Session:
    def __init__(self, status, body):
        self.status, self.body, self.calls = status, body, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        return _Resp(self.status, self.body)


async def test_fetch_api_ok_and_invalid_key():
    from tisseo_data.api import InvalidApiKey, fetch_stop_schedules
    s = _Session(200, json.dumps(API_PAYLOAD))
    deps = await fetch_stop_schedules(s, "K", "stop_area:SA_1", 5)
    assert len(deps) == 3
    url, params = s.calls[0]
    assert url == "https://api.tisseo.fr/v2/stops_schedules.json"
    assert params["stopAreaId"] == "stop_area:SA_1" and params["key"] == "K"
    for status, body in ((401, ""), (403, "denied"), (200, json.dumps({"error": "Invalid key"}))):
        with pytest.raises(InvalidApiKey):
            await fetch_stop_schedules(_Session(status, body), "K", "stop_point:SP_1")


# ---------------- health ----------------
def test_backoff_and_breaker():
    from tisseo_data.health import DEGRADED, DOWN, OK, FeedHealth, backoff_delay
    rng = random.Random(1)
    for a in range(8):
        d = backoff_delay(a, base=0.5, cap=8, rng=rng)
        assert 0 <= d <= min(8, 0.5 * 2 ** a)
    t = [1000.0]
    h = FeedHealth("x", clock=lambda: t[0])
    assert h.state == DEGRADED  # no data yet
    for _ in range(10):
        h.record(True)
    assert h.state == OK and h.success_rate == 1.0
    h.record(False, "boom")
    assert h.state == DEGRADED
    h.record(False)
    h.record(False)
    assert h.breaker_open and h.state == DOWN and not h.allow()
    t[0] += 40  # 30 s +/- 20 % jitter
    assert h.allow()
    h.record(True)
    assert not h.breaker_open and h.consecutive_failures == 0
    t[0] += 10_000
    assert h.state == DOWN  # stale: no success for too long
    assert h.as_dict()["breaker_trips"] == 1


# ---------------- GBFS / P+R ----------------
def test_gbfs_parse():
    from tisseo_data.bikes import nearest, parse_information, parse_status
    info = parse_information({"data": {"stations": [
        {"station_id": "1", "name": [{"text": "00001 - POIDS DE L'HUILE", "language": "fr"}],
         "lat": 43.6044, "lon": 1.4449, "address": "Rue", "capacity": 20},
        {"station_id": "2", "name": [{"text": "FAR", "language": "fr"}], "lat": 43.7, "lon": 1.5}]}})
    st, ts = parse_status({"last_updated": "2026-10-24T08:00:00Z", "data": {"stations": [
        {"station_id": "1", "num_vehicles_available": 5,
         "vehicle_types_available": [{"vehicle_type_id": "mechanical", "count": 3},
                                     {"vehicle_type_id": "electrical", "count": 2}],
         "num_docks_available": 14, "is_installed": True, "is_renting": True,
         "is_returning": True, "last_reported": "2026-10-24T07:59:00Z"}]}})
    assert info["1"].name.startswith("00001") and info["1"].capacity == 20
    assert st["1"].bikes == 5 and st["1"].electric == 2 and st["1"].mechanical == 3
    assert st["1"].docks == 14 and ts.year == 2026
    assert nearest(info, 43.6045, 1.4440)[0][1].station_id == "1"


def test_parkride_parse():
    from tisseo_data.parkride import parse_parkride
    p = parse_parkride({"results": [{"id": "31555-P-0024", "nom": "ARENES", "nb_places": 522,
                                     "nb_pmr": 11, "nb_velo": 20, "adresse": "Rue",
                                     "commune": "TOULOUSE",
                                     "geo_point_2d": {"lat": 43.59, "lon": 1.41}}]})
    assert p["31555-P-0024"].capacity == 522 and p["31555-P-0024"].name == "Arenes"


def test_gbfs_skips_unnamed_placeholder_stations():
    from custom_components.tisseo.data.bikes import parse_information
    info = parse_information({"data": {"stations": [
        {"station_id": "303", "name": [{"text": "", "language": "fr"}], "lat": 43.6, "lon": 1.44, "capacity": 0},
        {"station_id": "1", "name": [{"text": "", "language": "fr"}, {"text": "POIDS DE L'HUILE", "language": "en"}],
         "lat": 43.6, "lon": 1.44, "capacity": 19}]}})
    assert list(info) == ["1"] and info["1"].name == "POIDS DE L'HUILE"
