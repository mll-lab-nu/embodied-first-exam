"""Offline compatibility tests: synthetic keys, no paid provider calls."""
import asyncio
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import urllib.request

ROOT=Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from harbor_agents.muse_transport.bridge import Bridge
from harbor_agents.muse_transport.launch import launch, VERSION, IMPORT_PATH
import agent_batch_host as host

MODEL='meta/muse-spark-1.3-contributor'
KEY='synthetic-openrouter-test-key'


class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({'data':[{'id':MODEL,'context_length':262144,
                        'top_provider':{'max_completion_tokens':16384}}]}).encode())
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(data)
        self.server.authorizations.append(self.headers.get('Authorization'))
        if self.server.failure:
            self.send_response(self.server.failure); self.end_headers()
            self.wfile.write(json.dumps({'error':{'message':'Unsupported request field; credential='+KEY,
                'metadata':{'raw':json.dumps({'error':{'message':'Nested provider rejection '+KEY}})}}}).encode()); return
        index=len(self.server.requests); rid=f'resp_{index}'
        message=dict(id=f'msg_{index}',type='message',status='completed',role='assistant',
                     content=[dict(type='output_text',text='OK',annotations=[])])
        response=dict(id=rid,object='response',created_at=1791244800,status='completed',model=MODEL,
                      output=[message],usage=dict(input_tokens=17,output_tokens=2,input_tokens_details=dict(cached_tokens=3)))
        events=[dict(type='response.created',response=dict(response,status='in_progress',output=[],usage=None)),
                dict(type='response.output_item.added',output_index=0,item=dict(message,status='in_progress',content=[])),
                dict(type='response.content_part.added',item_id=message['id'],output_index=0,content_index=0,
                     part=dict(type='output_text',text='',annotations=[])),
                dict(type='response.output_text.delta',item_id=message['id'],output_index=0,content_index=0,delta='OK'),
                dict(type='response.output_text.done',item_id=message['id'],output_index=0,content_index=0,text='OK'),
                dict(type='response.content_part.done',item_id=message['id'],output_index=0,content_index=0,part=message['content'][0]),
                dict(type='response.output_item.done',output_index=0,item=message),dict(type='response.completed',response=response)]
        if self.server.tool_file and index==1:
            call=dict(type='function_call',id='fc_test_1',call_id='call_test_1',name='write_file',
                      namespace='muse',arguments=json.dumps({'path':str(self.server.tool_file),'content':'offline-tool-ok'}),status='completed')
            response['output']=[call]
            events=[dict(type='response.created',response=dict(response,status='in_progress',output=[],usage=None)),
                    dict(type='response.output_item.added',output_index=0,item=dict(call,arguments='',status='in_progress')),
                    dict(type='response.function_call_arguments.delta',item_id=call['id'],output_index=0,delta=call['arguments']),
                    dict(type='response.function_call_arguments.done',item_id=call['id'],output_index=0,arguments=call['arguments']),
                    dict(type='response.output_item.done',output_index=0,item=call),dict(type='response.completed',response=response)]
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
        for event in events:
            self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode()); self.wfile.flush()


@contextlib.contextmanager
def upstream(failure=0):
    server=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    server.requests=[]; server.authorizations=[]; server.failure=failure; server.tool_file=None
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield server, f'http://127.0.0.1:{server.server_port}/api/v1'
    finally: server.shutdown(); server.server_close(); thread.join()


class HostTests(unittest.TestCase):
    def test_missing_docker_precedes_installation(self):
        import agent_batch_bootstrap as bootstrap
        with tempfile.TemporaryDirectory() as td,patch.object(host.platform,'system',return_value='Linux'), \
             patch.object(host.shutil,'which',return_value=None),patch.object(bootstrap,'run') as run:
            with self.assertRaisesRegex(ValueError,'Docker CLI not found'): bootstrap.bootstrap(td)
            run.assert_not_called(); self.assertEqual(list(Path(td).iterdir()),[])

    def test_wsl_help_and_daemon_compose_errors(self):
        with patch.object(host.platform,'system',return_value='Linux'),patch.object(host.platform,'release',return_value='microsoft-standard-WSL2'), \
             patch.object(host.shutil,'which',return_value=None):
            with self.assertRaisesRegex(ValueError,'WSL Integration'): host.require_docker()
        result=lambda rc,out: subprocess.CompletedProcess([],rc,out,'private stderr not shown')
        for answers, error in [([result(1,'')],'daemon'),([result(0,'windows')],'Linux containers'),
                               ([result(0,'linux'),result(1,'')],'Compose v2'),
                               ([result(0,'linux'),result(0,'1.29.2')],'Compose v2')]:
            with patch.object(host.shutil,'which',return_value='/usr/bin/docker'),patch.object(host.subprocess,'run',side_effect=answers):
                with self.assertRaisesRegex(ValueError,error): host.require_docker()
        with patch.object(host.shutil,'which',return_value='/usr/bin/docker'), \
             patch.object(host.subprocess,'run',side_effect=[result(0,'linux'),result(0,'2.39.1')]): host.require_docker()


class BridgeTests(unittest.TestCase):
    def test_canary_uses_isolated_container_and_no_key_arguments(self):
        import check_agent_batch_auth as auth
        from types import SimpleNamespace
        plan=dict(agent=dict(name='muse-openrouter',model='openrouter/'+MODEL,kwargs={'version':VERSION}),
                  tasks=[dict(runtime_binding={'image':{'reference':'fixture:image'}})],plan_sha256='a'*64)
        calls=[]
        def popen(argv,**kwargs):
            calls.append(argv)
            mount=next(a for a in argv if a.endswith(':/canary:rw'))
            work=Path(mount.removesuffix(':/canary:rw'));(work/'logs').mkdir()
            (work/'logs/openrouter-usage.json').write_text('{"complete":true}')
            return SimpleNamespace(returncode=0,wait=lambda **kw:0,poll=lambda:0)
        with tempfile.TemporaryDirectory() as td,patch('harbor_agents.muse_transport.launch.ensure_binary'),patch.object(auth,'locked',return_value=contextlib.nullcontext()), \
             patch.object(auth.subprocess,'Popen',side_effect=popen),patch.object(auth.subprocess,'run') as cleanup:
            report=auth.canary(plan,{'OPENROUTER_API_KEY':KEY},diagnostics_dir=Path(td)/'diagnostics')
            self.assertTrue((Path(report['diagnostics'])/'summary.json').is_file())
        self.assertTrue(report['passed'])
        self.assertEqual(calls[0][:2],['docker','run'])
        self.assertIn('--read-only',calls[0]);self.assertIn('fixture:image',calls[0])
        self.assertNotIn(KEY,' '.join(calls[0]));cleanup.assert_called_once()

    def test_catalog_sse_usage_and_fixed_model(self):
        with tempfile.TemporaryDirectory() as td,upstream() as (server,url):
            bridge=Bridge(KEY,MODEL,td,upstream=url)
            thread=threading.Thread(target=bridge.serve_forever,daemon=True); thread.start()
            base=f'http://127.0.0.1:{bridge.server_port}'
            try:
                catalog=json.load(urllib.request.urlopen(base+'/muse-code/models'))
                self.assertEqual(catalog['data'][0]['model_id'],MODEL)
                long_name='muse_tool_'+'x'*80
                body={'model':MODEL,'stream':True,'max_output_tokens':999999,'input':[],
                      'tools':[{'type':'function','name':long_name,'parameters':{'type':'object'}}]}
                data=urllib.request.urlopen(urllib.request.Request(base+'/responses',data=json.dumps(body).encode())).read().decode()
                self.assertIn('sequence_number',data)
                self.assertEqual(server.authorizations,['Bearer '+KEY])
                self.assertEqual(server.requests[0]['max_output_tokens'],16384)
                self.assertLessEqual(len(server.requests[0]['tools'][0]['name']),64)
                report=json.loads((Path(td)/'openrouter-usage.json').read_text())
                self.assertTrue(report['complete']); self.assertEqual(report['totals']['input_tokens'],17)
                body['model']='meta/other'
                with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(urllib.request.Request(base+'/responses',data=json.dumps(body).encode()))
                self.assertEqual(len(server.requests),1)
                self.assertNotIn(KEY,(Path(td)/'openrouter-usage.json').read_text())
            finally: bridge.shutdown(); bridge.server_close(); thread.join()

    def test_provider_failure_is_sanitized_and_not_complete(self):
        with tempfile.TemporaryDirectory() as td,upstream(402) as (_,url):
            bridge=Bridge(KEY,MODEL,td,upstream=url); thread=threading.Thread(target=bridge.serve_forever,daemon=True); thread.start()
            try:
                request=urllib.request.Request(f'http://127.0.0.1:{bridge.server_port}/responses',data=json.dumps({'model':MODEL}).encode())
                with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request)
                self.assertNotIn(KEY,error.exception.read().decode())
                report=json.loads((Path(td)/'openrouter-usage.json').read_text())
                self.assertFalse(report['complete']); self.assertIn('http_402',report['errors'])
                self.assertIn('Unsupported request field',report['error_details'][0]['message'])
                self.assertNotIn(KEY,json.dumps(report))
            finally: bridge.shutdown(); bridge.server_close(); thread.join()

    def test_http_400_and_transport_details_are_retained_without_key(self):
        with tempfile.TemporaryDirectory() as td,upstream(400) as (_,url):
            bridge=Bridge(KEY,MODEL,td,upstream=url);thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
            try:
                request=urllib.request.Request(f'http://127.0.0.1:{bridge.server_port}/responses',data=json.dumps({'model':MODEL}).encode())
                with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request)
                body=error.exception.read().decode();self.assertIn('Unsupported request field',body);self.assertNotIn(KEY,body)
                self.assertIn('Nested provider rejection',body)
                report=json.loads((Path(td)/'openrouter-usage.json').read_text())
                self.assertIn('http_400',report['errors']);self.assertNotIn(KEY,json.dumps(report))
                bridge.fail('transport_or_protocol_error','SSLError: test certificate failure '+KEY)
                report=json.loads((Path(td)/'openrouter-usage.json').read_text())
                self.assertIn('SSLError',report['error_details'][-1]['message']);self.assertNotIn(KEY,json.dumps(report))
            finally: bridge.shutdown();bridge.server_close();thread.join()

    def test_canary_retains_docker_and_muse_failures_after_cleanup(self):
        import check_agent_batch_auth as auth
        from types import SimpleNamespace
        plan=dict(agent=dict(name='muse-openrouter',model='openrouter/'+MODEL,kwargs={'version':VERSION}),
                  tasks=[dict(runtime_binding={'image':{'reference':'fixture:image'}})],plan_sha256='a'*64)
        for code,report,wanted in [(125,None,'docker_startup'),(126,None,'container_command'),
                                  (1,{'complete':False,'requests':0,'errors':[]},'muse_startup'),
                                  (2,{'complete':False,'requests':1,'errors':['http_400'],
                                      'error_details':[{'code':'http_400','message':'unsupported field '+KEY}]},'provider_or_transport')]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as td:
                originals=[]
                def popen(argv,**kwargs):
                    work=Path(next(a for a in argv if a.endswith(':/canary:rw')).removesuffix(':/canary:rw'));originals.append(work)
                    kwargs['stdout'].write(('container diagnostic '+KEY+'\n').encode())
                    (work/'logs').mkdir();(work/'logs/muse-code.stderr.log').write_text('Muse diagnostic '+KEY)
                    (work/'logs/muse-code.jsonl').write_text(json.dumps({'type':'error','message':'native error '+KEY})+'\n')
                    if report is not None: (work/'logs/openrouter-usage.json').write_text(json.dumps(report))
                    return SimpleNamespace(returncode=code,wait=lambda **kw:code,poll=lambda:code)
                diagnostics=Path(td)/'diagnostics';console=io.StringIO()
                with patch('harbor_agents.muse_transport.launch.ensure_binary'),patch.object(auth,'locked',return_value=contextlib.nullcontext()), \
                     patch.object(auth.subprocess,'Popen',side_effect=popen),patch.object(auth.subprocess,'run'),contextlib.redirect_stdout(console):
                    with self.assertRaises(ValueError) as error: auth.canary(plan,{'OPENROUTER_API_KEY':KEY},diagnostics_dir=diagnostics)
                self.assertIn(wanted,str(error.exception));self.assertIn('container diagnostic',str(error.exception))
                self.assertNotIn(KEY,str(error.exception));self.assertNotIn(KEY,console.getvalue())
                self.assertTrue(all(not p.exists() for p in originals))
                summary=next(diagnostics.glob('*/summary.json'));self.assertEqual(json.loads(summary.read_text())['stage'],wanted)
                self.assertEqual(summary.stat().st_mode & 0o777,0o600)
                self.assertEqual(summary.parent.stat().st_mode & 0o777,0o700)
                for p in diagnostics.rglob('*'):
                    if p.is_file(): self.assertNotIn(KEY,p.read_text())

    def test_canary_timeout_and_docker_launch_exception_keep_diagnostics(self):
        import check_agent_batch_auth as auth
        from types import SimpleNamespace
        plan=dict(agent=dict(name='muse-openrouter',model='openrouter/'+MODEL,kwargs={'version':VERSION}),
                  tasks=[dict(runtime_binding={'image':{'reference':'fixture:image'}})],plan_sha256='a'*64)
        for timeout in (True,False):
            with self.subTest(timeout=timeout),tempfile.TemporaryDirectory() as td:
                def popen(argv,**kwargs):
                    if not timeout: raise PermissionError('docker access denied '+KEY)
                    child=SimpleNamespace(returncode=None,pid=12345,poll=lambda:child.returncode)
                    def wait(**kw):
                        if kw.get('timeout')==120: raise subprocess.TimeoutExpired(argv,120)
                        child.returncode=-15;return -15
                    child.wait=wait;return child
                with patch('harbor_agents.muse_transport.launch.ensure_binary'),patch.object(auth,'locked',return_value=contextlib.nullcontext()), \
                     patch.object(auth.subprocess,'Popen',side_effect=popen),patch.object(auth.subprocess,'run'),patch.object(auth.os,'killpg'):
                    with self.assertRaises(ValueError) as error: auth.canary(plan,{'OPENROUTER_API_KEY':KEY},diagnostics_dir=Path(td))
                self.assertIn('timed out' if timeout else 'docker access denied',str(error.exception));self.assertNotIn(KEY,str(error.exception))
                summary=json.loads(next(Path(td).glob('*/summary.json')).read_text())
                self.assertFalse(summary['passed']);self.assertEqual(summary['stage'],'container_check')

    def test_diagnostics_skip_symlinks_and_preserve_each_attempt(self):
        import check_agent_batch_auth as auth
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=root/'work';work.mkdir();(work/'logs').mkdir()
            outside=root/'outside';outside.write_text('must not copy this file')
            (work/'logs/muse-code.stderr.log').symlink_to(outside)
            (work/'docker.log').write_text('test error '+KEY)
            plan={'agent':{'model':'openrouter/'+MODEL}}
            first=auth.retain_muse_diagnostics(work,root/'out',plan,{'OPENROUTER_API_KEY':KEY},1,None)
            second=auth.retain_muse_diagnostics(work,root/'out',plan,{'OPENROUTER_API_KEY':KEY},1,None)
            self.assertNotEqual(first['diagnostics'],second['diagnostics'])
            self.assertTrue(first['notes']);self.assertFalse((Path(first['diagnostics'])/'muse-code.stderr.log').exists())

    def test_native_harbor_adapter_identity_and_usage(self):
        from harbor.agents.factory import AgentFactory
        from harbor.models.trial.config import AgentConfig
        from harbor.models.agent.context import AgentContext
        with tempfile.TemporaryDirectory() as td:
            cfg=AgentConfig(name=IMPORT_PATH,model_name='openrouter/'+MODEL,kwargs={'version':VERSION})
            agent=AgentFactory.create_agent_from_config(cfg,logs_dir=Path(td))
            self.assertEqual(agent.name(),'muse-openrouter')
            context=AgentContext()
            (Path(td)/'openrouter-usage.json').write_text(json.dumps(dict(complete=True,model=MODEL,totals=dict(input_tokens=150000001,output_tokens=5,cached_tokens=0))))
            agent.populate_context_post_run(context)
            self.assertEqual(context.n_input_tokens,150000001)
            self.assertFalse(context.metadata['native_d11'])

    @unittest.skipUnless(os.environ.get('TOPOGYM_TEST_MUSE_BINARY'),'fixed Muse binary required for offline native CLI test')
    def test_actual_muse_cli_uses_bridge_and_records_session(self):
        with tempfile.TemporaryDirectory() as td,upstream() as (server,url):
            root=Path(td); prompt=root/'prompt.txt'; prompt.write_text('Reply OK. Do not call tools.')
            rc=launch(os.environ['TOPOGYM_TEST_MUSE_BINARY'],MODEL,'default',prompt,root/'logs',KEY,
                      upstream=url,environment={'PATH':os.environ['PATH']},max_steps=1)
            if rc: print((root/'logs/muse-code.stderr.log').read_text()[-5000:])
            self.assertEqual(rc,0)
            self.assertTrue(server.requests)
            self.assertEqual(server.requests[0]['model'],MODEL)
            self.assertTrue(list((root/'logs/native-data/muse/sessions').rglob('*.jsonl')))
            for p in (root/'logs').rglob('*'):
                if p.is_file(): self.assertNotIn(KEY,p.read_text(errors='replace'))

    @unittest.skipUnless(os.environ.get('TOPOGYM_TEST_MUSE_BINARY'),'fixed Muse binary required for offline native CLI test')
    def test_actual_muse_tool_call_returns_to_provider(self):
        with tempfile.TemporaryDirectory() as td,upstream() as (server,url):
            root=Path(td); server.tool_file=root/'tool-result.txt'
            prompt=root/'prompt.txt'; prompt.write_text('Write offline-tool-ok to '+str(server.tool_file)+' then reply OK.')
            with contextlib.chdir(root):
                rc=launch(os.environ['TOPOGYM_TEST_MUSE_BINARY'],MODEL,'high',prompt,root/'logs',KEY,
                          upstream=url,environment={'PATH':os.environ['PATH'],'HOME':str(Path.home())},max_steps=2)
            if rc: print((root/'logs/muse-code.stderr.log').read_text()[-5000:])
            self.assertEqual(rc,0)
            if not server.tool_file.is_file():
                import shutil
                evidence=ROOT/'runs/test_results/muse_openrouter_20261005/tool-roundtrip'
                shutil.copytree(root/'logs',evidence,dirs_exist_ok=True)
                (evidence/'requests.json').write_text(json.dumps(server.requests,indent=2))
            self.assertTrue(server.tool_file.is_file(),(root/'logs/muse-code.jsonl').read_text()[-3000:])
            self.assertEqual(server.tool_file.read_text(),'offline-tool-ok')
            self.assertGreaterEqual(len(server.requests),2)
            self.assertTrue(any('function_call_output' in json.dumps(r['input']) for r in server.requests[1:]))
            self.assertEqual(json.loads((root/'logs/openrouter-usage.json').read_text())['totals']['input_tokens'],17*len(server.requests))

    def test_muse_assignment_seal_receive_and_agent_tamper(self):
        import agent_batch_contract as c
        import agent_batch_delivery as delivery
        spec=importlib.util.spec_from_file_location('native_fixture',ROOT/'ci_checks/test-native-agent-batch.py')
        fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); jobs,plan=fixture.fixture(root)
            plan.update(agent=dict(name='muse-openrouter',model='openrouter/'+MODEL,kwargs={'version':VERSION}),
                        harness_protocol='muse-openrouter-adapted-v1',helper_selects_model=True,
                        token_budget=dict(input_tokens=150000000,output_tokens=10000000,enforcement='post_run_score'))
            plan.pop('plan_sha256'); plan['plan_sha256']=c.digest(plan); c.validate(plan)
            selected=c.select_agent(plan,effort='high')
            c.match_assignment(plan,selected)
            c.save(jobs/'fixture-plan.json',selected)
            metadata=c.read(jobs/'fixture-metadata.json');metadata['plan_sha256']=selected['plan_sha256'];c.save(jobs/'fixture-metadata.json',metadata)
            for p in jobs.glob('*/*/config.json'):
                cfg=c.read(p); cfg['agent']=dict(name=IMPORT_PATH,model_name=selected['agent']['model'],kwargs=selected['agent']['kwargs']); c.save(p,cfg)
                result=c.read(p.with_name('result.json')); result['agent_result']=dict(n_input_tokens=17,n_output_tokens=2); c.save(p.with_name('result.json'),result)
            result_path=next(jobs.glob('*/*/result.json')); result=c.read(result_path)
            result['agent_result']['n_input_tokens']=150000001;c.save(result_path,result)
            budget_report=c.check_batch(jobs,selected)
            self.assertIn('over_token_budget',[row['status'] for row in budget_report['rows']])
            result['agent_result']['n_input_tokens']=17;c.save(result_path,result)
            report=delivery.seal(jobs,selected,{'synthetic':fixture.SECRET.encode()})
            self.assertTrue(report['delivery_complete'])
            archive=fixture.pack(root,jobs,selected)
            accepted=delivery.receive(archive,plan,root/'receiver',require_complete=True)
            self.assertTrue(accepted['report']['delivery_complete'])
            p=next(jobs.glob('*/*/config.json')); cfg=c.read(p);cfg['agent']['name']='codex';c.save(p,cfg)
            report=c.check_batch(jobs,selected)
            self.assertFalse(report['evaluation_complete'])


if __name__=='__main__': unittest.main()
