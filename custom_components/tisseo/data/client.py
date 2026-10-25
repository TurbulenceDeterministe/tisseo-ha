"""Async downloads of the keyless Tisséo open-data feeds (aiohttp)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

import aiohttp

from .const import GTFS_RT_URLS, GTFS_URLS, TZ, USER_AGENT
from .health import FeedHealth, backoff_delay
from .realtime import RealtimeSnapshot, parse_realtime
from .static import GtfsStore, build_index, stops_key

_LOGGER = logging.getLogger(__name__)
HEADERS = {"User-Agent": USER_AGENT}


class TisseoFeeds:
    """Owns the GTFS cache directory and the shared real-time snapshot."""

    def __init__(self, session: aiohttp.ClientSession, cache_dir: str,
                 run_in_executor=None, rt_min_interval: float = 25.0) -> None:
        self.session = session
        self.cache_dir = cache_dir
        self.zip_path = os.path.join(cache_dir, "tisseo_gtfs.zip")
        self.db_path = os.path.join(cache_dir, "tisseo_gtfs.sqlite")
        self.meta_path = os.path.join(cache_dir, "tisseo_gtfs.json")
        self.store = GtfsStore(self.db_path)
        self._exec = run_in_executor or (lambda f, *a: asyncio.get_running_loop().run_in_executor(None, f, *a))
        self._rt: RealtimeSnapshot | None = None
        self._rt_fetched: datetime | None = None
        self._rt_lock = asyncio.Lock()
        self._gtfs_lock = asyncio.Lock()
        self.rt_min_interval = rt_min_interval
        self.rt_error: str | None = None
        self.rt_source_url: str | None = None
        self._alerts_at: datetime | None = None
        self.health: dict[str, FeedHealth] = {
            "gtfs_rt": FeedHealth("gtfs_rt"), "gtfs": FeedHealth("gtfs", stale_after=7 * 86400),
        }
        self.rt_attempts = 4
        self.sleep = asyncio.sleep
        # stop ids the lean index must cover (None = whole network)
        self.required_stops: set[str] | None = set()
        self.index_stats: dict | None = None

    # ---------------- lean index ----------------
    async def ensure_index(self, stop_ids: set[str] | None = None) -> bool:
        """Rebuild the index from the cached zip when the configured stops changed."""
        if stop_ids is not None:
            self.required_stops = set(stop_ids)
        async with self._gtfs_lock:
            if not await self._exec(os.path.exists, self.zip_path):
                return False
            want = stops_key(self.required_stops)
            have = await self._exec(self.store.stops_key) if await self._exec(self.store.is_valid) else None
            if have == want:
                return False
            await self._build(self._read_meta_sync_version())
            return True

    def _read_meta_sync_version(self) -> str:
        m = self._read_meta()
        return m.get("etag") or m.get("last_modified") or m.get("checked") or ""

    async def _build(self, version: str) -> None:
        _LOGGER.info("Indexing Tisséo GTFS for %s stop(s)",
                     "all" if self.required_stops is None else len(self.required_stops))
        stops = None if self.required_stops is None else sorted(self.required_stops)
        self.index_stats = await self._exec(build_index, self.zip_path, self.db_path, version, stops)
        from .departures import clear_caches
        clear_caches()

    # ---------------- static ----------------
    def _read_meta(self) -> dict:
        try:
            with open(self.meta_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _write_meta(self, meta: dict) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)

    async def ensure_gtfs(self, max_age: timedelta = timedelta(hours=24), force: bool = False) -> bool:
        """Download (conditionally) and index the GTFS feed. Returns True if rebuilt."""
        async with self._gtfs_lock:
            await self._exec(lambda: os.makedirs(self.cache_dir, exist_ok=True))
            meta = await self._exec(self._read_meta)
            valid = await self._exec(self.store.is_valid)
            if valid and await self._exec(self.store.stops_key) != stops_key(self.required_stops):
                valid = False if not await self._exec(os.path.exists, self.zip_path) else valid
                if valid:
                    await self._build(meta.get("etag") or meta.get("last_modified") or "")
            checked = meta.get("checked")
            if valid and not force and checked and \
                    datetime.now(TZ) - datetime.fromisoformat(checked) < max_age:
                return False
            headers = dict(HEADERS)
            if valid and meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if valid and meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]
            last_err: Exception | None = None
            for url in GTFS_URLS:
                try:
                    async with self.session.get(url, headers=headers,
                                                timeout=aiohttp.ClientTimeout(total=300)) as resp:
                        if resp.status == 304:
                            self.health["gtfs"].record(True)
                            meta["checked"] = datetime.now(TZ).isoformat()
                            await self._exec(self._write_meta, meta)
                            return False
                        resp.raise_for_status()
                        tmp = self.zip_path + ".part"
                        # all file I/O runs in the executor (HA flags blocking calls in the loop)
                        fh = await self._exec(open, tmp, "wb")
                        try:
                            buf = bytearray()
                            async for chunk in resp.content.iter_chunked(1 << 16):
                                buf += chunk
                                if len(buf) >= 1 << 20:
                                    await self._exec(fh.write, bytes(buf))
                                    buf.clear()
                            if buf:
                                await self._exec(fh.write, bytes(buf))
                        finally:
                            await self._exec(fh.close)
                        await self._exec(os.replace, tmp, self.zip_path)
                        new_meta = {
                            "url": url, "etag": resp.headers.get("ETag"),
                            "last_modified": resp.headers.get("Last-Modified"),
                            "checked": datetime.now(TZ).isoformat(),
                        }
                    version = new_meta["etag"] or new_meta["last_modified"] or new_meta["checked"]
                    await self._build(version)
                    await self._exec(self._write_meta, new_meta)
                    self.health["gtfs"].record(True)
                    return True
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
                    last_err = err
                    self.health["gtfs"].record(False, f"{type(err).__name__}")
                    _LOGGER.warning("GTFS download from %s failed: %s", url, err)
            if valid:
                return False  # keep using the cached index
            raise RuntimeError(f"Could not download Tisséo GTFS: {last_err}")

    # ---------------- realtime ----------------
    async def realtime(self) -> RealtimeSnapshot | None:
        """Shared, rate-limited GTFS-RT snapshot (one download for all stops)."""
        async with self._rt_lock:
            now = datetime.now(TZ)
            if self._rt_fetched and (now - self._rt_fetched).total_seconds() < self.rt_min_interval:
                return self._rt
            hl = self.health["gtfs_rt"]
            if not hl.allow():
                self.rt_error = "circuit breaker open"
                attempts = []
            else:
                attempts = [GTFS_RT_URLS[i % len(GTFS_RT_URLS)] for i in range(self.rt_attempts)]
            for attempt, url in enumerate(attempts):
                if attempt:
                    # api.tisseo.fr intermittently drops TLS handshakes: jittered backoff
                    await self.sleep(backoff_delay(attempt - 1))
                try:
                    async with self.session.get(url, headers=HEADERS,
                                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        resp.raise_for_status()
                        data = await resp.read()
                    snap = await self._exec(parse_realtime, data)
                    # The feed occasionally omits the alerts block; keep the last
                    # known alerts for up to 10 minutes instead of flapping to zero.
                    if not snap.alerts and self._rt and self._rt.alerts and self._alerts_at and \
                            (now - self._alerts_at).total_seconds() < 600:
                        snap.alerts = self._rt.alerts
                    elif snap.alerts:
                        self._alerts_at = now
                    self._rt = snap
                    self._rt_fetched = now
                    self.rt_source_url = url
                    self.rt_error = None
                    hl.record(True)
                    return self._rt
                except Exception as err:  # noqa: BLE001 - feed errors must not kill updates
                    self.rt_error = f"{url}: {type(err).__name__}: {err}"
                    hl.record(False, f"{type(err).__name__}")
                    _LOGGER.debug("GTFS-RT fetch failed: %s", self.rt_error)
                    if not hl.allow():
                        break
            # keep a stale snapshot for up to 5 minutes, then fall back to schedule only
            if self._rt_fetched and (now - self._rt_fetched).total_seconds() > 300:
                self._rt = None
            return self._rt

    def feed_age(self) -> float | None:
        """Seconds since the GTFS-RT header timestamp of the current snapshot."""
        if self._rt is None or not self._rt.timestamp:
            return None
        return max(0.0, datetime.now(TZ).timestamp() - self._rt.timestamp)
