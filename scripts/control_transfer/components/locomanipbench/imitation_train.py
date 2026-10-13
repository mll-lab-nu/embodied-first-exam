"""Train a goal-conditioned whole-body neural controller by expert imitation.
Training uses only public nominal robot models, never deployment plants.
"""

import argparse, json, time, hashlib
from pathlib import Path
import numpy as np
from .models import Robot, verify
from .task import Reference, BALANCED_MODES

DEFAULT = {
    "learning_rate": 0.001,
    "epochs": 80,
    "samples": 24000,
    "teacher_gain": 4.0,
    "ik_damping": 0.03,
    "joint_noise": 0.06,
}
BOUNDS = {
    "learning_rate": (0.00003, 0.003),
    "epochs": (10, 120),
    "samples": (4000, 48000),
    "teacher_gain": (1.0, 8.0),
    "ik_damping": (0.01, 0.15),
    "joint_noise": (0.01, 0.15),
}


def validate(c):
    if not isinstance(c, dict) or set(c) != set(BOUNDS):
        raise ValueError("Invalid configuration fields")
    for k, (a, b) in BOUNDS.items():
        if isinstance(c[k], bool) or not isinstance(c[k], (int, float)) or not np.isfinite(c[k]) or not a <= c[k] <= b:
            raise ValueError("Invalid " + k)
    for k in ["epochs", "samples"]:
        if not isinstance(c[k], int):
            raise ValueError("Integer " + k + " required")
    return c.copy()


def train(robot, out, config=DEFAULT, seed=42, device="cuda:2"):
    config = validate(config)
    archive_hash = verify(robot)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    rng = np.random.default_rng(seed)
    r = Robot(robot)
    refs = [Reference(robot, int(rng.integers(2**31)), BALANCED_MODES[i % len(BALANCED_MODES)]) for i in range(12)]
    xs = []
    ys = []
    for i in range(config["samples"]):
        ref = refs[i % len(refs)]
        t = float(rng.uniform(0, 12))
        goal, twist = ref.sample(t)
        q = ref.r.d.qpos.copy() if i % 2 else r.home.copy()
        q[r.qids[:3]] = goal[0]
        q[r.qids] += rng.normal(0, config["joint_noise"], r.n)
        q[r.qids] = np.clip(q[r.qids], r.limits[:, 0] + 0.02, r.limits[:, 1] - 0.02)
        v = np.zeros(r.m.nv)
        v[r.vids] = rng.normal(0, 0.1, r.n)
        x, error = r.feature(q, v, goal, twist)
        y = r.expert(error, twist, config["teacher_gain"], config["ik_damping"])
        xs.append(x)
        ys.append(y)
        if (i + 1) % 4000 == 0:
            print("generated", i + 1, flush=True)
    x = np.asarray(xs, dtype=np.float32)
    y = np.asarray(ys, dtype=np.float32)
    split = int(len(x) * 0.9)
    order = rng.permutation(len(x))
    x = x[order]
    y = y[order]
    mean = x[:split].mean(0)
    std = np.maximum(x[:split].std(0), 0.03)
    import torch

    torch.set_num_threads(4)
    torch.manual_seed(seed)
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("Requested GPU unavailable")
    net = torch.nn.Sequential(
        torch.nn.Linear(x.shape[1], 256),
        torch.nn.Tanh(),
        torch.nn.Linear(256, 256),
        torch.nn.Tanh(),
        torch.nn.Linear(256, r.n),
    ).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=config["learning_rate"])
    xt = torch.tensor((x - mean) / std, device=device)
    yt = torch.tensor(y, device=device)
    history = []
    for epoch in range(config["epochs"]):
        order = torch.randperm(split, device=device)
        for idx in order.split(512):
            loss = (net(xt[idx]) - yt[idx]).square().mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        with torch.no_grad():
            valid = (net(xt[split:]) - yt[split:]).square().mean().item()
        history.append({"epoch": epoch + 1, "validation_mse": valid})
        if (epoch + 1) % 10 == 0:
            print("epoch", epoch + 1, "validation_mse", valid, flush=True)
    arrays = {"mean": mean, "std": std, **{}}
    for i, layer in enumerate([net[0], net[2], net[4]]):
        arrays[f"w{i}"] = layer.weight.detach().cpu().numpy()
        arrays[f"b{i}"] = layer.bias.detach().cpu().numpy()
    np.savez_compressed(out / "policy.npz", **arrays)
    from .policy import Policy

    Policy(out / "policy.npz", robot)
    record = {
        "robot": robot,
        "method": "nominal whole-body IK imitation learning",
        "config": config,
        "seed": seed,
        "device": device,
        "attachment_sha256": archive_hash,
        "feature_dim": x.shape[1],
        "action_dim": r.n,
        "history": history,
        "elapsed_s": time.monotonic() - start,
        "policy_sha256": hashlib.sha256((out / "policy.npz").read_bytes()).hexdigest(),
        "status": "completed",
        "validation_note": "Random sample split from training trajectory family; not held-out deployment performance.",
    }
    (out / "training.json").write_text(json.dumps(record, indent=2))
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--robot", choices=["linearbot", "vega"], required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--config", type=Path)
    p.add_argument("--device", default="cuda:2")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    train(a.robot, a.out, json.loads(a.config.read_text()) if a.config else DEFAULT, a.seed, a.device)
