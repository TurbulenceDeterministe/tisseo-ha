"""Journeys between two stops: direct trips and one-transfer connections.

Bounded search on the lean index (trips calling at the configured origin and
destination are indexed in full, plus the trunk lines when a journey is configured):
  * direct: a trip boards at the origin and later sets down at the destination;
  * one transfer: a trip from the origin sets down at stop area X, another trip
    (different line) boards at X at least ``min_transfer`` later and reaches the
    destination;
  * two transfers: origin -> X by a first trip, X -> Y by any indexed trip of
    another line (in practice metro / tram / Linéo), then Y -> destination. Only
    used when it arrives at least ``min_transfer`` earlier than the best option
    with fewer changes from the same first departure.
For every first-leg departure only the earliest arrival is kept, then dominated
connections (leave earlier *and* arrive later) are dropped.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .const import ROUTE_TYPE_NAMES, TZ
from .departures import apply_rt, service_day_origin
from .realtime import RealtimeSnapshot
from .static import GtfsStore


@dataclass
class Leg:
    trip_id: str
    route_id: str
    line: str
    mode: str
    color: str
    text_color: str
    headsign: str
    from_stop_id: str
    from_name: str
    to_stop_id: str
    to_name: str
    sched_departure: datetime
    sched_arrival: datetime
    departure: datetime
    arrival: datetime
    realtime: bool = False
    delay: int | None = None
    canceled: bool = False
    stops: int = 0

    def as_dict(self) -> dict:
        return {
            "line": self.line, "route_id": self.route_id, "mode": self.mode,
            "color": self.color, "text_color": self.text_color, "headsign": self.headsign,
            "trip_id": self.trip_id, "from": self.from_name, "from_stop_id": self.from_stop_id,
            "to": self.to_name, "to_stop_id": self.to_stop_id,
            "departure": self.departure.isoformat(), "arrival": self.arrival.isoformat(),
            "scheduled_departure": self.sched_departure.isoformat(),
            "scheduled_arrival": self.sched_arrival.isoformat(),
            "realtime": self.realtime, "delay": self.delay, "canceled": self.canceled,
            "stops": self.stops,
        }


@dataclass
class Connection:
    legs: list[Leg] = field(default_factory=list)
    transfer_at_risk: bool = False

    @property
    def departure(self) -> datetime:
        return self.legs[0].departure

    @property
    def arrival(self) -> datetime:
        return self.legs[-1].arrival

    @property
    def transfers(self) -> int:
        return len(self.legs) - 1

    @property
    def duration_min(self) -> int:
        return round((self.arrival - self.departure).total_seconds() / 60)

    def as_dict(self) -> dict:
        return {
            "departure": self.departure.isoformat(), "arrival": self.arrival.isoformat(),
            "duration_min": self.duration_min, "transfers": self.transfers,
            "lines": [lg.line for lg in self.legs], "realtime": any(lg.realtime for lg in self.legs),
            "transfer_at_risk": self.transfer_at_risk, "canceled": any(lg.canceled for lg in self.legs),
            "legs": [lg.as_dict() for lg in self.legs],
        }


_DIRECT_SQL = """
SELECT t.trip_id, t.headsign, r.route_id, a.seq AS aseq, sa.stop_id AS a_stop, sa.name AS a_name,
       a.dep AS a_dep, b.seq AS bseq, sb.stop_id AS b_stop, sb.name AS b_name,
       COALESCE(sb.parent, sb.stop_id) AS b_area, b.dep - b.dwell AS b_arr
FROM stop_times a
JOIN trips t ON t.idx = a.trip_idx
JOIN service_dates sd ON sd.service_idx = t.service_idx AND sd.d = ?
JOIN stop_times b ON b.trip_idx = a.trip_idx AND b.seq > a.seq AND b.alight = 1
JOIN stops sa ON sa.idx = a.stop_idx
JOIN stops sb ON sb.idx = b.stop_idx
JOIN routes r ON r.idx = t.route_idx
WHERE a.stop_idx IN ({orig}) AND a.board = 1 AND a.dep BETWEEN ? AND ? {dest_filter}
ORDER BY a.dep, b.seq
"""

_LAST_LEG_SQL = """
SELECT t.trip_id, t.headsign, r.route_id, c.seq AS cseq, sc.stop_id AS c_stop, sc.name AS c_name,
       COALESCE(sc.parent, sc.stop_id) AS c_area, c.dep AS c_dep, e.seq AS eseq,
       se.stop_id AS e_stop, se.name AS e_name, e.dep - e.dwell AS e_arr
FROM stop_times e
JOIN trips t ON t.idx = e.trip_idx
JOIN service_dates sd ON sd.service_idx = t.service_idx AND sd.d = ?
JOIN stop_times c ON c.trip_idx = e.trip_idx AND c.seq < e.seq AND c.board = 1
JOIN stops sc ON sc.idx = c.stop_idx
JOIN stops se ON se.idx = e.stop_idx
JOIN routes r ON r.idx = t.route_idx
WHERE e.stop_idx IN ({dest}) AND e.alight = 1 AND e.dep - e.dwell BETWEEN ? AND ?
"""


_MID_LEG_SQL = """
SELECT t.trip_id, t.headsign, r.route_id, c.seq AS cseq, sc.stop_id AS c_stop, sc.name AS c_name,
       COALESCE(sc.parent, sc.stop_id) AS c_area, c.dep AS c_dep, e.seq AS eseq,
       se.stop_id AS e_stop, se.name AS e_name, COALESCE(se.parent, se.stop_id) AS e_area,
       e.dep - e.dwell AS e_arr
FROM stop_times c
JOIN trips t ON t.idx = c.trip_idx
JOIN service_dates sd ON sd.service_idx = t.service_idx AND sd.d = ?
JOIN stop_times e ON e.trip_idx = c.trip_idx AND e.seq > c.seq AND e.alight = 1
JOIN stops sc ON sc.idx = c.stop_idx
JOIN stops se ON se.idx = e.stop_idx
JOIN routes r ON r.idx = t.route_idx
WHERE c.stop_idx IN ({a1}) AND c.board = 1 AND c.dep BETWEEN ? AND ? AND e.stop_idx IN ({a2})
"""


def _suffix_best(items: list[tuple], arr_key) -> tuple[list, list]:
    """Sort by departure; for each position, the item with the earliest arrival from there on."""
    items.sort(key=lambda x: x[0])
    suffix: list = [None] * len(items)
    best = None
    for i in range(len(items) - 1, -1, -1):
        if best is None or arr_key(items[i]) < arr_key(best):
            best = items[i]
        suffix[i] = best
    return [x[0] for x in items], suffix


def _stop_idx(con, store: GtfsStore, stop_id: str) -> tuple[list[int], str]:
    ids = store.child_stop_ids(stop_id) + [stop_id]
    ph = ",".join("?" * len(ids))
    rows = con.execute(f"SELECT idx FROM stops WHERE stop_id IN ({ph})", ids).fetchall()
    st = store.get_stop(stop_id)
    return [r[0] for r in rows], (st.parent or st.stop_id) if st else stop_id


def find_connections(store: GtfsStore, rt: RealtimeSnapshot | None, origin: str,
                     destination: str, now: datetime | None = None, count: int = 3,
                     window: timedelta = timedelta(hours=3),
                     min_transfer: timedelta = timedelta(minutes=3),
                     max_transfers: int = 2, max_first_legs: int = 80) -> list[Connection]:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    rt = rt or RealtimeSnapshot.empty()
    routes = store.routes()
    look_back = timedelta(minutes=20)
    today = now.date()

    def mk_leg(trip_id, headsign, rid, from_stop, from_name, from_seq, sched_dep,
               to_stop, to_name, to_seq, sched_arr) -> Leg:
        r = routes.get(rid)
        trip = rt.trips.get(trip_id)
        dep, d_delay, d_rt, d_cx = apply_rt(trip, from_stop, from_seq, sched_dep)
        arr, a_delay, a_rt, a_cx = apply_rt(trip, to_stop, to_seq, sched_arr)
        if d_rt and not a_rt and d_delay is not None:
            arr = sched_arr + timedelta(seconds=d_delay)  # propagate the known delay
        return Leg(
            trip_id=trip_id, route_id=rid, line=r.short_name if r else rid,
            mode=ROUTE_TYPE_NAMES.get(r.type, "bus") if r else "bus",
            color=f"#{r.color}" if r and r.color else "",
            text_color=f"#{r.text_color}" if r and r.text_color else "",
            headsign=headsign, from_stop_id=from_stop, from_name=from_name,
            to_stop_id=to_stop, to_name=to_name, sched_departure=sched_dep,
            sched_arrival=sched_arr, departure=dep, arrival=arr,
            realtime=d_rt or a_rt, delay=d_delay if d_rt else a_delay,
            canceled=d_cx or a_cx, stops=max(0, to_seq - from_seq))

    candidates: list[Connection] = []
    with store._con() as con:  # noqa: SLF001 - read-only helper of the data layer
        orig_idx, orig_area = _stop_idx(con, store, origin)
        dest_idx, dest_area = _stop_idx(con, store, destination)
        if not orig_idx or not dest_idx:
            return []
        oph, dph = ",".join(map(str, orig_idx)), ",".join(map(str, dest_idx))
        dest_set = set(dest_idx)

        first_legs: list[tuple] = []  # (abs_dep, row, origin)
        last_legs: dict[str, list[tuple]] = {}  # area -> [(abs c_dep, abs e_arr, row, origin)]
        for day in (today - timedelta(days=1), today, today + timedelta(days=1)):
            o = service_day_origin(day)
            lo = int((now - look_back - o).total_seconds())
            hi = int((now + window - o).total_seconds())
            if hi < 0 or lo > 48 * 3600:
                continue
            d = int(day.strftime("%Y%m%d"))
            seen_dep: dict[tuple, dict] = {}
            n_first = 0
            for row in con.execute(_DIRECT_SQL.format(orig=oph, dest_filter=""),
                                   (d, max(lo, 0), hi)):
                key = (row["trip_id"], row["aseq"])
                if key not in seen_dep:
                    n_first += 1
                    if n_first > max_first_legs:
                        break
                    seen_dep[key] = {"row": row, "alights": []}
                seen_dep[key]["alights"].append(row)
            for info in seen_dep.values():
                first_legs.append((o, info))
            if max_transfers >= 1:
                arr_hi = int((now + window + timedelta(hours=2) - o).total_seconds())
                for row in con.execute(_LAST_LEG_SQL.format(dest=dph), (d, max(lo, 0), arr_hi)):
                    last_legs.setdefault(row["c_area"], []).append(
                        (o + timedelta(seconds=row["c_dep"]), o + timedelta(seconds=row["e_arr"]),
                         row))

        # Earliest arrival from each boarding area: sort by departure, suffix-min arrival.
        index: dict[str, tuple[list, list]] = {}
        for area, items in last_legs.items():
            deps_, best_ = _suffix_best(items, lambda x: x[1])
            index[area] = (deps_, [(b, ) for b in best_])

        # Two transfers: middle legs from any first-leg set-down area to any area
        # with a last leg. mid_index[area] -> (deps, best (c_dep, final_arr, row, last)).
        mid_index: dict[str, tuple[list, list]] = {}
        if max_transfers >= 2 and index and first_legs:
            skip = {orig_area, dest_area}
            a1_areas = {r["b_area"] for _, info in first_legs for r in info["alights"]} - skip
            a2_areas = set(index) - skip
            by_area: dict[str, list[int]] = {}
            for idx_, ar in con.execute("SELECT idx, COALESCE(parent, stop_id) FROM stops"):
                if ar in a1_areas or ar in a2_areas:
                    by_area.setdefault(ar, []).append(idx_)
            a1 = ",".join(str(i) for a in a1_areas for i in by_area.get(a, []))
            a2 = ",".join(str(i) for a in a2_areas for i in by_area.get(a, []))
            mids: dict[str, list[tuple]] = {}
            if a1 and a2:
                for day in (today - timedelta(days=1), today, today + timedelta(days=1)):
                    o = service_day_origin(day)
                    lo = int((now - look_back - o).total_seconds())
                    hi = int((now + window + timedelta(hours=1) - o).total_seconds())
                    if hi < 0 or lo > 48 * 3600:
                        continue
                    d = int(day.strftime("%Y%m%d"))
                    for row in con.execute(_MID_LEG_SQL.format(a1=a1, a2=a2), (d, max(lo, 0), hi)):
                        if row["e_area"] == row["c_area"]:
                            continue
                        e_arr = o + timedelta(seconds=row["e_arr"])
                        deps_, best_ = index[row["e_area"]]
                        i = bisect_left(deps_, e_arr + min_transfer)
                        if i >= len(deps_):
                            continue
                        last = best_[i][0]
                        if last[2]["route_id"] == row["route_id"]:
                            continue
                        mids.setdefault(row["c_area"], []).append(
                            (o + timedelta(seconds=row["c_dep"]), last[1], row, e_arr, last))
            for area, items in mids.items():
                mid_index[area] = _suffix_best(items, lambda x: x[1])

        dest_stop_ids = set(store.child_stop_ids(destination)) | {destination}
        for o, info in first_legs:
            head = info["row"]
            sched_dep = o + timedelta(seconds=head["a_dep"])
            best: Connection | None = None
            for row in info["alights"]:
                sched_arr = o + timedelta(seconds=row["b_arr"])
                if row["b_stop"] in dest_stop_ids:
                    leg = mk_leg(row["trip_id"], row["headsign"], row["route_id"], row["a_stop"],
                                 row["a_name"], row["aseq"], sched_dep, row["b_stop"],
                                 row["b_name"], row["bseq"], sched_arr)
                    conn = Connection([leg])
                    extra = min_transfer if best is not None and best.transfers >= 2 else timedelta(0)
                    if best is None or conn.arrival < best.arrival + extra or \
                            (conn.arrival == best.arrival and conn.transfers < best.transfers):
                        best = conn
                    break  # later calls of the same trip cannot be better
                area = row["b_area"]
                if max_transfers < 1 or area in (orig_area, dest_area):
                    continue
                if area in mid_index:
                    m_deps, m_best = mid_index[area]
                    j = bisect_left(m_deps, sched_arr + min_transfer)
                    if j < len(m_deps):
                        m_dep, f_arr, mrow, m_arr, last = m_best[j]
                        if mrow["route_id"] != row["route_id"] and mrow["trip_id"] != row["trip_id"] \
                                and (best is None or f_arr + min_transfer <= best.arrival):
                            c_dep3, e_arr3, r3 = last
                            legs = [
                                mk_leg(row["trip_id"], row["headsign"], row["route_id"], row["a_stop"],
                                       row["a_name"], row["aseq"], sched_dep, row["b_stop"],
                                       row["b_name"], row["bseq"], sched_arr),
                                mk_leg(mrow["trip_id"], mrow["headsign"], mrow["route_id"],
                                       mrow["c_stop"], mrow["c_name"], mrow["cseq"], m_dep,
                                       mrow["e_stop"], mrow["e_name"], mrow["eseq"], m_arr),
                                mk_leg(r3["trip_id"], r3["headsign"], r3["route_id"], r3["c_stop"],
                                       r3["c_name"], r3["cseq"], c_dep3, r3["e_stop"], r3["e_name"],
                                       r3["eseq"], e_arr3)]
                            risk = any(a.arrival + min_transfer > b.departure
                                       for a, b in zip(legs, legs[1:]))
                            best = Connection(legs, transfer_at_risk=risk)
                if area not in index:
                    continue
                deps, best_after = index[area]
                i = bisect_left(deps, sched_arr + min_transfer)
                if i >= len(deps):
                    continue
                c_dep, e_arr, r2 = best_after[i][0]
                if r2["trip_id"] == row["trip_id"] or r2["route_id"] == row["route_id"]:
                    continue
                if best is not None and (e_arr >= best.arrival if best.transfers <= 1
                                         else e_arr >= best.arrival + min_transfer):
                    continue
                leg1 = mk_leg(row["trip_id"], row["headsign"], row["route_id"], row["a_stop"],
                              row["a_name"], row["aseq"], sched_dep, row["b_stop"],
                              row["b_name"], row["bseq"], sched_arr)
                leg2 = mk_leg(r2["trip_id"], r2["headsign"], r2["route_id"], r2["c_stop"],
                              r2["c_name"], r2["cseq"], c_dep, r2["e_stop"], r2["e_name"],
                              r2["eseq"], e_arr)
                risk = leg1.arrival + min_transfer > leg2.departure
                best = Connection([leg1, leg2], transfer_at_risk=risk)
            if best is not None:
                candidates.append(best)

    # Pareto filter: drop connections that leave earlier and arrive no sooner.
    candidates = [c for c in candidates if c.departure >= now - timedelta(seconds=30)
                  and not any(lg.canceled for lg in c.legs)]
    candidates.sort(key=lambda c: (c.departure, c.arrival, c.transfers))
    kept: list[Connection] = []
    best_arr = None
    for c in reversed(candidates):
        if best_arr is None or c.arrival < best_arr:
            kept.append(c)
            best_arr = c.arrival
    kept.reverse()
    # same departure: keep the fastest / fewest transfers only
    out: list[Connection] = []
    for c in kept:
        if out and out[-1].departure == c.departure:
            continue
        out.append(c)
    return out[:count]


def search_with_fallback(store: GtfsStore, rt: RealtimeSnapshot | None, origin: str,
                         destination: str, now: datetime | None = None, count: int = 3,
                         min_transfer: timedelta = timedelta(minutes=3),
                         tries: int = 3) -> tuple[list[Connection], bool]:
    """Connections in the next 3 h; if none, the first ones of the next service.

    Returns (connections, later): `later` is True when they start after the 3 h window
    (late evening, or a day without service on the origin's lines)."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    conns = find_connections(store, rt, origin, destination, now=now, count=count,
                             min_transfer=min_transfer)
    if conns:
        return conns, False
    origin_ids = store.child_stop_ids(origin)
    after = now + timedelta(hours=3)
    for _ in range(tries):
        nxt = store.next_scheduled(origin_ids, after)
        if not nxt:
            break
        start = nxt["dep"] - timedelta(minutes=1)
        conns = find_connections(store, rt, origin, destination, now=start, count=count,
                                 min_transfer=min_transfer)
        if conns:
            return conns, True
        after = start + timedelta(hours=3)
    return [], False
