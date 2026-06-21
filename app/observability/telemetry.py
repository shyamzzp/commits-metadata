"""Observability: structured Logs, Metrics counters, and an Error Tracker."""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field


def get_logger(name: str = "commits-metadata") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)sZ %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


class Metrics:
    """Minimal in-memory counter/gauge registry (Prometheus-shaped)."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}

    def inc(self, name: str, value: int = 1) -> None:
        self._counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def snapshot(self) -> dict:
        return {"counters": dict(self._counters), "gauges": dict(self._gauges)}


@dataclass
class ErrorTracker:
    """Records failures from the retry/dead-letter queues for inspection."""

    errors: list[dict] = field(default_factory=list)

    def record(self, *, repository: str, sha: str, error: str, fatal: bool = False) -> None:
        self.errors.append(
            {"repository": repository, "sha": sha, "error": error, "fatal": fatal}
        )

    def all(self) -> list[dict]:
        return list(self.errors)

    def __len__(self) -> int:
        return len(self.errors)


class Telemetry:
    """Bundle of logger + metrics + error tracker shared across the app."""

    def __init__(self) -> None:
        self.log = get_logger()
        self.metrics = Metrics()
        self.errors = ErrorTracker()
