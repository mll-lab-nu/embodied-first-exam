"""Adapter around pinned upstream G1 PPO. Target evaluator is never imported here."""

import argparse, json, os, sys, time
from pathlib import Path
from .assets import UPSTREAM, COMMIT, verify, digest
from .contract import BASELINE, validate


def train(config, out, seed=0, gpu=0, iterations=10000, num_envs=4096):
    verify()
    config = validate(config)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    if not 1 <= iterations <= 20000 or not 1 <= num_envs <= 8192:
        raise ValueError("Invalid operator compute budget")
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ["WANDB_MODE"] = "disabled"
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    sys.path.insert(0, str(UPSTREAM))
    import torch

    torch.set_num_threads(4)
    from scripts.train import TrainConfig, run_train
    import mjlab.tasks  # noqa: F401 -- registers tasks
    import src.tasks  # noqa: F401 -- registers Unitree tasks

    cfg = TrainConfig.from_task("Unitree-G1-Flat")
    cfg.env.scene.num_envs = num_envs
    cfg.agent.max_iterations = iterations
    cfg.agent.seed = seed
    cfg.agent.logger = "tensorboard"
    cfg.agent.algorithm.learning_rate = config["learning_rate"]
    cfg.agent.algorithm.entropy_coef = config["entropy_coef"]
    cfg.env.events["foot_friction"].params["ranges"] = (config["friction_low"], config["friction_high"])
    cfg.env.events["encoder_bias"].params["bias_range"] = (-config["encoder_bias"], config["encoder_bias"])
    cfg.env.events["base_com"].params["ranges"] = {i: (-config["com_offset"], config["com_offset"]) for i in range(3)}
    cfg.env.rewards["action_rate_l2"].weight = config["action_rate_weight"]
    cfg.agent.save_interval = min(100, iterations)
    record = {
        "upstream_commit": COMMIT,
        "config": config,
        "seed": seed,
        "gpu": gpu,
        "iterations": iterations,
        "num_envs": num_envs,
        "steps": iterations * num_envs * cfg.agent.num_steps_per_env,
        "status": "running",
    }
    (out / "training.json").write_text(json.dumps(record))
    start = time.monotonic()
    try:
        run_train("Unitree-G1-Flat", cfg, out)
        from .policy import Policy
        from control_public.weights import convert_g1

        convert_g1(out / "policy.onnx", out / "policy.npz")
        Policy(out / "policy.npz")
        record.update(
            status="completed", elapsed_s=time.monotonic() - start, checkpoint_sha256=digest(out / "policy.onnx")
        )
        if (out / "policy.onnx.data").exists():
            record["external_weights_sha256"] = digest(out / "policy.onnx.data")
    except Exception as e:
        record.update(status="failed", error=type(e).__name__)
        raise
    finally:
        (out / "training.json").write_text(json.dumps(record, indent=2))
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--gpu", type=int, default=0)
    p.add_argument("--iterations", type=int, default=10000)
    p.add_argument("--num-envs", type=int, default=4096)
    a = p.parse_args()
    train(json.loads(a.config.read_text()) if a.config else BASELINE, a.out, a.seed, a.gpu, a.iterations, a.num_envs)
