"""Actual RCB1/client HTTP tests with synthetic tiny RGB; no simulator/model.

Install under scripts/robosafe/tests, or set ROBOSAFE_ORACLE_TEST_SOURCE to that
scripts/robosafe directory when loading this external draft. Tiny2x3 camera
contracts exercise byte transport only; they establish no native/task images,
real RT deadline, native evidence credit, or physical task success.
"""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

SOURCE = Path(os.environ.get('ROBOSAFE_ORACLE_TEST_SOURCE', Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(SOURCE))


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WIRE = load_module('rsb_oracle_test_wire', SOURCE/'shared/standard/rcb1.py')
with patch.dict(sys.modules, {'rcb1':WIRE}):
    CLIENT = load_module('rsb_oracle_test_rt_client', SOURCE/'shared/realtime/rcb_client.py')
OBS = load_module('rsb_oracle_test_observation_plan', SOURCE/'public_observation_plan.py')
with patch.dict(sys.modules, {'rcb_client':CLIENT, 'public_observation_plan':OBS}):
    ORACLE = load_module('rsb_oracle_test_rt_oracle', SOURCE/'shared/realtime/oracle_rt.py')


class ToyHTTP:
    """A finite deterministic queue/cost mock, not a simulated robot or native clock."""
    def __init__(self):
        self.spec = {'protocol':'eai-standard/2.3', 'control_dt':0.1, 'max_chunk_s':0.2,
                     'budget':{'wall_clock_s':2}, 'action_types':{'joint_position':{'dim':2},
                     'done':{'dim':0}, 'decline':{'dim':0}},
                     'cameras':{name:{'hw':[2,3], 'rgb':True} for name in ('front','top','wrist')},
                     'timing':{'max_cameras_while_running':2, 'picture_cost_steps':3,
                               'picture_cost_steps_by_camera':{'front':2,'top':3,'wrist':5}}}
        self.images = {name:np.asarray([(index*47+value*13)%256 for value in range(18)],
                                      dtype=np.uint8).reshape(2,3,3)
                       for index,name in enumerate(self.spec['cameras'])}
        self.requests, self.errors = [], []
        self.state = {'status':'ready', 'running':False, 'done':False, 'planned_steps':0,
                      'control_steps':0, 'picture_steps':0}
        self.frame_fault = None
        self.status_calls = 0
        self.undrained_second_status = False

    def status(self):
        self.status_calls += 1
        result = dict(self.state)
        if self.undrained_second_status and self.status_calls == 2:
            result['planned_steps'] = 1
        self.requests.append({'method':'GET','path':'/status','response':dict(result)})
        # Queue progress is deterministic, made only at this mock's status boundary.
        if self.state['planned_steps']:
            self.state['planned_steps'] -= 1
            self.state['control_steps'] += 1
        return result

    def post(self, path, body):
        meta, parts = WIRE.decode(body)
        entry = {'method':'POST', 'path':path, 'meta':meta, 'raw':body,
                 'planned_steps_at_request':self.state['planned_steps']}
        if 'actions' in parts:
            entry['actions'] = parts['actions']['data'].copy()
        self.requests.append(entry)
        if path == '/submit':
            if meta.get('cameras') != []:
                return 400, {'error':'toy motion requires explicit no pictures'}, []
            rows = parts['actions']['data']
            self.state['running'] = True
            if meta['type'] in ('done','decline'):
                self.state['done'] = True
            else:
                self.state['planned_steps'] += len(rows)
            return 200, dict(self.state), []
        if path != '/observe':
            return 404, {'error':'unknown toy route'}, []
        cameras = meta.get('cameras')
        if (self.state['planned_steps'] or not isinstance(cameras,list) or len(cameras)>2
                or any(name not in self.images for name in cameras)):
            return 400, {'error':'toy observe requires drained queue and at most2 public cameras'}, []
        if self.state['running']:
            cost = sum(self.spec['timing']['picture_cost_steps_by_camera'][name] for name in cameras)
            self.state['picture_steps'] += cost
            self.state['control_steps'] += cost
        frames = []
        for name in cameras:
            image = self.images[name]
            if self.frame_fault == 'missing' and name == 'wrist':
                continue
            if self.frame_fault == 'dimensions' and name == 'front':
                image = image[:1]
            if self.frame_fault == 'dtype' and name == 'front':
                image = image.astype(np.uint16)
            frames.append(WIRE.array_part('last/'+name,image))
        if self.frame_fault == 'extra':
            frames.append(WIRE.array_part('last/undeclared',self.images['front']))
        return 200, dict(self.state), frames


@contextmanager
def loopback(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, content_type, body):
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/spec':
                state.requests.append({'method':'GET','path':'/spec'})
                self.send(200,'application/json',json.dumps(state.spec).encode())
            elif self.path == '/status':
                self.send(200,'application/json',json.dumps(state.status()).encode())
            else:
                self.send(404,'application/json',b'{"error":"unknown toy route"}')

        def do_POST(self):
            try:
                if self.headers.get('Content-Type') != 'application/x-rcb1':
                    raise AssertionError('Actual client did not send RCB1')
                body = self.rfile.read(int(self.headers['Content-Length']))
                code, meta, parts = state.post(self.path,body)
                if code == 200:
                    self.send(code,'application/x-rcb1',WIRE.encode(meta,parts))
                else:
                    self.send(code,'application/json',json.dumps(meta).encode())
            except Exception as error:
                state.errors.append(repr(error))
                self.send(500,'application/json',json.dumps({'error':repr(error)}).encode())

    server = HTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=lambda:server.serve_forever(poll_interval=0.01),daemon=True)
    thread.start()
    try:
        # requests is the real installed client dependency; only localhost is used.
        with patch.dict(os.environ, {'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}):
            yield CLIENT.Robot('http://127.0.0.1:'+str(server.server_port),timeout=2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise AssertionError('Toy HTTP server thread did not terminate')
        if state.errors:
            raise AssertionError(state.errors)


def snapshot(index=0):
    boundary = {'source':'native_record_observe','record_call_index':index,'row_offset':None,
                'skill_call_index':None,'kind':'raw_observe','opportunity_only':True}
    return OBS.snapshot(boundary,OBS.batches(['front','top','wrist']))


def document(plan):
    return {'schema':OBS.SCHEMA,'observation_policy':OBS.policy(),'plan':plan,'source_record_canonical_sha256':'f'*64}


class PublicRTOracleHTTPTests(unittest.TestCase):
    def setUp(self):
        self.state = ToyHTTP()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)/'deliveries'
        self.motion = np.asarray([[0.125,-0.75],[0.625,0.25],[1.0,-0.125],[0.0,0.5]],dtype=np.float64)

    def execute(self, doc, arrays=None):
        if arrays is None:
            end=max([item['rows'][1] for item in doc['plan'] if 'rows' in item] or [0])
            arrays={'joint_position':self.motion[:end]} if end else {}
        with loopback(self.state) as robot:
            return ORACLE.run_reference(doc, arrays,
                                        robot,self.output,sleep=lambda delay:None,monotonic=time.monotonic)

    def posts(self, route):
        return [entry for entry in self.state.requests if entry['method']=='POST' and entry['path']==route]

    def test_actual_wire_and_realtime_client_get_obs_preserve_each_original_rgb_byte(self):
        with loopback(self.state) as robot:
            result = robot.get_obs(cameras=['front','top'],seconds=0,video='none',include_depth=False)
        self.assertEqual(set(result.last), {'front','top'})
        self.assertEqual(result.frames,{})
        self.assertEqual(result.video,{})
        for name,array in result.last.items():
            self.assertEqual(array.dtype,np.uint8)
            self.assertEqual(array.shape,(2,3,3))
            self.assertEqual(array.tobytes(),self.state.images[name].tobytes())
        request = self.posts('/observe')[0]
        self.assertEqual(request['raw'][:4],b'RCB1')
        decoded, parts = WIRE.decode(request['raw'])
        self.assertEqual(decoded['cameras'],['front','top'])
        self.assertEqual(parts,{})

    def test_frozen_batches_drain_motion_keep_original_arrays_and_save_exact_rgb(self):
        doc = document([{'type':'joint_position','rows':[0,2]},snapshot(),
                        {'type':'joint_position','rows':[2,4]},snapshot(1),
                        {'type':'done','row':[]}])
        before = self.motion.copy()
        result = self.execute(doc)
        self.assertTrue(result['done'])
        self.assertEqual(self.motion.tobytes(),before.tobytes())
        observations = self.posts('/observe')
        self.assertEqual([r['meta']['cameras'] for r in observations],
                         [['front','top'],['wrist'],['front','top'],['wrist']])
        self.assertTrue(all(r['planned_steps_at_request']==0 for r in observations))
        for request in observations:
            self.assertEqual(request['meta']['seconds'],0.0)
            self.assertEqual(request['meta']['video'],'none')
            self.assertFalse(request['meta']['include_depth'])
        receipts = list(self.output.glob('*-*/receipt.json'))
        self.assertEqual(len(receipts),4)
        for path in receipts:
            receipt = json.loads(path.read_text())
            for name,frame in receipt['frames'].items():
                raw = (path.parent/frame['path']).read_bytes()
                self.assertEqual(raw,self.state.images[name].tobytes())
                self.assertEqual(frame['shape'],[2,3,3])
                self.assertEqual(frame['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertFalse(receipt['native_or_task_credit_granted'])
        motion = self.posts('/submit')
        self.assertEqual([r['meta']['cameras'] for r in motion],[[],[],[]])
        self.assertTrue(all(r['meta']['video']=='none' for r in motion))
        np.testing.assert_array_equal(np.concatenate([r['actions'] for r in motion[:-1]]),before)
        report = json.loads((self.output/'DELIVERY_RECEIPT.json').read_text())
        self.assertEqual(report['snapshot_batches_delivered'],4)
        self.assertFalse(report['native_or_task_credit_granted'])

    def test_each_delivered_batch_charges_actual_mock_public_picture_cost(self):
        self.execute(document([{'type':'joint_position','rows':[0,2]},snapshot(),{'type':'done','row':[]}]))
        costs = [json.loads(path.read_text())['picture_cost_contract']
                 for path in sorted(self.output.glob('*-*/receipt.json'))]
        self.assertEqual([cost['expected_steps_if_running'] for cost in costs],[5,5])
        self.assertEqual([cost['picture_steps_delta'] for cost in costs],[5,5])
        self.assertTrue(all(cost['running_before'] for cost in costs))
        self.assertEqual(self.state.state['picture_steps'],10)

    def test_missing_declared_frame_holds_and_never_seals_run_delivery(self):
        self.state.frame_fault = 'missing'
        with self.assertRaisesRegex(ValueError,'every and only'):
            self.execute(document([snapshot()]))
        self.assertFalse((self.output/'DELIVERY_RECEIPT.json').exists())

    def test_wrong_original_pixel_dimensions_or_dtype_hold(self):
        for fault in ('dimensions','dtype'):
            self.state = ToyHTTP();self.state.frame_fault = fault
            self.output = Path(self.temp.name)/fault
            with self.assertRaisesRegex(ValueError,'original-resolution'):
                self.execute(document([snapshot()]))
            self.assertFalse((self.output/'DELIVERY_RECEIPT.json').exists())

    def test_undeclared_frame_holds_even_if_requested_frames_are_present(self):
        self.state.frame_fault = 'extra'
        with self.assertRaisesRegex(ValueError,'every and only'):
            self.execute(document([snapshot()]))

    def test_second_status_detects_an_undrained_boundary_before_http_observe(self):
        self.state.undrained_second_status = True
        with self.assertRaisesRegex(ValueError,'undrained motion boundary'):
            self.execute(document([snapshot()]))
        self.assertEqual(self.posts('/observe'),[])

    def test_three_camera_single_batch_and_reordered_frozen_batches_hold_before_motion(self):
        for batches in ([['front','top','wrist']],[['wrist'],['front','top']]):
            doc = document([snapshot()]);doc['plan'][0]['camera_batches'] = batches
            self.state = ToyHTTP();self.output = Path(self.temp.name)/str(len(batches))
            with self.assertRaisesRegex(ValueError,'batching|order'):
                self.execute(doc)
            self.assertEqual(self.posts('/observe'),[])
            self.assertEqual(self.posts('/submit'),[])

    def test_actual_spec_limit_below_frozen_two_camera_batch_holds(self):
        self.state.spec['timing']['max_cameras_while_running'] = 1
        with self.assertRaisesRegex(ValueError,'camera limit'):
            self.execute(document([snapshot()]))
        self.assertEqual(self.posts('/observe'),[])

    def test_literal_nop_has_no_submit_or_observe_and_does_not_start_clock(self):
        self.execute({'plan':[]},arrays={})
        self.assertEqual(self.posts('/observe'),[])
        self.assertEqual(self.posts('/submit'),[])
        self.assertFalse(self.state.state['running'])
        self.assertFalse(self.output.exists())

    def test_version2_empty_control_has_no_initial_or_checker_observation(self):
        self.execute(document([]),arrays={})
        self.assertEqual(self.posts('/observe'),[])
        self.assertEqual(self.posts('/submit'),[])
        report = json.loads((self.output/'DELIVERY_RECEIPT.json').read_text())
        self.assertEqual(report['snapshot_batches_delivered'],0)
        self.assertFalse(self.state.state['running'])

    def test_schema1_original_motion_plan_keeps_no_picture_policy(self):
        self.execute({'schema':'rsb.public-control-plan/1',
                      'plan':[{'type':'joint_position','rows':[0,2]},{'type':'done','row':[]}]})
        self.assertEqual(self.posts('/observe'),[])
        self.assertEqual([r['meta']['cameras'] for r in self.posts('/submit')],[[],[]])
        self.assertFalse(self.output.exists())

    def test_unreported_picture_cost_counter_is_recorded_unknown_not_zero(self):
        # the realtime service's /status does not report picture_steps: the receipt says so instead of assuming 0
        self.state.state.pop('picture_steps')
        self.execute(document([snapshot()]))
        receipts=sorted(self.output.glob('*/receipt.json'))
        self.assertTrue(receipts)
        for r in receipts:
            self.assertIsNone(json.loads(r.read_text())['picture_cost_contract']['picture_steps_delta'])

    def test_invalid_picture_cost_counter_holds(self):
        self.state.state['picture_steps']=-1
        with self.assertRaisesRegex(ValueError,'counter missing or invalid'):
            self.execute(document([snapshot()]))
        self.assertFalse((self.output/'DELIVERY_RECEIPT.json').exists())

    def test_authored_pre_first_call_snapshot_is_delivered_without_automatic_initial_picture(self):
        boundary={'source':'native_compiled_skill_opportunity','record_call_index':-1,'row_offset':0,
            'position':'before_first_call','skill_call_index':0,'kind':'skill_observe',
            'opportunity_only':True,'compiled_row_end':0,'preceding_kept_segments':0,
            'oracle_index':0,'play_record_call_start_index':0}
        obs=OBS.snapshot(boundary,OBS.batches(['front','top','wrist']))
        self.execute(document([obs,{'type':'joint_position','rows':[0,2]},{'type':'done','row':[]}]))
        self.assertEqual(len(self.posts('/observe')),2)
        self.assertEqual(self.state.state['picture_steps'],0)
        for path in self.output.glob('*-*/receipt.json'):
            self.assertFalse(json.loads(path.read_text())['picture_cost_contract']['running_before'])

    def test_schema1_cannot_smuggle_unversioned_observe(self):
        with self.assertRaisesRegex(ValueError,'legacy RT semantics'):
            self.execute({'schema':'rsb.public-control-plan/1','plan':[snapshot()]})
        self.assertEqual(self.posts('/observe'),[])
        self.assertEqual(self.posts('/submit'),[])


if __name__ == '__main__':
    unittest.main()
