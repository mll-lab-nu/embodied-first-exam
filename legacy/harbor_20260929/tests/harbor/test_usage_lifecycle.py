import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from harbor.models.agent.context import AgentContext
from harbor.models.task.config import NetworkMode
import harbor_runners.agents.usage_adapter as adapter
from topogym.agents.usage.relay import UnixConnection
from harbor_runners.usage_bridge import validate_usage
from harbor_runners.endpoints import resolve_model, freeze_routes


@contextmanager
def provider(inputs):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            data=json.dumps({'usage':{'input_tokens':inputs,'output_tokens':3}}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
    thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}/v1'
    finally: server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('inputs,expected',[(5,None),(11,'budget_exceeded')])
def test_native_wrapper_lifecycle_with_real_unix_gateway(tmp_path,monkeypatch,inputs,expected):
    published, stops, uploads = [], [], []
    sockets=tmp_path/'sockets'
    sockets.mkdir()
    class Delegate:
        _version='test'
        def __init__(self,token): self.token=token
        def version(self): return self._version
        async def run(self,instruction,environment,context):
            def generate():
                connection=UnixConnection(str(next(sockets.glob('*.sock'))))
                try:
                    connection.request('POST','/v1/responses',json.dumps({'model':'fixture','input':'hello'}),
                        {'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
                    response=connection.getresponse()
                    response.read()
                    assert response.status==200
                finally: connection.close()
            await asyncio.to_thread(generate)
            if expected: await asyncio.Event().wait()
    async def root(*args,**kwargs):
        return SimpleNamespace(stdout=json.dumps({'pid':0,'port':1}),return_code=0)
    async def publish(environment,snapshot,**kwargs): published.append(snapshot)
    async def stop(environment,snapshot,**kwargs):
        stops.append(snapshot)
        return {'agent_stopped_at':1,'worker_stopped_at':1}
    async def upload(source,target): uploads.append(target)
    monkeypatch.setattr(adapter,'root_python',root)
    monkeypatch.setattr(adapter,'publish_usage',publish)
    monkeypatch.setattr(adapter,'stop_trial',stop)
    environment=SimpleNamespace(network_policy=SimpleNamespace(network_mode=NetworkMode.NO_NETWORK),upload_file=upload)
    agent=adapter.UsageAgent(connection=resolve_model('openai/fixture',version='1.18.33'),
        usage=validate_usage({'mode':'observed','limits':{'input_tokens':10,'output_tokens':100}}),
        sockets=str(sockets),logs_dir=tmp_path/'trial/agent',model_name='openai/fixture')
    agent.delegate=Delegate('setup')
    agent._new_delegate=lambda **kwargs: Delegate(kwargs['bindings']['primary']['token'])
    context=AgentContext()
    with provider(inputs) as upstream:
        agent.connection['url']=upstream
        agent.endpoints,agent.binding=freeze_routes(agent.connection)
        monkeypatch.setenv('TOPOGYM_MODEL_API_KEY','provider-key')
        asyncio.run(asyncio.wait_for(agent.run('solve',environment,context),timeout=5))
    snapshot=json.loads((tmp_path/'trial/usage/snapshot.json').read_text())
    assert snapshot['closed'] and snapshot['failure_reason']==expected
    assert snapshot['budget_qualified']==(expected is None)
    assert bool(stops)==bool(expected)
    assert published[-1]['failure_reason']==expected
    assert context.n_input_tokens==inputs and context.n_output_tokens==3
    assert uploads==['/trial/rollout/usage_events.jsonl','/trial/rollout/usage_binding.json']
    assert list(sockets.iterdir())==[]


def test_adapter_cleanup_cannot_restart_agent_after_budget_stop():
    calls=[]
    async def execute(*args,**kwargs): calls.append(kwargs)
    service=SimpleNamespace(stopped=threading.Event())
    gateway=SimpleNamespace(closing=threading.Event())
    env=adapter.RunEnvironment(SimpleNamespace(exec=execute),service,gateway)
    asyncio.run(env.exec(command='before'))
    service.stopped.set()
    with pytest.raises(RuntimeError,match='closed'):
        asyncio.run(env.exec(command='native finally command'))
    assert len(calls)==1
