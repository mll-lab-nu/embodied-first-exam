"""Shared provider cooldown; never change payloads or add model retries."""
from __future__ import annotations

import fcntl
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import uuid


class Cooldown:
    def __init__(self, directory, seconds=75, *, clock=time.time):
        if not math.isfinite(seconds) or seconds < 60:
            raise ValueError("Provider cooldown must be at least 60 seconds")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.seconds, self.clock = seconds, clock

    def remaining(self):
        state = self.directory / "state.json"
        if not state.exists():
            return 0.0
        return max(0.0, json.loads(state.read_text())["until"] - self.clock())

    def limited(self, headers=None):
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        delay = float(self.seconds)
        for key, scale in (("retry-after", 1), ("retry-after-ms", .001),
                           ("x-ms-retry-after-ms", .001)):
            try:
                value = float(headers[key]) * scale
                if math.isfinite(value):
                    delay = max(delay, value)
            except (KeyError, TypeError, ValueError):
                pass
        with (self.directory / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.directory / "state.json"
            state = json.loads(path.read_text()) if path.exists() else {}
            now = self.clock()
            state = {"until": max(state.get("until", 0), now + delay),
                     "updated_at": now, "observed_limits": state.get("observed_limits", 0) + 1}
            temporary = path.with_name("state-" + uuid.uuid4().hex + ".tmp")
            temporary.write_text(json.dumps(state) + "\n")
            os.replace(temporary, path)
        return state

    def wait(self, closed):
        start = self.clock()
        while (remaining := self.remaining()) > 0:
            if closed.wait(min(remaining, 1)):
                raise RuntimeError("Episode closed during provider cooldown")
        return max(0.0, self.clock() - start)


def install(config, control, *, service_module=None, recorder=None):
    """Delay the harness's next existing request after HTTP/SSE rate limits."""
    if service_module is None:
        from humanclaw_bench.harnesses import services as service_module
    if recorder is None:
        from humanclaw_bench.experiments import recorder
    cls = service_module.LocalServices
    if getattr(cls, "_repair_provider_cooldown", False):
        raise RuntimeError("Provider cooldown already installed")
    endpoint = config["endpoint"].rstrip("/")
    if not endpoint.startswith("https://"):
        raise ValueError("Expected the configured HTTPS provider endpoint")
    gate = Cooldown(Path(control) / "provider-rate-limit", config.get("backoff_seconds", 75))
    original_responses = cls.responses
    original_events = cls._response_events
    original_open = service_module.urllib.request.urlopen

    def relevant(url):
        return str(url).split("?", 1)[0].rstrip("/") == endpoint

    def note_limit(headers):
        state = gate.limited(headers)
        recorder.event("provider.rate_limit_observed", kind="transport", name="azure.cooldown",
                       data={"cooldown_until_unix": state["until"],
                             "observed_limits": state["observed_limits"],
                             "additional_model_attempts": 0})

    def responses(self, handler, payload):
        if self.responder is None and self.azure and relevant(self.upstream_url):
            if gate.remaining() > 0:
                # Outside model.responses: queue time is recorded separately
                # from actual upstream calls, and stays in episode wall time.
                with recorder.span("provider.rate_limit_wait", kind="transport",
                                   attributes={"policy": "shared_cooldown_after_rate_limit"}) as waiting:
                    seconds = gate.wait(self.closed)
                    waiting.set_output({"wait_seconds": seconds, "additional_model_attempts": 0})
        return original_responses(self, handler, payload)

    def urlopen(request, *args, **kwargs):
        url = getattr(request, "full_url", request)
        try:
            return original_open(request, *args, **kwargs)
        except urllib.error.HTTPError as exc:
            if relevant(url) and exc.code == 429:
                note_limit(exc.headers)
            raise

    def response_events(response):
        ours = relevant(response.geturl())
        for item in original_events(response):
            result = item.get("response", {})
            error = result.get("error") or (item if item.get("type") == "error" else {})
            if ours and isinstance(error, dict) and error.get("code") == "rate_limit_exceeded":
                note_limit(response.headers)
            yield item  # Preserve the original event, including the failure.

    cls.responses = responses
    cls._response_events = staticmethod(response_events)
    service_module.urllib.request.urlopen = urlopen
    cls._repair_provider_cooldown = True
    return gate
