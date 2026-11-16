from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RunContext:
    clock: Callable[[], float]
    stages: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)

    def run_stage(self, name, function, *args, **kwargs):
        return run_stage(self.timings, self.clock, name, function, *args, **kwargs)


def run_stage(timings, clock, name, function, *args, **kwargs):
    started = clock()
    try:
        return function(*args, **kwargs)
    finally:
        timings[name] = round(clock() - started, 3)
