"""run_eval pieces that need no GPU: outcome classes, make arguments, output path and tracking error."""
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from omegaconf import OmegaConf

from vla.gym import run_eval
from vla.gym.run_eval import classify, load_config, make_args, output_dir, set_render_defaults, tracking_error
from vla.protocol import PolicySpec


def spec(action_space="joint_abs", control_hz=15):
    return PolicySpec(name="m", embodiment="panda_robotiq", cameras=["agentview"],
                      action_space=action_space, control_hz=control_hz, chunk_size=15, execute_steps=8)


@pytest.mark.parametrize("outcome, reason, status, expected", [
    ("success", "task_terminal", "available", "success"),
    ("failure", "task_terminal", "available", "task_failure"),
    ("ongoing", "time_limit", "available", "time_limit"),
    ("unknown", "time_limit", "unavailable", "unevaluated"),
    ("ongoing", None, "available", "unfinished"),
])
def test_classify_follows_the_public_info(outcome, reason, status, expected):
    info = dict(task_outcome=outcome, termination_reason=reason, evaluation_status=status)
    assert classify(info) == expected


def test_make_args_follow_the_policy_spec():
    cfg = OmegaConf.create(dict(task=dict(id="buzz_wire_3d", variation="base", sim_seconds=60), env={}))
    assert make_args(cfg, spec()) == dict(
        variation_id="base", control_mode="JOINT_ABS", observation_mode="JOINT", physics_dt_s=0.0025,
        control_decimation=27, max_physics_steps=24000)
    ee = make_args(cfg, spec("ee_abs", control_hz=30))
    assert (ee["control_mode"], ee["observation_mode"], ee["control_decimation"]) == ("EE_ABS", "EE", 13)


def test_make_args_pass_env_overrides_through():
    cfg = OmegaConf.create(dict(task=dict(id="cast_coil", variation="easy", sim_seconds=2),
                                env=dict(physics_dt_s=0.005, enable_depth=True)))
    args = make_args(cfg, spec(control_hz=50))
    assert (args["physics_dt_s"], args["control_decimation"], args["max_physics_steps"], args["enable_depth"]) == (
        0.005, 4, 400, True)


def test_make_args_resolve_references():
    cfg = OmegaConf.create(dict(task=dict(id="cast_coil", variation="base", sim_seconds=2), env=dict(note="${task.id}")))
    assert make_args(cfg, spec(control_hz=50))["note"] == "cast_coil"


def test_tracking_error_is_the_worst_arm_distance_without_gripper():
    action = {"left": {"joint_position_rad": [0.0, 0.3, 0.0], "gripper_position_m": 0.037},
              "right": {"joint_position_rad": [0.0, 0.0, 0.1], "gripper_position_m": 0.002}}
    robot = {"left": {"joint_position_rad": [0.0, 0.0, 0.4]}, "right": {"joint_position_rad": [0.0, 0.0, 0.0]}}
    assert tracking_error(action, robot, "joint_abs") == pytest.approx(0.5)
    action = {"arm": {"position_world_m": [1.0, 2.0, 3.0], "orientation_wxyz": [1, 0, 0, 0]}}
    robot = {"arm": {"tcp_position_world_m": [1.0, 2.0, 2.9]}}
    assert tracking_error(action, robot, "ee_abs") == pytest.approx(0.1)


def test_output_defaults_to_date_model_and_task():
    cfg = OmegaConf.create(dict(task=dict(id="buzz_wire_3d"), run=dict(output=None)))
    assert output_dir(cfg, spec()) == Path(f"runs/test_results/{date.today():%Y%m%d}_vla_m_buzz_wire_3d")
    cfg.run.output = "runs/test_results/mine"
    assert output_dir(cfg, spec()) == Path("runs/test_results/mine")


def test_config_overrides_apply_after_the_base_and_must_name_existing_keys(tmp_path):
    (tmp_path / "base.yaml").write_text("policy: {address: localhost:8000, local: null}\n"
                                        "task: {id: '???', variation: base, seeds: [0], sim_seconds: 2}\n"
                                        "run: {execute_steps: null, record: false, output: null}\nenv: {}\n")
    path = tmp_path / "cast_coil.yaml"
    path.write_text("_base_: base.yaml\ntask: {id: cast_coil}\n")
    cfg = load_config(path, ["task.seeds=[1,2]", "env.enable_depth=true", "policy.address=localhost:8001"])
    assert cfg.task.id == "cast_coil" and list(cfg.task.seeds) == [1, 2] and cfg.env.enable_depth is True
    assert cfg.policy.address == "localhost:8001" and cfg.policy.local is None
    with pytest.raises(Exception, match="seed"):
        load_config(path, ["task.seed=[0]"])


def test_render_defaults_fill_only_unset_variables_with_existing_paths(tmp_path, monkeypatch):
    icd, assets = tmp_path / "nvidia_icd.json", tmp_path / "nyx-assets"
    icd.write_text("{}")
    assets.mkdir()
    monkeypatch.setattr(run_eval, "NVIDIA_ICD", icd)
    monkeypatch.setattr(run_eval, "NYX_ASSETS", assets)
    environ = {}
    set_render_defaults(environ)
    assert environ == {"TOPOGYM_VISUAL_ASSET_ROOT": str(assets), "VK_ICD_FILENAMES": str(icd)}
    environ = {"TOPOGYM_VISUAL_ASSET_ROOT": "assets", "VK_ICD_FILENAMES": "mine.json"}
    set_render_defaults(environ)
    assert environ == {"TOPOGYM_VISUAL_ASSET_ROOT": "assets", "VK_ICD_FILENAMES": "mine.json"}
    monkeypatch.setattr(run_eval, "NVIDIA_ICD", tmp_path / "missing.json")
    monkeypatch.setattr(run_eval, "NYX_ASSETS", tmp_path / "missing")
    environ = {}
    set_render_defaults(environ)
    assert environ == {}  # TopoGym's own asset default (~/.cache/topogym/visuals/nyx) applies


class FakeEnv:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_summary_records_the_code_the_run_started_with(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run_eval, "git_state", lambda: calls.append("git") or dict(git_commit="abc", git_dirty=True),
                        raising=False)
    monkeypatch.setattr(run_eval.topogym, "make", lambda task_id, **args: FakeEnv())

    def episode(env, client, spec, seed, instruction, execute_steps, video_dir):
        calls.append("episode")
        return dict(outcome="time_limit", task_success=False, failure_code=None, sim_time_s=1.0, control_steps=2,
                    inference_calls=1, tracking_error_mean=0.0, tracking_error_max=0.0, tracking_error_unit="rad",
                    clipped_actions=0, skipped_actions=0, reset_wall_s=0.0, rollout_wall_s=1.0, error=None)

    monkeypatch.setattr(run_eval, "run_episode", episode)
    cfg = OmegaConf.create(dict(policy=dict(address="localhost:1", local=None), env={},
                                task=dict(id="buzz_wire_3d", variation="base", seeds=[0, 1], sim_seconds=1),
                                run=dict(execute_steps=None, record=False, output=str(tmp_path / "out"))))
    run_eval.evaluate(cfg, SimpleNamespace(spec=spec()))
    summary = json.loads((tmp_path / "out/summary.json").read_text())
    assert calls == ["git", "episode", "episode"]  # read before the code can change under a long run
    assert (summary["git_commit"], summary["git_dirty"]) == ("abc", True)
