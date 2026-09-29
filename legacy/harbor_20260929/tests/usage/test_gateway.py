from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import urllib.error
import urllib.request

import pytest
from topogym.agents.usage import BudgetPolicy
from topogym.agents.usage.gateway import Gateway
from topogym.agents.usage.service import UsageService


@contextmanager
def provider(payloads, *, streaming=False, status=200, hold=None):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append((self.path, dict(self.headers), data))
            self.send_response(status)
            self.send_header('Content-Type', 'text/event-stream' if streaming else 'application/json')
            self.end_headers()
            try:
                if streaming:
                    for payload in payloads:
                        raw = ('data: '+json.dumps(payload)+'\n\n').encode()
                        # HTTP transport chunks need not align with JSON or SSE.
                        self.wfile.write(raw[:11]); self.wfile.flush()
                        self.wfile.write(raw[11:]); self.wfile.flush()
                    if hold: hold.wait(2)
                else:
                    self.wfile.write(json.dumps(payloads).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:'+str(server.server_port)+'/v1', seen
    finally:
        if hold: hold.set()
        server.shutdown(); server.server_close(); thread.join()


@contextmanager
def gateway(tmp_path, upstream, *, protocol='responses', inputs=100, outputs=100, model=None):
    service = UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy(inputs, outputs), interval=.01)
    proxy = Gateway(service, protocol=protocol, upstream_url=upstream, api_key='provider-only-secret', model=model)
    try:
        yield proxy, service
    finally:
        proxy.close(); service.close()


def request(proxy, *, path='/v1/responses', body=None, token=None):
    data = json.dumps(body or {'model':'fixture','input':'hello'}).encode()
    req = urllib.request.Request(proxy.url+path, data, headers={
        'Authorization':'Bearer '+(token or proxy.token), 'Content-Type':'application/json'})
    return urllib.request.urlopen(req, timeout=5).read()


def test_streamed_usage_stops_before_connection_ends(tmp_path):
    hold = threading.Event()
    payloads = [{'type':'message_start','message':{'usage':{'input_tokens':11,'output_tokens':1}}}]
    with provider(payloads, streaming=True, hold=hold) as (url, seen), gateway(tmp_path, url,
            protocol='messages', inputs=10) as (proxy, service):
        thread = threading.Thread(target=lambda: request(proxy, path='/v1/messages', body={
            'model':'fixture','messages':[], 'stream':True,'max_tokens':10}))
        start = time.monotonic()
        thread.start()
        assert service.stopped.wait(1)
        assert time.monotonic() - start < 1
        assert not hold.is_set()  # decision did not wait for final usage/EOF
        snapshot = service.ledger.snapshot()
        assert snapshot['failure_reason'] == 'budget_exceeded'
        assert snapshot['input_tokens'] == 11
        thread.join(2)
        assert not thread.is_alive()


def test_nonstream_totals_auth_and_output_cap(tmp_path):
    payload = {'usage':{'input_tokens':7,'output_tokens':8}}
    with provider(payload) as (url, seen), gateway(tmp_path, url, outputs=10) as (proxy, service):
        request(proxy, body={'model':'fixture','input':'hello','max_output_tokens':100})
        assert seen[0][0] == '/v1/responses'
        assert seen[0][1]['Authorization'] == 'Bearer provider-only-secret'
        assert seen[0][2]['max_output_tokens'] == 10
        assert service.ledger.finalize()['budget_qualified']
        assert service.ledger.snapshot()['output_tokens'] == 8
    assert 'provider-only-secret' not in (tmp_path/'snapshot.json').read_text()
    assert 'hello' not in (tmp_path/'events.jsonl').read_text()


@pytest.mark.parametrize('dimension,payload', [
    ('input_tokens', {'usage':{'input_tokens':11,'output_tokens':1}}),
    ('output_tokens', {'usage':{'input_tokens':1,'output_tokens':11}})])
def test_receipt_overrun_closes_all_later_calls(tmp_path, dimension, payload):
    with provider(payload) as (url, seen), gateway(tmp_path, url, inputs=10, outputs=10) as (proxy, service):
        request(proxy)
        with pytest.raises(urllib.error.HTTPError) as error:
            request(proxy)
        assert error.value.code == 409 and len(seen) == 1
        assert service.ledger.snapshot()['stop']['dimensions'] == [dimension]


def test_chat_final_chunk_not_counted_as_text_estimate(tmp_path):
    payloads = [{'choices':[{'delta':{'content':'hello'}}]},
                {'choices':[], 'usage':{'prompt_tokens':2,'completion_tokens':3}}]
    with provider(payloads, streaming=True) as (url, seen), gateway(tmp_path, url,
            protocol='chat_completions') as (proxy, service):
        response = request(proxy, path='/v1/chat/completions', body={'model':'fixture','messages':[],'stream':True})
        assert b'hello' in response
        assert seen[0][2]['stream_options']['include_usage'] is True
        assert service.ledger.finalize()['output_tokens'] == 3


@pytest.mark.parametrize('case', ['missing','disconnect','provider_error','bad_endpoint','hosted_tool'])
def test_coverage_failures_never_pass(tmp_path, case):
    with provider({} if case != 'disconnect' else [], streaming=case == 'disconnect',
                  status=500 if case == 'provider_error' else 200) as (url, seen):
        with gateway(tmp_path, url) as (proxy, service):
            try:
                request(proxy, path='/v1/unknown' if case == 'bad_endpoint' else '/v1/responses',
                    body={'model':'fixture','tools':[{'type':'web_search'}]} if case == 'hosted_tool' else None)
            except urllib.error.HTTPError:
                pass
            result = service.ledger.finalize()
            assert result['stop'] and not result['budget_qualified']


def test_invalid_credential_does_not_consume_or_stop_other_trial(tmp_path):
    with provider({}) as (url, seen), gateway(tmp_path, url) as (proxy, service):
        with pytest.raises(urllib.error.HTTPError) as error:
            request(proxy, token='another-trial-token')
        assert error.value.code == 401 and seen == []
        assert service.ledger.snapshot()['stop'] is None


def test_unexpected_auxiliary_model_rejected_before_upstream_and_admission(tmp_path):
    with provider({}) as (url, seen), gateway(tmp_path, url, model='selected-model') as (proxy, service):
        with pytest.raises(urllib.error.HTTPError) as error:
            request(proxy,body={'model':'surprise-title-model','input':'hello'})
        assert error.value.code == 400
        assert b'frozen trial model' in error.value.read()
        assert seen == [] and service.ledger.snapshot()['request_count'] == 0
        assert service.stopped.is_set() and not service.ledger.finalize()['budget_qualified']


@pytest.mark.parametrize('protocol,path,body,payload,cap_field', [
    ('chat_completions','/v1/chat/completions',
     {'model':'nested/model','messages':[{'role':'user','content':[
         {'type':'text','text':'look'},{'type':'image_url','image_url':{'url':'data:image/png;base64,ZmFrZQ=='}}]}],
      'tools':[{'type':'function','function':{'name':'move','parameters':{'type':'object'}}}]},
     {'usage':{'prompt_tokens':7,'completion_tokens':2}},'max_tokens'),
    ('messages','/v1/messages',
     {'model':'nested/model','messages':[{'role':'user','content':[
         {'type':'image','source':{'type':'base64','media_type':'image/png','data':'ZmFrZQ=='}},
         {'type':'text','text':'look'}]}],
      'tools':[{'name':'move','input_schema':{'type':'object'}}]},
     {'usage':{'input_tokens':7,'output_tokens':2}},'max_tokens'),
    ('responses','/v1/responses',
     {'model':'nested/model','input':[{'role':'user','content':[
         {'type':'input_text','text':'look'},{'type':'input_image','image_url':'data:image/png;base64,ZmFrZQ=='}]}],
      'tools':[{'type':'function','name':'move','parameters':{'type':'object'}}]},
     {'usage':{'input_tokens':7,'output_tokens':2}},'max_output_tokens'),
])
def test_three_protocols_keep_tools_images_model_and_provider_auth(tmp_path,protocol,path,body,payload,cap_field):
    with provider(payload) as (url, seen), gateway(tmp_path,url,protocol=protocol,outputs=10,
                                                model='nested/model') as (proxy,service):
        request(proxy,path=path,body=body)
        sent_path,headers,sent_body=seen[0]
        assert sent_path==path and sent_body['model']=='nested/model'
        assert sent_body['tools']==body['tools']
        content_key='input' if protocol=='responses' else 'messages'
        assert sent_body[content_key]==body[content_key] and sent_body[cap_field]==10
        if protocol=='messages':
            assert headers['x-api-key']=='provider-only-secret'
        else:
            assert headers['Authorization']=='Bearer provider-only-secret'
        assert 'provider-only-secret' not in json.dumps(service.ledger.snapshot())
        result=service.ledger.finalize()
        assert result['budget_qualified'] and result['input_tokens']==7 and result['output_tokens']==2


def test_manager_update_is_seen_without_agent_stdout(tmp_path):
    from topogym.agents.usage import UsageLedger, UsageEvent
    service = UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy(), interval=.01)
    try:
        service.ledger.admit('r', source='test')
        service.ledger.mark_sent('r')
        service.record(UsageEvent('r','e',0,'test',10,5,final=True))
        other = UsageLedger(tmp_path/'ledger.sqlite')
        other.update_limits(input_tokens=9, output_tokens=5, expected_revision=1, actor='test', reason='hot-update')
        assert service.stopped.wait(.5)
    finally:
        service.close()


def test_compaction_is_counted_without_injecting_unsupported_output_cap(tmp_path):
    payload = {'object':'response.compaction','usage':{'input_tokens':12,'output_tokens':4}}
    with provider(payload) as (url, seen), gateway(tmp_path, url) as (proxy, service):
        request(proxy,path='/v1/responses/compact')
        assert seen[0][0] == '/v1/responses/compact'
        assert 'max_output_tokens' not in seen[0][2]
        snapshot=service.ledger.finalize()
        assert snapshot['usage']=={'input_tokens':12,'output_tokens':4}
        assert snapshot['by_model']['fixture']['input_tokens']==12


def test_cancellation_interrupts_response_owned_socket(tmp_path):
    hold=threading.Event()
    payloads=[{'type':'message_start','message':{'usage':{'input_tokens':1,'output_tokens':1}}}]
    with provider(payloads,streaming=True,hold=hold) as (url,seen), gateway(tmp_path,url,
            protocol='messages') as (proxy,service):
        errors=[]
        def generate():
            try: request(proxy,path='/v1/messages',body={'model':'fixture','messages':[],'stream':True})
            except Exception as error: errors.append(type(error).__name__)
        thread=threading.Thread(target=generate)
        thread.start()
        deadline=time.monotonic()+1
        while service.ledger.snapshot()['input_tokens']!=1 and time.monotonic()<deadline: time.sleep(.01)
        assert service.ledger.snapshot()['input_tokens']==1
        start=time.monotonic()
        proxy.cancel()
        thread.join(1)
        assert not thread.is_alive() and time.monotonic()-start<1
        assert service.stopped.wait(.5)
        assert not service.ledger.snapshot()['usage_complete']
        hold.set()
