"""Feed health tracking, jittered exponential backoff and a circuit breaker."""
from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass, field

OK, DEGRADED, DOWN = "ok", "degraded", "down"


def backoff_delay(attempt: int, base: float = 0.75, cap: float = 8.0,
                  rng: random.Random | None = None) -> float:
    """'Full jitter' exponential backoff: uniform(0, min(cap, base * 2**attempt))."""
    r = rng or random
    return r.uniform(0, min(cap, base * (2 ** attempt)))


@dataclass
class FeedHealth:
    """Rolling success window + circuit breaker for one upstream feed."""

    name: str
    window: int = 50
    breaker_threshold: int = 3
    breaker_base: float = 30.0
    breaker_cap: float = 600.0
    stale_after: float = 600.0  # seconds without success => down
    clock: callable = time.time
    results: deque = field(default_factory=deque)
    last_success: float | None = None
    last_failure: float | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    open_until: float = 0.0
    trips: int = 0  # how many times the breaker opened
    attempts: int = 0

    def record(self, ok: bool, error: str | None = None) -> None:
        now = self.clock()
        self.attempts += 1
        self.results.append(bool(ok))
        while len(self.results) > self.window:
            self.results.popleft()
        if ok:
            self.last_success = now
            self.consecutive_failures = 0
            self.open_until = 0.0
            return
        self.last_failure = now
        self.last_error = error
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.breaker_threshold:
            n = self.consecutive_failures - self.breaker_threshold
            span = min(self.breaker_cap, self.breaker_base * (2 ** n))
            self.open_until = now + span * random.uniform(0.8, 1.2)
            self.trips += 1

    @property
    def breaker_open(self) -> bool:
        return self.clock() < self.open_until

    def allow(self) -> bool:
        """False while the breaker is open (callers skip the request)."""
        return not self.breaker_open

    @property
    def success_rate(self) -> float | None:
        if not self.results:
            return None
        return sum(self.results) / len(self.results)

    @property
    def state(self) -> str:
        now = self.clock()
        if self.breaker_open:
            return DOWN
        if not self.results:
            return DEGRADED
        if self.last_success is None or now - self.last_success > self.stale_after:
            return DOWN
        rate = self.success_rate or 0.0
        if rate < 0.9 or self.consecutive_failures:
            return DEGRADED
        return OK

    def as_dict(self) -> dict:
        def iso(ts):
            if ts is None:
                return None
            from datetime import datetime, timezone
            return datetime.fromtimestamp(ts, timezone.utc).isoformat()
        rate = self.success_rate
        return {
            "state": self.state, "success_rate": None if rate is None else round(rate * 100, 1),
            "window": len(self.results), "attempts": self.attempts,
            "last_success": iso(self.last_success), "last_failure": iso(self.last_failure),
            "last_error": self.last_error, "consecutive_failures": self.consecutive_failures,
            "breaker_open": self.breaker_open,
            "breaker_open_until": iso(self.open_until) if self.breaker_open else None,
            "breaker_trips": self.trips,
        }
