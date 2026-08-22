"""The pinned arXiv traffic bounds, enforced in code and testable without sleeping.

The arXiv API Terms of Use say: "Make no more than one request every three
seconds, and limit requests to a single connection at a time."  ADR-0067 turns
both into pinned bounds rather than caller arguments.  This module is the only
place a corpus request may start.

Three properties are enforced, all of them fail-closed:

* **Interval.**  A request may not start until the pinned interval has elapsed
  since the previous start.  The pacer asks the injected sleeper to wait and
  then RE-READS the clock; a sleeper that returns without time having passed is
  a refusal, not a warning, so a broken or lying sleeper cannot leak traffic.
* **Single connection.**  A second overlapping request is refused outright.
* **Request budget.**  A run may not exceed the pinned request count.

A caller may narrow a bound and may never widen one.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from .constants import (
    MAX_CONCURRENT_CONNECTIONS, MAX_REQUESTS_PER_RUN,
    MIN_REQUEST_INTERVAL_MILLISECONDS,
)
from .errors import (
    ClockNonMonotonicError, ConcurrentRequestForbiddenError, CorpusError,
    RateLimitViolationError, RequestBudgetExceededError,
)


class SystemMonotonicClock:
    """The only clock that reads real time. Never used by the offline path."""

    def now_milliseconds(self) -> int:
        return time.monotonic_ns() // 1_000_000


class SystemSleeper:
    """The only sleeper that really sleeps. Never used by the offline path."""

    def sleep_milliseconds(self, milliseconds: int) -> None:
        if isinstance(milliseconds, bool) or not isinstance(milliseconds, int):
            raise CorpusError("sleep duration is not an integer", code="corpus_sleep_invalid")
        if milliseconds < 0:
            raise CorpusError("sleep duration is negative", code="corpus_sleep_invalid")
        time.sleep(milliseconds / 1_000)


class FixedClock:
    """A clock that never advances. Used by the dry-run and replay paths."""

    def __init__(self, value: int = 0) -> None:
        self.value = int(value)

    def now_milliseconds(self) -> int:
        return self.value


class ManualClock:
    """A clock advanced only by an explicit call. Test and probe instrument."""

    def __init__(self, value: int = 0) -> None:
        self.value = int(value)

    def advance(self, milliseconds: int) -> None:
        self.value += int(milliseconds)

    def now_milliseconds(self) -> int:
        return self.value


class SleeperThatAdvances:
    """Honest sleeper over a :class:`ManualClock`; advances by exactly the wait."""

    def __init__(self, clock: ManualClock, *, overshoot_milliseconds: int = 0) -> None:
        self.clock = clock
        self.overshoot_milliseconds = int(overshoot_milliseconds)
        self.waits: list[int] = []

    def sleep_milliseconds(self, milliseconds: int) -> None:
        self.waits.append(int(milliseconds))
        self.clock.advance(int(milliseconds) + self.overshoot_milliseconds)


class SleeperThatDoesNotSleep:
    """A sleeper that returns immediately. The pacer must refuse to proceed."""

    def __init__(self) -> None:
        self.waits: list[int] = []

    def sleep_milliseconds(self, milliseconds: int) -> None:
        self.waits.append(int(milliseconds))


class RequestPacer:
    """Gate every corpus request through the pinned arXiv traffic bounds."""

    def __init__(
        self, clock: Any, sleeper: Any, *,
        min_interval_milliseconds: int = MIN_REQUEST_INTERVAL_MILLISECONDS,
        max_requests: int = MAX_REQUESTS_PER_RUN,
        max_concurrent_connections: int = MAX_CONCURRENT_CONNECTIONS,
    ) -> None:
        if (
            isinstance(min_interval_milliseconds, bool)
            or not isinstance(min_interval_milliseconds, int)
            or min_interval_milliseconds < MIN_REQUEST_INTERVAL_MILLISECONDS
        ):
            raise RateLimitViolationError(
                "the minimum request interval is pinned by the arXiv terms and "
                f"may only be narrowed; got {min_interval_milliseconds!r}"
            )
        if (
            isinstance(max_concurrent_connections, bool)
            or not isinstance(max_concurrent_connections, int)
            or not 1 <= max_concurrent_connections <= MAX_CONCURRENT_CONNECTIONS
        ):
            raise ConcurrentRequestForbiddenError(
                "the arXiv terms allow a single connection at a time; "
                f"got {max_concurrent_connections!r}"
            )
        if (
            isinstance(max_requests, bool) or not isinstance(max_requests, int)
            or not 1 <= max_requests <= MAX_REQUESTS_PER_RUN
        ):
            raise RequestBudgetExceededError(
                f"the request budget is pinned at {MAX_REQUESTS_PER_RUN} and may "
                f"only be narrowed; got {max_requests!r}"
            )
        self.clock = clock
        self.sleeper = sleeper
        self.min_interval_milliseconds = min_interval_milliseconds
        self.max_requests = max_requests
        self.max_concurrent_connections = max_concurrent_connections
        self.requests = 0
        self.in_flight = 0
        self.last_start_milliseconds: int | None = None
        self.observed_intervals: list[int | None] = []
        self.sleep_requests: list[int] = []
        self._last_reading: int | None = None

    def _read_clock(self) -> int:
        try:
            observed = self.clock.now_milliseconds()
        except Exception as error:  # noqa: BLE001 - a failed clock is fail-closed
            raise ClockNonMonotonicError("the injected clock raised") from error
        if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
            raise ClockNonMonotonicError(f"clock reading is not a whole millisecond count: {observed!r}")
        if self._last_reading is not None and observed < self._last_reading:
            raise ClockNonMonotonicError(
                f"clock went backwards: {observed} after {self._last_reading}"
            )
        self._last_reading = observed
        return observed

    def start(self) -> int:
        """Reserve the single connection and return the observed start time."""

        if self.in_flight >= self.max_concurrent_connections:
            raise ConcurrentRequestForbiddenError(
                "a corpus request is already in flight; the arXiv terms allow "
                "one connection at a time"
            )
        if self.requests >= self.max_requests:
            raise RequestBudgetExceededError(
                f"the run already made {self.requests} of {self.max_requests} requests"
            )
        observed = self._read_clock()
        interval: int | None = None
        if self.last_start_milliseconds is not None:
            interval = observed - self.last_start_milliseconds
            if interval < self.min_interval_milliseconds:
                wait = self.min_interval_milliseconds - interval
                self.sleep_requests.append(wait)
                self.sleeper.sleep_milliseconds(wait)
                observed = self._read_clock()
                interval = observed - self.last_start_milliseconds
                if interval < self.min_interval_milliseconds:
                    raise RateLimitViolationError(
                        f"only {interval} ms elapsed since the previous request; "
                        f"the arXiv terms require {self.min_interval_milliseconds} ms"
                    )
        self.in_flight += 1
        self.requests += 1
        self.last_start_milliseconds = observed
        self.observed_intervals.append(interval)
        return observed

    def finish(self) -> None:
        if self.in_flight <= 0:
            raise ConcurrentRequestForbiddenError("no corpus request is in flight")
        self.in_flight -= 1

    @contextmanager
    def request(self) -> Iterator[int]:
        started_at = self.start()
        try:
            yield started_at
        finally:
            self.finish()

    def observation(self) -> dict[str, Any]:
        """Operational, not semantic: these are timings and race observations."""

        measured = [item for item in self.observed_intervals if item is not None]
        return {
            "requests": self.requests,
            "max_requests": self.max_requests,
            "min_request_interval_milliseconds": self.min_interval_milliseconds,
            "max_concurrent_connections": self.max_concurrent_connections,
            "observed_intervals_milliseconds": list(self.observed_intervals),
            "min_observed_interval_milliseconds": min(measured) if measured else None,
            "sleep_requests_milliseconds": list(self.sleep_requests),
        }


__all__ = [
    "FixedClock",
    "ManualClock",
    "RequestPacer",
    "SleeperThatAdvances",
    "SleeperThatDoesNotSleep",
    "SystemMonotonicClock",
    "SystemSleeper",
]
