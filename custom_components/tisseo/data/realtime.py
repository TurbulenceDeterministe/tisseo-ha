"""GTFS-Realtime (trip updates + service alerts) parsing."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from google.transit import gtfs_realtime_pb2

# TripDescriptor.ScheduleRelationship
SCHEDULED, ADDED, UNSCHEDULED, CANCELED = 0, 1, 2, 3
# StopTimeUpdate.ScheduleRelationship
STU_SKIPPED, STU_NO_DATA = 1, 2


@dataclass
class StopUpdate:
    seq: int | None
    stop_id: str
    time: int | None  # POSIX seconds (departure, else arrival)
    delay: int | None
    skipped: bool = False
    no_data: bool = False


@dataclass
class TripRT:
    trip_id: str
    route_id: str
    relationship: int
    updates: list[StopUpdate] = field(default_factory=list)
    vehicle: str | None = None

    def update_for(self, stop_id: str, seq: int | None) -> StopUpdate | None:
        for u in self.updates:
            if (seq is not None and u.seq == seq) or u.stop_id == stop_id:
                return u
        return None

    def propagated_delay(self, seq: int | None) -> int | None:
        """Delay of the last update before `seq` (GTFS-RT delay propagation rule)."""
        if seq is None:
            return None
        best = None
        for u in self.updates:
            if u.seq is not None and u.seq <= seq and u.delay is not None and not u.no_data:
                if best is None or u.seq > best.seq:
                    best = u
        return best.delay if best else None


@dataclass
class Alert:
    id: str
    header: str
    description: str
    url: str | None
    cause: str
    effect: str
    active_periods: list[tuple[int | None, int | None]]
    route_ids: set[str]
    stop_ids: set[str]
    network_wide: bool

    def active_at(self, ts: float) -> bool:
        if not self.active_periods:
            return True
        return any((s is None or s <= ts) and (e is None or ts <= e)
                   for s, e in self.active_periods)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "header": self.header, "description": self.description,
            "url": self.url, "cause": self.cause, "effect": self.effect,
            "lines": sorted(self.route_ids), "stops": sorted(self.stop_ids),
            "network_wide": self.network_wide,
        }


@dataclass
class RealtimeSnapshot:
    timestamp: int
    trips: dict[str, TripRT]
    alerts: list[Alert]

    @classmethod
    def empty(cls) -> "RealtimeSnapshot":
        return cls(0, {}, [])


_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<\s*(br|/p|/h\d|/li)\s*/?>", re.I)


def html_to_text(text: str) -> str:
    text = _BR.sub("\n", text or "")
    text = html.unescape(_TAG.sub("", text)).replace("\r", "")
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _tr(ts) -> str:
    if not ts.translation:
        return ""
    for t in ts.translation:
        if t.language in ("fr", ""):
            return t.text
    return ts.translation[0].text


def parse_realtime(data: bytes) -> RealtimeSnapshot:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    trips: dict[str, TripRT] = {}
    alerts: list[Alert] = []
    cause_names = gtfs_realtime_pb2.Alert.Cause.Name
    effect_names = gtfs_realtime_pb2.Alert.Effect.Name
    for ent in feed.entity:
        if ent.HasField("trip_update"):
            tu = ent.trip_update
            trip = TripRT(tu.trip.trip_id, tu.trip.route_id, tu.trip.schedule_relationship,
                          vehicle=tu.vehicle.id or None)
            for s in tu.stop_time_update:
                ev = s.departure if s.HasField("departure") else s.arrival
                trip.updates.append(StopUpdate(
                    seq=s.stop_sequence if s.HasField("stop_sequence") else None,
                    stop_id=s.stop_id,
                    time=ev.time if ev.HasField("time") else None,
                    delay=ev.delay if ev.HasField("delay") else None,
                    skipped=s.schedule_relationship == STU_SKIPPED,
                    no_data=s.schedule_relationship == STU_NO_DATA,
                ))
            if trip.trip_id:
                trips[trip.trip_id] = trip
        if ent.HasField("alert"):
            a = ent.alert
            routes = {ie.route_id for ie in a.informed_entity if ie.route_id}
            stops = {ie.stop_id for ie in a.informed_entity if ie.stop_id}
            routes |= {ie.trip.route_id for ie in a.informed_entity
                       if ie.HasField("trip") and ie.trip.route_id}
            alerts.append(Alert(
                id=ent.id,
                header=html_to_text(_tr(a.header_text)),
                description=html_to_text(_tr(a.description_text)),
                url=_tr(a.url) or None,
                cause=cause_names(a.cause) if a.HasField("cause") else "UNKNOWN_CAUSE",
                effect=effect_names(a.effect) if a.HasField("effect") else "UNKNOWN_EFFECT",
                active_periods=[(p.start or None, p.end or None) for p in a.active_period],
                route_ids=routes, stop_ids=stops,
                network_wide=not routes and not stops,
            ))
    return RealtimeSnapshot(feed.header.timestamp, trips, alerts)
