"""Operator-only complete-bank local validation. Not Harbor or an LLM score."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import mujoco
import numpy as np

from .neuralfly_reference import solve
from .neuralfly_spec import make_spec
from .trusted.session import Session, atomic
from .trusted.verify import verdict
from .trusted.fly import ASSET_SHA256


class LocalClient:
    """Test transport using the shared protocol implementation; not a security boundary."""

    def __init__(self, session, out):
        self.session = session
        self.out = Path(out)
        self.out.mkdir()
        self.count = 0

    def call(self, operation, args):
        result = self.session.call(operation, args)
        prefix = self.out / f"{self.count:03d}-{operation}"
        prefix.with_suffix(".request.json").write_bytes(json.dumps(args, sort_keys=True, allow_nan=False).encode())
        if operation == "deploy" and "round_id" in result:
            raw = (self.session.root / f"round-{result['round_id']}" / "agent-view.json").read_bytes()
        else:
            raw = json.dumps(result, sort_keys=True, allow_nan=False).encode()
        prefix.with_suffix(".response.json").write_bytes(raw)
        self.count += 1
        return json.loads(raw)

    def describe(self):
        return self.call("describe", {})

    def deploy(self, policy, diagnosis):
        return self.call("deploy", {"policy": policy, "diagnosis": diagnosis})

    def seal(self, round_id, summary):
        return self.call("seal", {"round_id": round_id, "summary": summary})


def run_instance(request):
    index, output, asset, revision = request
    root = Path(output) / f"i{index:02d}"
    root.mkdir()
    spec = make_spec(index, revision=revision)
    spec.update(private_asset=str(Path(asset).resolve()), private_asset_sha256=ASSET_SHA256)
    atomic(root / "instance.json", spec)
    session = Session(root / "session", spec, wall_clock_s=14400, render=True)
    solve(LocalClient(session, root / "wire"), root / "reference")
    # No fourth round or held-out query is permitted, including after seal.
    assert "error" in session.call("deploy", {"policy": spec["public"]["default_policy"], "diagnosis": "fourth"})
    assert "error" in session.call("held-out", {})
    session.finalize()
    result = verdict(session.root, root / "instance.json")
    if result["infra_error"] or result["episodes"] != 10 or result["deterministic"] != 1:
        raise RuntimeError(f"Full-bank validation/replay failure for {index}: {result}")
    nop = Session(root / "nop", spec, render=False)
    nop.finalize()
    negative = verdict(nop.root, root / "instance.json")
    assert negative["success"] == negative["infra_error"] == negative["final_reward"] == 0
    videos = []
    for path in sorted(root.rglob("video.mp4")):
        probe = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-count_frames",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height,nb_read_frames",
                    "-of",
                    "json",
                    str(path),
                ],
                text=True,
            )
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-threads", "1", "-i", str(path), "-f", "null", "-"],
            check=True,
            capture_output=True,
        )
        videos.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                **probe["streams"][0],
            }
        )
    held = []
    for i, case in enumerate(spec["bank"]["held_out"]):
        record = json.loads((root / "session" / "held-out" / f"case-{i}-a" / "record.json").read_text())
        held.append(
            {"case": i, "stratum": case["stratum"], **record["metrics"], "state_sha256": record["state_sha256"]}
        )
    summary = {
        "instance": index,
        "verdict": result,
        "nop": negative,
        "held_out": held,
        "videos": videos,
        "all_strata": sorted({r["stratum"] for r in held}),
        "local_only": True,
        "container_isolation_tested": False,
        "model_evaluation": False,
        "selected_round": session.state["selected"],
    }
    atomic(root / "validation.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--instances", nargs="+", type=int, default=[0, 1])
    parser.add_argument("--workers", type=int, choices=[1, 2], default=2)
    parser.add_argument("--revision", choices=["fixed-eight/1", "general-eight/1"], default="fixed-eight/1")
    args = parser.parse_args()
    if os.environ.get("MUJOCO_GL") != "osmesa" or os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("Set MUJOCO_GL=osmesa and CUDA_VISIBLE_DEVICES to the empty string")
    if any(os.environ.get(k) != "1" for k in ["OPENBLAS_NUM_THREADS", "LP_NUM_THREADS"]):
        raise ValueError("Set OPENBLAS_NUM_THREADS=1 and LP_NUM_THREADS=1")
    args.out.mkdir(parents=True, exist_ok=False)
    runtime = {
        "python": sys.version,
        "mujoco": mujoco.__version__,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "cpu_workers": args.workers,
        "trajectory_revision": args.revision,
        "gl_backend": "osmesa",
        "gpu_visible": False,
        "asset_sha256": ASSET_SHA256,
    }
    files = list(Path(__file__).parent.glob("neuralfly_*.py")) + [
        Path(__file__).parent / n for n in ["trusted/fly.py", "control_public/fly.py"]
    ]
    runtime["source_sha256"] = {
        str(p.relative_to(Path(__file__).parents[2])): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    atomic(args.out / "runtime.json", runtime)
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(
            run_instance,
            [(i, str(args.out.resolve()), str(args.asset.resolve()), args.revision) for i in args.instances],
        ):
            results.append(result)
            atomic(args.out / "validation.json", results)
            print(
                json.dumps(
                    {"instance": result["instance"], "verdict": result["verdict"], "videos": len(result["videos"])}
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
