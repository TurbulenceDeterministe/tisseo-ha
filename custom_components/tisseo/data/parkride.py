"""Tisséo park-and-ride (parkings relais) from Toulouse Métropole open data (keyless).

Only *static* capacities are published as keyless open data (dataset
``parkings-relais``, Licence Ouverte v2.0). Live occupancy is shown on tisseo.fr,
which sits behind bot protection and is deliberately not used.
"""
from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from .const import USER_AGENT

PARKRIDE_URL = ("https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/"
                "parkings-relais/records?limit=50")


@dataclass
class ParkRide:
    id: str
    name: str
    capacity: int | None
    pmr: int | None
    bikes: int | None
    ev: int | None
    address: str
    city: str
    lat: float | None
    lon: float | None
    info: str = ""


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_parkride(payload: dict) -> dict[str, ParkRide]:
    out = {}
    for r in payload.get("results") or []:
        name = str(r.get("nom") or "").strip()
        if not name:
            continue
        geo = r.get("geo_point_2d") or {}
        pid = str(r.get("id") or name.lower().replace(" ", "_"))
        out[pid] = ParkRide(
            id=pid, name=name.title(), capacity=_int(r.get("nb_places") or r.get("nb_voitures")),
            pmr=_int(r.get("nb_pmr")), bikes=_int(r.get("nb_velo")),
            ev=_int(r.get("nb_voitures_electriques")), address=str(r.get("adresse") or ""),
            city=str(r.get("commune") or ""), lat=geo.get("lat"), lon=geo.get("lon"),
            info=str(r.get("info") or ""))
    return out


async def fetch_parkride(session: aiohttp.ClientSession) -> dict[str, ParkRide]:
    async with session.get(PARKRIDE_URL, headers={"User-Agent": USER_AGENT},
                           timeout=aiohttp.ClientTimeout(total=20)) as resp:
        resp.raise_for_status()
        return parse_parkride(await resp.json(content_type=None))
