"""Operator-only reproducible local campaign. Does not claim container isolation or model evaluation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from ..control_public.anycar import DEFAULT, validate
from ..anycar_spec import make_spec
from .anycar_reference import fit, public_feedback


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + "\n")


def run(policy, case, out, render):
    command = [
        sys.executable,
        "-m",
        "scripts.control_transfer.trusted.anycar",
        "--policy",
        str(policy),
        "--out",
        str(out),
        "--plant-seed",
        str(case["plant_seed"]),
        "--episode-seed",
        str(case["episode_seed"]),
    ]
    if not render:
        command.append("--no-render")
    env = dict(
        os.environ,
        MUJOCO_GL="osmesa",
        LIBGL_ALWAYS_SOFTWARE="1",
        GALLIUM_DRIVER="llvmpipe",
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        LP_NUM_THREADS="2",
    )
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(result.stderr)
    (out / "worker-output.txt").write_text(result.stdout)
    record = json.loads((out / "record.json").read_text())
    if render:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-threads", "1", "-i", str(out / "video.mp4"), "-f", "null", "-"],
            capture_output=True,
            check=True,
            timeout=60,
        )
        probe = json.loads(
            subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out / "video.mp4")])
        )
        stream = probe["streams"][0]
        if (stream["width"], stream["height"], int(stream["nb_frames"])) != (1280, 480, 241):
            raise ValueError("Invalid video")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--index", type=int, default=0)
    a = parser.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    source_root = Path(__file__).resolve().parents[1]
    source_files = (
        list(source_root.glob("anycar_spec.py"))
        + list((source_root / "trusted").glob("anycar*.py"))
        + list((source_root / "control_public").glob("anycar*.py"))
        + list((source_root / "components/anycarbench").glob("*.py"))
    )
    source_hashes = {str(p.relative_to(source_root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    write(a.out / "source-sha256.json", source_hashes)
    spec = make_spec(a.index)
    write(a.out / "instance-private.json", spec)
    policy = dict(DEFAULT)
    rounds = []
    diagnosis = "Nominal controller; use only noisy response measurements to identify command tracking mismatch."
    for iteration in range(3):
        folder = a.out / f"round-{iteration}"
        folder.mkdir()
        path = folder / "policy.json"
        path.write_bytes(validate(policy))
        write(folder / "diagnosis.json", dict(diagnosis=diagnosis))
        feedback = []
        metrics = []
        for j, case in enumerate(spec["bank"]["adaptation"]):
            out = folder / f"case-{j}"
            record = run(path, case, out, True)
            public = public_feedback(record, out)
            write(out / "delivered-feedback.json", public)
            feedback.append(public)
            metrics.append(record["metrics"])
        rounds.append(
            dict(round_id=iteration, policy_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metrics=metrics)
        )
        write(folder / "agent-view.json", dict(round_id=iteration, feedback=feedback))
        print(json.dumps(dict(round=iteration, metrics=metrics)), flush=True)
        if iteration < 2:
            policy, diagnosis = fit(policy, feedback)
    # Frozen artifact before any held-out case executes.
    final = a.out / "selected-policy.json"
    final.write_bytes(validate(policy))
    write(a.out / "seal.json", dict(round_id=2, policy_sha256=hashlib.sha256(final.read_bytes()).hexdigest()))
    held = []
    for j, case in enumerate(spec["bank"]["held_out"]):
        r = run(final, case, a.out / f"held-{j:02}", True)
        replay = run(final, case, a.out / f"replay-{j:02}", False)
        assert (
            r["state_sha256"] == replay["state_sha256"]
            and r["metrics"] == replay["metrics"]
            and r["feedback"] == replay["feedback"]
        )
        held.append(dict(case=j, state_sha256=r["state_sha256"], metrics=r["metrics"], exact_replay=True))
        print(json.dumps(held[-1]), flush=True)
        write(a.out / "progress.json", dict(rounds=rounds, held_out=held))
    negative = []
    for label, coeff in [
        ("zero-drive", dict(DEFAULT, drive_scale=0)),
        ("bad-steering", dict(DEFAULT, steering_bias=0.12, heading_gain=0.1, position_gain=0.1, drive_scale=2)),
    ]:
        p = a.out / f"{label}.json"
        p.write_bytes(validate(coeff))
        r = run(p, spec["bank"]["held_out"][0], a.out / label, True)
        assert not r["metrics"]["success"]
        negative.append(dict(name=label, metrics=r["metrics"]))
    assert all(
        hashlib.sha256((source_root / name).read_bytes()).hexdigest() == sha for name, sha in source_hashes.items()
    ), "Source changed during validation"
    summary = dict(
        source_sha256=source_hashes,
        schema="anycar-local-validation/2",
        instance_index=a.index,
        instance_schema=spec["schema"],
        transfer_track=spec["transfer_track"],
        container_isolation_tested=False,
        llm_agent_tested=False,
        rounds=rounds,
        held_out=held,
        negative=negative,
        successes=sum(r["metrics"]["success"] for r in held),
        videos=21,
        backend="CPU MuJoCo / CPU NumPy / OSMesa llvmpipe; CUDA_VISIBLE_DEVICES empty",
        limits="OMP/OpenBLAS/MKL 1 thread; llvmpipe 2; ffmpeg 1",
        policy_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
    )
    write(a.out / "validation.json", summary)
    print(json.dumps({"complete": True, "successes": summary["successes"], "held_out": len(held)}), flush=True)


if __name__ == "__main__":
    main()
