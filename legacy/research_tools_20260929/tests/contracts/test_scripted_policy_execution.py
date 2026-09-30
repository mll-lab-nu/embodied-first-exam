"""Passive policies exercise the actual Env/segment loop with the tiny world."""
from dataclasses import replace
import json
import numpy as np
import pytest

from topogym.planning.base import ActionSequencePolicy
from topogym.simulator import SegmentRunner
from topogym.simulator.rollout_simulation.segment_contract import SegmentError
from topogym.tasks.base import TaskResult

HASH = "a" * 64


@pytest.fixture
def managed(local_env, monkeypatch, tmp_path):
    spec = dict(robot_id="fixture", mode="JOINT_ABS", arms=["arm"], groups={"arm": dict(
        arm_joint_names=["joint"], gripper_field="gripper_position_m", gripper_limits=[0., .04])})
    monkeypatch.setattr(type(local_env), "action_spec", property(lambda self: spec))
    original = local_env._robot.observe
    def observe():
        values = original()
        values["arm"].update(tcp_position_world_m=np.array([local_env._world.position, 0., 0.]),
            tcp_orientation_wxyz=np.array([1., 0., 0., 0.]), finger_position_m=np.array([.01, .01]),
            joint_position_target_rad=np.array([999.]))
        return values
    monkeypatch.setattr(local_env._robot, "observe", observe)
    local_env._sensors.invalidate()
    with SegmentRunner(local_env, tmp_path / "trail") as runner:
        yield runner, local_env


def run(runner, policy, identifier="test", **options):
    return runner.run_policy(request_id=identifier, policy=policy, submission_hash=HASH, **options)


def test_single_argument_feedback_and_final_notification(managed):
    runner, env = managed
    env._config = replace(env.config, enable_privileged=False)
    class Policy:
        seen = []
        def act(self, obs):
            self.seen.append(obs)
            if len(self.seen) == 3:
                return None
            return {"target": len(self.seen)}
        def on_segment_end(self, obs, result):
            self.final = obs, result
    policy = Policy()
    result = run(runner, policy)
    assert result["reason"] == "policy_done" and result["physics_steps"] == 6
    assert [o["state"]["physics_step"] for o in policy.seen] == [0, 3, 6]
    assert policy.seen[0]["execution_state"]["previous"] is None
    assert policy.seen[1]["execution_state"]["previous"]["action"] == {"target": 1}
    assert policy.seen[1]["execution_state"]["previous"]["info"]["physics_steps"] == 3
    assert policy.final[1] is result
    for obs in policy.seen:
        assert set(obs["robot"]["arm"]) == {"joint_position_rad", "tcp_position_world_m",
                                            "tcp_orientation_wxyz", "finger_position_m"}
        assert "privileged" not in obs and "camera_calibration" not in obs
        assert "reward" not in str(obs["execution_state"])
        assert obs["robot"]["arm"]["tcp_position_world_m"][0] == obs["robot"]["arm"]["joint_position_rad"][0]
        with pytest.raises(ValueError):
            obs["robot"]["arm"]["joint_position_rad"].setflags(write=True)


def test_early_terminal_gets_last_observation_without_extra_act(managed):
    runner, env = managed
    def update(state, dt):
        env._task.result = TaskResult(terminated=True, reason="hidden pose failure")
        return env._task.result
    env._task.update = update
    class Policy:
        calls = 0
        def act(self, obs):
            self.calls += 1
            return {"target": 1.}
        def on_segment_end(self, obs, result):
            self.final = obs
    policy = Policy()
    result = run(runner, policy)
    assert result["reason"] == "env_terminal" and result["physics_steps"] == 1
    assert policy.calls == 1 and policy.final["state"]["physics_step"] == 1
    previous = policy.final["execution_state"]["previous"]
    assert previous["completed"] and previous["terminated"]
    assert "hidden pose" not in str(policy.final)


def test_idempotence_profile_conflict_and_expired_episode(managed):
    runner, env = managed
    policy = ActionSequencePolicy([{"target": 1.}])
    first = run(runner, policy)
    class Never:
        def act(self, obs):
            raise AssertionError("Replay must not call policy")
    assert run(runner, Never()) is first
    assert env._world.physics_step == 3
    with pytest.raises(SegmentError, match="conflict"):
        run(runner, Never(), observation_profile={"rgb_camera_ids": []})
    env.reset(seed=9)
    with pytest.raises(SegmentError, match="expired"):
        run(runner, Never())


@pytest.mark.parametrize("failure,reason", [("output", "invalid_policy_output"),
    ("action", "invalid_action"), ("policy", "policy_error"), ("initialize", "policy_error")])
def test_failures_preserve_prefix_and_close_segment(managed, failure, reason):
    runner, env = managed
    class Policy:
        def initialize(self, context):
            if failure == "initialize":
                raise RuntimeError("private /owner/location")
        def act(self, obs):
            if obs["execution_state"]["control_steps"] == 0:
                return {"target": 1.}
            if failure == "output":
                return [1, 2]
            if failure == "action":
                return {"invalid": 1.}
            raise RuntimeError("private /owner/location")
    result = run(runner, Policy())
    assert result["reason"] == reason
    assert result["control_steps"] == (0 if failure == "initialize" else 1)
    assert runner._active is None
    assert "private /owner" not in str(result)
    assert run(runner, ActionSequencePolicy([]), "next")["reason"] == "policy_done"


def test_faulted_result_replay_and_stale_observation(managed, monkeypatch):
    runner, env = managed
    original = env._world.advance
    def fail():
        if env._world.physics_step == 2:
            raise RuntimeError("private engine error")
        original()
    monkeypatch.setattr(env._world, "advance", fail)
    class Policy(ActionSequencePolicy):
        def on_segment_end(self, obs, result):
            self.final = obs
    policy = Policy([{"target": 2.}])
    result = run(runner, policy)
    assert result["reason"] == "env_error" and result["physics_steps"] == 2
    assert policy.final["state"]["physics_step"] == 0
    assert not policy.final["execution_state"]["observation_is_current"]
    assert not policy.final["execution_state"]["previous"]["completed"]
    assert run(runner, policy) is result


def test_callback_and_reentrancy_do_not_advance(managed):
    runner, env = managed
    class Policy:
        def act(self, obs):
            with pytest.raises(SegmentError, match="busy"):
                runner.interaction().run_segment(request_id="nested", actions=[])
            with pytest.raises(SegmentError):
                env.step({"target": 4.})
            return None
        def on_segment_end(self, obs, result):
            raise RuntimeError("callback private detail")
    result = run(runner, Policy())
    assert result["physics_steps"] == 0
    events = [json.loads(line) for line in (runner.root / "private/control_steps.jsonl").read_text().splitlines()]
    assert events[-1]["kind"] == "policy_notification" and events[-1]["status"] == "failed"


def test_unlimited_only_selected_state_and_owner_authorization(managed):
    runner, env = managed
    class Policy:
        def act(self, obs):
            assert set(obs["privileged"]) == {"world"}
            assert obs["privileged"]["world"]["position"] == 0.
            return None
    run(runner, Policy(), mode="unlimited", state_fields=("world",))
    with pytest.raises(PermissionError):
        run(runner, Policy(), "denied", state_fields=("world",))
    env._config = replace(env.config, enable_privileged=False)
    with pytest.raises(PermissionError):
        run(runner, Policy(), mode="unlimited", state_fields=("world",))


def test_evidence_failure_prevents_next_step(managed, monkeypatch):
    runner, env = managed
    original = runner._evidence.policy_event
    def fail(kind, **kwargs):
        if kind == "policy_output":
            raise OSError("disk failure")
        return original(kind, **kwargs)
    monkeypatch.setattr(runner._evidence, "policy_event", fail)
    result = run(runner, ActionSequencePolicy([{"target": 1.}]))
    assert result["reason"] == "evidence_error" and not result["evidence_complete"]
    assert env._world.physics_step == 0


def test_termination_at_episode_limit_discards_remaining_actions(managed):
    runner, env = managed
    result = run(runner, ActionSequencePolicy([{"target": 1.}]*50))
    assert result["control_steps"] == 4 and result["physics_steps"] == 12
    assert result["reason"] == "env_time_limit"


def test_policy_core_report_failure_cannot_publish_complete(managed, monkeypatch):
    runner, env = managed
    original = runner._evidence.write_policy_report
    def fail(identity, report):
        if report["status"] != "running":
            raise OSError("final report failure")
        original(identity, report)
    monkeypatch.setattr(runner._evidence, "write_policy_report", fail)
    result = run(runner, ActionSequencePolicy([]))
    assert not result["evidence_complete"] and result["status"] == "incomplete"


def test_projection_failure_reports_the_last_valid_observation(managed, monkeypatch):
    runner, env = managed
    original = runner._policy_inputs
    def fail_after_step(*args):
        if env._world.physics_step:
            raise RuntimeError("private observation failure")
        return original(*args)
    monkeypatch.setattr(runner, "_policy_inputs", fail_after_step)
    class Policy(ActionSequencePolicy):
        def on_segment_end(self, obs, result):
            self.final = obs
    policy = Policy([{"target": 1.}])
    result = run(runner, policy)
    assert result["reason"] == "observation_error" and not result["evidence_complete"]
    assert result["control_steps"] == 1 and result["physics_steps"] == 3
    assert policy.final["state"]["physics_step"] == 0
    assert not policy.final["execution_state"]["observation_is_current"]
    assert policy.final["execution_state"]["previous"]["completed"]
    assert "private observation" not in str(policy.final)


@pytest.mark.parametrize("camera_ids", [("a",), ()])
def test_selected_rgb_limits_both_observation_and_segment_media(managed, camera_ids):
    runner, env = managed
    class Camera:
        res, fov, transform = (24, 16), 60., np.eye(4)
        def render(self, rgb):
            return np.full((16, 24, 3), env._state_id, dtype=np.uint8)
    env._world.cameras = {"a": Camera(), "b": Camera()}
    env._config = replace(env.config, enable_rgb=True)
    env._sensors.enable_rgb = True
    env._sensors.invalidate()
    class Policy:
        def act(self, obs):
            assert tuple(obs["rgb"]) == camera_ids
            for pixels in obs["rgb"].values():
                assert pixels[0, 0, 0] == obs["state"]["state_id"]
            return {"target": 1.} if obs["execution_state"]["control_steps"] == 0 else None
    result = run(runner, Policy(), observation_profile={"rgb_camera_ids": camera_ids})
    assert result["physics_steps"] == 3 and result["evidence_complete"]
    assert set(result["media"]["videos"]) == ({"a", "combined"} if camera_ids else set())
    assert not (runner.root / "views/b").exists()


def test_prepared_rollout_root_and_public_export(local_env, tmp_path):
    from topogym.simulator.rollout_simulation import SegmentRunner as Other
    assert Other is SegmentRunner
    root = tmp_path / "experiment_20260926/task/rollout_0001"
    root.mkdir(parents=True)
    (root / "run_report.json").write_text('{"status":"starting"}')
    with SegmentRunner(local_env, root, prepared_output=True):
        assert (root / "private/physics_states.jsonl").is_file()
    with pytest.raises(FileExistsError):
        SegmentRunner(local_env, root, prepared_output=True)


def test_incomplete_goal_known_failure_reaches_policy_and_rewind_clears_it(managed):
    runner, env = managed
    env._task.goal_complete=False
    anchor=env.state_history[0].ref
    env._task.evaluate_state=lambda state: (False, 'wire_touched' if state['physics_step'] else None, {})
    def unexpected_instruction():
        pytest.fail("Task instructions must not be fetched for policy observations")
    env._task.public_instruction=unexpected_instruction
    class Policy:
        calls=0
        def act(self,obs):
            self.calls+=1
            assert 'task' not in obs
            return {'target':1.}
        def on_segment_end(self,obs,result):
            self.final=obs
    policy=Policy(); result=run(runner,policy)
    assert result['reason']=='env_terminal' and result['physics_steps']==1 and policy.calls==1
    info=policy.final['execution_state']['previous']['info']
    assert info['evaluation_status']=='available' and info['task_outcome']=='failure'
    assert info['task_success'] is False and info['failure_code']=='wire_touched'
    _, restored=env.privileged.rewind_to(anchor)
    assert not restored['task_terminated'] and env._task.task_state=={}
