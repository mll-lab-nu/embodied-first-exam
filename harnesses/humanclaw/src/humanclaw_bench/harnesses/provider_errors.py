"""Classify provider failures and defer subsequent requests after transient errors."""
from __future__ import annotations

from email.utils import parsedate_to_datetime
import math
import random
import threading
import time


def provider_failure(*, status=None, error=None, incomplete=None):
    """Interpret explicit HTTP/SSE error fields without inspecting model-generated text."""
    detail = error if isinstance(error, dict) else {}
    code = detail.get("code")
    reason = incomplete.get("reason") if isinstance(incomplete, dict) else None
    if code == "episode_closed":
        category, retryable = "episode_closed", False
    elif code in {"content_filter", "content_policy_violation"} or reason == "content_filter":
        category, retryable = "content_filter", False
    elif status == 429 or code == "rate_limit_exceeded":
        category, retryable = "rate_limit", True
    elif status in {408, 500, 502, 503, 504} or code in {"server_error", "internal_server_error", "overloaded", "temporarily_unavailable"}:
        category, retryable = "provider_unavailable", True
    elif error or incomplete or (isinstance(status, int) and status >= 400):
        category, retryable = "provider_error", False
    else:
        return None
    return {"category": category, "retryable": retryable, "http_status": status,
            "code": code or reason, "message": detail.get("message")}


def retry_after_seconds(headers):
    """Read finite Retry-After seconds, HTTP dates and Azure millisecond headers."""
    values = {k.lower(): v for k, v in (headers or {}).items()}
    for key, scale in (("retry-after-ms", .001), ("x-ms-retry-after-ms", .001), ("retry-after", 1)):
        value = values.get(key)
        if value is None:
            continue
        try:
            delay = float(value) * scale
        except (ValueError, TypeError):
            try:
                delay = parsedate_to_datetime(value).timestamp() - time.time() if key == "retry-after" else -1
            except (ValueError, TypeError, OverflowError):
                continue
        if math.isfinite(delay) and delay >= 0:
            return delay
    return None


class ProviderBackoff:
    """Keep SDK/reviewer retries on the same task behind an interruptible cooldown."""

    def __init__(self):
        """Start with no failure or delay; do not impose a reasoning quota."""
        self.failures = 0
        self.not_before = 0.0
        self.lock = threading.Lock()

    def failed(self, failure, headers=None):
        """Honor provider guidance, otherwise allow a token-rate window to recover."""
        if not failure or not failure["retryable"]:
            return 0.0
        with self.lock:
            self.failures += 1
            delay = retry_after_seconds(headers)
            if delay is None:
                base = 60 if failure["category"] == "rate_limit" else 2
                delay = min(300, base * 2 ** min(self.failures - 1, 8))
                delay += random.uniform(0, delay * .1)
            self.not_before = max(self.not_before, time.monotonic() + delay)
            return delay

    def succeeded(self):
        """Reset consecutive-failure backoff after a complete model response."""
        with self.lock:
            self.failures = 0
            self.not_before = 0.0

    def remaining(self):
        """Return the remaining cooldown for transport audit records."""
        with self.lock:
            return max(0.0, self.not_before - time.monotonic())

    def wait(self, closed, deadline):
        """Wait without issuing a provider request; closing or deadline stops admission."""
        while True:
            if closed.is_set():
                raise InterruptedError("Model transport closed")
            remaining = deadline - time.monotonic()
            delay = self.remaining()
            if remaining <= 0 or delay >= remaining:
                raise TimeoutError("Episode deadline prevents another provider request")
            if delay <= 0:
                return
            closed.wait(delay)
