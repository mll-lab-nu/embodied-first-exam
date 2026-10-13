"""Operator-only fit to pinned real flight logs; never a Neural-Fly algorithm reproduction."""

import argparse, ast, csv, hashlib, json, subprocess
from pathlib import Path
import numpy as np
from .trusted.fly import features

COMMIT = "0ed50246b1f1db194e8f0726749351636d3501bf"
SPEED = {
    "nowind": 0,
    "10wind": 1.3,
    "20wind": 2.5,
    "30wind": 3.7,
    "35wind": 4.2,
    "40wind": 4.9,
    "50wind": 6.1,
    "70wind": 8.5,
    "100wind": 12.1,
}


def fit(source, out):
    source = Path(source)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip() != COMMIT:
        raise ValueError("Unpinned flight data")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "data"], cwd=source, check=True)
    train = []
    test = []
    manifest = {}
    for p in sorted(source.glob("data/*/custom_*_baseline_*.csv")):
        condition = p.stem.split("_")[-1]
        if condition not in SPEED:
            continue
        manifest[str(p.relative_to(source))] = hashlib.sha256(p.read_bytes()).hexdigest()
        with p.open() as f:
            rows = list(csv.DictReader(f))
        for i, row in enumerate(rows):
            q = np.array(ast.literal_eval(row["q"]))[[3, 0, 1, 2]]
            import mujoco

            rotation = np.empty(9)
            mujoco.mju_quat2Mat(rotation, q)
            if not np.allclose(rotation.reshape(3, 3), np.array(ast.literal_eval(row["R"])), atol=1e-6):
                raise ValueError("Quaternion/frame convention mismatch")
            x = features(ast.literal_eval(row["v"]), q, SPEED[condition])
            y = np.array(ast.literal_eval(row["fa"]))
            if np.isfinite(x).all() and np.isfinite(y).all():
                (train if i < int(0.8 * len(rows)) else test).append((x, y))
    X = np.array([x for x, y in train])
    Y = np.array([y for x, y in train])
    W = np.linalg.solve(X.T @ X + np.eye(X.shape[1]) * 0.1, X.T @ Y)
    a = np.array([x for x, y in test])
    b = np.array([y for x, y in test])
    rmse = np.sqrt(np.mean((a @ W - b) ** 2, axis=0))
    np.savez(out / "forces.npz", weights=W)
    report = {
        "upstream_commit": COMMIT,
        "sources": manifest,
        "training_rows": len(train),
        "validation_rows": len(test),
        "validation": "final 20 percent of each flight, temporally separated; not unseen flights",
        "rmse_N_by_axis": rmse.tolist(),
        "sha256": hashlib.sha256((out / "forces.npz").read_bytes()).hexdigest(),
        "model": "ridge quadratic surrogate; not DAIML, not a fully calibrated digital twin",
        "license": "upstream personal/educational use only; not redistributed",
    }
    (out / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    fit(a.source, a.out)
