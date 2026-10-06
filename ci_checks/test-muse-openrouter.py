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




class BridgeTests(unittest.TestCase):

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





if __name__=='__main__': unittest.main()
