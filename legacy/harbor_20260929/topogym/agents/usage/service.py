"""Immediate event decisions plus independent policy-update/watchdog polling."""
from pathlib import Path
import threading

from .ledger import UsageLedger
from .publisher import PipelineOwnership, UsagePublisher


class UsageService:
    def __init__(self, root, *, scope_id, policy, interval=.1):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.ownership = PipelineOwnership(self.root)
        self.stopped = threading.Event()
        self.shutdown = threading.Event()
        self.interval = interval
        self.lock = threading.RLock()
        self.error = None
        self.callbacks, self.health_checks = [], []
        self.callback_lock = threading.RLock()
        self.closed = False
        try:
            self.ledger = UsageLedger(self.root / "ledger.sqlite", scope_id=scope_id, policy=policy)
            if self.ledger.snapshot()["in_flight_requests"]:
                self.ledger.fail("usage_incomplete")  # no silent reuse of interrupted reservations
            self.publisher = UsagePublisher(self.root, self.ledger)
            self.refresh()
        except BaseException:
            self.ownership.close()
            raise
        self.thread = threading.Thread(target=self._watch, name="token-budget-watchdog", daemon=True)
        self.thread.start()

    def refresh(self):
        with self.lock:
            result = self.ledger.snapshot()
            if result["stop"]:
                self.notify_stop()  # notify before fsync/export work
            self.publisher.publish(result)
            return result

    def subscribe_stop(self, callback):
        with self.callback_lock:
            self.callbacks.append(callback)
            stopped = self.stopped.is_set()
        if stopped:
            callback()

    def notify_stop(self):
        with self.callback_lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            callbacks = tuple(self.callbacks)
        for callback in callbacks:
            callback()

    def record(self, event):
        result = self.ledger.record(event)
        if result["stop"]:
            self.notify_stop()
        return result

    def fail(self, reason, *, request_id=None):
        result = self.ledger.fail(reason, request_id=request_id)
        self.notify_stop()
        return result

    def _watch(self):
        try:
            while not self.shutdown.wait(self.interval):
                for check in tuple(self.health_checks):
                    if not check():
                        self.fail("gateway_failed")
                self.refresh()
        except Exception as error:
            self.error = type(error).__name__
            try:
                self.ledger.fail("gateway_failed")
            finally:
                self.notify_stop()

    def close(self):
        if self.closed:
            return self.ledger.snapshot()
        self.shutdown.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.fail("gateway_failed")
            # Retain ownership while the publisher can still write. A caller
            # may retry close after the blocked I/O returns.
            raise RuntimeError("Usage publisher did not stop")
        try:
            with self.lock:
                result = self.ledger.snapshot()
                self.publisher.finalize(result)
                return result
        except Exception:
            self.fail("gateway_failed")
            raise
        finally:
            self.closed = True
            self.ownership.close()
