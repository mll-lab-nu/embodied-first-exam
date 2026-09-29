"""Real core + IPC with a deterministic CPU world; never a GPU acceptance claim."""
from dataclasses import replace
import io
import json
from pathlib import Path
import threading
import time

import numpy as np
import pytest

from topogym.agents.rollout.client import call, check_initial, wait_result
from topogym.agents.rollout.policy_process import PolicyCancelled, RemotePolicyProxy
from topogym.agents.rollout.protocol import (API_VERSION, ProtocolError, decode, dumps,
    encode, loads, receive, send, validate_submit)
from topogym.agents.rollout.verify import finalize, score, seal_archive
from topogym.agents.rollout.worker import RolloutSession, serve
from topogym.simulator import SegmentRunner


SOURCE = """class Policy:
    def initialize(self, context):
        assert context['schema_version'] == 2
        assert 'task_instruction' not in context['observation_profile']
    def act(self, obs):
        assert 'privileged' not in obs
        assert 'task' not in obs
        assert 'tcp_position_world_m' in obs['robot']['arm']
        if obs['execution_state']['control_steps'] >= 1:
            return None
        return {'target': 1.0}
def create_policy(**kwargs):
    return Policy()
"""


def budget_snapshot(tmp_path, *, inputs=11):
    from topogym.agents.usage import BudgetPolicy, UsageEvent, UsageLedger
    ledger = UsageLedger(tmp_path / 'ledger.sqlite', scope_id='trial', policy=BudgetPolicy(10, 10))
    ledger.admit('r', source='test')
    ledger.mark_sent('r')
    ledger.record(UsageEvent('r', 'e', 0, 'test', inputs, 1, final=True))
    return ledger.finalize()


def test_budget_stop_latches_over_finish_and_rejects_new_policy(session, tmp_path):
    from topogym.agents.rollout.protocol import atomic_json
    snapshot = budget_snapshot(tmp_path / 'usage')
    session.cancel('budget_exceeded', snapshot=snapshot)
    session.cancel('agent_finished')
    assert session.state['stop_reason'] == 'budget_exceeded'
    with pytest.raises(ProtocolError, match='episode_ended'):
        session.dispatch(message(session.runner.episode_id))
    atomic_json(session.runner.root / 'usage_final.json', snapshot)
    session.finish()
    result = score(session.runner.root)
    assert result['reward'] == 0 and result['failure_reason'] == 'budget_exceeded'
    assert not result['budget_qualified']


def test_budget_failure_overrides_late_physical_success(session, tmp_path):
    from topogym.agents.rollout.protocol import atomic_json
    session.instance['evaluation'] = 'task_success'
    atomic_json(session.runner.root / 'instance.json', session.instance)
    session.dispatch(message(session.runner.episode_id))
    session.execute_next()
    session.cancel('agent_finished')
    session.finish()
    final = json.loads((session.runner.root/'session_final.json').read_text())
    final['final_feedback'].update(evaluation_status='available',task_success=True)
    atomic_json(session.runner.root/'session_final.json',final)
    atomic_json(session.runner.root/'usage_final.json',budget_snapshot(tmp_path/'usage'))
    result=score(session.runner.root)
    assert result['task_success'] is True  # physical fact preserved
    assert result['reward'] == 0 and result['outcome'] == 'failed'


def test_budget_socket_cancels_running_real_policy(session,tmp_path):
    socket = tmp_path/'budget.sock'
    admin = serve(session,socket,admin=True)
    source='import time\nclass P:\n def act(self,obs): time.sleep(100)\ndef create_policy(): return P()'
    session.dispatch(message(session.runner.episode_id,source=source))
    errors=[]
    def execute():
        try: session.execute_next()
        except BaseException as error: errors.append(error)
    owner=threading.Thread(target=execute)
    owner.start()
    try:
        deadline=time.monotonic()+3
        while session.proxy is None and time.monotonic()<deadline: time.sleep(.01)
        assert session.proxy is not None
        time.sleep(.1)
        snapshot=budget_snapshot(tmp_path/'usage')
        start=time.monotonic()
        call({'operation':'budget_stop','snapshot':snapshot},socket)
        owner.join(2)
        assert not owner.is_alive() and not errors
        assert time.monotonic()-start < 2
        call({'operation':'finish'},socket)
        assert session.state['stop_reason']=='budget_exceeded'
        assert call({'operation':'budget_status'},socket)['execution_stopped']
        from topogym.agents.rollout.history import HistoryReader
        history=HistoryReader(session.publisher.root)
        assert [entry['segment_id'] for entry in history.index()['segments']]==[0,1]
        assert history.result(1)['reason']=='cancelled'
        assert len(history.page(1,'steps',0,10)['rows'])==1
    finally:
        session.cancel()
        admin.shutdown(); admin.server_close()


def message(episode, identifier="one", source=SOURCE):
    return dict(api_version=API_VERSION, operation="submit_policy", episode_id=episode,
        request_id=identifier, policy=dict(source_utf8=source, filename="segment_1.py",
            factory="create_policy", parameters={}))


@pytest.fixture
def session(local_env, monkeypatch, tmp_path):
    local_env._config = replace(local_env.config, enable_privileged=False)
    spec = dict(robot_id="fixture", mode="JOINT_ABS", arms=["arm"], groups={"arm": dict(
        arm_joint_names=["joint"], gripper_field="gripper_position_m", gripper_limits=[0., .04])})
    monkeypatch.setattr(type(local_env), "action_spec", property(lambda self: spec))
    original = local_env._robot.observe
    def observe():
        values = original()
        values["arm"].update(tcp_position_world_m=np.array([local_env._world.position, 0., 0.]),
            tcp_orientation_wxyz=np.array([1., 0., 0., 0.]), finger_position_m=np.array([.01, .01]))
        return values
    monkeypatch.setattr(local_env._robot, "observe", observe)
    local_env._sensors.invalidate()
    with SegmentRunner(local_env, tmp_path / "private") as runner:
        owner = RolloutSession(runner, {"mode": "limited", "evaluation": "pipeline_smoke",
            "simulator": {"task_id": "fixture", "enable_rgb": False}}, tmp_path / "public",
            proxy_factory=lambda source, path: RemotePolicyProxy(source, path, isolated=False))
        yield owner
        if owner.proxy:
            owner.proxy.cancel()


def test_two_submissions_share_state_and_freeze_source(session):
    spec = json.loads(Path(session.state["spec_path"]).read_text())
    assert spec["schema_version"] == 2 and spec["mode"] == "limited"
    assert "task_instruction" not in spec["observation_profile"]
    assert "task" not in spec["observation_spec"]
    assert set(spec["observation_spec"]["robot"]["arm"]["fields"]) == {
        "joint_position_rad", "tcp_position_world_m", "tcp_orientation_wxyz", "finger_position_m"}
    first = message(session.runner.episode_id)
    receipt = session.dispatch(first)
    assert receipt["request_status"] == "accepted"
    first["policy"]["source_utf8"] = "raise AssertionError('changed after acceptance')"
    assert session.execute_next()
    one = session.dispatch(dict(api_version=API_VERSION, operation="result", request_id="one"))
    assert one["request_status"] == "finished"
    r1 = json.loads(Path(one["result_path"]).read_text())
    assert r1["control_steps"] == 1 and r1["reason"] == "policy_done"
    second = message(session.runner.episode_id, "two")
    session.dispatch(second)
    session.execute_next()
    r2 = json.loads(Path(session.state["latest_result_path"]).read_text())
    assert r1["end_state_ref"] == r2["start_state_ref"]
    assert r1["segment_id"] == 1 and r2["segment_id"] == 2
    assert session.runner.env._world.physics_step == 6
    assert session.dispatch(second)["request_status"] == "finished"
    assert session.pending.empty()
    session.cancel("agent_finished")
    session.finish()
    report = score(session.runner.root)
    assert report["pipeline_passed"] and report["reward"] == 1
    assert report["task_success"] is False  # Pipeline success is not puzzle success.
    assert report["usage"]["input_tokens"] is None


def test_busy_conflict_stale_and_unauthorized_options(session):
    first = message(session.runner.episode_id)
    session.dispatch(first)
    assert session.dispatch(first)["request_status"] == "accepted"
    for bad, code in [(message(session.runner.episode_id, "two"), "execution_busy"),
                      (message("stale"), "episode_expired"),
                      (message(session.runner.episode_id, source=SOURCE+"\n# changed"), "request_id_conflict")]:
        with pytest.raises(ProtocolError, match=code):
            session.dispatch(bad)
    changed = {**first, "mode": "unlimited"}
    with pytest.raises(ProtocolError, match="invalid_fields"):
        session.dispatch(changed)
    assert session.runner.env._world.physics_step == 0


def test_socket_status_and_wait_timeout_does_not_cancel(session, tmp_path):
    path = tmp_path / "agent.sock"
    server = serve(session, path)
    try:
        state = call({"operation": "status"}, path)
        assert check_initial(state, check_rgb=False)["phase"] == "ready"
        with pytest.raises(ValueError, match="video"):
            check_initial(state)
        receipt = call(message(session.runner.episode_id), path)
        with pytest.raises(TimeoutError):
            wait_result(receipt, .01, path)
        assert not session.stop.is_set()
        session.execute_next()
        assert wait_result(receipt, 2, path)["request_status"] == "finished"
        rejected = call({"operation": "reset"}, path)
        assert rejected["request_status"] == "rejected"
    finally:
        server.shutdown()
        server.server_close()


def test_hanging_policy_cancel_is_independent(session):
    hanging = "import time\nclass Policy:\n def act(self, obs):\n  time.sleep(100)\ndef create_policy(): return Policy()\n"
    session.dispatch(message(session.runner.episode_id, source=hanging))
    def cancel():
        while session.proxy is None:
            time.sleep(.01)
        time.sleep(.3)
        session.cancel()
    thread = threading.Thread(target=cancel, daemon=True)
    thread.start()
    started = time.monotonic()
    session.execute_next()
    thread.join(timeout=3)
    assert time.monotonic() - started < 5
    result = json.loads(Path(session.state["latest_result_path"]).read_text())
    assert result["reason"] == "cancelled" and result["control_steps"] == 0
    session.finish()
    assert score(session.runner.root)["reward"] == 0


@pytest.mark.parametrize("source", [
    "def create_policy(): raise RuntimeError('private-secret')",
    "class Policy:\n def act(self, obs): return {'wrong_action': 1}\ndef create_policy(): return Policy()",
    "class Policy:\n def act(self, obs): return [1,2]\ndef create_policy(): return Policy()",
])
def test_invalid_policy_seals_result_without_private_error_leak(session, source):
    session.dispatch(message(session.runner.episode_id, source=source))
    session.execute_next()
    receipt = session.requests["one"]["receipt"]
    assert receipt["request_status"] == "finished"
    result = Path(receipt["result_path"]).read_text()
    assert "private-secret" not in result and '"token"' not in result
    assert json.loads(result)["reason"] in {"policy_error", "invalid_action", "invalid_policy_output"}


def test_queued_cancel_does_not_start_policy(session):
    session.dispatch(message(session.runner.episode_id))
    session.cancel()
    session.execute_next()
    assert session.runner.env._world.physics_step == 0
    assert session.requests["one"]["receipt"]["request_status"] == "error"


def test_wire_arrays_readonly_and_finite_json():
    original = {"rgb": np.arange(12, dtype=np.uint8).reshape(2,2,3), "none": None}
    wire = io.BytesIO()
    send(wire, encode(original))
    wire.seek(0)
    restored = decode(receive(wire))
    assert np.array_equal(original["rgb"], restored["rgb"])
    with pytest.raises(ValueError):
        restored["rgb"].setflags(write=True)
    with pytest.raises(ValueError):
        loads('{"number":NaN}')
    with pytest.raises(ValueError):
        loads('{"number":1,"number":2}')
    with pytest.raises(ValueError):
        decode({"__array__": "", "dtype": "O", "shape": [1]})
    with pytest.raises(ValueError):
        decode({"__array__": "", "dtype": "f8", "shape": [1000000000]})


def test_noisy_policy_stdout_cannot_corrupt_transport(tmp_path):
    source = "import os\nos.write(1,b'noise\\n')\nclass Policy:\n def act(self, obs):\n  print('noise')\n  return None\ndef create_policy(): return Policy()"
    proxy = RemotePolicyProxy(message("episode", source=source)["policy"], tmp_path / "process", isolated=False)
    try:
        assert proxy.act({}) is None
    finally:
        proxy.close()
    assert b"noise" in (tmp_path / "process/stderr.log").read_bytes()


def test_active_results_and_private_artifacts_never_published(session, tmp_path):
    with pytest.raises(ValueError, match="sealed"):
        session.publisher.publish({"segment_id": 1, "status": "active", "token": "secret"})
    path = session.runner.root / "secret.txt"
    path.write_text("secret")
    descriptor = session.runner._artifacts.add("secret.txt", private=True)
    with pytest.raises(PermissionError):
        session.publisher.publish({"segment_id": 1, "status": "complete", "artifact": descriptor})
    assert not list(session.publisher.root.rglob("*.txt"))


def test_publication_bytes_and_hash_are_checked_before_marker(session):
    path = session.runner.root / "fake.png"
    path.write_bytes(b"fixture bytes, not an RGB acceptance image")
    descriptor = session.runner._artifacts.add("fake.png")
    result = {"segment_id": 1, "status": "complete", "artifact": descriptor}
    session.publisher.publish(result)
    entry = session.publisher.entries[descriptor["artifact_id"]]
    assert Path(entry["path"]).read_bytes() == path.read_bytes()
    path.write_bytes(b"changed")
    with pytest.raises(ValueError):
        session.publisher.publish({**result, "segment_id": 2})
    assert not (session.publisher.root / "segments/segment_2/result.json").exists()


def test_verifier_unknown_is_not_success_and_corruption_fails(session):
    session.dispatch(message(session.runner.episode_id))
    session.execute_next()
    session.cancel("agent_finished")
    session.finish()
    root = session.runner.root
    final = json.loads((root / "session_final.json").read_text())
    final["final_feedback"]["evaluation_status"] = "unavailable"
    final["final_feedback"]["task_success"] = True  # inconsistent input must not earn reward
    (root / "session_final.json").write_text(json.dumps(final))
    instance = json.loads((root / "instance.json").read_text())
    instance["evaluation"] = "task_success"
    (root / "instance.json").write_text(json.dumps(instance))
    report = finalize(root)
    assert report["task_success"] is None and report["reward"] == 0
    assert (root / "archive_manifest.json").exists()


def test_smoke_requires_measured_up_and_down(tmp_path):
    from topogym.agents.rollout.verify import smoke_motion
    path = tmp_path / "private/physics_states.jsonl"
    path.parent.mkdir()
    def write(heights):
        path.write_text("".join(json.dumps({"segment_id": i, "robot": {
            "arm": {"tcp_position_world_m": [0, 0, height]}}}) + "\n" for i, height in enumerate(heights)))
    write([.4, .402, .4001])
    assert smoke_motion(tmp_path)["passed"]
    write([.4, .4, .4])
    assert not smoke_motion(tmp_path)["passed"]
