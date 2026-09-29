"""Exercise the shared core through independent local providers and harnesses."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from topogym.agents.usage import UsageEvent, UsagePipeline, UsageLedger


@contextmanager
def provider(protocol, inputs=3, outputs=2, hold=None, started=None):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append((self.path, body))
            if started: started.set()
            if hold: hold.wait(3)
            if protocol == 'chat_completions':
                usage = dict(prompt_tokens=inputs, completion_tokens=outputs)
            else:
                usage = dict(input_tokens=inputs, output_tokens=outputs)
            data = json.dumps(dict(usage=usage)).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers(); self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
    thread.start()
    try: yield dict(url=f'http://127.0.0.1:{server.server_port}/v1',protocol=protocol), seen
    finally:
        if hold: hold.set()
        server.shutdown(); server.server_close(); thread.join()


def settings(inputs=100, outputs=100, interval=10):
    return dict(mode='observed',limits=dict(input_tokens=inputs,output_tokens=outputs),watchdog_interval_ms=interval)


def request(binding, path='/v1/responses', cap=2):
    req=urllib.request.Request(binding['url']+path, json.dumps(dict(model='fixture',
        input='hello', max_output_tokens=cap, max_tokens=cap)).encode(),headers={
        'Content-Type':'application/json','Authorization':'Bearer '+binding['token']})
    with urllib.request.urlopen(req,timeout=3) as response: return response.read()


def test_two_protocols_and_concurrent_routes_share_counts_and_keep_identity(tmp_path):
    with provider('responses') as (main,_), provider('chat_completions',inputs=4,outputs=1) as (helper,_):
        pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings())
        try:
            bindings=pipeline.start(dict(main=main,helper=helper),lambda route:'private-provider-key')
            with ThreadPoolExecutor(2) as executor:
                futures=[executor.submit(request,bindings['main']),
                         executor.submit(request,bindings['helper'],'/v1/chat/completions')]
                for future in futures: future.result(3)
            snapshot=pipeline.finalize()
            assert snapshot['input_tokens']==7 and snapshot['output_tokens']==3
            assert snapshot['request_count']==2 and snapshot['budget_qualified']
            assert snapshot['by_route']=={'main':dict(input_tokens=3,output_tokens=2),
                                          'helper':dict(input_tokens=4,output_tokens=1)}
        finally: pipeline.close()
        assert pipeline.close()==pipeline.ledger.snapshot()


def test_reserved_budget_is_shared_before_second_route_reaches_provider(tmp_path):
    hold,started=threading.Event(),threading.Event()
    with provider('responses',hold=hold,started=started) as (main,_), provider('responses') as (helper,seen):
        pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings(outputs=5))
        try:
            bindings=pipeline.start(dict(main=main,helper=helper),lambda route:'test-key')
            with ThreadPoolExecutor(1) as executor:
                future=executor.submit(request,bindings['main'],'/v1/responses',5)
                assert started.wait(1)
                with pytest.raises(urllib.error.HTTPError) as error:
                    request(bindings['helper'])
                assert error.value.code==429 and not seen
                assert not pipeline.stopped.is_set()
                hold.set(); future.result(3)
            request(bindings['helper'])
            assert pipeline.finalize()['output_tokens']==4
        finally:
            hold.set(); pipeline.close()


def test_failure_cancels_other_inflight_route_without_waiting_for_its_response(tmp_path):
    hold,started=threading.Event(),threading.Event()
    with provider('responses',hold=hold,started=started) as (blocked,_), provider('responses',inputs=11) as (over,_):
        pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings(inputs=10,interval=1000))
        try:
            bindings=pipeline.start(dict(blocked=blocked,over=over),lambda route:'test-key')
            def call_blocked():
                try: request(bindings['blocked'])
                except (OSError, urllib.error.URLError): pass
            with ThreadPoolExecutor(1) as executor:
                future=executor.submit(call_blocked)
                assert started.wait(1)
                notification=threading.Event()
                pipeline.service.subscribe_stop(notification.set)
                request(bindings['over'])
                assert notification.wait(.5)  # event notification, not 1s watchdog
                assert all(g.closing.is_set() for g in pipeline.gateways.values())
                future.result(1)
                assert not hold.is_set()
            with pytest.raises(urllib.error.HTTPError) as error: request(bindings['over'])
            assert error.value.code==409
            assert pipeline.finalize()['failure_reason']=='budget_exceeded'
        finally:
            hold.set(); pipeline.close()


def test_hot_update_from_separate_ledger_stops_all_routes(tmp_path):
    with provider('responses',inputs=6) as (route,_):
        pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings())
        try:
            binding=pipeline.start({'one':route,'two':route},lambda route:'test-key')
            request(binding['one'])
            manager=UsageLedger(tmp_path/'ledger.sqlite')
            manager.update_limits(input_tokens=5,output_tokens=100,expected_revision=1,actor='test',reason='reduce')
            assert pipeline.stopped.wait(1)
            assert pipeline.closing.is_set()
            manager.update_limits(input_tokens=100,output_tokens=100,expected_revision=2,actor='test',reason='increase')
            assert not pipeline.finalize()['budget_qualified']
        finally: pipeline.close()


def test_protocol_client_is_a_real_subprocess_using_only_trial_credentials(tmp_path):
    with provider('chat_completions') as (route,seen):
        pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings())
        try:
            bindings=pipeline.start({'primary':route},lambda route:'provider-only-key')
            env={"MODEL_URL":bindings["primary"]["url"]+"/v1","MODEL_KEY":bindings["primary"]["token"]}
            result=subprocess.run([sys.executable,'-c',"""import json,os,urllib.request
req=urllib.request.Request(os.environ['MODEL_URL']+'/chat/completions',
 json.dumps({'model':'fixture','messages':[],'max_tokens':2}).encode(),
 headers={'Authorization':'Bearer '+os.environ['MODEL_KEY'],'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=3) as response: assert response.status==200
"""],env=env,text=True,capture_output=True,timeout=5)
            assert result.returncode==0,result.stderr
            assert seen[0][0]=='/v1/chat/completions'
            assert pipeline.finalize()['input_tokens']==3
        finally: pipeline.close()


def test_event_source_test_double_does_not_need_an_http_listener(tmp_path):
    class Route:
        token='test-double'; url=None; socket_path=None
        thread=SimpleNamespace(is_alive=lambda:True)
        def cancel(self): pass
        def close(self): pass
    class Source:
        def create(self,service,route_id,route,credential):
            self.service=service
            return Route()
    source=Source()
    pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings(inputs=1),source=source)
    try:
        pipeline.start({'test':{}},lambda route:None)
        pipeline.ledger.admit('request',source='callback-test',route_id='test')
        pipeline.ledger.mark_sent('request')
        source.service.record(UsageEvent('request','final',0,'callback-test',2,1,final=True))
        assert pipeline.stopped.is_set()
        assert pipeline.finalize()['failure_reason']=='budget_exceeded'
    finally: pipeline.close()


def test_route_start_failure_closes_already_open_routes(tmp_path):
    with provider('responses') as (good,_):
        pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings())
        try:
            with pytest.raises(ValueError):
                pipeline.start({'good':good,'bad':dict(url='http://remote.invalid/v1',protocol='responses')},lambda r:'key')
            assert pipeline.stopped.is_set() and pipeline.gateways['good'].closing.is_set()
            assert pipeline.ledger.snapshot()['failure_reason']=='gateway_failed'
        finally: pipeline.close()


def test_lost_gateway_health_stops_whole_trial(tmp_path):
    with provider('responses') as (route,_):
        pipeline=UsagePipeline(tmp_path,scope_id='trial',settings=settings())
        try:
            pipeline.start({'a':route,'b':route},lambda r:'key')
            pipeline.gateways['a'].server.shutdown()
            assert pipeline.stopped.wait(1)
            assert pipeline.gateways['b'].closing.is_set()
            assert pipeline.ledger.snapshot()['failure_reason']=='gateway_failed'
        finally: pipeline.close()
