"""Public blind-terrain PPO curriculum. No evaluation seeds, hidden draws, or private asset paths."""

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def build_config(upstream, *, seed=0, num_envs=256, iterations=500, settings=None):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(upstream).resolve()))
    import mjlab.tasks  # noqa: F401
    import src.tasks  # noqa: F401
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg
    from mjlab.terrains import (
        BoxFlatTerrainCfg,
        BoxPyramidStairsTerrainCfg,
        BoxInvertedPyramidStairsTerrainCfg,
        HfPyramidSlopedTerrainCfg,
        HfRandomUniformTerrainCfg,
        TerrainGeneratorCfg,
    )

    cfg = load_env_cfg("Unitree-G1-Rough")
    agent = load_rl_cfg("Unitree-G1-Rough")
    cfg.seed = agent.seed = seed
    cfg.scene.num_envs = num_envs
    # Both actor and critic retain their original flat-policy observation dimensions.
    # This allows warm-starting and guarantees no terrain scan reaches the deployable actor.
    cfg.scene.sensors = tuple(s for s in cfg.scene.sensors if s.name != "terrain_scan")
    for group in ("actor", "critic"):
        cfg.observations[group].terms.pop("height_scan", None)
    assert list(cfg.observations["actor"].terms) == [
        "base_ang_vel",
        "projected_gravity",
        "command",
        "phase",
        "joint_pos",
        "joint_vel",
        "actions",
    ]
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
        seed=seed,
        curriculum=True,
        size=(8.0, 8.0),
        num_rows=5,
        num_cols=6,
        border_width=5,
        sub_terrains={
            "flat": BoxFlatTerrainCfg(proportion=1.0),
            "slope": HfPyramidSlopedTerrainCfg(proportion=1.0, slope_range=(0.0, 0.12), platform_width=2),
            "down_slope": HfPyramidSlopedTerrainCfg(
                proportion=1.0, slope_range=(0.0, 0.12), platform_width=2, inverted=True
            ),
            "rough": HfRandomUniformTerrainCfg(
                proportion=1.0,
                noise_range=(-0.025, 0.025),
                noise_step=0.005,
                horizontal_scale=0.1,
                downsampled_scale=0.2,
                border_width=0.25,
            ),
            "steps": BoxPyramidStairsTerrainCfg(
                proportion=1.0, step_height_range=(0.0, 0.06), step_width=0.6, platform_width=2, border_width=0.5
            ),
            "down_steps": BoxInvertedPyramidStairsTerrainCfg(
                proportion=1.0, step_height_range=(0.0, 0.06), step_width=0.6, platform_width=2, border_width=0.5
            ),
        },
    )
    cfg.scene.terrain.max_init_terrain_level = 1
    cfg.curriculum.pop("command_vel", None)
    command = cfg.commands["twist"]
    command.ranges.lin_vel_x = (0.35, 0.8)
    command.ranges.lin_vel_y = (-0.1, 0.1)
    command.ranges.ang_vel_z = (-0.2, 0.2)
    agent.max_iterations = iterations
    agent.save_interval = min(100, iterations)
    agent.logger = "tensorboard"
    agent.algorithm.learning_rate = 0.0001
    agent.algorithm.entropy_coef = 0.001
    if settings:
        agent.algorithm.learning_rate = settings["learning_rate"]
        agent.algorithm.entropy_coef = settings["entropy_coef"]
        cfg.events["foot_friction"].params["ranges"] = (settings["friction_low"], settings["friction_high"])
        cfg.events["encoder_bias"].params["bias_range"] = (-settings["encoder_bias"], settings["encoder_bias"])
        cfg.events["base_com"].params["ranges"] = {
            i: (-settings["com_offset"], settings["com_offset"]) for i in range(3)
        }
        cfg.rewards["action_rate_l2"].weight = settings["action_rate_weight"]
    return cfg, agent


def train(
    upstream, out, *, seed=0, gpu=0, iterations=500, num_envs=256, checkpoint=None, initial_actor=None, settings=None
):
    if (
        type(iterations) is not int
        or not 1 <= iterations <= 20000
        or type(num_envs) is not int
        or not 1 <= num_envs <= 1024
    ):
        raise ValueError("Invalid training budget")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    # This CLI runs one worker. The launcher/operator assigns the physical GPU.
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ["WANDB_MODE"] = "disabled"
    os.environ["OMP_NUM_THREADS"] = "4"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MUJOCO_GL"] = "egl"
    os.environ["XDG_CACHE_HOME"] = str(out / "cache")
    # no CPU pinning: the container's CPU quota bounds it, and pinning to the first four host CPUs put every
    # trial on a host on the same cores; the thread counts above / below bound the parallelism
    import torch
    import warp as wp

    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.cuda.set_per_process_memory_fraction(0.15, 0)
    wp.config.kernel_cache_dir = os.environ.get("WARP_CACHE_PATH", str(out / "warp-cache"))
    cfg, agent = build_config(upstream, seed=seed, num_envs=num_envs, iterations=iterations, settings=settings)
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_runner_cls
    from mjlab.utils.os import dump_yaml
    from .weights import arrays, shapes, convert_g1, Network
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    record = {
        "status": "running",
        "seed": seed,
        "gpu": gpu,
        "iterations": iterations,
        "num_envs": num_envs,
        "steps": iterations * num_envs * agent.num_steps_per_env,
        "actor_inputs": 98,
        "actor_outputs": 29,
        "terrain_curriculum": ["flat", "slope", "rough", "steps"],
        "training_backend": "mjlab / MuJoCo Warp GPU",
        "checkpoint_warm_start": checkpoint is not None,
        "numeric_actor_warm_start": initial_actor is not None,
    }
    (out / "training.json").write_text(json.dumps(record, indent=2))
    start = time.monotonic()
    env = None
    try:
        env = ManagerBasedRlEnv(cfg=cfg, device="cuda:0")
        wrapped = RslRlVecEnvWrapper(env, clip_actions=agent.clip_actions)
        runner = load_runner_cls("Unitree-G1-Rough")(wrapped, asdict(agent), str(out), "cuda:0")
        if checkpoint:
            state = torch.load(checkpoint, map_location="cuda:0", weights_only=True)
            runner.alg.load(state, {"actor": True, "critic": True, "optimizer": False, "iteration": False}, strict=True)
            record["initial_checkpoint_sha256"] = hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest()
        if initial_actor:
            values = arrays(initial_actor, shapes("g1"))
            actor = runner.alg.actor
            state = actor.state_dict()
            for key, source in [("_mean", "mean"), ("_std", "std")]:
                state[f"obs_normalizer.{key}"].copy_(torch.as_tensor(values[source], device="cuda:0").reshape(1, 98))
            state["obs_normalizer._var"].copy_(state["obs_normalizer._std"] ** 2)
            state["obs_normalizer.count"].fill_(1e8)
            for i in range(4):
                state[f"mlp.{2 * i}.weight"].copy_(torch.as_tensor(values[f"w{i}"], device="cuda:0"))
                state[f"mlp.{2 * i}.bias"].copy_(torch.as_tensor(values[f"b{i}"], device="cuda:0"))
            state["distribution.std_param"].fill_(0.15)
            actor.load_state_dict(state)
            record["initial_actor_sha256"] = hashlib.sha256(Path(initial_actor).read_bytes()).hexdigest()
        dump_yaml(out / "params" / "env.yaml", asdict(cfg))
        dump_yaml(out / "params" / "agent.yaml", asdict(agent))
        runner.learn(num_learning_iterations=iterations, init_at_random_ep_len=True)
        convert_g1(out / "policy.onnx", out / "policy.npz")
        actor_np = Network(out / "policy.npz", "g1")
        # Export fidelity compares the actual trained torch actor with the deployed numeric ABI.
        import numpy as np

        batch = np.random.default_rng(seed).normal(0, 0.25, (16, 98)).astype(np.float32)
        runner.alg.actor.eval()
        # Actor's as_onnx wraps normalization and deterministic MLP without TensorDict observation grouping.
        exported = runner.alg.actor.as_onnx(verbose=False).cpu().eval()
        with torch.no_grad():
            expected = exported(torch.from_numpy(batch)).numpy()
        actual = np.stack([actor_np(row) for row in batch])
        max_error = float(np.max(np.abs(np.clip(expected, -100, 100) - actual)))
        if max_error > 2e-4:
            raise RuntimeError("Numeric actor export mismatch")
        events = EventAccumulator(str(out), size_guidance={"scalars": 0}).Reload()
        curves = {
            tag: [{"step": e.step, "value": e.value} for e in events.Scalars(tag)] for tag in events.Tags()["scalars"]
        }
        (out / "learning-curves.json").write_text(json.dumps(curves, allow_nan=False))
        record.update(
            status="completed",
            numeric_export_max_abs_error=max_error,
            policy_sha256=hashlib.sha256((out / "policy.npz").read_bytes()).hexdigest(),
            torch_peak_gpu_bytes=torch.cuda.max_memory_allocated(),
            converged=False,
        )
    except Exception as exc:
        record.update(status="failed", error=type(exc).__name__, detail=str(exc))
        raise
    finally:
        record["elapsed_s"] = time.monotonic() - start
        (out / "training.json").write_text(json.dumps(record, indent=2))
        if env is not None:
            env.close()
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--num-envs", type=int, default=256)
    parser.add_argument("--checkpoint")
    parser.add_argument("--initial-actor")
    a = parser.parse_args()
    train(
        a.upstream,
        a.out,
        seed=a.seed,
        gpu=a.gpu,
        iterations=a.iterations,
        num_envs=a.num_envs,
        checkpoint=a.checkpoint,
        initial_actor=a.initial_actor,
    )
