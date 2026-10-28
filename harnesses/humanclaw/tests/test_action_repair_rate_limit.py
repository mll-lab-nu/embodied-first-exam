"""Provider backoff preserves requests, stream failures and native retry counts."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import urllib.error

import pytest

SPEC = importlib.util.spec_from_file_location("repair_cooldown", Path(__file__).parents[1] / "tools/action_repair_rate_limit.py")
cooldown = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cooldown)
ENDPOINT = "https://example.invalid/openai/v1/responses"


def test_cooldown_shared_between_workers_and_extends_for_retry_after(tmp_path):
    now = [100.0]
    first = cooldown.Cooldown(tmp_path, clock=lambda: now[0])
    second = cooldown.Cooldown(tmp_path, clock=lambda: now[0])
    assert second.remaining() == 0
    first.limited()
    assert second.remaining() == 75
    now[0] += 10
    second.limited({"Retry-After": "120"})
    assert first.remaining() == 120
    now[0] += 121
    assert second.remaining() == 0


def test_wait_uses_shared_cooldown_and_can_be_cancelled(tmp_path):
    now = [0.0]
    gate = cooldown.Cooldown(tmp_path, clock=lambda: now[0])
    gate.limited()
    class Clock:
        def wait(self, seconds):
            now[0] += seconds
            return False
    assert gate.wait(Clock()) == 75
    gate.limited()
    with pytest.raises(RuntimeError, match="Episode closed"):
        gate.wait(SimpleNamespace(wait=lambda _: True))


def fake_service(tmp_path, *, upstream=None):
    events, calls, waits = [], [], []
    class Service:
        responder = None
        azure = True
        upstream_url = ENDPOINT
        closed = SimpleNamespace(wait=lambda _: False)
        def responses(self, handler, payload):
            calls.append(payload)
            return payload
        @staticmethod
        def _response_events(response):
            yield from response.items
    @contextmanager
    def span(*args, **kwargs):
        waits.append((args, kwargs))
        yield SimpleNamespace(set_output=lambda value: waits.append(value))
    module = SimpleNamespace(LocalServices=Service,
        urllib=SimpleNamespace(request=SimpleNamespace(urlopen=upstream or (lambda *a, **k: None))))
    recorder = SimpleNamespace(event=lambda *a, **k: events.append((a, k)), span=span)
    gate = cooldown.install({"endpoint": ENDPOINT}, tmp_path, service_module=module, recorder=recorder)
    return Service, module, gate, events, calls, waits


def test_sse_rate_limit_is_retained_and_does_not_add_retries(tmp_path):
    Service, _, gate, events, calls, _ = fake_service(tmp_path)
    failed = {"type": "response.failed", "response": {"error": {"code": "rate_limit_exceeded"}}}
    response = SimpleNamespace(geturl=lambda: ENDPOINT, headers={}, items=[failed])
    result = list(Service._response_events(response))
    assert result[0] is failed
    assert gate.remaining() > 70 and len(events) == 1 and calls == []


def test_success_and_other_provider_events_do_not_trigger_waits(tmp_path):
    Service, _, gate, events, calls, waits = fake_service(tmp_path)
    payload = {"input": [{"image_url": "unchanged"}], "reasoning": {"effort": "max"}}
    assert Service().responses(None, payload) is payload
    assert calls == [payload] and waits == []
    completed = {"type": "response.completed", "response": {"usage": {"input_tokens": 10}}}
    response = SimpleNamespace(geturl=lambda: ENDPOINT, headers={}, items=[completed])
    assert list(Service._response_events(response))[0] is completed
    response.geturl = lambda: "https://other.invalid/responses"
    response.items = [{"type": "response.failed", "response": {"error": {"code": "rate_limit_exceeded"}}}]
    list(Service._response_events(response))
    assert gate.remaining() == 0 and events == []


def test_http_429_is_raised_unchanged_without_automatic_retry(tmp_path):
    error = urllib.error.HTTPError(ENDPOINT, 429, "limited", {"retry-after-ms": "120000"}, None)
    invoked = []
    def upstream(*args, **kwargs):
        invoked.append(args)
        raise error
    _, module, gate, _, _, _ = fake_service(tmp_path, upstream=upstream)
    with pytest.raises(urllib.error.HTTPError) as captured:
        module.urllib.request.urlopen(SimpleNamespace(full_url=ENDPOINT), timeout=180)
    assert captured.value is error and len(invoked) == 1 and gate.remaining() > 115


def test_wait_is_outside_model_call_and_keeps_original_payload(tmp_path):
    Service, _, gate, _, calls, waits = fake_service(tmp_path)
    gate.limited()
    def finish_wait(closed):
        assert calls == []
        return 75
    gate.wait = finish_wait
    payload = {"input": "original", "reasoning": {"effort": "max"}}
    assert Service().responses(None, payload) is payload
    assert calls == [payload] and waits[0][0] == ("provider.rate_limit_wait",)
    assert waits[1]["additional_model_attempts"] == 0
