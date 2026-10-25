"""GTFS static feed -> compact SQLite index.

The Tisséo GTFS zip is ~14 MB (≈75 MB stop_times.txt). We import only what is needed
for "next departures" (stops, routes, trips, calendar(_dates), stop_times) into a
single SQLite file with integer keys, then query it per stop. Import runs once per
feed version (checked daily) and is meant to be executed in a worker thread.
"""
from __future__ import annotations

import csv
import io
import os
import sqlite3
import unicodedata
import zipfile
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from datetime import date, datetime, timedelta

from .const import TZ

SCHEMA_VERSION = 5

# v4: "lean" index. Stops, routes, trips, calendars and a (stop, route) map are kept
# for the whole network (search, nearby stops, line lists), but stop_times are only
# kept for trips that call at one of the configured stop areas. Those trips are kept
# whole (every call, with arrival times and board/alight flags) so journeys and the
# trip dialog work.
# v5: when a journey is configured, the trips of the trunk lines (metro, tram, Linéo,
# Téléo) are also kept whole, so journeys can change twice (bus -> metro A ->
# metro B) through lines that call at neither end of the journey.
SCHEMA = """
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE stops (
  idx INTEGER PRIMARY KEY, stop_id TEXT UNIQUE, code TEXT, name TEXT, norm TEXT,
  lat REAL, lon REAL, location_type INTEGER, parent TEXT);
CREATE TABLE routes (
  idx INTEGER PRIMARY KEY, route_id TEXT UNIQUE, short_name TEXT, long_name TEXT,
  type INTEGER, color TEXT, text_color TEXT);
CREATE TABLE trips (
  idx INTEGER PRIMARY KEY, trip_id TEXT UNIQUE, route_idx INTEGER, service_idx INTEGER,
  direction INTEGER, headsign TEXT);
CREATE TABLE services (idx INTEGER PRIMARY KEY, service_id TEXT UNIQUE);
CREATE TABLE service_dates (service_idx INTEGER, d INTEGER, PRIMARY KEY (d, service_idx)) WITHOUT ROWID;
CREATE TABLE stop_routes (stop_idx INTEGER, route_idx INTEGER, PRIMARY KEY (stop_idx, route_idx)) WITHOUT ROWID;
CREATE TABLE stop_times (
  trip_idx INTEGER, seq INTEGER, stop_idx INTEGER, dep INTEGER, dwell INTEGER,
  board INTEGER, alight INTEGER, PRIMARY KEY (trip_idx, seq)) WITHOUT ROWID;
"""
POST_INDEXES = "CREATE INDEX st_stop_dep ON stop_times (stop_idx, dep);"


TRUNK_SUFFIX = "|trunk"


def stops_key(stop_ids, trunk: bool = False) -> str:
    """Canonical key of a set of configured stops ("*" = whole network)."""
    if stop_ids is None:
        return "*"
    return ",".join(sorted(set(stop_ids))) + (TRUNK_SUFFIX if trunk else "")


def is_trunk(route_type: int, short_name: str) -> bool:
    """Metro, tram, cable car, train... and the Linéo buses (L1, L2...)."""
    name = (short_name or "").strip().upper()
    return route_type != 3 or (len(name) > 1 and name[0] == "L" and name[1:].isdigit())


def normalize(text: str) -> str:
    """Lower-case, accent-free text for searching stop names."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = "".join(c if c.isalnum() else " " for c in text)
    return " ".join(text.split())


def _secs(hms: str) -> int:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def _rows(zf: zipfile.ZipFile, name: str):
    if name not in zf.namelist():
        return
    with zf.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))


@dataclass(frozen=True)
class StopInfo:
    stop_id: str
    name: str
    code: str
    lat: float
    lon: float
    is_area: bool
    parent: str | None


@dataclass(frozen=True)
class RouteInfo:
    route_id: str
    short_name: str
    long_name: str
    type: int
    color: str
    text_color: str


def build_index(zip_path: str, db_path: str, feed_version: str = "",
                stop_ids=None, trunk: bool = False) -> dict:
    """(Re)build the SQLite index from a GTFS zip, atomically.

    ``stop_ids``: configured stop ids (areas or points). Only trips calling in their
    stop areas get stop_times. ``None`` indexes the whole network. ``trunk`` also
    keeps every trip of the trunk lines (for journeys with two transfers). Returns stats.
    """
    t0 = datetime.now()
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    stats = {"trips_kept": 0, "stop_times": 0}
    try:
        con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
        with zipfile.ZipFile(zip_path) as zf:
            stop_idx: dict[str, int] = {}
            rows = []
            for i, r in enumerate(_rows(zf, "stops.txt")):
                stop_idx[r["stop_id"]] = i
                rows.append((i, r["stop_id"], r.get("stop_code") or "", r["stop_name"],
                             normalize(r["stop_name"]), float(r["stop_lat"] or 0),
                             float(r["stop_lon"] or 0), int(r.get("location_type") or 0),
                             r.get("parent_station") or None))
            con.executemany("INSERT INTO stops VALUES (?,?,?,?,?,?,?,?,?)", rows)
            _stop_rows = rows
            # area of a stop = its parent station (or itself)
            area = {r[0]: (r[8] or r[1]) for r in _stop_rows}

            keep: set[int] | None = None
            if stop_ids is not None:
                areas = set()
                for sid in stop_ids:
                    if sid in stop_idx:
                        areas.add(area[stop_idx[sid]])
                keep = {r[0] for r in _stop_rows if area[r[0]] in areas or r[1] in areas}

            route_idx: dict[str, int] = {}
            trunk_routes: set[int] = set()
            rows = []
            for i, r in enumerate(_rows(zf, "routes.txt")):
                route_idx[r["route_id"]] = i
                if trunk and is_trunk(int(r.get("route_type") or 3), r.get("route_short_name") or ""):
                    trunk_routes.add(i)
                rows.append((i, r["route_id"], r.get("route_short_name") or "",
                             r.get("route_long_name") or "", int(r.get("route_type") or 3),
                             r.get("route_color") or "", r.get("route_text_color") or ""))
            con.executemany("INSERT INTO routes VALUES (?,?,?,?,?,?,?)", rows)

            service_idx: dict[str, int] = {}

            def svc(sid: str) -> int:
                if sid not in service_idx:
                    service_idx[sid] = len(service_idx)
                return service_idx[sid]

            trip_idx: dict[str, int] = {}
            trip_route: dict[int, int] = {}
            trip_rows = []
            for i, r in enumerate(_rows(zf, "trips.txt")):
                trip_idx[r["trip_id"]] = i
                trip_route[i] = route_idx.get(r["route_id"], -1)
                trip_rows.append((i, r["trip_id"], trip_route[i],
                                  svc(r["service_id"]), int(r.get("direction_id") or 0),
                                  r.get("trip_headsign") or ""))
            kept_trips: set[int] = set()

            # Expand calendar.txt + calendar_dates.txt into explicit (service, yyyymmdd).
            dates: set[tuple[int, int]] = set()
            for r in _rows(zf, "calendar.txt"):
                start = datetime.strptime(r["start_date"], "%Y%m%d").date()
                end = datetime.strptime(r["end_date"], "%Y%m%d").date()
                days = [r[k] == "1" for k in ("monday", "tuesday", "wednesday", "thursday",
                                              "friday", "saturday", "sunday")]
                s = svc(r["service_id"])
                d = start
                while d <= end:
                    if days[d.weekday()]:
                        dates.add((s, int(d.strftime("%Y%m%d"))))
                    d += timedelta(days=1)
            for r in _rows(zf, "calendar_dates.txt"):
                key = (svc(r["service_id"]), int(r["date"]))
                if r["exception_type"] == "1":
                    dates.add(key)
                else:
                    dates.discard(key)
            con.executemany("INSERT INTO service_dates VALUES (?,?)", sorted(dates))
            con.executemany("INSERT INTO services VALUES (?,?)",
                            [(v, k) for k, v in service_idx.items()])

            batch: list[tuple] = []
            stop_routes: set[tuple[int, int]] = set()
            ins = "INSERT OR IGNORE INTO stop_times VALUES (?,?,?,?,?,?,?)"

            def flush_trip(trip: list[tuple]) -> None:
                """Record one trip.

                A call is boardable unless pickup_type=1 or it is one of the trip's
                final call(s) in the terminus stop area (a bus arriving at its
                terminus, possibly via two platforms of the same area, is not a
                departure from there)."""
                if not trip:
                    return
                trip.sort(key=lambda x: x[3])
                end = len(trip)
                tail = area[trip[-1][0]]
                while end and area[trip[end - 1][0]] == tail:
                    end -= 1
                ti = trip[0][2]
                rt = trip_route.get(ti, -1)
                rows_ = []
                touches = keep is None or rt in trunk_routes
                for n, (st, dep, _ti, seq, nopick, arr, nodrop) in enumerate(trip):
                    board = int(n < end and not nopick)
                    if board:
                        stop_routes.add((st, rt))
                    if keep is not None and st in keep:
                        touches = True
                    # dwell (dep - arr) is almost always 0, which SQLite stores in 0 bytes
                    rows_.append((ti, seq, st, dep, dep - arr, board, int(not nodrop)))
                if touches:
                    batch.extend(rows_)
                    kept_trips.add(ti)
                    stats["trips_kept"] += 1

            current: list[tuple] = []
            cur_trip = None
            for r in _rows(zf, "stop_times.txt"):
                t = r.get("departure_time") or r.get("arrival_time")
                if not t:
                    continue
                a = r.get("arrival_time") or t
                if r["trip_id"] != cur_trip:  # stop_times.txt is grouped by trip
                    flush_trip(current)
                    current = []
                    cur_trip = r["trip_id"]
                current.append((stop_idx[r["stop_id"]], _secs(t), trip_idx[r["trip_id"]],
                                int(r["stop_sequence"]), r.get("pickup_type") == "1",
                                _secs(a), r.get("drop_off_type") == "1"))
                if len(batch) >= 50000:
                    stats["stop_times"] += len(batch)
                    con.executemany(ins, batch)
                    batch.clear()
            flush_trip(current)
            stats["stop_times"] += len(batch)
            con.executemany(ins, batch)
            con.executemany("INSERT INTO stop_routes VALUES (?,?)", sorted(stop_routes))
            # lean index: only the trips that have stop_times
            con.executemany("INSERT INTO trips VALUES (?,?,?,?,?,?)",
                            [r for r in trip_rows if r[0] in kept_trips])
            con.executescript(POST_INDEXES)

        con.executemany("INSERT INTO meta VALUES (?,?)", [
            ("schema", str(SCHEMA_VERSION)), ("feed_version", feed_version),
            ("built", datetime.now(TZ).isoformat()), ("stops_key", stops_key(stop_ids, trunk))])
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    os.replace(tmp, db_path)
    stats["seconds"] = round((datetime.now() - t0).total_seconds(), 2)
    stats["bytes"] = os.path.getsize(db_path)
    return stats


class GtfsStore:
    """Read-only access to the SQLite index. Safe to share between threads (one connection per call)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def is_valid(self) -> bool:
        if not os.path.exists(self.db_path):
            return False
        try:
            with self._con() as con:
                row = con.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
                return bool(row) and row[0] == str(SCHEMA_VERSION)
        except sqlite3.Error:
            return False

    def meta(self) -> dict[str, str]:
        with self._con() as con:
            return {r["k"]: r["v"] for r in con.execute("SELECT k, v FROM meta")}

    # ---- stops / routes -------------------------------------------------
    @staticmethod
    def _stop(r) -> StopInfo:
        return StopInfo(r["stop_id"], r["name"], r["code"], r["lat"], r["lon"],
                        r["location_type"] == 1, r["parent"])

    def search_stops(self, query: str, limit: int = 30) -> list[tuple[StopInfo, list[str]]]:
        """Search stop areas by name (accent-insensitive) or a stop id/code.

        Returns (stop, [line short names]) tuples.
        """
        q = query.strip()
        with self._con() as con:
            rows = con.execute(
                "SELECT * FROM stops WHERE stop_id=? OR (code<>'' AND code=?)", (q, q)).fetchall()
            tokens = normalize(q).split()
            if not rows and tokens:
                where = " AND ".join("(' ' || norm) LIKE ?" for _ in tokens)
                rows = con.execute(
                    f"SELECT * FROM stops WHERE location_type=1 AND {where} "
                    "ORDER BY (norm=?) DESC, length(name), name LIMIT ?",
                    (*[f"% {t}%" for t in tokens], " ".join(tokens), limit)).fetchall()
            out = []
            for r in rows:
                st = self._stop(r)
                out.append((st, [x.short_name for x in self._routes_for(con, [st.stop_id])]))
            return out

    def get_stop(self, stop_id: str) -> StopInfo | None:
        with self._con() as con:
            r = con.execute("SELECT * FROM stops WHERE stop_id=?", (stop_id,)).fetchone()
            return self._stop(r) if r else None

    def child_stop_ids(self, stop_id: str) -> list[str]:
        """A stop area expands to its stop points; a stop point is returned as-is."""
        with self._con() as con:
            kids = [r[0] for r in con.execute(
                "SELECT stop_id FROM stops WHERE parent=?", (stop_id,))]
        return kids or [stop_id]

    def _routes_for(self, con, stop_ids: list[str]) -> list[RouteInfo]:
        ids = self.child_stop_ids(stop_ids[0]) if len(stop_ids) == 1 else stop_ids
        ph = ",".join("?" * len(ids))
        rows = con.execute(
            f"SELECT DISTINCT r.* FROM stops s JOIN stop_routes sr ON sr.stop_idx=s.idx "
            f"JOIN routes r ON r.idx=sr.route_idx WHERE s.stop_id IN ({ph})", ids).fetchall()
        routes = [RouteInfo(r["route_id"], r["short_name"], r["long_name"], r["type"],
                            r["color"], r["text_color"]) for r in rows]
        return sorted(routes, key=lambda x: (x.type != 1, x.type, len(x.short_name), x.short_name))

    def routes_for_stop(self, stop_id: str) -> list[RouteInfo]:
        with self._con() as con:
            return self._routes_for(con, [stop_id])

    def routes(self) -> dict[str, RouteInfo]:
        with self._con() as con:
            return {r["route_id"]: RouteInfo(r["route_id"], r["short_name"], r["long_name"],
                                             r["type"], r["color"], r["text_color"])
                    for r in con.execute("SELECT * FROM routes")}

    def stop_names(self, stop_ids) -> dict[str, str]:
        ids = list(stop_ids)
        if not ids:
            return {}
        with self._con() as con:
            ph = ",".join("?" * len(ids))
            return {r[0]: r[1] for r in con.execute(
                f"SELECT stop_id, name FROM stops WHERE stop_id IN ({ph})", ids)}

    # ---- schedule --------------------------------------------------------
    def scheduled(self, stop_ids: list[str], service_day: date, from_secs: int,
                  to_secs: int) -> list[dict]:
        """Scheduled departures for one service day in [from_secs, to_secs] (GTFS seconds)."""
        ph = ",".join("?" * len(stop_ids))
        d = int(service_day.strftime("%Y%m%d"))
        sql = (
            "SELECT s.stop_id, st.dep, st.seq, t.trip_id, t.headsign, t.direction, r.route_id "
            "FROM stops s JOIN stop_times st ON st.stop_idx=s.idx "
            "JOIN trips t ON t.idx=st.trip_idx "
            "JOIN service_dates sd ON sd.service_idx=t.service_idx AND sd.d=? "
            "JOIN routes r ON r.idx=t.route_idx "
            f"WHERE s.stop_id IN ({ph}) AND st.board=1 AND st.dep BETWEEN ? AND ? ORDER BY st.dep")
        with self._con() as con:
            return [dict(r) for r in con.execute(sql, (d, *stop_ids, from_secs, to_secs))]

    def next_scheduled(self, stop_ids: list[str], after: datetime,
                       route_ids: set[str] | None = None, days: int = 7) -> dict | None:
        """First boardable scheduled departure at the stops strictly after ``after``.

        Looks up to ``days`` service days ahead (lines with no evening, weekend or
        holiday service). Returns stop_id, dep (aware datetime), trip_id, headsign,
        route_id, or None."""
        from .departures import service_day_origin  # local import: avoid a cycle
        after = after.astimezone(TZ)
        ph = ",".join("?" * len(stop_ids))
        rf, rargs = "", []
        if route_ids:
            rf = f" AND r.route_id IN ({','.join('?' * len(route_ids))})"
            rargs = sorted(route_ids)
        sql = ("SELECT s.stop_id, st.dep, t.trip_id, t.headsign, r.route_id "
               "FROM stops s JOIN stop_times st ON st.stop_idx=s.idx "
               "JOIN trips t ON t.idx=st.trip_idx "
               "JOIN service_dates sd ON sd.service_idx=t.service_idx AND sd.d=? "
               "JOIN routes r ON r.idx=t.route_idx "
               f"WHERE s.stop_id IN ({ph}) AND st.board=1 AND st.dep > ?{rf} "
               "ORDER BY st.dep LIMIT 1")
        best = None
        with self._con() as con:
            for n in range(-1, days + 1):
                day = after.date() + timedelta(days=n)
                origin = service_day_origin(day)
                if best is not None and origin > best["dep"]:
                    break
                lo = max(-1, int((after - origin).total_seconds()))
                r = con.execute(sql, (int(day.strftime("%Y%m%d")), *stop_ids, lo, *rargs)).fetchone()
                if r:
                    dep = origin + timedelta(seconds=r["dep"])
                    if best is None or dep < best["dep"]:
                        best = {"stop_id": r["stop_id"], "dep": dep, "trip_id": r["trip_id"],
                                "headsign": r["headsign"], "route_id": r["route_id"]}
        return best

    def stops_key(self) -> str:
        try:
            return self.meta().get("stops_key", "")
        except sqlite3.Error:
            return ""

    def area_of(self, stop_id: str) -> str:
        st = self.get_stop(stop_id)
        return (st.parent or st.stop_id) if st else stop_id

    # ---- nearby ---------------------------------------------------------------
    def nearby_stops(self, lat: float, lon: float, limit: int = 10,
                     max_km: float = 5.0) -> list[tuple[StopInfo, float, list[str]]]:
        """Stop areas closest to (lat, lon): (stop, distance in metres, line names)."""
        with self._con() as con:
            d_lat = max_km / 111.0
            d_lon = max_km / (111.0 * max(0.1, cos(radians(lat))))
            rows = con.execute(
                "SELECT * FROM stops WHERE location_type=1 AND lat BETWEEN ? AND ? "
                "AND lon BETWEEN ? AND ?", (lat - d_lat, lat + d_lat, lon - d_lon, lon + d_lon)
            ).fetchall()
            found = sorted(((haversine_m(lat, lon, r["lat"], r["lon"]), self._stop(r)) for r in rows),
                           key=lambda x: x[0])
            out = []
            for dist, st in found:
                lines = [x.short_name for x in self._routes_for(con, [st.stop_id])]
                if lines:  # skip areas no line serves any more
                    out.append((st, dist, lines))
                if len(out) >= limit:
                    break
            return out

    # ---- trips ----------------------------------------------------------------
    def trip_calls(self, trip_id: str) -> list[dict]:
        """Every call of an indexed trip (empty if the trip is not in the lean index)."""
        sql = ("SELECT st.seq, s.stop_id, s.name, s.parent, s.lat, s.lon, st.dep - st.dwell AS arr, st.dep, "
               "st.board, st.alight, t.headsign, r.route_id FROM trips t "
               "JOIN stop_times st ON st.trip_idx=t.idx JOIN stops s ON s.idx=st.stop_idx "
               "JOIN routes r ON r.idx=t.route_idx WHERE t.trip_id=? ORDER BY st.seq")
        with self._con() as con:
            return [dict(r) for r in con.execute(sql, (trip_id,))]

    def trip_info(self, trip_id: str) -> dict | None:
        with self._con() as con:
            r = con.execute("SELECT t.trip_id, t.headsign, t.direction, r.route_id FROM trips t "
                            "JOIN routes r ON r.idx=t.route_idx WHERE t.trip_id=?",
                            (trip_id,)).fetchone()
            return dict(r) if r else None

    # ---- service summaries (timetable change detection) ---------------------
    def day_summary(self, stop_ids: list[str], day: date,
                    route_ids: set[str] | None = None) -> dict:
        """Departures of one service day at the stops: count, first/last, per line."""
        ph = ",".join("?" * len(stop_ids))
        d = int(day.strftime("%Y%m%d"))
        sql = ("SELECT r.route_id, r.short_name, st.dep, sv.service_id FROM stops s "
               "JOIN stop_times st ON st.stop_idx=s.idx JOIN trips t ON t.idx=st.trip_idx "
               "JOIN service_dates sd ON sd.service_idx=t.service_idx AND sd.d=? "
               "JOIN services sv ON sv.idx=t.service_idx JOIN routes r ON r.idx=t.route_idx "
               f"WHERE s.stop_id IN ({ph}) AND st.board=1")
        with self._con() as con:
            rows = [r for r in con.execute(sql, (d, *stop_ids))
                    if not route_ids or r["route_id"] in route_ids]
        per_line: dict[str, int] = {}
        for r in rows:
            per_line[r["short_name"]] = per_line.get(r["short_name"], 0) + 1
        deps = sorted(r["dep"] for r in rows)
        return {"date": day.isoformat(), "count": len(rows), "per_line": per_line,
                "first": deps[0] if deps else None, "last": deps[-1] if deps else None,
                "services": sorted({r["service_id"] for r in rows})}

    def active_services(self, day: date) -> int:
        """Number of service ids running on ``day`` (whole network)."""
        with self._con() as con:
            return con.execute("SELECT count(*) FROM service_dates WHERE d=?",
                               (int(day.strftime("%Y%m%d")),)).fetchone()[0]

    def coverage_end(self, ratio: float = 0.3) -> date | None:
        """Last day whose number of running services is still >= ratio * median.

        GTFS feeds often trail off (a few services published weeks ahead); days after
        this are treated as "not published yet" rather than "no service"."""
        with self._con() as con:
            rows = con.execute("SELECT d, count(*) FROM service_dates GROUP BY d ORDER BY d").fetchall()
        if not rows:
            return None
        counts = sorted(c for _, c in rows)
        median = counts[len(counts) // 2]
        good = [d for d, c in rows if c >= ratio * median]
        return datetime.strptime(str(good[-1]), "%Y%m%d").date() if good else None

    def feed_dates(self) -> tuple[int, int] | None:
        with self._con() as con:
            r = con.execute("SELECT min(d), max(d) FROM service_dates").fetchone()
            return (r[0], r[1]) if r and r[0] else None

    def trip_runs_on(self, trip_id: str, day: date) -> bool:
        with self._con() as con:
            return con.execute(
                "SELECT 1 FROM trips t JOIN service_dates sd ON sd.service_idx=t.service_idx "
                "WHERE t.trip_id=? AND sd.d=?",
                (trip_id, int(day.strftime("%Y%m%d")))).fetchone() is not None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = p2 - p1, radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371000 * asin(sqrt(a))

