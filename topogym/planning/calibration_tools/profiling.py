"""Nested wall-clock spans, owned and journaled by the development supervisor."""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import inspect
import time


class Profiler:
    """Instrument only this private worker; never changes arguments or results."""
    def __init__(self, send, context):
        self.send, self.context = send, context
        self.stack = []
        self.sequence = 0
        self.patches = []
        self.coverage = {}

    @contextmanager
    def span(self, stage, **metadata):
        self.sequence += 1
        row = dict(span_id=self.sequence, parent_id=self.stack[-1]["span_id"] if self.stack else None,
                   stage=stage, started=time.monotonic(), **self.context(), metadata=metadata)
        self.stack.append(row)
        self.send(dict(kind="span_begin", span=row))
        failed = False
        try:
            yield row
        except BaseException:
            failed = True
            raise
        finally:
            self.stack.pop()
            self.send(dict(kind="span_end", span=dict(span_id=row["span_id"], ended=time.monotonic(),
                                                     failed=failed, metadata=row["metadata"])))

    def wrap(self, target, name, stage, *, before=None, after=None, metadata=None, optional=False):
        """Preserve descriptors, including inherited methods, and restore exactly."""
        if not hasattr(target, name):
            if optional:
                self.coverage[stage] = "unavailable"
                return False
            raise AttributeError(name)
        if any(obj is target and key == name for obj, key, *_ in self.patches):
            return True
        own = name in vars(target)
        original = inspect.getattr_static(target, name) if own else None
        value = inspect.getattr_static(target, name) if isinstance(target, type) else getattr(target, name)
        descriptor = type(value) if isinstance(value, (classmethod, staticmethod)) else None
        function = value.__func__ if descriptor else value

        @wraps(function)
        def wrapped(*args, **kwargs):
            details = metadata(*args, **kwargs) if metadata else {}
            with self.span(stage, **details) as span:
                if before:
                    before(*args, **kwargs)
                result = function(*args, **kwargs)
                if after:
                    updated = after(result, *args, **kwargs)
                    if updated is not None:
                        span["metadata"].update(updated)
                return result
        try:
            setattr(target, name, descriptor(wrapped) if descriptor else wrapped)
        except (TypeError, AttributeError):
            if not optional:
                raise
            self.coverage[stage] = "unavailable"
            return False
        self.patches.append((target, name, own, original))
        self.coverage[stage] = "instrumented"
        return True

    def close(self):
        for target, name, own, original in reversed(self.patches):
            if own:
                setattr(target, name, original)
            else:
                delattr(target, name)
        self.patches.clear()


class TimingBook:
    """Parent-only accounting. Open spans survive worker death as incomplete."""
    def __init__(self):
        self.active = {}
        self.totals = {}
        self.operations = {}
        self.last_completed_physics_step = None
        self.last_completed_native_frame = None

    def accept(self, message):
        row = message["span"]
        key = row["span_id"]
        if message["kind"] == "span_begin":
            self.active[key] = dict(row, children_s=0.)
            return
        opened = self.active.pop(key)
        seconds = max(0., row["ended"] - opened["started"])
        exclusive = max(0., seconds - opened["children_s"])
        if opened["parent_id"] in self.active:
            self.active[opened["parent_id"]]["children_s"] += seconds
        for costs in (self.totals, self.operations.setdefault(opened.get("operation_id") or "startup", {})):
            item = costs.setdefault(opened["stage"], dict(calls=0, seconds=0., self_seconds=0.,
                                                        max_seconds=0., failed_calls=0))
            item["calls"] += 1
            item["seconds"] += seconds
            item["self_seconds"] += exclusive
            item["max_seconds"] = max(item["max_seconds"], seconds)
            item["failed_calls"] += int(row["failed"])
        if not row["failed"]:
            if opened["stage"] == "physics_tick":
                self.last_completed_physics_step = opened["metadata"].get("target_physics_step")
            elif opened["stage"] == "ipc_native_advance":
                metadata = row.get("metadata", {})
                if metadata.get("native_valid") is True:
                    self.last_completed_native_frame = metadata["native_frame"]

    def progress(self, now=None):
        now = time.monotonic() if now is None else now
        active = [dict(row, elapsed_s=max(0., now-row["started"])) for row in self.active.values()]
        return dict(stage=active[-1]["stage"] if active else None, active_spans=active,
                    last_completed_physics_step=self.last_completed_physics_step,
                    last_completed_native_frame=self.last_completed_native_frame)

    def snapshot(self):
        return dict(schema_version=1, clock="host monotonic wall time; existing engine synchronization only",
                    accounting="seconds include children; self_seconds exclude instrumented children; do not sum inclusive stages",
                    costs=deepcopy(self.totals), operations=deepcopy(self.operations),
                    incomplete_spans=self.progress()["active_spans"],
                    scope="development instrumentation, including transport overhead; not GPU kernel time")

    def expired_step(self, budget_s, now=None):
        now = time.monotonic() if now is None else now
        # Nested stage messages and heartbeats never reset the World tick clock.
        for row in self.active.values():
            if row["stage"] in {"physics_tick", "ipc_native_advance"} and now-row["started"] > budget_s:
                return dict(row, elapsed_s=now-row["started"])
        return None
