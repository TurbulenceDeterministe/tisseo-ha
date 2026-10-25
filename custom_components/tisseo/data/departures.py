"""Merge scheduled GTFS departures with GTFS-RT trip updates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

from .const import ROUTE_TYPE_NAMES, TZ
from .realtime import ADDED, CANCELED, Alert, RealtimeSnapshot
from .static import GtfsStore, RouteInfo

# Ignore an RT match whose time differs from the schedule by more than this
# (protects against applying today's update to yesterday's instance of a trip id).
MAX_RT_SHIFT = 3 * 3600


@dataclass
class Departure:
    line: str
    line_name: str
    route_id: str
    mode: str
    color: str
    destination: str
    stop_id: str
    stop_name: str
    scheduled: datetime | None
    expected: datetime
    delay: int | None          # seconds, None when no real-time info
    realtime: bool
    canceled: bool
    trip_id: str
    # Where the expected time comes from: "gtfs_rt" (TripUpdates) or "timetable".
    realtime_source: str = "timetable"
    text_color: str = ""
    # Live coverage of this line right now: "live" (the GTFS-RT feed carries
    # trip updates for this route), "not_published" (feed OK but nothing for
    # this route, e.g. metro A/B) or "feed_unavailable".
    live_coverage: str = "feed_unavailable"

    @property
    def minutes(self) -> int:
        return max(0, int((self.expected - datetime.now(TZ)).total_seconds() // 60))

    def as_dict(self, now: datetime | None = None) -> dict:
        d = asdict(self)
        d["scheduled"] = self.scheduled.isoformat() if self.scheduled else None
        d["expected"] = self.expected.isoformat()
        now = now or datetime.now(TZ)
        d["minutes"] = max(0, int((self.expected - now).total_seconds() // 60))
        return d


def service_day_origin(day: date) -> datetime:
    """GTFS times are measured from 'noon minus 12h' (correct across DST changes)."""
    return datetime(day.year, day.month, day.day, 12, tzinfo=TZ) - timedelta(hours=12)


def apply_rt(trip, stop_id: str, seq: int | None, sched: datetime):
    """Expected time for one scheduled call given the trip's GTFS-RT update (or None).

    Returns (expected, delay_seconds | None, is_realtime, canceled)."""
    exp, delay, is_rt, canceled = sched, None, False, False
    if trip is None:
        return exp, delay, is_rt, canceled
    if trip.relationship == CANCELED:
        return exp, delay, True, True
    u = trip.update_for(stop_id, seq)
    if u is not None and u.skipped:
        return exp, delay, True, True
    if u is not None and u.time:
        cand = datetime.fromtimestamp(u.time, TZ)
        if abs((cand - sched).total_seconds()) <= MAX_RT_SHIFT:
            exp, is_rt = cand, True
            delay = u.delay if u.delay is not None else int((cand - sched).total_seconds())
    else:
        d = u.delay if u is not None and u.delay is not None else trip.propagated_delay(seq)
        if d is not None and abs(d) <= MAX_RT_SHIFT:
            exp, delay, is_rt = sched + timedelta(seconds=d), d, True
    return exp, delay, is_rt, canceled


def next_departures(store: GtfsStore, rt: RealtimeSnapshot | None, stop_id: str,
                    now: datetime | None = None, route_ids: set[str] | None = None,
                    count: int = 5, window: timedelta = timedelta(hours=3),
                    include_canceled: bool = False) -> list[Departure]:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    feed_ok = rt is not None
    rt = rt or RealtimeSnapshot.empty()
    covered = live_routes(rt)
    stop_ids = store.child_stop_ids(stop_id)
    stop_set = set(stop_ids)
    names = store.stop_names(stop_ids)
    routes: dict[str, RouteInfo] = store.routes()
    look_back = timedelta(minutes=30)  # late vehicles may still be ahead of us
    out: list[Departure] = []
    seen_trips: set[str] = set()

    def route_ok(rid: str) -> bool:
        return not route_ids or rid in route_ids

    def mk(rid, dest, sid, sched, exp, delay, is_rt, canceled, trip_id) -> Departure:
        r = routes.get(rid)
        return Departure(
            line=r.short_name if r else rid, line_name=r.long_name if r else "",
            route_id=rid, mode=ROUTE_TYPE_NAMES.get(r.type, "bus") if r else "bus",
            color=f"#{r.color}" if r and r.color else "", destination=dest, stop_id=sid,
            stop_name=names.get(sid, sid), scheduled=sched, expected=exp, delay=delay,
            realtime=is_rt, canceled=canceled, trip_id=trip_id,
            realtime_source="gtfs_rt" if is_rt else "timetable",
            text_color=f"#{r.text_color}" if r and r.text_color else "",
            live_coverage=("live" if rid in covered else "not_published") if feed_ok
            else "feed_unavailable")

    today = now.date()
    for day in (today - timedelta(days=1), today, today + timedelta(days=1)):
        origin = service_day_origin(day)
        lo = int((now - look_back - origin).total_seconds())
        hi = int((now + window - origin).total_seconds())
        if hi < 0 or lo > 48 * 3600:
            continue
        for row in store.scheduled(stop_ids, day, max(lo, 0), hi):
            if not route_ok(row["route_id"]):
                continue
            sched = origin + timedelta(seconds=row["dep"])
            trip = rt.trips.get(row["trip_id"])
            exp, delay, is_rt, canceled = apply_rt(trip, row["stop_id"], row["seq"], sched)
            if is_rt:
                seen_trips.add(row["trip_id"])
            if canceled and not include_canceled:
                continue
            if exp < now - timedelta(seconds=30) or exp > now + window:
                continue
            out.append(mk(row["route_id"], row["headsign"], row["stop_id"], sched, exp,
                          delay, is_rt, canceled, row["trip_id"]))

    # Trips that only exist in the real-time feed (ADDED / not in the static GTFS).
    stop_names_cache: dict[str, str] = {}
    for trip in rt.trips.values():
        if trip.trip_id in seen_trips or trip.relationship == CANCELED:
            continue
        if trip.relationship != ADDED and trip.trip_id and _in_static(store, trip.trip_id):
            continue
        if not route_ok(trip.route_id):
            continue
        for u in trip.updates:
            if u.stop_id in stop_set and u.time and not u.skipped:
                exp = datetime.fromtimestamp(u.time, TZ)
                if now - timedelta(seconds=30) <= exp <= now + window:
                    last = trip.updates[-1].stop_id
                    if last not in stop_names_cache:
                        stop_names_cache.update(store.stop_names([last]))
                    out.append(mk(trip.route_id, stop_names_cache.get(last, ""), u.stop_id,
                                  None, exp, u.delay, True, False, trip.trip_id))
                break

    out.sort(key=lambda d: d.expected)
    return out[:count]


def live_routes(rt: RealtimeSnapshot | None) -> set[str]:
    """Route ids for which the GTFS-RT feed currently publishes trip updates."""
    if rt is None:
        return set()
    return {t.route_id for t in rt.trips.values() if t.route_id}


_static_trip_cache: dict[str, dict[str, bool]] = {}


def _in_static(store: GtfsStore, trip_id: str) -> bool:
    cache = _static_trip_cache.setdefault(store.db_path, {})
    if trip_id not in cache:
        with store._con() as con:  # noqa: SLF001
            cache[trip_id] = con.execute(
                "SELECT 1 FROM trips WHERE trip_id=?", (trip_id,)).fetchone() is not None
    return cache[trip_id]


def clear_caches() -> None:
    _static_trip_cache.clear()


def alerts_for(rt: RealtimeSnapshot | None, stop_ids: set[str], route_ids: set[str],
               include_network: bool = True, now: datetime | None = None) -> list[Alert]:
    """Active alerts relevant to the given stops / routes (plus network-wide ones)."""
    if rt is None:
        return []
    ts = (now or datetime.now(TZ)).timestamp()
    out = []
    for a in rt.alerts:
        if not a.active_at(ts):
            continue
        if (a.network_wide and include_network) or (a.route_ids & route_ids) or (a.stop_ids & stop_ids):
            out.append(a)
    return out


API_MATCH_WINDOW = timedelta(minutes=15)


def _api_route(api_dep, routes: dict[str, RouteInfo], allowed: set[str] | None) -> str | None:
    if api_dep.line_id and api_dep.line_id in routes:
        return api_dep.line_id
    cands = [rid for rid, r in routes.items()
             if r.short_name and r.short_name == api_dep.line_short and (not allowed or rid in allowed)]
    return cands[0] if len(cands) == 1 else None


def merge_api(deps: list[Departure], api_deps: list, routes: dict[str, RouteInfo],
              live: set[str], stop_routes: set[str] | None, route_filter: set[str] | None,
              now: datetime | None = None, window: timedelta = timedelta(hours=3),
              stop_name: str = "", stop_id: str = "") -> list[Departure]:
    """Merge official-API (user key) real-time departures into GTFS departures.

    Only routes *without* GTFS-RT predictions are touched (GTFS-RT wins when both
    exist). An API real-time departure updates the closest not-yet-matched scheduled
    departure of the same line within ±15 min; unmatched ones are added.
    Returns a new sorted list (input objects may be modified).
    """
    now = (now or datetime.now(TZ)).astimezone(TZ)
    used: set[int] = set()
    added: list[Departure] = []
    for a in sorted(api_deps, key=lambda x: x.when):
        if not a.realtime:
            continue
        rid = _api_route(a, routes, stop_routes)
        if rid is None or rid in live or (route_filter and rid not in route_filter):
            continue
        best, best_gap = None, None
        for i, d in enumerate(deps):
            if i in used or d.route_id != rid or d.realtime or d.scheduled is None:
                continue
            gap = abs((d.scheduled - a.when).total_seconds())
            if gap <= API_MATCH_WINDOW.total_seconds() and (best_gap is None or gap < best_gap):
                best, best_gap = i, gap
        if best is not None:
            d = deps[best]
            used.add(best)
            d.expected = a.when
            d.delay = int((a.when - d.scheduled).total_seconds())
            d.realtime = True
            d.realtime_source = "tisseo_api"
        elif now - timedelta(seconds=30) <= a.when <= now + window:
            r = routes.get(rid)
            added.append(Departure(
                line=r.short_name if r else a.line_short, line_name=r.long_name if r else a.line_name,
                route_id=rid, mode=ROUTE_TYPE_NAMES.get(r.type, "bus") if r else "bus",
                color=f"#{r.color}" if r and r.color else a.color, destination=a.destination,
                stop_id=stop_id, stop_name=stop_name, scheduled=None, expected=a.when, delay=None,
                realtime=True, canceled=False, trip_id="", realtime_source="tisseo_api",
                text_color=f"#{r.text_color}" if r and r.text_color else "",
                live_coverage="api"))
    out = [d for d in deps + added if d.expected >= now - timedelta(seconds=30)]
    out.sort(key=lambda d: d.expected)
    return out
