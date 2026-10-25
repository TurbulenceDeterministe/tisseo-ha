"""VélôToulouse bike-share availability (keyless GBFS v3 published by JCDecaux/Cyclocity).

Licence: JCDecaux Open Licence. Feed discovery: GBFS_URL.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

import aiohttp

from .const import USER_AGENT
from .static import haversine_m

GBFS_URL = "https://api.cyclocity.fr/contracts/toulouse/gbfs/v3/gbfs.json"
_FALLBACK = {
    "station_information": "https://api.cyclocity.fr/contracts/toulouse/gbfs/v3/station_information.json",
    "station_status": "https://api.cyclocity.fr/contracts/toulouse/gbfs/v3/station_status.json",
}


@dataclass
class BikeStation:
    station_id: str
    name: str
    lat: float
    lon: float
    address: str = ""
    capacity: int | None = None


@dataclass
class BikeStatus:
    station_id: str
    bikes: int
    mechanical: int
    electric: int
    docks: int
    bikes_disabled: int
    docks_disabled: int
    installed: bool
    renting: bool
    returning: bool
    last_reported: datetime | None


def _text(v) -> str:
    if isinstance(v, list):
        for item in v:
            if isinstance(item, dict) and str(item.get("text") or "").strip():
                return str(item["text"])
        return ""
    return str(v or "")


def _ts(v) -> datetime | None:
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            from datetime import timezone
            return datetime.fromtimestamp(v, timezone.utc)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, OSError):
        return None


def parse_information(payload: dict) -> dict[str, BikeStation]:
    out = {}
    for s in (payload.get("data") or {}).get("stations", []):
        sid = str(s.get("station_id"))
        name = _text(s.get("name")).strip()
        if not name:
            continue  # the Toulouse feed lists ~11 unnamed placeholder stations (capacity 0)
        out[sid] = BikeStation(sid, name, float(s.get("lat") or 0),
                               float(s.get("lon") or 0), _text(s.get("address")),
                               s.get("capacity"))
    return out


def parse_status(payload: dict) -> tuple[dict[str, BikeStatus], datetime | None]:
    out = {}
    for s in (payload.get("data") or {}).get("stations", []):
        types = {str(v.get("vehicle_type_id")): int(v.get("count") or 0)
                 for v in s.get("vehicle_types_available") or []}
        bikes = s.get("num_vehicles_available", s.get("num_bikes_available", 0)) or 0
        sid = str(s.get("station_id"))
        out[sid] = BikeStatus(
            station_id=sid, bikes=int(bikes), mechanical=types.get("mechanical", 0),
            electric=types.get("electrical", types.get("electric", 0)),
            docks=int(s.get("num_docks_available") or 0),
            bikes_disabled=int(s.get("num_vehicles_disabled", s.get("num_bikes_disabled", 0)) or 0),
            docks_disabled=int(s.get("num_docks_disabled") or 0),
            installed=bool(s.get("is_installed", True)), renting=bool(s.get("is_renting", True)),
            returning=bool(s.get("is_returning", True)), last_reported=_ts(s.get("last_reported")))
    return out, _ts(payload.get("last_updated"))


def nearest(stations: dict[str, BikeStation], lat: float, lon: float, limit: int = 10):
    ranked = sorted(((haversine_m(lat, lon, s.lat, s.lon), s) for s in stations.values()),
                    key=lambda x: x[0])
    return ranked[:limit]


class GbfsClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self._urls: dict[str, str] | None = None
        self._info: dict[str, BikeStation] | None = None
        self._info_at: float = 0.0

    async def _get(self, url: str) -> dict:
        async with self.session.get(url, headers={"User-Agent": USER_AGENT},
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def urls(self) -> dict[str, str]:
        if self._urls is None:
            try:
                d = await self._get(GBFS_URL)
                feeds = (d.get("data") or {}).get("feeds") or []
                if not feeds:  # GBFS 2.x nests feeds per language
                    for v in (d.get("data") or {}).values():
                        if isinstance(v, dict) and v.get("feeds"):
                            feeds = v["feeds"]
                            break
                self._urls = {f["name"]: f["url"] for f in feeds} or dict(_FALLBACK)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
                return dict(_FALLBACK)
        return self._urls

    async def stations(self, max_age: float = 86400) -> dict[str, BikeStation]:
        loop = asyncio.get_running_loop()
        if self._info is None or loop.time() - self._info_at > max_age:
            urls = await self.urls()
            self._info = parse_information(await self._get(urls["station_information"]))
            self._info_at = loop.time()
        return self._info

    async def status(self) -> tuple[dict[str, BikeStatus], datetime | None]:
        urls = await self.urls()
        return parse_status(await self._get(urls["station_status"]))
