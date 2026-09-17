"""Local observations; missing provider usage is unknown, never estimated as zero."""
import time
from contextlib import contextmanager


class Metrics:
    def __init__(self):
        self.seconds = dict(model=0.0, compact=0.0, tools=0.0, commands=0.0, permission=0.0)
        self.calls = dict(model=0, compact=0)
        self.usage = {phase: dict(input_tokens=0, output_tokens=0, reported=0) for phase in self.calls}
        self._stack = []

    @contextmanager
    def measure(self, phase):
        frame = [time.monotonic(), 0.0]
        self._stack.append(frame)
        try:
            yield
        finally:
            elapsed = max(0.0, time.monotonic() - frame[0])
            self._stack.pop()
            self.seconds[phase] += max(0.0, elapsed - frame[1])
            if self._stack:
                self._stack[-1][1] += elapsed

    def record_usage(self, phase, usage):
        if not isinstance(usage, dict):
            return
        values = [usage.get(key) for key in ("input_tokens", "output_tokens")]
        if not all(type(value) is int and value >= 0 for value in values):
            return
        self.usage[phase]["input_tokens"] += values[0]
        self.usage[phase]["output_tokens"] += values[1]
        self.usage[phase]["reported"] += 1

    def snapshot(self):
        return {"seconds": {key: round(value, 3) for key, value in self.seconds.items()},
                "calls": dict(self.calls), "usage": {key: dict(value) for key, value in self.usage.items()}}
