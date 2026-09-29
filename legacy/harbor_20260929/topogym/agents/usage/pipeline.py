"""One trial, one ledger, many gateway routes; no concrete agent dependencies."""
from pathlib import Path
import secrets
import threading

from .config import BudgetSettings
from .gateway import Gateway
from .service import UsageService


class GatewaySource:
    """Transport factory; injectable for tests without involving an agent harness."""
    def __init__(self, sockets=None):
        self.sockets = Path(sockets) if sockets is not None else None

    def create(self, service, route_id, route, credential):
        path = self.sockets / (secrets.token_hex(12) + ".sock") if self.sockets else None
        return Gateway(service, protocol=route["protocol"], upstream_url=route["url"],
                       api_key=credential, socket_path=path, route_id=route_id, model=route.get("model"))


class UsagePipeline:
    def __init__(self, root, *, scope_id, settings, source=None):
        self.settings = settings if isinstance(settings, BudgetSettings) else BudgetSettings.from_mapping(settings)
        self.source = source if source is not None else GatewaySource()
        self.gateways = {}
        self.closing = threading.Event()
        self.lock = threading.RLock()
        self.started = False
        self.finalized = False
        self.closed = False
        self.service = UsageService(root, scope_id=scope_id, policy=self.settings.policy,
                                    interval=self.settings.watchdog_interval_ms / 1000)
        self.ledger = self.service.ledger
        self.stopped = self.service.stopped
        self.service.subscribe_stop(self.cancel_requests)
        self.service.health_checks.append(self.healthy)

    def start(self, routes, credential_resolver):
        with self.lock:
            if self.started or self.closing.is_set() or self.ledger.snapshot()["closed"]:
                raise RuntimeError("Pipeline is already started or closed")
            if not routes:
                raise ValueError("Pipeline requires at least one route")
            self.started = True
            try:
                for name, route in routes.items():
                    self.gateways[name] = self.source.create(self.service, name, route, credential_resolver(route))
            except BaseException:
                self.service.fail("gateway_failed")
                raise
            return {name: dict(token=gateway.token,
                    url=None if gateway.socket_path else gateway.url,
                    socket_path=str(gateway.socket_path) if gateway.socket_path else None)
                    for name, gateway in self.gateways.items()}

    def healthy(self):
        with self.lock:
            return self.closing.is_set() or all(g.thread.is_alive() for g in self.gateways.values())

    def cancel_requests(self):
        self.closing.set()
        with self.lock:
            for gateway in self.gateways.values():
                gateway.cancel()

    def finalize(self, *, require_requests=True):
        self.cancel_requests()
        if not self.finalized:
            errors = []
            for gateway in self.gateways.values():
                try:
                    gateway.close()
                except Exception as error:
                    errors.append(type(error).__name__)
            if errors:
                self.service.fail("gateway_failed")
                raise RuntimeError("Gateway shutdown failed")
            self.finalized = True
        snapshot = self.ledger.finalize(require_requests=require_requests)
        if snapshot["stop"]:
            self.service.notify_stop()
        return snapshot

    def close(self):
        if not self.closed:
            try:
                self.finalize()
            finally:
                self.service.close()
                self.closed = True
        return self.ledger.snapshot()
