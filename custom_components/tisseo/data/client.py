"""Async downloads of the keyless Tisséo open-data feeds (aiohttp)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

import aiohttp

from .const import GTFS_RT_URLS, GTFS_URLS, TZ, USER_AGENT
from .realtime import RealtimeSnapshot, parse_realtime
from .static import GtfsStore, build_index

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
                    _LOGGER.info("Indexing Tisséo GTFS from %s", url)
                    await self._exec(build_index, self.zip_path, self.db_path, version)
                    await self._exec(self._write_meta, new_meta)
                    from .departures import clear_caches
                    clear_caches()
                    return True
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
                    last_err = err
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
            for attempt, url in enumerate(GTFS_RT_URLS * 2):
                if attempt:
                    await asyncio.sleep(2)  # api.tisseo.fr intermittently drops TLS handshakes
                try:
                    async with self.session.get(url, headers=HEADERS,
                                                timeout=aiohttp.ClientTimeout(total=20)) as resp:
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
                    return self._rt
                except Exception as err:  # noqa: BLE001 - feed errors must not kill updates
                    self.rt_error = f"{url}: {err}"
                    _LOGGER.debug("GTFS-RT fetch failed: %s", self.rt_error)
            # keep a stale snapshot for up to 5 minutes, then fall back to schedule only
            if self._rt_fetched and (now - self._rt_fetched).total_seconds() > 300:
                self._rt = None
            return self._rt
