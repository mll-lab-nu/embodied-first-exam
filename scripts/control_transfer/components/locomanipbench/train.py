"""PPO whole-body policy training with MuJoCo Warp GPU physics."""

import argparse, json, time, hashlib
from pathlib import Path
import numpy as np

DEFAULT = {
    "learning_rate": 0.0001,
    "entropy_coef": 0.003,
    "encoder_noise": 0.003,
    "motor_range": 0.10,
    "action_rate_weight": 0.01,
}
BOUNDS = {
    "learning_rate": (0.00001, 0.001),
    "entropy_coef": (0.0, 0.03),
    "encoder_noise": (0.001, 0.01),
    "motor_range": (0.0, 0.2),
    "action_rate_weight": (0.0, 0.1),
}


def validate(c):
    if not isinstance(c, dict) or set(c) != set(BOUNDS):
        raise ValueError("Invalid configuration fields")
    for k, (a, b) in BOUNDS.items():
        if isinstance(c[k], bool) or not isinstance(c[k], (int, float)) or not np.isfinite(c[k]) or not a <= c[k] <= b:
            raise ValueError("Invalid " + k)
    return c.copy()


def train(robot, out, config=DEFAULT, seed=42, device="cuda:2", iterations=100, num_envs=128):
    config = validate(config)
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1 <= iterations <= 10000:
        raise ValueError("Invalid iterations")
    if isinstance(num_envs, bool) or not isinstance(num_envs, int) or not 1 <= num_envs <= 1024:
        raise ValueError("Invalid num_envs")
    if not device.startswith("cuda:"):
        raise ValueError("MuJoCo Warp GPU required")
    import torch
    from .warp_env import WarpEnv
    from .policy import Policy

    torch.set_num_threads(4)
    torch.manual_seed(seed)
    torch.cuda.set_device(device)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    initial = Path(__import__("os").environ.get("CONTROL_INITIAL_POLICY", "/app/output/initial.npz"))
    p = Policy(initial, robot)
    actor = torch.nn.Sequential(
        torch.nn.Linear(len(p.mean), 256),
        torch.nn.Tanh(),
        torch.nn.Linear(256, 256),
        torch.nn.Tanh(),
        torch.nn.Linear(256, len(p.layers[-1][1])),
    ).to(device)
    with torch.no_grad():
        for layer, (w, b) in zip([actor[0], actor[2], actor[4]], p.layers):
            layer.weight.copy_(torch.as_tensor(w, device=device))
            layer.bias.copy_(torch.as_tensor(b, device=device))
    critic = torch.nn.Sequential(
        torch.nn.Linear(len(p.mean), 256),
        torch.nn.Tanh(),
        torch.nn.Linear(256, 256),
        torch.nn.Tanh(),
        torch.nn.Linear(256, 1),
    ).to(device)
    logstd = torch.nn.Parameter(torch.full((len(p.layers[-1][1]),), -2.3, device=device))
    parameters = list(actor.parameters()) + list(critic.parameters()) + [logstd]
    optimizer = torch.optim.Adam(parameters, lr=config["learning_rate"])
    mean = torch.tensor(p.mean, device=device)
    std = torch.tensor(p.std, device=device)
    history = []
    from .task import REFERENCE_VERSION

    record = {
        "evaluation_protocol": "fixed-moving-v1",
        "training_class_balance": "equal fixed and moving trajectory counts in the default bank",
        "reference_version": REFERENCE_VERSION,
        "robot": robot,
        "method": "PPO in MuJoCo Warp GPU physics",
        "training_backend": "mujoco_warp",
        "evaluation_backend": "native CPU MuJoCo",
        "initialization": "frozen nominal-IK imitation checkpoint",
        "initial_policy_sha256": hashlib.sha256(initial.read_bytes()).hexdigest(),
        "config": config,
        "seed": seed,
        "device": device,
        "iterations": iterations,
        "num_envs": num_envs,
        "rollout_steps": 32,
        "physics_dt": 0.002,
        "control_dt": 0.02,
        "environment_steps": 0,
        "status": "running",
        "history": history,
        "versions": {},
    }
    import importlib.metadata

    for name in ["mujoco", "mujoco-warp", "warp-lang", "torch", "mjlab"]:
        record["versions"][name] = importlib.metadata.version(name)

    def save_record():
        (out / "training.json").write_text(json.dumps(record, indent=2, allow_nan=False))

    save_record()
    try:
        env = WarpEnv(robot, num_envs, device, seed, noise=config["encoder_noise"], motor_range=config["motor_range"])
        record["attachment_sha256"] = env.archive_hash
        record["training_trajectory_seeds"] = env.train_trajectory_seeds
        record["feature_dim"] = len(p.mean)
        record["action_dim"] = env.n
        obs = env.obs
        horizon = 32
        gamma = 0.99
        lam = 0.95
        for iteration in range(iterations):
            xs = []
            actions = []
            logprobs = []
            values = []
            rewards = []
            dones = []
            for _ in range(horizon):
                with torch.no_grad():
                    x = (obs - mean) / std
                    mu = actor(x)
                    distribution = torch.distributions.Normal(mu, logstd.clamp(-4, 0).exp())
                    action = distribution.sample()
                    lp = distribution.log_prob(action).sum(-1)
                    value = critic(x).squeeze(-1)
                xs.append(x)
                actions.append(action)
                logprobs.append(lp)
                values.append(value)
                obs, reward, done, info = env.step(action, config["action_rate_weight"])
                rewards.append(reward)
                dones.append(done)
            with torch.no_grad():
                nextvalue = critic((obs - mean) / std).squeeze(-1)
                adv = torch.zeros(num_envs, device=device)
                advantages = []
                for t in reversed(range(horizon)):
                    alive = (~dones[t]).float()
                    delta = rewards[t] + gamma * nextvalue * alive - values[t]
                    adv = delta + gamma * lam * alive * adv
                    advantages.append(adv)
                    nextvalue = values[t]
                advantages = torch.stack(advantages[::-1])
                returns = advantages + torch.stack(values)
                advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
            x = torch.stack(xs).flatten(0, 1)
            a = torch.stack(actions).flatten(0, 1)
            oldlp = torch.stack(logprobs).flatten()
            ret = returns.flatten()
            advantages = advantages.flatten()
            losses = []
            for _ in range(4):
                for ids in torch.randperm(len(x), device=device).split(1024):
                    dist = torch.distributions.Normal(actor(x[ids]), logstd.clamp(-4, 0).exp())
                    lp = dist.log_prob(a[ids]).sum(-1)
                    ratio = (lp - oldlp[ids]).exp()
                    policy_loss = -torch.minimum(
                        ratio * advantages[ids], ratio.clamp(0.8, 1.2) * advantages[ids]
                    ).mean()
                    value_loss = (critic(x[ids]).squeeze(-1) - ret[ids]).square().mean()
                    entropy = dist.entropy().sum(-1).mean()
                    loss = policy_loss + 0.5 * value_loss - config["entropy_coef"] * entropy
                    if not torch.isfinite(loss):
                        raise RuntimeError("Nonfinite PPO loss")
                    optimizer.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(parameters, 1.0)
                    optimizer.step()
                    losses.append(float(loss.detach()))
            record["environment_steps"] += horizon * num_envs
            history.append(
                {
                    "iteration": iteration + 1,
                    "environment_steps": record["environment_steps"],
                    "mean_training_reward": float(torch.stack(rewards).mean()),
                    "mean_loss": float(np.mean(losses)),
                    "elapsed_s": time.monotonic() - start,
                }
            )
            if iteration == 0 or (iteration + 1) % 10 == 0:
                save_record()
                print(json.dumps(history[-1]), flush=True)
        arrays = {"mean": p.mean, "std": p.std, **{}}
        for i, layer in enumerate([actor[0], actor[2], actor[4]]):
            arrays[f"w{i}"] = layer.weight.detach().cpu().numpy()
            arrays[f"b{i}"] = layer.bias.detach().cpu().numpy()
        np.savez_compressed(out / "policy.npz", **arrays)
        cpu = Policy(out / "policy.npz", robot)
        probe = obs[0].detach().cpu().numpy()
        with torch.no_grad():
            expected = actor((torch.tensor(probe, device=device) - mean) / std).clamp(-1, 1).cpu().numpy()
        if not np.allclose(cpu(probe), expected, atol=2e-5):
            raise RuntimeError("CPU policy export mismatch")
        record.update(
            status="completed",
            elapsed_s=time.monotonic() - start,
            policy_sha256=hashlib.sha256((out / "policy.npz").read_bytes()).hexdigest(),
            export_parity_verified=True,
        )
    except Exception as e:
        record.update(status="failed", error=repr(e))
        raise
    finally:
        save_record()
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--robot", choices=["linearbot", "vega"], required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--config", type=Path)
    p.add_argument("--device", default="cuda:2")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--iterations", type=int, default=100)
    p.add_argument("--num-envs", type=int, default=128)
    a = p.parse_args()
    train(
        a.robot,
        a.out,
        json.loads(a.config.read_text()) if a.config else DEFAULT,
        a.seed,
        a.device,
        a.iterations,
        a.num_envs,
    )
