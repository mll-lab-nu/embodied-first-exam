"""Fit the Neural Fly force surrogate forces.npz locally from the public Neural-Fly flight logs.

The fitted file cannot be redistributed: the logs (github.com/aerorobotics/neural-fly) are "for personal and educational
use only ... written permission from the authors is required for further use". So every user fits it locally; with the
pinned logs and numpy==2.3.1 / mujoco==3.5.0 (the evaluator image's versions) the result is byte-identical to the asset
the roboengineer-neuralfly-* tasks pin (trusted/fly.py ASSET_SHA256), which the script checks.

An 18-feature quadratic ridge surrogate of the baseline flights' aerodynamic residual force; not Neural-Fly's DAIML.

usage: python3 calibrate_fly.py --source <neural-fly checkout at COMMIT> --out <new dir>
       (images/control-transfer/fetch_assets.sh --fit-fly does the checkout, the fit and the staging)
"""

import argparse, ast, csv, hashlib, json, sys
from pathlib import Path

import numpy as np

COMMIT = "0ed50246b1f1db194e8f0726749351636d3501bf"
ASSET_SHA256 = "8e1c148ed034b9f4c541dfaa71b70b48a652f43c7abcc381416040d7901459b9"   # = trusted/fly.py ASSET_SHA256
VERSIONS = {"numpy": "2.3.1", "mujoco": "3.5.0"}   # the evaluator image's pins; other versions may change the bytes
SPEED = {   # fan duty cycle -> wind speed (m/s), from the upstream README
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
SOURCES = {   # sha256 of every flight log the pinned asset was fitted to
    "data/experiment/custom_figure8_baseline_100wind.csv": "29b1ef5978502976da84d9433812ef007e16e7743c716432f70519f733902b0b",
    "data/experiment/custom_figure8_baseline_35wind.csv": "74ad71b239047dd50a1c1457a455300a2c2e97e94221f6eca9beecd51f0cc6ec",
    "data/experiment/custom_figure8_baseline_70wind.csv": "60ceee5aa469ca0b32585f0750d2b904535d3585629c084b2202c9eb357eb3a7",
    "data/experiment/custom_figure8_baseline_nowind.csv": "9000c62eef3b9ec893f551c4b5dbac6d24d1902dac7705786bb6877c8118808a",
    "data/training/custom_random3_baseline_10wind.csv": "42ab694e30eece8a7e97a455994bf1890ffe93ee815abc643a3ad3db3fc849c1",
    "data/training/custom_random3_baseline_20wind.csv": "3fbe543e4999a5feb36b6a01327f1fa77f0dfb82eabd8fc21792049a9dc7bc6f",
    "data/training/custom_random3_baseline_30wind.csv": "bf0200473f4063815d1e8b0d1c811b3e361a7185587da5457578340ad1c26136",
    "data/training/custom_random3_baseline_40wind.csv": "8c89bf90c3d15ce7e42d6773a217f506dab91e77e7c66a2640be69d55d70c7d0",
    "data/training/custom_random3_baseline_50wind.csv": "71d881ac329a0579d56a5a9e143ac7ed88e910c3a8abcb728d3e1c5c51eb798e",
    "data/training/custom_random3_baseline_nowind.csv": "ff0f5bb470ca0f592593023aa4d40fc58cf3569f0ecdb938afcbafb3f92a94da",
}


def features(v, q, wind):   # identical to the tasks' environment/sim/scripts/control_transfer/trusted/fly.py features()
    q = np.asarray(q, dtype=float)
    q = q / np.linalg.norm(q)
    q = q if q[0] >= 0 else -q
    x = np.r_[v, q[1:], wind / 6.1]
    return np.r_[1, x, x * x, x[:3] * x[-1]]


def fit(source, out):
    import mujoco

    source, out = Path(source), Path(out)
    for mod, want in VERSIONS.items():
        have = (np if mod == "numpy" else mujoco).__version__
        if have != want:
            print(f"warning: {mod} {have}, the pinned asset was fitted with {want}; the bytes may differ", file=sys.stderr)
    out.mkdir(parents=True, exist_ok=False)
    train, test, manifest = [], [], {}
    for p in sorted(source.glob("data/*/custom_*_baseline_*.csv")):
        condition = p.stem.split("_")[-1]
        if condition not in SPEED:
            continue
        manifest[str(p.relative_to(source))] = hashlib.sha256(p.read_bytes()).hexdigest()
        with p.open() as f:
            rows = list(csv.DictReader(f))
        for i, row in enumerate(rows):
            q = np.array(ast.literal_eval(row["q"]))[[3, 0, 1, 2]]
            rotation = np.empty(9)
            mujoco.mju_quat2Mat(rotation, q)
            if not np.allclose(rotation.reshape(3, 3), np.array(ast.literal_eval(row["R"])), atol=1e-6):
                raise ValueError("Quaternion/frame convention mismatch")
            x = features(ast.literal_eval(row["v"]), q, SPEED[condition])
            y = np.array(ast.literal_eval(row["fa"]))
            if np.isfinite(x).all() and np.isfinite(y).all():
                (train if i < int(0.8 * len(rows)) else test).append((x, y))
    if manifest != SOURCES:   # the logs of aerorobotics/neural-fly at COMMIT, file by file
        raise SystemExit("the flight logs differ from the pinned ones: " + ", ".join(sorted(set(manifest.items()) ^ set(SOURCES.items()))))
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
    print(json.dumps({k: report[k] for k in ("training_rows", "validation_rows", "rmse_N_by_axis", "sha256")}))
    if report["sha256"] != ASSET_SHA256:
        raise SystemExit(f"FAIL forces.npz sha256 {report['sha256']} is not the tasks' pin {ASSET_SHA256} "
                         f"(use numpy=={VERSIONS['numpy']} mujoco=={VERSIONS['mujoco']})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    fit(a.source, a.out)
