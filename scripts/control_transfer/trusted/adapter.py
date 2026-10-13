"""Trusted family adapters. Returned feedback is projected through an explicit allowlist."""

import base64, hashlib, json, subprocess, sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "components"))
sys.path.insert(0, str(SRC))
from control_public.weights import Network


def validate(family, policy):
    if family in ("linearbot", "g1"):
        if (
            not isinstance(policy, dict)
            or set(policy) != {"npz_base64"}
            or not isinstance(policy["npz_base64"], str)
            or len(policy["npz_base64"]) > 12 * 1024**2
        ):
            raise ValueError("Policy payload")
        raw = base64.b64decode(policy["npz_base64"], validate=True)
        Network(raw, family)
        return raw
    if family == "neural-fly":
        from ..control_public.fly import validate as check
    elif family == "spacecraft":
        from nonlinearbench.contract import validate as check
    elif family == "yam":
        from manipulationbench.contract import validate as check
    else:
        raise ValueError("Unknown family")
    return json.dumps(check(policy), sort_keys=True, allow_nan=False).encode()


def run(family, policy, case, out, render, asset=None):
    out = Path(out)
    if family == "neural-fly":
        from .fly import rollout

        return rollout(json.loads(Path(policy).read_text()), case, out, asset, render)
    if family == "linearbot":
        from locomanipbench.deploy import rollout

        record = rollout(
            "linearbot",
            policy,
            mode=case["mode"],
            plant_seed=case["plant_seed"],
            episode_seed=case["episode_seed"],
            render=render,
            out=out,
        )
    elif family == "g1":
        from sim2realbench.g1.deploy import rollout

        record = rollout(
            policy, out=out, plant_seed=case["plant_seed"], episode_seed=case["episode_seed"], render=render
        )
        record["metrics"]["success"] = record["metrics"]["walking_success"]
    elif family == "yam":
        from manipulationbench.simulation import rollout

        record = rollout(
            "catch_varied",
            json.loads(Path(policy).read_text()),
            plant_seed=case["plant_seed"],
            episode_seed=case["episode_seed"],
            render=render,
            out=out,
        )
    elif family == "spacecraft":
        from nonlinearbench.simulation import run_episode

        result = run_episode(json.loads(Path(policy).read_text()), case["plant_seed"], case["episode_seed"], render)
        out.mkdir(parents=True, exist_ok=False)
        if render:
            (out / "video.mp4").write_bytes(result.video)
        record = {
            "state_sha256": result.metrics["state_sha256"],
            "metrics": {**result.metrics, "success": bool(result.metrics["captured"])},
            "feedback": result.feedback,
            "dynamics": result.dynamics,
        }
    else:
        raise ValueError("Unknown family")
    (out / "record.json").write_text(json.dumps(record, allow_nan=False))
    return record


def feedback(family, record, folder):
    value = record["feedback"]
    allowed = {"telemetry", "targets"} if family == "linearbot" else {"telemetry"}
    if set(value) != allowed:
        raise ValueError("Unexpected observation fields")
    # Exact sensor payloads only; no scores, contacts, dynamics, filenames or seeds.
    import math

    for row in value["telemetry"]:
        if family == "neural-fly":
            if set(row) != {
                "t",
                "position",
                "velocity",
                "quaternion",
                "omega",
                "target_position",
                "target_velocity",
                "target_acceleration",
            }:
                raise ValueError("Observation fields")
            vals = [row["t"]] + [v for k, x in row.items() if k != "t" for v in x]
        else:
            if set(row) != {"t", "values"}:
                raise ValueError("Observation fields")
            dimensions = {"g1": 29, "linearbot": 16, "spacecraft": 13, "yam": 11}
            if len(row["values"]) != dimensions[family]:
                raise ValueError("Observation dimension")
            vals = [row["t"]] + row["values"]
        if not all(type(x) in (int, float) and math.isfinite(x) for x in vals):
            raise ValueError("Observation values")
    folder = Path(folder)
    frames = []
    if (folder / "video.mp4").exists():
        # A fixed schedule, independent of launch state, contacts, reward or failure labels.
        fps = 5 if family == "yam" else 0.1 if family == "spacecraft" else 1
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(folder / "video.mp4"),
                "-vf",
                f"select=not(mod(n\\,{int(round((5 if family == 'spacecraft' else 10) / fps))}))",
                "-vsync",
                "vfr",
                "-frames:v",
                "48",
                "-q:v",
                "3",
                str(folder / "frame-%03d.jpg"),
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )
        for i, p in enumerate(sorted(folder.glob("frame-*.jpg"))):
            raw = p.read_bytes()
            frames.append(
                {
                    "time_s": i / fps + (0.02 if family == "neural-fly" else 0.0),
                    "mime_type": "image/jpeg",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "base64": base64.b64encode(raw).decode(),
                }
            )
    return {**value, "images": frames}


def worker():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--request", required=True)
    a = p.parse_args()
    v = json.loads(Path(a.request).read_text())
    run(**v)


if __name__ == "__main__":
    worker()
