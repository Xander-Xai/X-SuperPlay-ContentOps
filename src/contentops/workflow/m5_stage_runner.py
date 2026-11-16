from __future__ import annotations


def run_stage(timings, clock, name, function, *args, **kwargs):
    started = clock()
    try:
        return function(*args, **kwargs)
    finally:
        timings[name] = round(clock() - started, 3)
