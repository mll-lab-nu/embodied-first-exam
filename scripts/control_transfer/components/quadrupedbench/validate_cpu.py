"""Operator validation: frozen references, ten held-out cases each, fresh-process replay.

This checks the family simulator and numeric boundary. It is not a Harbor runner
and does not establish container isolation or report an LLM benchmark score.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from ...control_public.go2 import validate
from ...trusted.go2 import TASKS, make_spec


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(policy, case, out, render, environment):
    command = [
        sys.executable,
        "-m",
        "scripts.control_transfer.components.quadrupedbench.simulation",
        "--policy",
        str(policy),
        "--case",
        str(case),
        "--out",
        str(out),
    ]
    if not render:
        command.append("--no-render")
    result = subprocess.run(
        command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300
    )
    (out.parent / (out.name + ".log")).write_text(result.stdout + "\n" + result.stderr)
    if result.returncode:
        raise RuntimeError(f"Rollout failed; inspect {out.name}.log")
    return json.loads((out / "record.json").read_text())


def main():
    import mujoco
    import numpy

    if mujoco.__version__ != "3.5.0":
        raise RuntimeError("Acceptance requires MuJoCo 3.5.0")
    parser = argparse.ArgumentParser()
    parser.add_argument("--policies", required=True, help="Operator-only directory with TASK.json for all four tasks")
    parser.add_argument("--out", required=True)
    parser.add_argument("--index", type=int, default=0)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    environment = dict(
        os.environ,
        MUJOCO_GL="osmesa",
        CUDA_VISIBLE_DEVICES="",
        LIBGL_ALWAYS_SOFTWARE="1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="4",
        LP_NUM_THREADS="4",
    )
    summary = {
        "kind": "local-family-validation",
        "instance_schema": "control-transfer-instance/2",
        "transfer_track": "same-plant",
        "runtime": {
            "python": sys.executable,
            "mujoco_version": mujoco.__version__,
            "mujoco_module": mujoco.__file__,
            "numpy_version": numpy.__version__,
            "pythonpath": environment.get("PYTHONPATH", ""),
            "osmesa_library_directory": environment.get("LD_LIBRARY_PATH", ""),
            "assets": environment.get("GO2_ASSET_DIR", ""),
            "environment": {
                k: environment[k]
                for k in (
                    "MUJOCO_GL",
                    "CUDA_VISIBLE_DEVICES",
                    "LIBGL_ALWAYS_SOFTWARE",
                    "OPENBLAS_NUM_THREADS",
                    "OMP_NUM_THREADS",
                    "LP_NUM_THREADS",
                )
            },
        },
        "container_isolation_tested": False,
        "llm_agent_run": False,
        "tasks": {},
        "source_sha256": {},
    }
    here = Path(__file__).parent
    sources = (
        list(here.glob("*.py"))
        + [here / "requirements-cpu.txt"]
        + list((here.parents[1] / "control_public").glob("go2*.py"))
        + list((here.parents[1] / "trusted").glob("go2*.py"))
    )
    summary["source_sha256"] = {str(p.relative_to(here.parents[1])): digest(p) for p in sources}
    for task in TASKS:
        folder = out / task
        folder.mkdir()
        policy = json.loads((Path(args.policies) / (task + ".json")).read_text())
        artifact = folder / "policy.json"
        artifact.write_bytes(validate(policy))
        nop = dict(policy, enabled=False)
        nop_path = folder / "nop.json"
        nop_path.write_bytes(validate(nop))
        spec = make_spec(args.index, task)
        (folder / "instance.json").write_text(json.dumps(spec, sort_keys=True, indent=2))
        assert spec["schema"] == "control-transfer-instance/2"
        assert spec["transfer_track"] == "same-plant"
        assert {c["plant_seed"] for bank in spec["bank"].values() for c in bank} == {10000 + args.index * 1000 + 100}
        records = []
        dynamics = None
        for k, case in enumerate(spec["bank"]["held_out"]):
            case_path = folder / f"case-{k:02d}.json"
            case_path.write_text(json.dumps(case, sort_keys=True))
            record = evaluate(artifact, case_path, folder / f"case-{k:02d}", k == 0, environment)
            replay = evaluate(artifact, case_path, folder / f"replay-{k:02d}", False, environment)
            assert record["state_sha256"] == replay["state_sha256"], "Fresh-process state mismatch"
            assert record["feedback_sha256"] == replay["feedback_sha256"], "Fresh-process feedback mismatch"
            assert record["metrics"] == replay["metrics"], "Fresh-process scoring mismatch"
            assert type(record["metrics"]["success"]) is bool
            assert 0 <= record["metrics"]["score"] <= 100
            if dynamics is None:
                dynamics = record["dynamics"]
            assert record["dynamics"] == replay["dynamics"] == dynamics, "Hidden plant changed"
            assert set(record["feedback"]) == {"telemetry"}
            for row in record["feedback"]["telemetry"]:
                assert set(row) == {"t", "values"} and len(row["values"]) == 37
            records.append(
                {
                    "case": k,
                    "metrics": record["metrics"],
                    "state_sha256": record["state_sha256"],
                    "feedback_sha256": record["feedback_sha256"],
                    "deterministic": True,
                }
            )
            print(task, k, record["metrics"]["success"], record["metrics"]["score"], flush=True)
        negative = evaluate(nop_path, folder / "case-00.json", folder / "nop", False, environment)
        assert negative["metrics"]["score"] == 0 and not negative["metrics"]["success"]
        video = folder / "case-00/video.mp4"
        info = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,width,height,nb_frames",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(video),
                ],
                text=True,
            )
        )
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True, timeout=120)
        summary["tasks"][task] = {
            "cases": records,
            "successes": sum(r["metrics"]["success"] for r in records),
            "held_out_cases": len(records),
            "mean_score": sum(r["metrics"]["score"] for r in records) / len(records),
            "nop_score": negative["metrics"]["score"],
            "video": str(video.relative_to(out)),
            "video_sha256": digest(video),
            "video_info": info,
            "renderer_gl": json.loads((folder / "case-00/record.json").read_text())["renderer_gl"],
            "policy_sha256": digest(artifact),
        }
        (out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: {x: v[x] for x in ("successes", "held_out_cases", "mean_score", "nop_score")}
                for k, v in summary["tasks"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
