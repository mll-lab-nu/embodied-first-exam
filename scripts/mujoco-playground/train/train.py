"""Train one env with rsl_rl PPO on CPU (Playground's rsl_rl hyperparameters).

  python train.py Go1Getup --iters 1000 --envs 2048 --workers 16 --out runs/go1_getup
Writes runs/<out>/model_<it>.pt (rsl_rl checkpoints) and policy.pt (TorchScript, deterministic actor)."""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import torch
from rsl_rl.runners import OnPolicyRunner
from vecenv import CpuVecEnv

ap = argparse.ArgumentParser()
ap.add_argument("env"); ap.add_argument("--iters", type=int, default=1000); ap.add_argument("--envs", type=int, default=2048)
ap.add_argument("--workers", type=int, default=16); ap.add_argument("--out", required=True); ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--lr", type=float, default=3e-4); ap.add_argument("--entropy", type=float, default=0.001)
ap.add_argument("--steps", type=int, default=24); ap.add_argument("--resume", default="")
ap.add_argument("--threads", type=int, default=8)
a = ap.parse_args()
torch.set_num_threads(a.threads)

cfg = {
    "seed": a.seed, "num_steps_per_env": a.steps, "save_interval": 50, "check_for_nan": True,
    "obs_groups": {"actor": ["state"], "critic": ["privileged_state"]},
    "logger": "tensorboard", "experiment_name": a.env, "run_name": "",
    "algorithm": {"class_name": "PPO", "value_loss_coef": 1.0, "use_clipped_value_loss": True, "clip_param": 0.2,
                  "entropy_coef": a.entropy, "num_learning_epochs": 5, "num_mini_batches": 4, "learning_rate": a.lr,
                  "schedule": "fixed", "gamma": 0.99, "lam": 0.95, "desired_kl": 0.01, "max_grad_norm": 1.0},
    "actor": {"class_name": "MLPModel", "hidden_dims": [512, 256, 128], "activation": "elu", "obs_normalization": True,
              "distribution_cfg": {"class_name": "GaussianDistribution", "init_std": 1.0}},
    "critic": {"class_name": "MLPModel", "hidden_dims": [512, 256, 128], "activation": "elu", "obs_normalization": True},
}
env = CpuVecEnv(a.env, num_envs=a.envs, workers=a.workers, seed=a.seed)
os.makedirs(a.out, exist_ok=True)
runner = OnPolicyRunner(env, cfg, a.out, device="cpu")
resume = a.resume or (open(a.out.rstrip("/") + ".resume").read().strip() if os.path.exists(a.out.rstrip("/") + ".resume") else "")
if resume:   # --resume, or <out>.resume holding a checkpoint path (how a queued job fine-tunes)
    runner.load(resume)
    print(f"resumed from {resume}", flush=True)
t0 = time.time()
chunk = 50
done_it = 0
while done_it < a.iters:
    n = min(chunk, a.iters - done_it)
    runner.learn(num_learning_iterations=n)
    done_it += n
    import numpy as np
    r = np.mean(env.done_rets) if env.done_rets else float("nan"); L = np.mean(env.done_lens) if env.done_lens else float("nan")
    print(f"[{a.env}] it {done_it}/{a.iters}  ep_return {r:.3f}  ep_len {L:.0f}  elapsed {time.time() - t0:.0f}s", flush=True)
    runner.save(os.path.join(a.out, f"model_{done_it}.pt"))
    runner.export_policy_to_jit(a.out, "policy.pt")
env.close()
