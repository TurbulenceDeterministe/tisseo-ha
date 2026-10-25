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
from datetime import date, datetime, timedelta

from .const import TZ

SCHEMA_VERSION = 3

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
CREATE TABLE stop_times (
  stop_idx INTEGER, dep INTEGER, trip_idx INTEGER, seq INTEGER, pickup INTEGER,
  PRIMARY KEY (stop_idx, dep, trip_idx)) WITHOUT ROWID;
"""


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


def build_index(zip_path: str, db_path: str, feed_version: str = "") -> None:
    """(Re)build the SQLite index from a GTFS zip, atomically."""
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
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

            route_idx: dict[str, int] = {}
            rows = []
            for i, r in enumerate(_rows(zf, "routes.txt")):
                route_idx[r["route_id"]] = i
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
            rows = []
            for i, r in enumerate(_rows(zf, "trips.txt")):
                trip_idx[r["trip_id"]] = i
                rows.append((i, r["trip_id"], route_idx.get(r["route_id"], -1),
                             svc(r["service_id"]), int(r.get("direction_id") or 0),
                             r.get("trip_headsign") or ""))
            con.executemany("INSERT INTO trips VALUES (?,?,?,?,?,?)", rows)

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

            # area of a stop = its parent station (or itself)
            area = {r[0]: (r[8] or r[1]) for r in _stop_rows}
            batch: list[tuple] = []
            ins = "INSERT OR IGNORE INTO stop_times VALUES (?,?,?,?,?)"

            def flush_trip(trip: list[tuple]) -> None:
                """Queue one trip's boardable stops.

                Drops pickup_type=1 rows and the trip's final stop(s) in the
                terminus stop area: a bus arriving at its terminus (possibly via
                two platforms of the same area) is not a departure from there."""
                if not trip:
                    return
                trip.sort(key=lambda x: x[3])
                end = len(trip)
                tail = area[trip[-1][0]]
                while end and area[trip[end - 1][0]] == tail:
                    end -= 1
                batch.extend((st, dep, ti, seq, 0) for st, dep, ti, seq, pick in trip[:end]
                             if not pick)

            current: list[tuple] = []
            cur_trip = None
            for r in _rows(zf, "stop_times.txt"):
                t = r.get("departure_time") or r.get("arrival_time")
                if not t:
                    continue
                if r["trip_id"] != cur_trip:  # stop_times.txt is grouped by trip
                    flush_trip(current)
                    current = []
                    cur_trip = r["trip_id"]
                current.append((stop_idx[r["stop_id"]], _secs(t), trip_idx[r["trip_id"]],
                                int(r["stop_sequence"]), r.get("pickup_type") == "1"))
                if len(batch) >= 50000:
                    con.executemany(ins, batch)
                    batch.clear()
            flush_trip(current)
            con.executemany(ins, batch)

        con.executemany("INSERT INTO meta VALUES (?,?)", [
            ("schema", str(SCHEMA_VERSION)), ("feed_version", feed_version),
            ("built", datetime.now(TZ).isoformat())])
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    os.replace(tmp, db_path)


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
            f"SELECT DISTINCT r.* FROM stops s JOIN stop_times st ON st.stop_idx=s.idx "
            f"JOIN trips t ON t.idx=st.trip_idx JOIN routes r ON r.idx=t.route_idx "
            f"WHERE s.stop_id IN ({ph})", ids).fetchall()
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
            f"WHERE s.stop_id IN ({ph}) AND st.dep BETWEEN ? AND ? ORDER BY st.dep")
        with self._con() as con:
            return [dict(r) for r in con.execute(sql, (d, *stop_ids, from_secs, to_secs))]
