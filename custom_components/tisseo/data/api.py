"""Official Tisséo API v2 (requires a *user-supplied* key from opendata@tisseo.fr).

Only ``stops_schedules`` is used. The key is sent as a query parameter (as the API
documentation requires) and is never logged: errors are sanitised before they are
raised or recorded. Per the documentation (21/05/2025), real time only covers bus
and tram; metro times are frequency based.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime

import aiohttp

from .const import TZ, USER_AGENT

API_BASE = "https://api.tisseo.fr/v2"
SCHEDULES_URL = f"{API_BASE}/stops_schedules.json"


class ApiError(Exception):
    """Transient API failure (network, 5xx, bad payload)."""


class InvalidApiKey(ApiError):
    """The API rejected the key (HTTP 401/403 or an explicit key error)."""


@dataclass
class ApiDeparture:
    when: datetime
    realtime: bool
    line_id: str | None
    line_short: str
    line_name: str
    color: str
    destination: str
    stop_id: str | None = None


def sanitize(text: str, key: str | None) -> str:
    text = str(text)
    if key:
        text = text.replace(key, "***")
    return re.sub(r"(key=)[^&\s'\"]+", r"\1***", text)


def _rgb_to_hex(value: str | None) -> str:
    if not value:
        return ""
    m = re.match(r"\(?\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)?", value)
    if m:
        return "#" + "".join(f"{min(255, int(x)):02X}" for x in m.groups())
    if re.fullmatch(r"#?[0-9A-Fa-f]{6}", value):
        return "#" + value.lstrip("#").upper()
    return ""


def _key_error(payload) -> bool:
    if isinstance(payload, dict):
        blob = " ".join(str(v) for k, v in payload.items() if k in ("error", "message", "code", "erreur"))
        return bool(re.search(r"\bkey\b|cl[ée]", blob, re.I))
    return False


def parse_schedules(payload: dict) -> list[ApiDeparture]:
    """Parse a stops_schedules.json response (timetableByArea=0 form)."""
    if not isinstance(payload, dict):
        raise ApiError("unexpected payload")
    deps = payload.get("departures")
    if isinstance(deps, dict):
        items = deps.get("departure") or []
    elif isinstance(deps, list):
        items = deps
    else:
        items = payload.get("departure") or []
    if isinstance(items, dict):
        items = [items]
    out: list[ApiDeparture] = []
    for it in items:
        try:
            when = datetime.strptime(it["dateTime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        except (KeyError, ValueError, TypeError):
            continue
        line = it.get("line") or {}
        dest = it.get("destination") or []
        if isinstance(dest, dict):
            dest = [dest]
        rt = str(it.get("realTime", "no")).lower() in ("yes", "1", "true")
        out.append(ApiDeparture(
            when=when, realtime=rt, line_id=line.get("id"),
            line_short=str(line.get("shortName") or ""), line_name=str(line.get("name") or ""),
            color=_rgb_to_hex(line.get("color")),
            destination=(dest[0].get("name") if dest else "") or "",
            stop_id=(it.get("stop") or {}).get("id") if isinstance(it.get("stop"), dict) else None))
    return out


async def fetch_stop_schedules(session: aiohttp.ClientSession, key: str, stop_id: str,
                               number: int = 10, timeout: float = 15.0) -> list[ApiDeparture]:
    param = "stopAreaId" if stop_id.startswith("stop_area:") else "stopPointId"
    params = {param: stop_id, "number": str(number), "displayRealTime": "1",
              "timetableByArea": "0", "key": key}
    try:
        async with session.get(SCHEDULES_URL, params=params, headers={"User-Agent": USER_AGENT},
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status in (401, 403):
                raise InvalidApiKey(f"HTTP {resp.status}")
            text = await resp.text()
            if resp.status >= 400:
                try:
                    import json
                    if _key_error(json.loads(text)):
                        raise InvalidApiKey(f"HTTP {resp.status}")
                except ValueError:
                    pass
                raise ApiError(f"HTTP {resp.status}")
    except InvalidApiKey:
        raise
    except ApiError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ApiError(sanitize(f"{type(err).__name__}: {err}", key)) from None
    try:
        import json
        payload = json.loads(text)
    except ValueError:
        raise ApiError("invalid JSON") from None
    if _key_error(payload) and not payload.get("departures"):
        raise InvalidApiKey("key rejected")
    return parse_schedules(payload)
