"""Independent protocol fixtures; no reference repository dependency."""
import json
import struct
import threading
from types import SimpleNamespace
import numpy as np
import pytest

from topogym.benchmark import wire
from topogym.benchmark.requests import validate
from topogym.benchmark.client import Result, Robot, EpisodeOver
from topogym.benchmark.session import Session
from topogym.benchmark.service import handler_for
from topogym.sensors.observation import SensorFrame


def spec():
    return dict(protocol="rcb-limited/2.2",default_cameras=["view"],cameras={"view":dict(depth=True)},control_hz=40,
        video_fps=20,max_watch_s=30,max_chunk_s=10,proprio_layout=["q"],proprio_groups={"joint_pos":[0,1,"rad"]},
        action_types={"joint_position":dict(dim=2,limits=[[-1,1],[0,.04]]),"ee_pose":dict(dim=8)},
        robot_spec=dict(grippers=dict(arm=dict(command=dict(range=[0,.04])))),budget=dict(wall_clock_s=600))


def test_literal_wire_frame():
    header = b'{"v":1,"meta":{"type":"joint_position","dt":0.025},"parts":[{"name":"actions","kind":"array","len":8,"dtype":"<f4","shape":[1,2]}]}'
    data = b"RCB1"+struct.pack("<I",len(header))+header+struct.pack("<ff",.5,.02)
    meta,parts = wire.decode(data)
    assert meta["dt"] == .025
    np.testing.assert_allclose(parts["actions"]["data"],[[.5,.02]])
    assert wire.decode(wire.encode(meta,[wire.array("actions",parts["actions"]["data"])]))[0] == meta


@pytest.mark.parametrize("payload",[
    b"",b"RCB1\xff\xff\xff\xff",b"RCB1\x02\0\0\0{}", b"garbage",
    b'RCB1'+struct.pack('<I',36)+b'{"v":1,"v":1,"meta":{},"parts":[]}',
])
def test_invalid_framing(payload):
    with pytest.raises(ValueError):
        wire.decode(payload)


def test_unsafe_array_and_trailing_bytes():
    raw = wire.encode({},[wire.blob("x",b"12345678",kind="array",dtype="O",shape=[1])])
    with pytest.raises(ValueError): wire.decode(raw)
    with pytest.raises(ValueError): wire.decode(wire.encode({})+b"x")
    with pytest.raises(ValueError): wire.json_loads('{"x":NaN}')
    with pytest.raises(ValueError): wire.json_loads('{"x":0,"x":1}')


@pytest.mark.parametrize("change",[
    {"dt":.026},{"dt":float("nan")},{"dt":True},{"type":"joint_torque"},
    {"depth":"garbage"},{"video":"gif"},{"interpolate":"cubic"},
    {"cameras":"view"},{"reset":True},{"note":[]},
])
def test_submit_validation(change):
    with pytest.raises(ValueError):
        validate({"type":"joint_position",**change},
            {"actions":dict(data=np.zeros((1,2),np.float32))},spec(),submit=True)


def test_clip_reports_and_depth_compatibility():
    request = validate(dict(type="joint_position",include_depth=True),{"actions":dict(data=np.array([[5,-1]],np.float32))},spec(),submit=True)
    assert request.depth == "legacy" and len(request.clipped)==2
    np.testing.assert_array_equal(request.rows,[[1,0]])
    assert validate(dict(include_depth=True,depth="last"),{},spec(),submit=False).depth == "last"


def test_chunk_and_shape_rejected():
    for value in (np.zeros((401,2),np.float32),np.zeros((1,3),np.float32),np.zeros((1,2)),np.full((1,2),np.nan,np.float32)):
        with pytest.raises(ValueError):
            validate(dict(type="joint_position"),{"actions":dict(data=value)},spec(),submit=True)


class FakeEnv:
    def __init__(self):
        self.n = 0
        self.target = np.array([0.,.02])
    def sensor_frame(self,depth=False):
        transform=np.eye(4);transform[0,3]=self.n*.001
        calibration = dict(K_px=np.eye(3).tolist(),resolution_px=[4,4],T_camera_cv_from_world=transform.tolist(),T_world_from_camera_cv=np.linalg.inv(transform).tolist())
        return SensorFrame("test",0,self.n,self.n*10,self.n/40,{"view":np.full((4,4,3),self.n,np.uint8)},
            {"view":calibration},{"view":np.full((4,4),1+self.n*.001,np.float32)} if depth else {})
    def step(self,command):
        self.n += 1
        self.target = command
        return {},0,False,False,dict(physics_steps=10,task_success=False)


@pytest.fixture
def session(tmp_path):
    import time
    s=Session.__new__(Session)
    s.env=FakeEnv()
    s.spec=spec()
    s.started=time.monotonic()
    s.rows=s.calls=s.control_steps=s.physics_steps=0
    s.actions=[];s.tick_counts=[];s.done=False;s.reason=None
    s.log_path=tmp_path/"episode.jsonl"
    s.robot=SimpleNamespace(measure=lambda:np.array([s.env.n*.001],np.float32),targets=lambda:s.env.target.copy(),
        command=lambda row:row.copy(),gripper_columns=[1],kinematics=lambda r:dict(ok=True,op=r["op"]))
    return s


def test_shared_axis_watching_and_legacy_depth(session):
    result=session.get_obs(seconds=.1,depth="frames",video="frames")
    np.testing.assert_array_equal(result.frame_step,[0,2,4])
    np.testing.assert_allclose(result.frame_time_s,[0,.05,.1])
    assert result.frames["view"].shape==(3,4,4,3)
    assert result.depth["view"].shape==(3,4,4)
    assert result.extrinsic_cv["view"].shape==(3,3,4)
    np.testing.assert_allclose(result.depth["view"][:,0,0],[1,1.002,1.004])
    assert session.physics_steps==40 and len(session.actions)==4
    legacy=session.get_obs(include_depth=True)
    assert legacy.depth["view"].dtype==np.float16
    assert session.env.n==4


def test_interpolation_gripper_switch_and_no_invalid_mutation(session):
    session.submit("joint_position",[[.4,.04]],dt=.1,video="none")
    np.testing.assert_allclose(session.actions,[[.1,.04],[.2,.04],[.3,.04],[.4,.04]],atol=1e-8)
    before=(session.calls,session.control_steps,session.physics_steps)
    with pytest.raises(ValueError): session.submit("joint_position",[[0,0],[np.nan,0]])
    assert before==(session.calls,session.control_steps,session.physics_steps)
    session.done=True
    with pytest.raises(EpisodeOver): session.submit("joint_position",[[0,0]])
    assert session.get_obs(seconds=1).done
    assert session.control_steps==4


def test_real_http_client_and_hidden_endpoints(session):
    from http.server import HTTPServer
    from urllib.request import urlopen,Request
    from urllib.error import HTTPError
    with HTTPServer(("127.0.0.1",0),handler_for(session)) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_port}"
            robot=Robot(base=base,timeout=2)
            assert robot.get_obs(depth="last").last_depth["view"].shape==(4,4)
            for endpoint in ("/reset","/state","/success","/finalize"):
                with pytest.raises(HTTPError) as exc: urlopen(Request(base+endpoint,data=b"{}"))
                assert exc.value.code==404
            with pytest.raises(ValueError):robot.submit("joint_position",[[float("nan"),0]])
            assert session.env.n==0
            assert robot.submit("joint_position",[[.1,.02]],video="frames").frame_step[-1]==1
        finally:
            server.shutdown();thread.join()
