"""Evaluate one policy on one task variation over several seeds, from the repository root:

    python -m vla.gym.run_eval --config vla/configs/eval/<name>.yaml [dotted.key=value ...]

Writes into run.output: results.jsonl (one row per episode), summary.json, report.md and, with run.record, one
MP4 per camera under seed_<seed>/videos/. The output directory must not exist yet; a null run.output means
runs/test_results/<YYYYMMDD>_vla_<model>_<task>. The model is whichever server listens at policy.address.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from omegaconf import OmegaConf

import topogym
from topogym.recording import RecordingSession
from vla.config import load_yaml
from vla.gym import instructions
from vla.gym.adapter import Adapter
from vla.gym.agent import VLAAgent
from vla.gym.client import LocalClient, PolicyError, RemoteClient
from vla.gym.report import table
from vla.models.base import load_model

VLA_DIR = Path(__file__).resolve().parents[1]
NYX_ASSETS = VLA_DIR.parent / ".external/nyx-assets"
NVIDIA_ICD = Path("/usr/share/vulkan/icd.d/nvidia_icd.json")
CONTROL_MODES = {"joint_abs": "JOINT_ABS", "ee_abs": "EE_ABS"}
OUTCOMES = ("success", "task_failure", "time_limit", "unevaluated", "unfinished",
            "invalid_action", "policy_error", "env_error")


def classify(info):
    """Outcome of a finished episode from the public step info, as in docs/vla_doc/vla_eval_demo.py."""
    if info["task_outcome"] == "success":
        return "success"
    if info["task_outcome"] == "failure":
        return "task_failure"
    if info["termination_reason"] == "time_limit":
        return "time_limit" if info["evaluation_status"] == "available" else "unevaluated"
    return "unfinished"


def make_args(cfg, spec):
    """topogym.make arguments: control/observation modes, decimation and time limit follow the policy spec."""
    env = OmegaConf.to_container(cfg.env, resolve=True)
    dt = env.pop("physics_dt_s", topogym.SimulatorConfig.physics_dt_s)
    return dict(variation_id=cfg.task.variation, control_mode=CONTROL_MODES[spec.action_space],
                observation_mode="EE" if spec.action_space == "ee_abs" else "JOINT",
                physics_dt_s=dt, control_decimation=round(1 / (spec.control_hz * dt)),
                max_physics_steps=round(cfg.task.sim_seconds / dt), **env)


def output_dir(cfg, spec):
    if cfg.run.output:
        return Path(cfg.run.output)
    return Path("runs/test_results") / f"{date.today():%Y%m%d}_vla_{spec.name}_{cfg.task.id}"


def tracking_error(action, robot, action_space):
    """Largest per-arm distance between the commanded arm target and the next measurement, gripper excluded:
    joint positions in rad (joint_abs) or the TCP position in m (ee_abs)."""
    target, measured = (("joint_position_rad", "joint_position_rad") if action_space == "joint_abs"
                        else ("position_world_m", "tcp_position_world_m"))
    return max(float(np.linalg.norm(np.subtract(command[target], robot[arm][measured])))
               for arm, command in action.items())


@contextmanager
def recording(env, video_dir, metadata):
    """One MP4 per camera from the frames the Env renders for observations; yields None when off."""
    if video_dir is None:
        yield None
        return
    with RecordingSession(video_dir, fps=30, metadata=metadata) as session:
        session.append(env.sensor_frame())
        stop = env.add_frame_sink(session.append)
        try:
            yield session
        finally:
            stop()


def run_episode(env, client, spec, seed, instruction, execute_steps, video_dir):
    """Reset, then act and step until the episode ends; returns the outcome, control and diagnostic fields."""
    start = time.monotonic()
    env.reset(seed=seed)
    reset_wall_s = time.monotonic() - start
    actor = env.interaction()
    agent = VLAAgent(client, Adapter(actor.action_spec, spec), execute_steps)
    obs, info, errors, error = actor.observe(), {}, [], None
    metadata = dict(episode=env.episode_metadata, model=spec.name, instruction=instruction)
    with recording(env, video_dir, metadata) as session:
        try:
            agent.reset(seed, instruction, obs["state"]["episode_id"])
            while True:
                robot = obs["robot"]
                action = agent.act(obs["rgb"], robot)
                try:
                    obs, _, terminated, truncated, info = actor.step(action)
                except ValueError:  # rejected before physics; an ee target beyond IK tolerance is skipped per arm
                    if spec.action_space != "ee_abs":
                        raise
                    action, (obs, _, terminated, truncated, info) = agent.skip(robot, actor.step)
                errors.append(tracking_error(action, obs["robot"], spec.action_space))
                if terminated or truncated:
                    outcome = classify(info)
                    break
        except PolicyError as exc:  # model error, malformed chunk or disconnect
            outcome, error = "policy_error", str(exc)
        except ValueError as exc:  # invalid action: physics did not advance
            outcome, error = "invalid_action", str(exc)
        except RuntimeError as exc:  # the Env faulted; its owner-side detail names the cause (as SegmentRunner)
            outcome, error = "env_error", f"{exc}: {env._fault_detail}"
        row = dict(outcome=outcome, task_success=info.get("task_success"), failure_code=info.get("failure_code"),
                   sim_time_s=float(obs["state"]["sim_time_s"]), control_steps=len(errors),
                   inference_calls=agent.inference_calls,
                   tracking_error_mean=float(np.mean(errors)) if errors else None,
                   tracking_error_max=max(errors, default=None),
                   tracking_error_unit="rad" if spec.action_space == "joint_abs" else "m",
                   clipped_actions=agent.clipped, skipped_actions=agent.skipped,
                   reset_wall_s=round(reset_wall_s, 2),
                   rollout_wall_s=round(time.monotonic() - start - reset_wall_s, 2), error=error)
        if session is not None and not session.failed:  # a failed recording closes as incomplete
            if outcome != "env_error":
                session.append_final(env.sensor_frame())
            session.finish(row)
    return row


def git_state():
    """The commit being evaluated and whether tracked files differ from it."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=VLA_DIR, capture_output=True, text=True).stdout.strip()
    return dict(git_commit=git("rev-parse", "HEAD"),
                git_dirty=bool(git("status", "--porcelain", "--untracked-files=no")))


def evaluate(cfg, client):
    """Run every seed with one Env; write results.jsonl, summary.json and report.md into the output directory."""
    code = git_state()  # before the run: the working tree may change during a long evaluation
    spec = client.spec
    output = output_dir(cfg, spec)
    output.mkdir(parents=True)  # never overwrite earlier results
    instruction = instructions.INSTRUCTIONS[cfg.task.id]
    execute_steps = spec.execute_steps if cfg.run.execute_steps is None else cfg.run.execute_steps
    args = make_args(cfg, spec)
    control_hz = 1 / (args["control_decimation"] * args["physics_dt_s"])
    rows = []
    with topogym.make(cfg.task.id, **args) as env:
        for seed in cfg.task.seeds:
            video_dir = output / f"seed_{seed}" if cfg.run.record else None
            episode = run_episode(env, client, spec, seed, instruction, execute_steps, video_dir)
            row = dict(task=cfg.task.id, variation=cfg.task.variation, seed=seed, model=spec.name,
                       instruction_version=instructions.VERSION, **episode, execute_steps=execute_steps,
                       control_decimation=args["control_decimation"], control_hz_actual=round(control_hz, 3))
            rows.append(row)
            with open(output / "results.jsonl", "a") as file:
                file.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)
    outcomes = [row["outcome"] for row in rows]
    summary = dict(model=spec.name, task=cfg.task.id, variation=cfg.task.variation, episodes=len(rows),
                   success_rate=outcomes.count("success") / len(rows),
                   outcomes={name: outcomes.count(name) for name in OUTCOMES}, spec=asdict(spec),
                   instruction=instruction, instruction_version=instructions.VERSION,
                   config=OmegaConf.to_container(cfg, resolve=True), **code)
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    (output / "report.md").write_text(table([output]) + "\n")


def load_config(path, overrides):
    """The eval config (with its _base_ files) plus dotlist overrides; a misspelled key raises instead of being
    added (env stays open for topogym.make arguments)."""
    cfg = load_yaml(path)
    OmegaConf.set_struct(cfg, True)
    OmegaConf.set_struct(cfg.env, False)
    return OmegaConf.merge(cfg, OmegaConf.from_dotlist(overrides))


def connect(policy):
    """The model server at ``policy.address``, or ``policy.local`` (a model config) in process for HoldVLA."""
    if policy.get("local"):
        return LocalClient(load_model(load_yaml(policy.local)))
    print(f"Connecting to the model server at {policy.address}; it serves one evaluation at a time", flush=True)
    return RemoteClient(policy.address)


def set_render_defaults(environ):
    """Let a fresh checkout render without exports; variables set by the user win, and a default is set only when
    its path exists. Nyx assets: the repo's .external/nyx-assets, as scripts/*.py pass it (otherwise TopoGym's own
    default applies). Vulkan: only the NVIDIA driver, since Nyx aborts at scene build when Vulkan also lists other
    devices, such as an integrated GPU or llvmpipe."""
    if NYX_ASSETS.is_dir():
        environ.setdefault("TOPOGYM_VISUAL_ASSET_ROOT", str(NYX_ASSETS))
    if NVIDIA_ICD.is_file():
        environ.setdefault("VK_ICD_FILENAMES", str(NVIDIA_ICD))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="evaluation config (vla/configs/eval/<task>.yaml)")
    parser.add_argument("overrides", nargs="*", help="OmegaConf dotlist, e.g. task.seeds=[0] run.record=false")
    args = parser.parse_args()
    set_render_defaults(os.environ)
    cfg = load_config(args.config, args.overrides)
    client = connect(cfg.policy)
    try:
        evaluate(cfg, client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
