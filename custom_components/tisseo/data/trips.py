"""Upcoming calls of one trip (for the card's trip dialog)."""
from __future__ import annotations

from datetime import datetime, timedelta

from .const import TZ
from .departures import apply_rt, service_day_origin
from .realtime import RealtimeSnapshot
from .static import GtfsStore


def trip_stops(store: GtfsStore, rt: RealtimeSnapshot | None, trip_id: str,
               stop_id: str | None = None, scheduled: datetime | None = None,
               now: datetime | None = None) -> dict | None:
    """Calls of ``trip_id`` with scheduled and (when known) real-time times.

    ``stop_id``/``scheduled`` (a departure of that trip from that stop) pin the
    service day; otherwise the running day closest to now is used.
    """
    now = (now or datetime.now(TZ)).astimezone(TZ)
    calls = store.trip_calls(trip_id)
    rt = rt or RealtimeSnapshot.empty()
    if not calls:
        # Trips added by the real-time feed (ADDED / not in the timetable): list the
        # calls the feed itself publishes.
        return _rt_only(store, rt, trip_id, stop_id, now)
    origin = None
    if scheduled is not None and stop_id:
        ids = set(store.child_stop_ids(stop_id)) | {stop_id}
        for c in calls:
            if c["stop_id"] in ids or c["parent"] in ids:
                origin = scheduled.astimezone(TZ) - timedelta(seconds=c["dep"])
                break
    if origin is None:
        best = None
        for day in (now.date() - timedelta(days=1), now.date()):
            if not store.trip_runs_on(trip_id, day):
                continue
            o = service_day_origin(day)
            end = o + timedelta(seconds=calls[-1]["arr"])
            gap = abs((end - now).total_seconds())
            if now <= end + timedelta(minutes=30) and (best is None or gap < best[0]):
                best = (gap, o)
        origin = best[1] if best else service_day_origin(now.date())
    # snap to a real service-day origin (handles DST days)
    trip = rt.trips.get(trip_id)
    out = []
    pinned = stop_id and (set(store.child_stop_ids(stop_id)) | {stop_id})
    for c in calls:
        sched_arr = origin + timedelta(seconds=c["arr"])
        sched_dep = origin + timedelta(seconds=c["dep"])
        exp_dep, delay, is_rt, canceled = apply_rt(trip, c["stop_id"], c["seq"], sched_dep)
        out.append({
            "stop_id": c["stop_id"], "stop_area": c["parent"] or c["stop_id"], "name": c["name"],
            "seq": c["seq"], "scheduled": sched_dep.isoformat(),
            "scheduled_arrival": sched_arr.isoformat(), "expected": exp_dep.isoformat(),
            "delay": delay, "realtime": is_rt, "skipped": canceled and trip is not None
            and trip.relationship != 3, "past": exp_dep < now - timedelta(seconds=30),
            "is_selected": bool(pinned and (c["stop_id"] in pinned or c["parent"] in pinned)),
            "lat": c["lat"], "lon": c["lon"],
        })
    info = store.trip_info(trip_id) or {}
    routes = store.routes()
    r = routes.get(info.get("route_id") or calls[0]["route_id"])
    nxt = next((i for i, s in enumerate(out) if not s["past"]), None)
    return {
        "trip_id": trip_id, "headsign": info.get("headsign") or calls[0]["headsign"],
        "route_id": r.route_id if r else calls[0]["route_id"], "line": r.short_name if r else "",
        "color": f"#{r.color}" if r and r.color else "",
        "text_color": f"#{r.text_color}" if r and r.text_color else "",
        "realtime": trip is not None, "canceled": bool(trip and trip.relationship == 3),
        "next_index": nxt, "stops": out,
    }


def _rt_only(store: GtfsStore, rt: RealtimeSnapshot, trip_id: str, stop_id: str | None,
             now: datetime) -> dict | None:
    trip = rt.trips.get(trip_id)
    ups = [u for u in (trip.updates if trip else []) if u.time]
    if not ups:
        return None
    names = store.stop_names({u.stop_id for u in ups})
    stops_ = {u.stop_id: store.get_stop(u.stop_id) for u in ups}
    pinned = set(store.child_stop_ids(stop_id)) | {stop_id} if stop_id else set()
    out = []
    for u in sorted(ups, key=lambda x: (x.seq if x.seq is not None else 0, x.time)):
        st = stops_.get(u.stop_id)
        t = datetime.fromtimestamp(u.time, TZ)
        area = (st.parent or st.stop_id) if st else u.stop_id
        out.append({
            "stop_id": u.stop_id, "stop_area": area, "name": names.get(u.stop_id, u.stop_id),
            "seq": u.seq, "scheduled": None, "scheduled_arrival": None,
            "expected": t.isoformat(), "delay": u.delay, "realtime": True,
            "skipped": u.skipped, "past": t < now - timedelta(seconds=30),
            "is_selected": bool(pinned and (u.stop_id in pinned or area in pinned)),
            "lat": st.lat if st else None, "lon": st.lon if st else None,
        })
    r = store.routes().get(trip.route_id)
    nxt = next((i for i, x in enumerate(out) if not x["past"]), None)
    return {
        "trip_id": trip_id, "headsign": out[-1]["name"], "route_id": trip.route_id,
        "line": r.short_name if r else trip.route_id,
        "color": f"#{r.color}" if r and r.color else "",
        "text_color": f"#{r.text_color}" if r and r.text_color else "",
        "realtime": True, "canceled": trip.relationship == 3, "added": True,
        "next_index": nxt, "stops": out,
    }
