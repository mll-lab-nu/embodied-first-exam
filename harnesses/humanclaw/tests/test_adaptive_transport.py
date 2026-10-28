import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.request

from PIL import Image
import pytest

from humanclaw_bench.experiments.recorder import TraceRecorder
from humanclaw_bench.experiments.report import summarize_run, validate_trace
from humanclaw_bench.harnesses.adaptive.broker import digest
from humanclaw_bench.harnesses.adaptive.bindings import HumanClawBinding
from humanclaw_bench.harnesses.adaptive.service import AdaptiveService, AdaptiveInfrastructureError
from humanclaw_bench.harnesses.adaptive.smoke import stream_response
from humanclaw_bench.harnesses.adaptive.state import DEFAULT_POLICY
from humanclaw_bench.harnesses.environment import EnvironmentBridge
from humanclaw_bench.harnesses.pi_adaptive import resolve_profile
from humanclaw_bench.harnesses.provider_errors import ProviderBackoff, provider_failure, retry_after_seconds
from humanclaw_bench.harnesses.runtime import NativeHarness, load_harness_config
from humanclaw_bench.harnesses.services import LocalServices

ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_harness_config(ROOT / "configs/harnesses/pi_adaptive.json")


def make_service(path):
    bridge = EnvironmentBridge(Image.new("RGB", (8, 8)), 3, lambda *_: None, "Inspect public evidence")
    return AdaptiveService(bridge, path, time.monotonic()+30)


def candidate(service):
    return service.lifecycle.propose({"protocol": "feedback-policy-v1", "implementation": DEFAULT_POLICY,
        "parent": None, "diagnosis": "Revise action after public feedback", "evidence": ["observation:0"]})["candidate_id"]


def failure_stream(payload, *, filtered=False):
    result = {"id": "failed", "object": "response", "model": payload["model"], "created_at": 0, "output": []}
    if filtered:
        result.update(status="incomplete", incomplete_details={"reason": "content_filter"})
    else:
        result.update(status="failed", error={"code": "rate_limit_exceeded", "message": "Token rate limit exceeded"})
    return [{"type": "response.created", "response": {**result, "status": "in_progress"}},
            {"type": "response.incomplete" if filtered else "response.failed", "response": result}]


def test_review_bypasses_proxy_but_upstream_keeps_proxy_and_candidate_activates(tmp_path, monkeypatch):
    seen = []
    class Proxy(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append(self.path)
            if self.path != 'http://provider.invalid/responses':
                self.send_response(503); self.end_headers(); return
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            for event in stream_response(payload, 1, text=json.dumps({'status':'pass', 'reason':'Fixed contract and evidence checked'})):
                self.wfile.write(b'data: '+json.dumps(event).encode()+b'\n\n')
        def log_message(self, *_): pass
    proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True); thread.start()
    for key in ('http_proxy', 'HTTP_PROXY'):
        monkeypatch.setenv(key, f'http://127.0.0.1:{proxy.server_port}')
    for key in ('no_proxy', 'NO_PROXY'): monkeypatch.setenv(key, '')
    # Rebuild the inherited global opener exactly as a new server worker would.
    monkeypatch.setattr(urllib.request, '_opener', None)
    try:
        with TraceRecorder(tmp_path/'trace', {}) as recorder:
            service = make_service(tmp_path/'adaptive')
            with LocalServices(service, upstream_url='http://provider.invalid/responses', api_key='test-only',
                    model_options={'model':'gpt-6-astra'}, pi_profile=resolve_profile(CONFIG), deadline=service.deadline) as transport:
                service.connect_reviewer(transport)
                ident = candidate(service)
                assert service.lifecycle.validate(ident)['report']['status'] == 'pass'
                assert service.lifecycle.activate(ident)['active']['feedback-policy-v1'] == ident
                assert transport.calls == 1
        assert seen == ['http://provider.invalid/responses']
        assert summarize_run(recorder.directory)['model_usage']['leaf_model_calls'] == 1
        assert validate_trace(recorder.directory)['ok']
    finally:
        proxy.shutdown(); proxy.server_close(); thread.join()


@pytest.mark.parametrize('filtered', [False, True])
def test_review_stream_errors_recover_only_transient_failures(tmp_path, monkeypatch, filtered):
    original = ProviderBackoff.failed
    monkeypatch.setattr(ProviderBackoff, 'failed', lambda self,f,headers=None: original(self,f,{'Retry-After':'0'}))
    requests = []
    def responder(payload, index):
        requests.append(payload)
        if index == 1: yield from failure_stream(payload, filtered=filtered)
        else: yield from stream_response(payload, index, text=json.dumps({'status':'pass','reason':'checked'}))
    service = make_service(tmp_path/'adaptive')
    with TraceRecorder(tmp_path/'trace', {}) as recorder:
        with LocalServices(service, responder=responder, model_options={'model':'gpt-6-astra'},
                pi_profile=resolve_profile(CONFIG), deadline=service.deadline) as transport:
            service.connect_reviewer(transport); ident = candidate(service)
            result = service.lifecycle.validate(ident)
            if filtered:
                assert result['report']['status'] == 'inconclusive'
                assert result['report']['review']['infrastructure_error']['category'] == 'content_filter'
                assert not result['release']['local_eligible'] and ident not in service.lifecycle.health
            else:
                assert result['report']['status'] == 'pass'
                service.lifecycle.activate(ident)
                assert requests[0] == requests[1]
            assert transport.calls == (1 if filtered else 2)
    summary = summarize_run(recorder.directory)
    assert summary['model_usage']['status_counts']['failed'] == 1
    assert validate_trace(recorder.directory)['ok']


def test_backoff_honors_headers_window_deadline_and_close(monkeypatch):
    import humanclaw_bench.harnesses.provider_errors as errors
    now = [100.0]
    monkeypatch.setattr(errors.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(errors.random, 'uniform', lambda *_: 0)
    backoff = ProviderBackoff(); failure = provider_failure(error={'code':'rate_limit_exceeded'})
    assert backoff.failed(failure) == 60
    now[0] += 60
    assert backoff.failed(failure) == 120
    assert backoff.failed(failure, {'retry-after-ms':'150000'}) == 150
    assert backoff.remaining() == 150
    with pytest.raises(TimeoutError): backoff.wait(threading.Event(), now[0]+100)
    closed = threading.Event(); closed.set()
    with pytest.raises(InterruptedError): backoff.wait(closed, now[0]+200)
    backoff.succeeded()
    assert backoff.remaining() == 0 and backoff.failures == 0
    assert backoff.failed(provider_failure(incomplete={'reason':'content_filter'})) == 0
    assert retry_after_seconds({'Retry-After':'nan'}) is None
    assert retry_after_seconds({'retry-after':'3.5'}) == 3.5


def test_review_transport_failure_stops_task_without_quarantining_candidate(tmp_path):
    service = make_service(tmp_path/'adaptive')
    service.lifecycle.review = lambda *_:{'status':'inconclusive','reason':'gateway unavailable',
        'infrastructure_error':{'category':'review_transport','retryable':False}}
    ident = candidate(service)
    with pytest.raises(AdaptiveInfrastructureError,match='Independent review unavailable'):
        service.call('validate', {'candidate_id':ident})
    assert service.lifecycle.reports[ident]['report']['status'] == 'inconclusive'
    assert ident not in service.lifecycle.health and service.broker.settled
    assert service.broker.db.execute("SELECT COUNT(*) FROM events WHERE kind='infrastructure.failed'").fetchone()[0] == 1
    service.close()


def test_real_sdk_retries_same_decision_without_replaying_physical_action(tmp_path, monkeypatch):
    original = ProviderBackoff.failed
    monkeypatch.setattr(ProviderBackoff, 'failed', lambda self,f,headers=None: original(self,f,{'Retry-After':'0'}))
    executed, requests = [], []
    def execute(index, decision):
        executed.append(decision.action.skill)
        return Image.new('RGB',(8,8)), decision.action.skill == 'stand'
    bridge = EnvironmentBridge(Image.new('RGB',(8,8)), 3, execute, 'Walk once and stop')
    catalog = {t['id']:t for t in HumanClawBinding(bridge).catalog()}
    def action(name, index):
        return ('execute', {'request_id':f'r{index}', 'tool':name, 'tool_version':catalog[name]['version'],
            'arguments':{'request_id':f'r{index}', 'observation_id':index, 'action_name':'Stop/Stand' if index else 'Walk<forward><slow>', 'visible_state':'public image'},
            'decision':{'intent':'check', 'expected_outcome':'next image', 'evidence':[f'observation:{index}'], 'policy_version':digest(DEFAULT_POLICY),'completion':'unknown'}})
    def responder(payload, index):
        requests.append(payload)
        if index == 2: yield from failure_stream(payload)
        else: yield from stream_response(payload,index,action('humanclaw.walk_forward',0) if index==1 else action('humanclaw.stand',1) if index==3 else None)
    with TraceRecorder(tmp_path/'trace', {}) as recorder:
        result = NativeHarness('pi', CONFIG, {'model':'gpt-6-astra'}).run(bridge,tmp_path,responder=responder)
    assert executed == ['walk_forward','stand'] and result['model_requests'] == 4
    assert requests[1] == requests[2]
    assert summarize_run(recorder.directory)['model_usage']['status_counts'] == {'completed':3,'failed':1}
