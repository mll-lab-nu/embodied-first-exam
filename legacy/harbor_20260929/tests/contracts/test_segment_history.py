"""Published multi-segment histories with real codecs and a deterministic CPU world."""
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from topogym.agents.rollout.client import check_initial, main
from topogym.agents.rollout.history import HistoryReader
from topogym.agents.rollout.policy_process import RemotePolicyProxy
from topogym.agents.rollout.protocol import API_VERSION, ProtocolError
from topogym.agents.rollout.verify import finalize, score
from topogym.agents.rollout.worker import RolloutSession
from topogym.simulator import SegmentRunner
from topogym.simulator.rollout_simulation.policy_observation import resolve_profile


@pytest.fixture
def history_env(local_env, monkeypatch):
    env = local_env
    env._config = replace(env.config, enable_rgb=True, max_physics_steps=60)
    class Camera:
        res, fov, transform = (24, 16), 60., np.eye(4)
        def render(self, rgb):
            return np.full((16, 24, 3), env._state_id, dtype=np.uint8)
    env._world.cameras = {"a": Camera(), "hidden": Camera()}
    env._sensors.enable_rgb = True
    spec = dict(robot_id="fixture", mode="JOINT_ABS", groups={"arm": dict(
        arm_joint_names=["joint"], gripper_field="gripper_position_m", gripper_limits=[0., .04])})
    monkeypatch.setattr(type(env), "action_spec", property(lambda self: spec))
    original_observe = env._robot.observe
    def observe():
        values = original_observe()
        values["arm"].update(tcp_position_world_m=np.array([env._world.position, 0., 0.]),
            tcp_orientation_wxyz=np.array([1., 0., 0., 0.]), finger_position_m=np.array([.01, .01]),
            secret_controller_target="DO_NOT_PUBLISH")
        return values
    monkeypatch.setattr(env._robot, "observe", observe)
    validate = env._robot.validate_action
    monkeypatch.setattr(env._robot, "validate_action", lambda action:
        validate(action or {"target": env._world.target}))
    read = env._world.read_state
    def world():
        return dict(read(), private_object_pose=[913., 914., 915.], samples=np.arange(1000))
    monkeypatch.setattr(env._world, "read_state", world)
    env._sensors.invalidate()
    return env


def instance(mode="limited", **extra):
    return dict(mode=mode, state_fields=["world"] if mode == "unlimited" else [],
        observation_profile={"rgb_camera_ids": ["a"]}, evaluation="pipeline_smoke",
        simulator={"task_id": "fixture", "enable_rgb": True}, **extra)


def profile(env, settings):
    return resolve_profile(env, mode=settings["mode"], state_fields=settings["state_fields"],
                           settings=settings["observation_profile"])


def session(runner, settings, public):
    return RolloutSession(runner, settings, public,
        proxy_factory=lambda source, path: RemotePolicyProxy(source, path, isolated=False))


def submit(owner, identifier, source=None):
    source = source or ("class P:\n def act(self,obs):\n"
        "  return {'target':1.0} if obs['execution_state']['control_steps']==0 else None\n"
        "def create_policy(): return P()\n")
    owner.dispatch(dict(api_version=API_VERSION, operation="submit_policy", episode_id=owner.runner.episode_id,
        request_id=identifier, policy=dict(source_utf8=source, filename="policy.py", factory="create_policy", parameters={})))
    assert owner.execute_next()
    assert owner.requests[identifier]["receipt"]["request_status"] == "finished"


@pytest.mark.parametrize("mode", ["limited", "unlimited"])
def test_all_segments_have_video_and_each_tick_with_granted_fields(history_env, tmp_path, mode):
    settings = instance(mode)
    with SegmentRunner(history_env, tmp_path / "owner", initial_observation_steps=2,
                       initial_profile=profile(history_env, settings)) as runner:
        owner = session(runner, settings, tmp_path / "public")
        assert check_initial(owner.state)["phase"] == "ready"
        reader = HistoryReader(owner.publisher.root)
        initial = reader.result(0)
        if mode == "unlimited":
            descriptor = runner.initial["logs"]["steps"]
            with pytest.raises(PermissionError):
                runner.interaction().read_artifact(descriptor["artifact_id"])
            assert b"private_object_pose" in runner.interaction(privileged=True).read_artifact(descriptor["artifact_id"])
            private = runner.root / "private/raw-secret.txt"
            private.write_text("DO_NOT_PUBLISH")
            raw = runner._artifacts.add("private/raw-secret.txt", private=True)
            with pytest.raises(PermissionError):
                owner.publisher._export(raw)
        assert initial["control_steps"] == 2 and initial["physics_steps"] == 6
        assert initial["start_state_ref"]["state_id"] == 0
        assert initial["end_state_ref"]["state_id"] == 6
        submit(owner, "one")
        submit(owner, "two")
        assert [item["segment_id"] for item in reader.index()["segments"]] == [0, 1, 2]
        previous = initial["start_state_ref"]
        for identity in range(3):
            result = reader.result(identity)
            assert result["start_state_ref"] == previous
            previous = result["end_state_ref"]
            assert set(result["media"]["videos"]) == {"a", "combined"}
            rows = reader.page(identity, "steps", 0, 100)["rows"]
            assert len(rows) == result["physics_steps"] + 1
            assert rows[0]["kind"] == "initial" and rows[0]["action"] is None
            assert rows[-1]["state"]["state_id"] == result["end_state_ref"]["state_id"]
            assert [row["state"]["physics_step"] for row in rows] == list(range(
                rows[0]["state"]["physics_step"], rows[-1]["state"]["physics_step"] + 1))
            assert all(row["action_index"] is not None for row in rows[1:])
            for row in rows:
                assert "secret_controller_target" not in row["robot"]["arm"]
                assert "joint_velocity_rad_s" not in row["robot"]["arm"]
                if mode == "limited":
                    assert "privileged" not in row and "private_object_pose" not in json.dumps(row)
                else:
                    assert set(row["privileged"]) == {"world"}
                    assert row["privileged"]["world"]["private_object_pose"] == [913., 914., 915.]
                    assert len(row["privileged"]["world"]["samples"]) == 1000
                    assert "array_file" not in json.dumps(row)
            frames = reader.page(identity, "frames", 0, 100)["rows"]
            assert frames[-1]["source_state_id"] == result["end_state_ref"]["state_id"]
            assert all(not row["camera_metadata"] for row in frames)
            assert all(row["source_state_id"] in {r["state"]["state_id"] for r in rows} for row in frames)
            assert reader.video(identity, "a")["frame_count"] == len(frames)
        assert not list(runner.root.rglob("*.png"))
        assert not list(owner.publisher.root.rglob("*.png"))
        assert not list(owner.publisher.root.rglob("hidden.mp4"))
        if mode == "limited":
            assert all("DO_NOT_PUBLISH" not in p.read_text() and "private_object_pose" not in p.read_text()
                       for p in owner.publisher.root.rglob("*.jsonl"))
        owner.cancel("agent_finished")
        owner.finish()
        assert finalize(runner.root)["pipeline_passed"]
        assert HistoryReader(runner.root).page(0, "steps", 0, 1)["next_start"] == 1


def test_history_cli_pagination_and_frame_extraction(history_env, tmp_path, capsys):
    settings = instance()
    with SegmentRunner(history_env, tmp_path / "owner", initial_observation_steps=2,
                       initial_profile=profile(history_env, settings)) as runner:
        owner = session(runner, settings, tmp_path / "public")
        root = str(owner.publisher.root)
        capsys.readouterr()
        assert main(["--public-root", root, "logs", "--segment", "0", "--limit", "2"]) == 0
        page = json.loads(capsys.readouterr().out)
        assert len(page["rows"]) == 2 and page["next_start"] == 2
        assert main(["--public-root", root, "frames", "--segment", "0", "--camera", "a",
                     "--output", str(tmp_path / "extract")]) == 0
        answer = json.loads(capsys.readouterr().out)
        from PIL import Image
        for row in answer["frames"]:
            Image.open(row["path"]).verify()
        assert answer["frames"][0]["source_state_id"] == 0
        assert answer["frames"][-1]["source_state_id"] == 6
        reader = HistoryReader(root)
        with pytest.raises(ValueError, match="camera"):
            reader.video(0, "hidden")
        with pytest.raises(ValueError, match="outside"):
            reader.frames(0, "a", [0], Path(root) / "extract")
        with pytest.raises(ValueError, match="published"):
            reader.result(99)
        owner.finish()


def test_initial_terminal_is_published_and_rejects_submissions(history_env, tmp_path):
    history_env._config = replace(history_env.config, max_physics_steps=2)
    settings = instance()
    with SegmentRunner(history_env, tmp_path / "owner", initial_observation_steps=5,
                       initial_profile=profile(history_env, settings)) as runner:
        owner = session(runner, settings, tmp_path / "public")
        assert check_initial(owner.state)["phase"] == "terminal"
        assert runner.initial["reason"] == "env_time_limit"
        assert runner.initial["control_steps"] == 1 and runner.initial["physics_steps"] == 2
        with pytest.raises(ProtocolError, match="episode_ended"):
            submit(owner, "late")
        owner.finish()
        assert not score(runner.root)["pipeline_passed"]


def test_zero_step_segment_and_cancel_keep_initial_row_and_video(history_env, tmp_path):
    settings = instance()
    with SegmentRunner(history_env, tmp_path / "owner", initial_profile=profile(history_env, settings)) as runner:
        owner = session(runner, settings, tmp_path / "public")
        submit(owner, "empty", "class P:\n def act(self,obs): return None\ndef create_policy(): return P()")
        reader = HistoryReader(owner.publisher.root)
        result = reader.result(1)
        assert result["control_steps"] == 0 and result["media"]["frame_count"] == 1
        assert len(reader.page(1, "steps", 0, 20)["rows"]) == 1
        assert [s["segment_id"] for s in reader.index()["segments"]] == [0, 1]
        owner.cancel()
        owner.finish()


def test_history_write_failure_stops_execution(history_env, tmp_path, monkeypatch):
    from topogym.simulator.rollout_simulation.history import SegmentHistory
    from topogym.simulator.rollout_simulation.evidence import EvidenceError
    settings = instance()
    with SegmentRunner(history_env, tmp_path / "owner", initial_profile=profile(history_env, settings)) as runner:
        owner = session(runner, settings, tmp_path / "public")
        original = SegmentHistory.tick
        def fail(self, record, **kwargs):
            if not kwargs.get("initial"):
                raise EvidenceError("simulated disk failure")
            return original(self, record, **kwargs)
        monkeypatch.setattr(SegmentHistory, "tick", fail)
        submit(owner, "fails")
        result = HistoryReader(owner.publisher.root).result(1)
        assert result["status"] == "incomplete" and not result["evidence_complete"]
        assert history_env._world.physics_step == 1
        assert owner.state["phase"] == "faulted"
        owner.finish()
        assert not score(runner.root)["pipeline_passed"]
