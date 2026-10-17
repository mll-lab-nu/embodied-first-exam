"""Paused publicV2 oracle with actual standard RCB1/client and localhost HTTP.

Synthetic tiny RGB and a synchronous integer-step queue exercise transport and
plan order only, never native rendering, physical credit or a realtime clock.
Install in scripts/robosafe/tests or set ROBOSAFE_PAUSED_TEST_SOURCE to that
source directory. Requires import-safe oracle_replay.run_reference.
"""
from contextlib import contextmanager
import copy
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np

SOURCE = Path(os.environ.get('ROBOSAFE_PAUSED_TEST_SOURCE',Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(SOURCE))


def load_module(name,filename):
    spec = importlib.util.spec_from_file_location(name,filename)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


WIRE = load_module('rsb_paused_test_wire',SOURCE/'shared/standard/rcb1.py')
with patch.dict(sys.modules,{'rcb1':WIRE}):
    CLIENT = load_module('rsb_paused_test_client',SOURCE/'shared/standard/rcb_client.py')
O = load_module('rsb_paused_test_plan',SOURCE/'public_observation_plan.py')
with patch.dict(sys.modules,{'rcb_client':CLIENT,'public_observation_plan':O}):
    ORACLE = load_module('rsb_paused_test_oracle',SOURCE/'shared/solution/oracle_replay.py')

HTTP_POLICY = {'cameras':'all_public','initial_observe':True,'video':'none','interpolate':'hold'}
ALL_PUBLIC = ['front','top','wrist']
DECLARED_PUBLIC = ['wrist','front','top']


class PausedToy:
    def __init__(self):
        self.spec = {'protocol':'eai-standard/2.1','control_dt':0.02,'max_chunk_s':0.04,
                     'action_types':{'joint_position':{'dim':2},'done':{'dim':0},'decline':{'dim':0},'report':{'dim':0}},
                     'cameras':{name:{'hw':[2,3],'rgb':True} for name in ('wrist','front','top')}}
        self.state = {'control_steps':0,'done':False,'status':'ready'}
        self.requests,self.errors = [],[]
        self.observe_count = 0
        self.fault = None

    def pixels(self,name,step):
        offset = ALL_PUBLIC.index(name)*41+step
        return np.asarray([(offset+value*13)%256 for value in range(18)],dtype=np.uint8).reshape(2,3,3)

    def status(self):
        self.requests.append({'method':'GET','path':'/status','step':self.state['control_steps']})
        return dict(self.state)

    def post(self,path,body):
        meta,parts = WIRE.decode(body)
        request = {'method':'POST','path':path,'meta':meta,'step':self.state['control_steps'],'raw':body}
        self.requests.append(request)
        cameras = meta.get('cameras')
        if not isinstance(cameras,list) or any(name not in ALL_PUBLIC for name in cameras):
            return 400,{'error':'toy requires explicit public cameras'},[]
        if path=='/submit':
            rows = parts['actions']['data'];request['actions'] = rows.copy()
            if meta['type'] in ('done','decline'):
                self.state['done'] = True
            else:
                self.state['control_steps'] += len(rows)
        elif path=='/observe':
            self.observe_count += 1
            if meta['seconds']!=0:
                return 400,{'error':'paused snapshot must take zero seconds'},[]
            if self.fault=='advance' and self.observe_count==2:
                self.state['control_steps'] += 1
        else:
            return 404,{'error':'unknown route'},[]
        frames = []
        fault = self.fault if path=='/observe' and self.observe_count==2 else None
        for name in cameras:
            image = self.pixels(name,self.state['control_steps'])
            if fault=='missing' and name=='wrist':continue
            if fault=='dimensions' and name=='front':image=image[:1]
            if fault=='dtype' and name=='front':image=image.astype(np.uint16)
            frames.append(WIRE.array_part('last/'+name,image))
        if fault=='extra':frames.append(WIRE.array_part('last/undeclared',self.pixels('front',0)))
        response=dict(self.state)
        if path=='/submit' and meta['type']=='joint_position' and self.fault=='blocked':
            response['blocked']=True;self.fault=None
        return 200,response,frames


@contextmanager
def loopback(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,code,kind,body):
            self.send_response(code);self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path=='/spec':self.send(200,'application/json',json.dumps(state.spec).encode())
            elif self.path=='/status':self.send(200,'application/json',json.dumps(state.status()).encode())
            else:self.send(404,'application/json',b'{"error":"unknown route"}')
        def do_POST(self):
            try:
                if self.headers.get('Content-Type')!='application/x-rcb1':
                    raise AssertionError('actual standard client must send RCB1')
                code,meta,parts = state.post(self.path,self.rfile.read(int(self.headers['Content-Length'])))
                self.send(code,'application/x-rcb1' if code==200 else 'application/json',
                          WIRE.encode(meta,parts) if code==200 else json.dumps(meta).encode())
            except Exception as error:
                state.errors.append(repr(error));self.send(500,'application/json',b'{"error":"toy failure"}')
    server = HTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=lambda:server.serve_forever(poll_interval=0.01),daemon=True);thread.start()
    try:
        with patch.dict(os.environ,{'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}):
            yield CLIENT.Robot('http://127.0.0.1:'+str(server.server_port),timeout=2)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
        if thread.is_alive():raise AssertionError('toy HTTP thread did not terminate')
        if state.errors:raise AssertionError(state.errors)


def authored_document(rows):
    boundary = {'skill_call_index':2,'skill_tool':'look','compiled_row_end':2,'preceding_kept_segments':0,
                'kind':'compiled_look_hold','opportunity_only':True,'oracle_index':0,
                'play_record_call_start_index':0,'record_call_index':0,'row_offset':2,'position':'within_act_rows'}
    record = {'instance':{'robot':'ur5e_2f85','interface':'control'},'calls':[
        {'tool':'act','args':{'type':'joint_position','rows':rows.tolist(),'dt':0.02,'images':False},'ok':True},
        {'tool':'end','args':{'reason':'done'},'ok':True}],
        'strategy_info':{'public_observation_boundaries':{'schema':O.NATIVE_SCHEMA,'complete':True,
            'boundaries':[boundary],'oracles':[{'oracle_index':0,'complete':True,'record_call_start_index':0,
                                               'expected_boundaries':1,'mapped_boundaries':1}]}}}
    plan = [{'type':'joint_position','rows':[0,len(rows)],'_source_call':0},
            {'type':'done','row':[],'text':'','_source_call':1}]
    document = O.build(record,plan,DECLARED_PUBLIC,clock='paused')
    document.update(candidate_identity={'fixture_only':True},http_policy=copy.deepcopy(HTTP_POLICY))
    return document


class PausedPublicOracleWire(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)/'observations';self.state = PausedToy()
        self.rows = np.asarray([[-0.0,0.125],[0.25,-0.75],[0.5,0.875],[-0.125,0.0],
                                [0.625,1.0],[-1.0,0.375]],dtype=np.float64)

    def execute(self,document,arrays=None):
        with loopback(self.state) as robot:
            return ORACLE.run_reference(document,{'joint_position':self.rows} if arrays is None else arrays,
                                        robot,self.output)

    def posts(self,path):
        return [r for r in self.state.requests if r['method']=='POST' and r['path']==path]

    def authored_receipts(self):
        result = []
        for path in self.output.rglob('receipt.json'):
            receipt = json.loads(path.read_text());boundary = receipt.get('boundary',{})
            if boundary.get('record_call_index')==0 and boundary.get('row_offset')==2:
                result.append((path,receipt))
        return result

    def test_actual_standard_wire_get_obs_transports_three_original_public_rgb_arrays(self):
        with loopback(self.state) as robot:
            result = robot.get_obs(cameras=ALL_PUBLIC,seconds=0,video='none',include_depth=False)
        self.assertEqual(set(result.last),set(ALL_PUBLIC))
        self.assertEqual(result.video,{})
        for camera,image in result.last.items():
            self.assertEqual(image.dtype,np.uint8);self.assertEqual(image.shape,(2,3,3))
            self.assertEqual(image.tobytes(),self.state.pixels(camera,0).tobytes())
        self.assertEqual(self.posts('/observe')[0]['raw'][:4],b'RCB1')
        self.assertEqual(self.state.state['control_steps'],0)

    def test_authored_near_look_is_observed_before_retreat_and_all_motion_rows_stay_exact(self):
        document = authored_document(self.rows);before=self.rows.tobytes()
        self.execute(document)
        self.assertEqual([r['step'] for r in self.posts('/observe')],[0,2])
        self.assertEqual([r['meta']['cameras'] for r in self.posts('/observe')],[ALL_PUBLIC,DECLARED_PUBLIC])
        submits = self.posts('/submit')
        self.assertTrue(all(r['meta']['cameras']==ALL_PUBLIC for r in submits))
        self.assertTrue(all(r['meta']['video']=='none' and r['meta']['interpolate']=='hold' for r in submits))
        motion = [r['actions'] for r in submits if r['meta']['type']=='joint_position']
        self.assertEqual(np.concatenate(motion).tobytes(),before)
        self.assertEqual(self.rows.tobytes(),before)
        # No async wait/drain loop is needed: each normal submit has already run.
        self.assertEqual(self.state.state['control_steps'],len(self.rows))

    def test_authored_snapshot_saves_original_near_pixels_without_advancing_control_steps(self):
        self.execute(authored_document(self.rows))
        receipts = self.authored_receipts();self.assertEqual(len(receipts),1)
        path,receipt = receipts[0]
        self.assertTrue(receipt['original_resolution'])
        self.assertEqual(receipt['status_before']['control_steps'],2)
        self.assertEqual(receipt['status_after']['control_steps'],2)
        for camera,frame in receipt['frames'].items():
            raw = (path.parent/frame['path']).read_bytes()
            self.assertEqual(raw,self.state.pixels(camera,2).tobytes())
            self.assertEqual(frame['shape'],[2,3,3])
            self.assertEqual(frame['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertNotIn('picture_steps',self.state.state)

    def test_extra_snapshots_depend_on_authored_boundaries_not_chunk_size(self):
        for per in (1,3):
            self.state=PausedToy();self.state.spec['max_chunk_s']=per*0.02
            self.output=Path(self.temp.name)/('chunk'+str(per))
            self.execute(authored_document(self.rows))
            self.assertEqual([r['step'] for r in self.posts('/observe')],[0,2])
            self.assertEqual(len(self.authored_receipts()),1)

    def test_version2_nop_keeps_original_initial_observe_and_adds_no_extra_snapshot(self):
        record={'instance':{},'calls':[]}
        document=O.build(record,[],ALL_PUBLIC,clock='paused')
        document.update(candidate_identity={'fixture_only':True},http_policy=copy.deepcopy(HTTP_POLICY))
        self.execute(document,arrays={})
        self.assertEqual(len(self.posts('/observe')),1)
        self.assertEqual(self.posts('/observe')[0]['meta']['cameras'],ALL_PUBLIC)
        self.assertEqual(self.posts('/submit'),[])
        self.assertEqual(self.authored_receipts(),[])
        self.assertEqual(self.state.state['control_steps'],0)

    def test_missing_extra_dimension_or_dtype_fault_at_authored_snapshot_holds(self):
        for fault in ('missing','extra','dimensions','dtype'):
            self.state=PausedToy();self.state.fault=fault;self.output=Path(self.temp.name)/fault
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                self.execute(authored_document(self.rows))
            self.assertFalse((self.output/'DELIVERY_RECEIPT.json').exists())

    def test_explicit_paused_observe_that_advances_control_steps_is_hold(self):
        self.state.fault='advance'
        with self.assertRaisesRegex(ValueError,'control|step|paused'):
            self.execute(authored_document(self.rows))
        self.assertFalse((self.output/'DELIVERY_RECEIPT.json').exists())

    def test_bad_paused_schema_policy_or_rt_batching_holds_before_delivery(self):
        for changed in ('rt_policy','rt_batches','missing_source'):
            self.state=PausedToy();self.output=Path(self.temp.name)/changed
            document=authored_document(self.rows)
            if changed=='rt_policy':document['observation_policy']=O.policy(clock='realtime')
            elif changed=='rt_batches':
                next(it for it in document['plan'] if it['type']=='observe')['camera_batches']=[['front','top'],['wrist']]
            else:document.pop('source_record_canonical_sha256')
            with self.subTest(changed=changed),self.assertRaises(ValueError):self.execute(document)
            self.assertEqual(self.posts('/observe'),[])

    def test_bound_legacy_plan_keeps_exact_initial_and_normal_all_public_policy_without_extras(self):
        legacy={'schema':'rsb.public-control-plan/1','candidate_identity':{'fixture_only':True},
                'http_policy':copy.deepcopy(HTTP_POLICY),'plan':[{'type':'joint_position','rows':[0,6]},
                                                            {'type':'done','row':[],'text':''}]}
        self.execute(legacy)
        self.assertEqual([r['step'] for r in self.posts('/observe')],[0])
        self.assertTrue(all(r['meta']['cameras']==ALL_PUBLIC for r in self.posts('/submit')))
        self.assertEqual(self.authored_receipts(),[])

    def test_legacy_blocked_chunk_still_emits_following_report_and_done(self):
        # Original schema1 only breaks the current motion-chunk loop on blocked.
        for bound in (False,True):
            with self.subTest(bound=bound):
                self.state=PausedToy();self.state.fault='blocked'
                document={'plan':[{'type':'joint_position','rows':[0,6]},
                                  {'type':'report','row':[],'text':'Contact stopped this motion'},
                                  {'type':'done','row':[],'text':''}]}
                if bound:
                    document.update(schema='rsb.public-control-plan/1',
                                    candidate_identity={'fixture_only':True},
                                    http_policy=copy.deepcopy(HTTP_POLICY))
                self.execute(document)
                submits=self.posts('/submit')
                self.assertEqual([r['meta']['type'] for r in submits],['joint_position','report','done'])
                self.assertEqual(submits[0]['actions'].tobytes(),self.rows[:2].tobytes())
                self.assertEqual(submits[1]['meta']['note'],'Contact stopped this motion')
                self.assertEqual([r['meta']['cameras'] for r in submits],
                                 [ALL_PUBLIC if bound else ['front']]*3)
                self.assertTrue(self.state.state['done'])

    def test_unbound_historical_plan_keeps_single_first_camera_and_no_initial_observe(self):
        legacy={'plan':[{'type':'joint_position','rows':[0,6]},{'type':'done','row':[],'text':''}]}
        self.execute(legacy)
        self.assertEqual(self.posts('/observe'),[])
        self.assertTrue(all(r['meta']['cameras']==['front'] for r in self.posts('/submit')))


if __name__=='__main__':unittest.main()
