"""Timetable change detection: does tomorrow's service differ from a normal day?"""
from __future__ import annotations

from datetime import date, timedelta

from .static import GtfsStore

_TXT = {
    "en": {
        "no_service": "No departures tomorrow ({d}) at this stop.",
        "count": "{n_t} departures tomorrow vs {n_b} {ref} ({pct:+d}%).",
        "lines_gone": "Not running tomorrow: {x}.",
        "lines_new": "Only tomorrow: {x}.",
        "first": "First departure {a} instead of {b}.",
        "last": "Last departure {a} instead of {b}.",
        "calendar": "Different service calendar ({x}).",
        "same": "Tomorrow's timetable matches {ref}.",
        "no_data": "The published timetable does not cover tomorrow ({d}) yet.",
        "ref_week": "the same day last week",
        "ref_next": "the same day next week",
        "ref_2w": "the same day two weeks ago",
        "ref_today": "today",
    },
    "fr": {
        "no_service": "Aucun départ demain ({d}) à cet arrêt.",
        "count": "{n_t} départs demain contre {n_b} {ref} ({pct:+d} %).",
        "lines_gone": "Lignes sans service demain : {x}.",
        "lines_new": "Lignes seulement demain : {x}.",
        "first": "Premier départ {a} au lieu de {b}.",
        "last": "Dernier départ {a} au lieu de {b}.",
        "calendar": "Calendrier de service différent ({x}).",
        "same": "Les horaires de demain sont identiques à {ref}.",
        "no_data": "Les horaires publiés ne couvrent pas encore demain ({d}).",
        "ref_week": "le même jour la semaine dernière",
        "ref_next": "le même jour la semaine prochaine",
        "ref_2w": "le même jour il y a deux semaines",
        "ref_today": "aujourd'hui",
    },
}


def _hhmm(secs: int | None) -> str:
    if secs is None:
        return "-"
    h, m = divmod(secs // 60, 60)
    return f"{h % 24:02d}:{m:02d}"


def timetable_change(store: GtfsStore, stop_ids: list[str], today: date,
                     route_ids: set[str] | None = None, lang: str = "en",
                     threshold: float = 0.1) -> dict:
    """Compare tomorrow with the same weekday a week before/after (or two weeks before).

    "changed" is true when tomorrow has no service, a line disappears/appears, the
    departure count differs by more than ``threshold`` or the first/last departure
    moves by more than 15 minutes. Holiday calendars show up this way.
    """
    t = lang if lang in _TXT else "en"
    tx = _TXT[t]
    tomorrow = today + timedelta(days=1)
    s_tom = store.day_summary(stop_ids, tomorrow, route_ids)
    s_today = store.day_summary(stop_ids, today, route_ids)
    end = store.coverage_end()
    if end is not None and tomorrow > end:
        return {
            "changed": False, "description": tx["no_data"].format(d=tomorrow.isoformat()),
            "tomorrow": tomorrow.isoformat(), "reference_day": None,
            "tomorrow_departures": s_tom["count"], "reference_departures": None,
            "today_departures": s_today["count"], "differs_from_today": False,
            "tomorrow_first": _hhmm(s_tom["first"]), "tomorrow_last": _hhmm(s_tom["last"]),
            "tomorrow_per_line": s_tom["per_line"], "reference_per_line": {},
            "service_calendar_changed": False, "data_incomplete": True,
            "coverage_end": end.isoformat(),
        }

    def compare(s_ref: dict, ref_name: str) -> list[str]:
        reasons: list[str] = []
        if s_tom["count"] == 0 and s_ref["count"] > 0:
            return [tx["no_service"].format(d=tomorrow.isoformat())]
        gone = sorted(set(s_ref["per_line"]) - set(s_tom["per_line"]))
        new = sorted(set(s_tom["per_line"]) - set(s_ref["per_line"]))
        if gone:
            reasons.append(tx["lines_gone"].format(x=", ".join(gone)))
        if new:
            reasons.append(tx["lines_new"].format(x=", ".join(new)))
        nb, nt = s_ref["count"], s_tom["count"]
        if nb and abs(nt - nb) / nb > threshold:
            reasons.append(tx["count"].format(n_t=nt, n_b=nb, ref=ref_name,
                                              pct=round((nt - nb) * 100 / nb)))
        for k in ("first", "last"):
            x, y = s_tom[k], s_ref[k]
            if x is not None and y is not None and abs(x - y) > 15 * 60:
                reasons.append(tx[k].format(a=_hhmm(x), b=_hhmm(y)))
        return reasons

    # Normal reference = same weekday last week and/or next week (whichever exist,
    # within the published, complete part of the feed). Tomorrow is "changed" only if
    # it differs from all of them, so a holiday last week does not flag a normal day.
    refs = []
    for delta, name in ((-7, tx["ref_week"]), (7, tx["ref_next"]), (-14, tx["ref_2w"])):
        dd = tomorrow + timedelta(days=delta)
        if store.active_services(dd) and (end is None or dd <= end):
            refs.append((dd, name, store.day_summary(stop_ids, dd, route_ids)))
    if not refs:
        refs = [(today, tx["ref_today"], s_today)]
    results = [(dd, name, sm, compare(sm, name)) for dd, name, sm in refs]
    match = next((r for r in results if not r[3]), None)
    ref_day, ref_name, s_ref, reasons = match or results[0]
    services_changed = set(s_tom["services"]) != set(s_ref["services"])
    changed = bool(reasons)
    if changed and services_changed:
        diff = sorted(set(s_tom["services"]) ^ set(s_ref["services"]))
        reasons.append(tx["calendar"].format(x=", ".join(diff[:4]) + ("…" if len(diff) > 4 else "")))
    description = " ".join(reasons) if reasons else tx["same"].format(ref=ref_name)
    return {
        "changed": changed, "description": description, "tomorrow": tomorrow.isoformat(),
        "reference_day": ref_day.isoformat(),
        "tomorrow_departures": s_tom["count"], "reference_departures": s_ref["count"],
        "today_departures": s_today["count"],
        "differs_from_today": s_tom["count"] != s_today["count"]
        or set(s_tom["services"]) != set(s_today["services"]),
        "tomorrow_first": _hhmm(s_tom["first"]), "tomorrow_last": _hhmm(s_tom["last"]),
        "tomorrow_per_line": s_tom["per_line"], "reference_per_line": s_ref["per_line"],
        "service_calendar_changed": services_changed, "data_incomplete": False,
    }
