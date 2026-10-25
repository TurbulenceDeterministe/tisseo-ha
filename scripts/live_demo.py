#!/usr/bin/env python3
"""Run the Tisséo data layer against the live keyless feeds and print next departures.

usage: python scripts/live_demo.py [stop name or id] [--lines A,B] [--count N]
"""
import argparse
import asyncio
import importlib.util
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "..", "custom_components", "tisseo", "data")
spec = importlib.util.spec_from_file_location("tisseo_data", os.path.join(PKG, "__init__.py"),
                                              submodule_search_locations=[PKG])
td = importlib.util.module_from_spec(spec)
sys.modules["tisseo_data"] = td
spec.loader.exec_module(td)
from tisseo_data.client import TisseoFeeds  # noqa: E402
from tisseo_data.departures import alerts_for, next_departures  # noqa: E402

import aiohttp  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stop", nargs="?", default="Capitole")
    ap.add_argument("--lines", default="")
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--cache", default=os.path.join(HERE, "..", ".cache"))
    args = ap.parse_args()
    async with aiohttp.ClientSession() as session:
        feeds = TisseoFeeds(session, args.cache)
        t = time.time()
        rebuilt = await feeds.ensure_gtfs()
        print(f"GTFS ready (rebuilt={rebuilt}) in {time.time()-t:.1f}s; meta={feeds.store.meta()}")
        t = time.time()
        rt = await feeds.realtime()
        if rt:
            print(f"GTFS-RT: {len(rt.trips)} trip updates, {len(rt.alerts)} alerts, "
                  f"feed time {datetime.fromtimestamp(rt.timestamp, td.TZ):%Y-%m-%d %H:%M:%S %Z} "
                  f"({time.time()-t:.1f}s)")
        else:
            print("GTFS-RT unavailable:", feeds.rt_error)
        matches = feeds.store.search_stops(args.stop)
        if not matches:
            sys.exit(f"no stop matches {args.stop!r}")
        print("Matches:", ", ".join(f"{s.name} [{s.stop_id}] lines={l}" for s, l in matches[:6]))
        stop = matches[0][0]
        routes = feeds.store.routes_for_stop(stop.stop_id)
        wanted = {x.strip() for x in args.lines.split(",") if x.strip()}
        route_ids = {r.route_id for r in routes if r.short_name in wanted} if wanted else None
        now = datetime.now(td.TZ)
        print(f"\nNext departures at {stop.name} ({stop.stop_id}) — now {now:%H:%M:%S %Z}")
        for d in next_departures(feeds.store, rt, stop.stop_id, now=now, route_ids=route_ids,
                                 count=args.count):
            sched = d.scheduled.strftime("%H:%M:%S") if d.scheduled else "  --  "
            delay = f"{d.delay:+d}s" if d.delay is not None else "  n/a"
            print(f"  {d.mode:<6} {d.line:<6} -> {d.destination:<38.38} "
                  f"sched {sched}  exp {d.expected:%H:%M:%S}  ({d.as_dict(now)['minutes']:>3} min)  "
                  f"{'RT ' if d.realtime else 'SCH'} delay {delay}  [{d.stop_id}]")
        rids = route_ids or {r.route_id for r in routes}
        al = alerts_for(rt, set(feeds.store.child_stop_ids(stop.stop_id)) | {stop.stop_id}, rids)
        print(f"\nAlerts relevant to this stop/lines: {len(al)}")
        for a in al[:5]:
            print(f"  - {a.header} ({'network' if a.network_wide else ','.join(sorted(a.route_ids))})")


if __name__ == "__main__":
    asyncio.run(main())
